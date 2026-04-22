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
You are an expert finance interview coach helping a student prepare for investment banking, \
equity research, or private equity interviews about a specific public company.

You receive recent news headlines and key financial metrics. Use both to generate a \
structured, practical interview prep guide tailored to this company.

Respond ONLY with a valid JSON object containing exactly these fields:
{
  "company_snapshot": "<2-3 sentence company overview the student should memorize — sector, business model, scale>",

  "likely_questions": [
    "<5 specific interview questions an interviewer would ask about this company — mix of business, valuation, and current events>"
  ],

  "answer_frameworks": {
    "business_overview": "<how to structure a 60-second company overview answer using the What/How/Why framework>",
    "valuation":         "<which valuation methods apply to this company (DCF, comps, precedent transactions), why, and the 2-3 key assumptions that drive value>",
    "investment_thesis": "<bull/bear structure: 2 upside catalysts vs 2 downside risks, and how to form a view>"
  },

  "modeling_guidance": [
    "<4-5 specific tips for modeling this company: key revenue drivers, margin structure, working capital dynamics, capex intensity, anything sector-specific>"
  ],

  "key_metrics": [
    "<6-8 'Metric Name: value — one sentence on why this metric matters for this company' strings, cite actual numbers from the data provided>"
  ],

  "recent_developments": [
    "<3 recent news items that are likely to come up in an interview, with a one-sentence take on implications>"
  ],

  "upside_catalysts": ["<2-3 specific catalysts that could drive outperformance>"],
  "downside_risks":   ["<2-3 specific risks to monitor>"]
}

Be specific, cite actual numbers where available, and tailor everything to this company.\
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
        "max_tokens": 4096,
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
