"""Page 5 – News, Sentiment & Filings"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime

from utils.sidebar import render_sidebar
from utils.data_fetcher import fetch_ticker_data, get_sec_filings
from utils.financial_metrics import calculate_ratios

st.set_page_config(page_title="News & Filings · FinSight", layout="wide")
ticker, peers = render_sidebar()

finnhub_key = st.session_state.get("finnhub_key", "")
openai_key  = st.session_state.get("openai_key", "")

with st.spinner(f"Loading {ticker}…"):
    data = fetch_ticker_data(ticker)

info          = data["info"]
history       = data["history"]
income_stmt   = data["income_stmt"]
balance_sheet = data["balance_sheet"]
cashflow      = data["cashflow"]
company_name  = info.get("longName", ticker)

st.title(f"News & Filings · {company_name} ({ticker})")

tab1, tab2, tab3, tab4 = st.tabs([
    "News Feed",
    "Sentiment × Price",
    "Interview Prep",
    "SEC Filings",
])


# ─── shared helper: load & score news ────────────────────────────────────────

def _load_news() -> list[dict]:
    """Fetch + score news, caching in session_state."""
    cache_key = f"news_{ticker}"
    if cache_key not in st.session_state:
        from utils.finnhub_news import get_company_news
        from utils.sentiment import score_articles
        with st.spinner("Fetching news from Finnhub…"):
            raw = get_company_news(ticker, finnhub_key, days_back=365)
            st.session_state[cache_key] = score_articles(raw)
    return st.session_state[f"news_{ticker}"]


def _fmt_big(v) -> str | None:
    if v is None:
        return None
    if abs(v) >= 1e12:
        return f"${v/1e12:.1f}T"
    if abs(v) >= 1e9:
        return f"${v/1e9:.2f}B"
    if abs(v) >= 1e6:
        return f"${v/1e6:.1f}M"
    return f"{v:.2f}"


# ── Tab 1: News Feed ───────────────────────────────────────────────────────────
with tab1:
    if not finnhub_key:
        st.warning("Enter your Finnhub API key in the sidebar (News & AI Keys) to load news.")
        st.stop()

    articles = _load_news()

    if not articles:
        st.warning("No news found for this ticker. Check the ticker symbol or Finnhub key.")
    else:
        # Summary stats bar
        scores = [a["sentiment"] for a in articles if a.get("sentiment") is not None]
        avg_s  = sum(scores) / len(scores) if scores else 0
        pos    = sum(1 for s in scores if s > 0.05)
        neg    = sum(1 for s in scores if s < -0.05)
        neu    = len(scores) - pos - neg

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Articles (12 mo)", len(articles))
        c2.metric("Avg Sentiment", f"{avg_s:+.3f}")
        c3.metric("Positive / Neutral / Negative", f"{pos} / {neu} / {neg}")
        sentiment_label = "Positive" if avg_s > 0.05 else "Negative" if avg_s < -0.05 else "Neutral"
        c4.metric("Overall Tone", sentiment_label)

        st.divider()

        # Filter
        col_f, _ = st.columns([2, 4])
        with col_f:
            show_filter = st.selectbox(
                "Filter by sentiment",
                ["All", "Positive (>0.05)", "Negative (<-0.05)", "Neutral"],
                label_visibility="collapsed",
            )

        filtered = articles
        if show_filter.startswith("Positive"):
            filtered = [a for a in articles if (a.get("sentiment") or 0) > 0.05]
        elif show_filter.startswith("Negative"):
            filtered = [a for a in articles if (a.get("sentiment") or 0) < -0.05]
        elif show_filter == "Neutral":
            filtered = [a for a in articles if -0.05 <= (a.get("sentiment") or 0) <= 0.05]

        st.caption(f"Showing {len(filtered)} articles")

        for a in filtered[:60]:
            ts       = a.get("datetime")
            date_str = datetime.fromtimestamp(ts).strftime("%b %d, %Y") if ts else "?"
            headline = a.get("headline", "No headline")
            source   = a.get("source", "")
            url      = a.get("url", "")
            score    = a.get("sentiment")
            summary  = a.get("summary", "")

            if score is None:
                badge = "⚪ N/A"
            elif score > 0.05:
                badge = f"🟢 {score:+.3f}"
            elif score < -0.05:
                badge = f"🔴 {score:+.3f}"
            else:
                badge = f"⚪ {score:+.3f}"

            col_txt, col_btn = st.columns([6, 1])
            with col_txt:
                st.markdown(f"**[{headline}]({url})**" if url else f"**{headline}**")
                st.caption(f"{source}  ·  {date_str}  ·  Sentiment: {badge}")
                if summary:
                    with st.expander("Summary", expanded=False):
                        st.write(summary)
            with col_btn:
                if url:
                    st.link_button("Read →", url, use_container_width=True)
            st.divider()


# ── Tab 2: Sentiment × Price Chart ────────────────────────────────────────────
with tab2:
    if not finnhub_key:
        st.warning("Enter your Finnhub API key in the sidebar to load this chart.")
        st.stop()

    from utils.sentiment import daily_sentiment_df

    articles = _load_news()
    sent_df  = daily_sentiment_df(articles)

    # history is already CRSP + yfinance stitched (done in data_fetcher._fetch_from_wrds)
    price_df = pd.DataFrame()
    if history is not None and not history.empty:
        cutoff   = pd.Timestamp.now() - pd.DateOffset(years=1)
        price_df = history[history.index >= cutoff][["Close"]].copy()

    if price_df.empty and sent_df.empty:
        st.warning("No price or sentiment data available.")
    else:
        fig = make_subplots(specs=[[{"secondary_y": True}]])

        # ── Stock price line ────────────────────────────────────────────────
        if not price_df.empty:
            fig.add_trace(
                go.Scatter(
                    x=price_df.index,
                    y=price_df["Close"],
                    name="Stock Price",
                    line={"color": "#2196F3", "width": 2},
                    hovertemplate="%{x|%b %d, %Y}  Price: $%{y:.2f}<extra></extra>",
                ),
                secondary_y=False,
            )

        # ── Sentiment bars ──────────────────────────────────────────────────
        if not sent_df.empty:
            bar_colors = [
                "#2ecc71" if v > 0.05 else "#e74c3c" if v < -0.05 else "#bdc3c7"
                for v in sent_df["sentiment"]
            ]
            fig.add_trace(
                go.Bar(
                    x=sent_df.index,
                    y=sent_df["sentiment"],
                    name="Daily Avg Sentiment",
                    marker_color=bar_colors,
                    opacity=0.65,
                    hovertemplate="%{x|%b %d, %Y}  Sentiment: %{y:.3f}  (%{customdata} articles)<extra></extra>",
                    customdata=sent_df["count"],
                ),
                secondary_y=True,
            )

            # Rolling average
            rolling = sent_df["sentiment"].rolling(7, min_periods=1).mean()
            fig.add_trace(
                go.Scatter(
                    x=rolling.index,
                    y=rolling.values,
                    name="7-day Sentiment MA",
                    line={"color": "#FF6F00", "width": 2, "dash": "dot"},
                    hovertemplate="%{x|%b %d, %Y}  7d MA: %{y:.3f}<extra></extra>",
                ),
                secondary_y=True,
            )

            fig.add_hline(y=0, line_dash="dash", line_color="#7f8c8d",
                          line_width=1, secondary_y=True)

        fig.update_layout(
            title=f"{company_name} ({ticker}) — Stock Price & News Sentiment",
            hovermode="x unified",
            legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
            height=520,
            margin={"l": 60, "r": 60, "t": 70, "b": 40},
            plot_bgcolor="#FAFAFA",
        )
        fig.update_yaxes(title_text="Stock Price (USD)", secondary_y=False,
                         showgrid=True, gridcolor="#ececec")
        fig.update_yaxes(title_text="Sentiment Score", secondary_y=True,
                         range=[-1.3, 1.3], showgrid=False)
        fig.update_xaxes(showgrid=True, gridcolor="#ececec",
                         rangeslider={"visible": True, "thickness": 0.06})

        st.plotly_chart(fig, use_container_width=True)
        st.caption("Use the range slider to zoom in/out.")

        if not sent_df.empty:
            avg    = sent_df["sentiment"].mean()
            p_days = (sent_df["sentiment"] > 0.05).sum()
            n_days = (sent_df["sentiment"] < -0.05).sum()
            total  = len(sent_df)
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Avg Sentiment",      f"{avg:+.3f}")
            c2.metric("Positive news days", f"{p_days} / {total}")
            c3.metric("Negative news days", f"{n_days} / {total}")
            c4.metric("Total articles",     str(len(articles)))

        # ── Correlation coefficient ─────────────────────────────────────────
        st.divider()
        st.markdown("#### Sentiment–Return Correlation")
        from utils.sentiment import sentiment_return_correlation

        corr = None
        if not sent_df.empty and not price_df.empty:
            corr = sentiment_return_correlation(sent_df, price_df, window=7)

        if corr is not None:
            color = "#2ecc71" if corr > 0 else "#e74c3c"
            st.markdown(
                f"<h3 style='text-align:center'>"
                f"7-day Rolling Sentiment MA × Daily Return &nbsp;"
                f"<span style='color:{color};background:{color}1a;"
                f"padding:6px 18px;border-radius:8px;font-weight:700'>"
                f"r = {corr:+.3f}</span></h3>",
                unsafe_allow_html=True,
            )
            st.caption(
                "Pearson correlation between the 7-day rolling average of daily "
                "news sentiment and same-day stock returns. "
                "**Exploratory only** — short sample window limits statistical significance."
            )
        else:
            st.info("Not enough overlapping sentiment and price data to compute correlation.")


# ── Tab 3: AI Analysis ────────────────────────────────────────────────────────
with tab3:
    if not finnhub_key:
        st.warning("Enter your Finnhub API key in the sidebar.")
        st.stop()
    if not openai_key:
        st.warning("Enter your Anthropic API key in the sidebar (News & AI Keys).")
        st.stop()

    gpt_cache_key = f"gpt_{ticker}"

    col_hdr, col_btn = st.columns([4, 1])
    with col_hdr:
        st.markdown("Claude generates a tailored interview prep guide based on recent news and financial metrics.")
    with col_btn:
        run_btn = st.button("Run Analysis", type="primary", use_container_width=True)

    if run_btn:
        # Clear stale cache so user can re-run
        st.session_state.pop(gpt_cache_key, None)

    if gpt_cache_key not in st.session_state and run_btn:
        from utils.gpt_analysis import analyze_with_gpt

        articles = _load_news()
        ratios   = calculate_ratios(income_stmt, balance_sheet, cashflow, info)

        fin_summary = {
            "Revenue":          _fmt_big(ratios.get("revenue")),
            "Gross Margin":     f"{ratios['gross_margin']:.1f}%"     if ratios.get("gross_margin")     else None,
            "Operating Margin": f"{ratios['operating_margin']:.1f}%" if ratios.get("operating_margin") else None,
            "Net Margin":       f"{ratios['net_margin']:.1f}%"       if ratios.get("net_margin")       else None,
            "ROE":              f"{ratios['roe']:.1f}%"              if ratios.get("roe")              else None,
            "EPS (diluted)":    f"{ratios['eps_diluted']:.2f}"       if ratios.get("eps_diluted")      else None,
            "P/E Ratio":        f"{ratios['pe_ratio']:.1f}x"         if ratios.get("pe_ratio")         else None,
            "Debt / Equity":    f"{ratios['debt_to_equity']:.2f}x"   if ratios.get("debt_to_equity")   else None,
            "Free Cash Flow":   _fmt_big(ratios.get("free_cf")),
            "Market Cap":       _fmt_big(ratios.get("market_cap")),
            "EBITDA Margin":    f"{ratios['ebitda_margin']:.1f}%"    if ratios.get("ebitda_margin")    else None,
        }

        with st.spinner("Analyzing with Claude (~10 seconds)…"):
            try:
                result = analyze_with_gpt(
                    ticker, company_name, articles, fin_summary, openai_key
                )
                st.session_state[gpt_cache_key] = result
            except Exception as e:
                st.error(f"GPT analysis failed: {e}")

    # ── Display results ───────────────────────────────────────────────────────
    result = st.session_state.get(gpt_cache_key)

    if result is None and not run_btn:
        st.info("Click **Run Analysis** to generate your interview prep guide.")
    elif result:
        # ── Company snapshot ──────────────────────────────────────────────────
        if result.get("company_snapshot"):
            st.info(result["company_snapshot"])

        st.divider()

        # ── Likely interview questions ────────────────────────────────────────
        if result.get("likely_questions"):
            st.markdown("### Likely Interview Questions")
            for i, q in enumerate(result["likely_questions"], 1):
                st.markdown(f"**Q{i}.** {q}")

        st.divider()

        # ── Answer frameworks ─────────────────────────────────────────────────
        frameworks = result.get("answer_frameworks", {})
        if frameworks:
            st.markdown("### How to Answer")
            col_l, col_r = st.columns(2)
            with col_l:
                if frameworks.get("business_overview"):
                    with st.expander("Business Overview (60-sec answer)", expanded=True):
                        st.write(frameworks["business_overview"])
                if frameworks.get("investment_thesis"):
                    with st.expander("Investment Thesis Framework", expanded=True):
                        st.write(frameworks["investment_thesis"])
            with col_r:
                if frameworks.get("valuation"):
                    with st.expander("Valuation Approach", expanded=True):
                        st.write(frameworks["valuation"])

        st.divider()

        # ── Modeling guidance ─────────────────────────────────────────────────
        if result.get("modeling_guidance"):
            st.markdown("### Modeling Guidance")
            for tip in result["modeling_guidance"]:
                st.markdown(f"- {tip}")

        st.divider()

        # ── Key metrics + Recent developments ────────────────────────────────
        col_l, col_r = st.columns(2)
        with col_l:
            if result.get("key_metrics"):
                st.markdown("### Key Metrics to Know")
                for m in result["key_metrics"]:
                    st.markdown(f"- {m}")

        with col_r:
            if result.get("recent_developments"):
                st.markdown("### Recent Developments")
                for d in result["recent_developments"]:
                    st.markdown(f"- {d}")

        st.divider()

        # ── Upside / Downside ─────────────────────────────────────────────────
        col_l, col_r = st.columns(2)
        with col_l:
            if result.get("upside_catalysts"):
                st.markdown("**Upside Catalysts**")
                for c in result["upside_catalysts"]:
                    st.markdown(f"- {c}")
        with col_r:
            if result.get("downside_risks"):
                st.markdown("**Downside Risks**")
                for r in result["downside_risks"]:
                    st.markdown(f"- {r}")

        st.caption("Powered by Claude (Anthropic) · Based on recent news + financial metrics")


# ── Tab 4: SEC Filings ────────────────────────────────────────────────────────
with tab4:
    st.subheader(f"SEC Filings — {company_name}")

    col1, col2 = st.columns(2)
    with col1:
        form_filter = st.multiselect(
            "Filing Types", ["10-K", "10-Q", "8-K", "DEF 14A", "S-1"],
            default=["10-K", "8-K"],
        )
    with col2:
        filing_count = st.slider("Number of filings", 5, 20, 10)

    with st.spinner("Fetching SEC EDGAR filings…"):
        filings = get_sec_filings(ticker, form_types=tuple(form_filter), count=filing_count)

    if not filings:
        st.warning("No filings retrieved. EDGAR may not have this ticker, or a network issue occurred.")
        st.markdown(
            f"[🔗 Search EDGAR directly](https://www.sec.gov/cgi-bin/browse-edgar?"
            f"action=getcompany&CIK={ticker}&type=10-K&dateb=&owner=include&count=40)"
        )
    else:
        ICONS = {"10-K": "📋", "10-Q": "📊", "8-K": "📢", "DEF 14A": "🗳️"}
        DESCS = {
            "10-K":    "Annual Report — comprehensive financial statements and business overview",
            "10-Q":    "Quarterly Report — interim financial statements",
            "8-K":     "Current Report — material events, earnings releases",
            "DEF 14A": "Proxy Statement — executive compensation, shareholder votes",
        }
        for f in filings:
            form = f.get("form", "?")
            date = f.get("date", "?")
            url  = f.get("url", "")
            icon = ICONS.get(form, "📄")
            with st.expander(f"{icon} {form} · Filed {date}", expanded=False):
                st.write(DESCS.get(form, "SEC Filing"))
                if url:
                    st.markdown(f"[📂 Open Filing]({url})")

    st.caption("Filings sourced from SEC EDGAR. Free, no API key required.")
