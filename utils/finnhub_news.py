"""
Finnhub fetcher for FinSight.
Endpoint: /company-news → recent news articles.
Free tier: 60 req/min.
"""

import requests
import streamlit as st
from datetime import datetime, timedelta

FINNHUB_BASE = "https://finnhub.io/api/v1"


@st.cache_data(ttl=86400, show_spinner=False)
def get_peer_tickers(ticker: str, api_key: str) -> list[str]:
    """
    Fetch peer tickers from Finnhub /stock/peers.
    Returns list of peers excluding the ticker itself.
    """
    try:
        r = requests.get(
            f"{FINNHUB_BASE}/stock/peers",
            params={"symbol": ticker.upper(), "token": api_key},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, list):
            return []
        return [t for t in data if t.upper() != ticker.upper()][:5]
    except Exception:
        return []


@st.cache_data(ttl=1800, show_spinner=False)
def get_company_news(ticker: str, api_key: str, days_back: int = 365) -> list[dict]:
    """
    Fetch company news from Finnhub for the past `days_back` days.
    Returns a list sorted newest-first.
    Each article has: category, datetime (unix ts), headline, source, summary, url.
    """
    to_date   = datetime.now().strftime("%Y-%m-%d")
    from_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    try:
        r = requests.get(
            f"{FINNHUB_BASE}/company-news",
            params={
                "symbol": ticker.upper(),
                "from":   from_date,
                "to":     to_date,
                "token":  api_key,
            },
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, list):
            return []
        return sorted(data, key=lambda x: x.get("datetime", 0), reverse=True)
    except Exception:
        return []
