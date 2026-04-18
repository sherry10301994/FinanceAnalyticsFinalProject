"""
Claude-powered news sentiment analysis and talking points for FinSight.
Uses the Anthropic Messages API directly via requests (no SDK needed).
Default model: claude-haiku-4-5-20251001 (fast, cheap).
"""

import json
import requests
from datetime import datetime

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

SYSTEM_PROMPT = """\
You are a senior equity research analyst preparing a company briefing note.
You receive recent news headlines and key financial metrics for a public company.

Respond ONLY with a valid JSON object containing exactly these fields:
{
  "overall_sentiment":  "Positive" | "Neutral" | "Negative",
  "sentiment_score":    <float -1.0 to 1.0>,
  "key_themes":         [<3-5 concise theme strings>],
  "positive_catalysts": [<up to 3 strings>],
  "risk_factors":       [<up to 3 strings>],
  "talking_points":     [<5-7 strings suitable for a finance interview, cite numbers where possible>],
  "one_liner":          "<one-sentence executive summary for interview use>"
}

Be concise, factual, and grounded in the data provided.\
"""


def _fmt_ts(unix_ts) -> str:
    try:
        return datetime.fromtimestamp(unix_ts).strftime("%Y-%m-%d")
    except Exception:
        return "?"


def _build_user_message(
    ticker: str,
    company_name: str,
    articles: list[dict],
    financial_summary: dict,
) -> str:
    headline_block = "\n".join(
        f"[{i+1}] ({_fmt_ts(a.get('datetime'))}) "
        f"{a.get('headline', '')} — {a.get('summary', '')[:200]}"
        for i, a in enumerate(articles[:30])
    )
    fin_block = "\n".join(
        f"  {k}: {v}" for k, v in financial_summary.items() if v is not None
    )
    return (
        f"Company: {company_name} ({ticker})\n\n"
        f"=== RECENT NEWS ({min(len(articles), 30)} articles) ===\n"
        f"{headline_block}\n\n"
        f"=== KEY FINANCIAL METRICS ===\n"
        f"{fin_block}\n"
    )


def analyze_with_gpt(
    ticker: str,
    company_name: str,
    articles: list[dict],
    financial_summary: dict,
    api_key: str,
    model: str = "claude-haiku-4-5-20251001",
) -> dict:
    """
    Call Anthropic Messages API directly via requests to produce structured analysis.
    Returns a parsed dict. Raises on API or JSON error.
    """
    user_msg = _build_user_message(ticker, company_name, articles, financial_summary)

    headers = {
        "x-api-key":         api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type":      "application/json",
    }
    payload = {
        "model":      model,
        "max_tokens": 1024,
        "system":     SYSTEM_PROMPT,
        "messages":   [{"role": "user", "content": user_msg}],
    }

    resp = requests.post(ANTHROPIC_API_URL, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    text = resp.json()["content"][0]["text"]
    # Strip markdown code fences if Claude wraps the JSON
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())
