"""
Per-article sentiment scoring using VADER (vaderSentiment).
VADER is a rule-based lexicon model well-suited for short news text.
Compound score ranges from -1.0 (very negative) to +1.0 (very positive).
Threshold convention: > +0.05 = positive, < -0.05 = negative, else neutral.
"""

import pandas as pd

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    _analyzer = SentimentIntensityAnalyzer()
    VADER_AVAILABLE = True
except ImportError:
    _analyzer = None
    VADER_AVAILABLE = False


def score_article(headline: str, summary: str = "") -> float | None:
    """
    Return VADER compound score for a single article.
    Combines headline (weighted more heavily) with the first 300 chars of summary.
    Returns None if vaderSentiment is not installed.
    """
    if not VADER_AVAILABLE or _analyzer is None:
        return None
    # Repeat headline twice so it weighs more than the summary snippet
    text = f"{headline}. {headline}. {summary[:300]}".strip()
    return _analyzer.polarity_scores(text)["compound"]


def score_articles(articles: list[dict]) -> list[dict]:
    """
    Return a copy of each article dict with a 'sentiment' key added.
    """
    return [
        {**a, "sentiment": score_article(a.get("headline", ""), a.get("summary", ""))}
        for a in articles
    ]


def sentiment_return_correlation(sent_df: pd.DataFrame, price_df: pd.DataFrame,
                                  window: int = 7) -> float | None:
    """
    Pearson correlation between the rolling `window`-day sentiment MA
    and same-day price returns.  Returns None if insufficient data.
    """
    if sent_df.empty or price_df.empty:
        return None
    returns = price_df["Close"].pct_change().dropna()
    rolling_sent = sent_df["sentiment"].rolling(window, min_periods=1).mean()
    aligned = pd.concat([rolling_sent.rename("sent"), returns.rename("ret")],
                        axis=1).dropna()
    if len(aligned) < 5:
        return None
    return float(aligned["sent"].corr(aligned["ret"]))


def event_study_df(articles: list[dict], price_df: pd.DataFrame,
                   windows: tuple = (0, 1, 2)) -> pd.DataFrame | None:
    """
    Compute average stock returns for articles bucketed by sentiment sign,
    over event windows of [0, +1, +2] trading days relative to article date.

    Returns a DataFrame:
        index   = window day (0, 1, 2)
        columns = Positive, Neutral, Negative, All  (mean return %)
        plus a 'n_articles' row showing article counts per bucket.
    """
    if price_df.empty or not articles:
        return None

    returns = price_df["Close"].pct_change()
    price_dates = returns.index.sort_values()

    rows = []
    for a in articles:
        ts    = a.get("datetime")
        score = a.get("sentiment")
        if ts is None or score is None:
            continue
        event_date = pd.Timestamp.fromtimestamp(ts).normalize()

        # Find position of event date (or next trading day) in the price index
        future = price_dates[price_dates >= event_date]
        if future.empty:
            continue
        pos = price_dates.get_loc(future[0])

        bucket = "Positive" if score > 0.05 else ("Negative" if score < -0.05 else "Neutral")
        row = {"bucket": bucket, "score": score}
        for w in windows:
            idx = pos + w
            if 0 <= idx < len(price_dates):
                row[f"d{w}"] = returns.iloc[idx] * 100
            else:
                row[f"d{w}"] = None
        rows.append(row)

    if not rows:
        return None

    df = pd.DataFrame(rows)
    results = {}
    counts  = {}
    for bucket in ["Positive", "Neutral", "Negative"]:
        sub = df[df["bucket"] == bucket]
        counts[bucket] = len(sub)
        results[bucket] = {f"d{w}": sub[f"d{w}"].dropna().mean() for w in windows}
    counts["All"] = len(df)
    results["All"] = {f"d{w}": df[f"d{w}"].dropna().mean() for w in windows}

    out = pd.DataFrame(results, index=[f"d{w}" for w in windows])
    out.index = [f"Day +{w}" for w in windows]
    out.loc["N articles"] = counts
    return out


def daily_sentiment_df(articles: list[dict]) -> pd.DataFrame:
    """
    Aggregate per-article sentiment scores to daily averages.
    Returns a DataFrame indexed by date with columns: sentiment, count.
    Only includes days that have at least one article.
    """
    rows = []
    for a in articles:
        ts    = a.get("datetime")
        score = a.get("sentiment")
        if ts is not None and score is not None:
            date = pd.Timestamp.fromtimestamp(ts).normalize()
            rows.append({"date": date, "sentiment": score})

    if not rows:
        return pd.DataFrame(columns=["sentiment", "count"])

    df = pd.DataFrame(rows)
    agg = (
        df.groupby("date")
        .agg(sentiment=("sentiment", "mean"), count=("sentiment", "count"))
        .sort_index()
    )
    return agg
