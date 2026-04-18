"""
Data fetching utilities for FinSight.

Priority:
  1. WRDS (Compustat + CRSP)  — required
  4. SEC EDGAR                — always used for filings

WRDS connection is stored in st.session_state["wrds_conn"].
"""

import pandas as pd
import requests
import streamlit as st
from datetime import datetime, timedelta


# ─── WRDS-aware ticker fetch ──────────────────────────────────────────────────

def fetch_ticker_data(ticker: str) -> dict:
    """
    Fetch all data for `ticker` from WRDS.
    Result is cached in session_state per ticker.
    """
    ticker = ticker.upper().strip()
    cache_key = f"data_{ticker}"

    if cache_key in st.session_state:
        return st.session_state[cache_key]

    conn = st.session_state.get("wrds_conn")

    if conn is not None:
        result = _fetch_from_wrds(ticker, conn)
    else:
        result = _empty_data(ticker)

    st.session_state[cache_key] = result
    return result


def _empty_data(ticker: str) -> dict:
    return {
        "ticker":        ticker,
        "info":          {},
        "income_stmt":   pd.DataFrame(),
        "balance_sheet": pd.DataFrame(),
        "cashflow":      pd.DataFrame(),
        "history":       pd.DataFrame(),
        "news":          [],
        "source":        "none",
    }


def invalidate_cache(ticker: str | None = None):
    """Clear cached data. If ticker is None, clear all tickers."""
    keys = list(st.session_state.keys())
    for k in keys:
        if k.startswith("data_") or k.startswith("market_history_"):
            if ticker is None or k == f"data_{ticker.upper()}":
                del st.session_state[k]


# ─── WRDS path ────────────────────────────────────────────────────────────────

def _fetch_from_wrds(ticker: str, conn) -> dict:
    from utils.wrds_fetcher import get_compustat_annual, get_crsp_prices

    data = {
        "ticker":        ticker,
        "info":          {},
        "income_stmt":   pd.DataFrame(),
        "balance_sheet": pd.DataFrame(),
        "cashflow":      pd.DataFrame(),
        "history":       pd.DataFrame(),
        "news":          [],
        "source":        "WRDS",
    }

    comp = get_compustat_annual(conn, ticker)
    if comp:
        data.update({
            "income_stmt":   comp.get("income_stmt",   pd.DataFrame()),
            "balance_sheet": comp.get("balance_sheet", pd.DataFrame()),
            "cashflow":      comp.get("cashflow",      pd.DataFrame()),
            "info":          comp.get("info",          {}),
        })

    crsp_hist = get_crsp_prices(conn, ticker)
    if crsp_hist is not None and not crsp_hist.empty:
        days_lag = (pd.Timestamp.now() - crsp_hist.index.max()).days
        if days_lag > 5:
            recent = _yf_price_only(ticker, period="6mo")
            data["history"] = _stitch_prices(crsp_hist, recent)
        else:
            data["history"] = crsp_hist
    else:
        data["history"] = _yf_price_only(ticker, period="5y")

    return data


def _yf_price_only(ticker: str, period: str = "5y") -> pd.DataFrame:
    """
    Fetch price-only history from yfinance (v1.2+, uses curl_cffi to bypass Yahoo auth).
    Normalizes the timezone-aware index to naive UTC so it's compatible with CRSP dates.
    """
    try:
        import yfinance as yf
        h = yf.Ticker(ticker).history(period=period)
        if h is None or h.empty:
            return pd.DataFrame()
        df = h[["Open", "High", "Low", "Close", "Volume"]].copy()
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        df.index = df.index.normalize()
        return df
    except Exception:
        return pd.DataFrame()


def _stitch_prices(crsp_df: pd.DataFrame, yf_df: pd.DataFrame) -> pd.DataFrame:
    """
    Merge CRSP historical prices with yfinance recent prices.
    CRSP is authoritative for the period it covers; yfinance fills dates after.
    """
    if yf_df.empty:
        return crsp_df
    cols = ["Open", "High", "Low", "Close", "Volume"]
    crsp_end  = crsp_df.index.max()
    yf_recent = yf_df[yf_df.index > crsp_end][cols]
    if yf_recent.empty:
        return crsp_df
    combined = pd.concat([crsp_df[cols], yf_recent]).sort_index()
    return combined[~combined.index.duplicated(keep="first")]


# ─── Market history for CAPM ──────────────────────────────────────────────────

def fetch_market_history(n_years: int = 5) -> pd.DataFrame:
    """
    Fetch CRSP value-weighted market index (crsp.dsi) for CAPM calculations.
    Returns a DataFrame with a synthetic 'Close' price series built from
    cumulative daily returns, so pct_change() recovers the original returns.
    """
    cache_key = f"market_history_{n_years}"
    if cache_key in st.session_state:
        return st.session_state[cache_key]

    conn = st.session_state.get("wrds_conn")
    if conn is None:
        return pd.DataFrame()

    start_date = (datetime.now() - timedelta(days=365 * n_years)).strftime("%Y-%m-%d")

    # Try crsp.dsi_v2 first, then legacy crsp.dsi
    for table in ("crsp.dsi_v2", "crsp.dsi"):
        date_col = "caldt"
        ret_col  = "vwretd"
        sql = f"""
            SELECT {date_col} AS date, {ret_col} AS mkt_return
            FROM {table}
            WHERE {date_col} >= '{start_date}'
            ORDER BY {date_col}
        """
        try:
            df = conn.raw_sql(sql, date_cols=["date"])
            if df is not None and not df.empty:
                df = df.set_index("date")
                df.index = pd.to_datetime(df.index)
                df["mkt_return"] = df["mkt_return"].fillna(0)
                # Build synthetic price from cumulative returns
                df["Close"] = (1 + df["mkt_return"]).cumprod() * 100
                result = df[["Close"]]
                st.session_state[cache_key] = result
                return result
        except Exception:
            continue

    return pd.DataFrame()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def safe_get(df: pd.DataFrame, keys: list, col_idx: int = 0):
    """
    Safely extract a scalar from a financial statement DataFrame.
    Tries each key in order; returns the first non-null value.
    col_idx=0 → most recent year.
    """
    if df is None or df.empty:
        return None
    cols = df.columns.tolist()
    if col_idx >= len(cols):
        return None
    col = cols[col_idx]
    for key in keys:
        if key in df.index:
            val = df.loc[key, col]
            if pd.notna(val):
                return float(val)
    return None


def get_metric_series(df: pd.DataFrame, keys: list) -> pd.Series:
    """
    Return a time series for the first matching key.
    Index = dates (oldest first), values = floats.
    """
    if df is None or df.empty:
        return pd.Series(dtype=float)
    for key in keys:
        if key in df.index:
            s = df.loc[key].dropna().astype(float)
            if not s.empty:
                return s.iloc[::-1]  # oldest first
    return pd.Series(dtype=float)


def year_label(ts) -> str:
    try:
        return str(pd.Timestamp(ts).year)
    except Exception:
        return str(ts)


# ─── Peer data ────────────────────────────────────────────────────────────────

def fetch_peers_data(tickers: list) -> dict:
    """Fetch data for a list of peer tickers."""
    result = {}
    for t in tickers:
        result[t] = fetch_ticker_data(t)
    return result


# ─── SEC EDGAR ────────────────────────────────────────────────────────────────

@st.cache_data(ttl=1800, show_spinner=False)
def get_cik(ticker: str) -> str | None:
    try:
        headers = {"User-Agent": "FinSight App finsight@bu.edu"}
        url = "https://www.sec.gov/files/company_tickers.json"
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        ticker_upper = ticker.upper()
        for entry in r.json().values():
            if entry.get("ticker", "").upper() == ticker_upper:
                return str(entry["cik_str"]).zfill(10)
    except Exception:
        pass
    return None


@st.cache_data(ttl=1800, show_spinner=False)
def get_sec_filings(ticker: str, form_types: tuple = ("10-K", "8-K"), count: int = 8) -> list:
    """Retrieve recent SEC filings from EDGAR submissions API."""
    cik = get_cik(ticker)
    if not cik:
        return []
    try:
        headers = {"User-Agent": "FinSight App finsight@bu.edu"}
        r = requests.get(f"https://data.sec.gov/submissions/CIK{cik}.json",
                         headers=headers, timeout=10)
        r.raise_for_status()
        sub    = r.json()
        recent = sub.get("filings", {}).get("recent", {})
        forms  = recent.get("form", [])
        dates  = recent.get("filingDate", [])
        accessions = recent.get("accessionNumber", [])
        docs   = recent.get("primaryDocument", [])

        filings = []
        for form, date, acc, doc in zip(forms, dates, accessions, docs):
            if form in form_types:
                acc_clean = acc.replace("-", "")
                url = (f"https://www.sec.gov/Archives/edgar/data/"
                       f"{int(cik)}/{acc_clean}/{doc}")
                filings.append({"form": form, "date": date, "url": url, "accession": acc})
                if len(filings) >= count:
                    break
        return filings
    except Exception:
        return []
