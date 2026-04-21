"""
WRDS data fetcher for FinSight.
Sources: Compustat (financials) + CRSP (stock prices).

Compustat variables are in millions → converted to actual dollars.
Output DataFrames match the yfinance-style format used throughout the app:
  income_stmt / balance_sheet / cashflow:
      index   = metric name (string)
      columns = fiscal year-end date (pd.Timestamp), most recent first
  history:
      index   = date, columns = Open/High/Low/Close/Volume
"""

import pandas as pd
import numpy as np
import streamlit as st
from datetime import datetime, timedelta


class _WRDSConn:
    """Thin wrapper around a raw psycopg2 connection, mimics wrds.Connection."""
    def __init__(self, psycopg2_conn):
        self.connection = psycopg2_conn

    def raw_sql(self, sql: str, date_cols=None):
        return _sql(self, sql, date_cols=date_cols)


def _sql(conn, sql: str, date_cols: list = None) -> pd.DataFrame:
    """
    Run a SQL query via wrds connection, compatible with all wrds/pandas versions.
    1. Try conn.raw_sql() (wrds native)
    2. Try direct psycopg2 cursor via conn.connection
    3. Try SQLAlchemy engine via conn.engine
    """
    date_cols = date_cols or []

    # Attempt 1: wrds native
    try:
        return conn.raw_sql(sql, date_cols=date_cols)
    except Exception:
        pass

    # Attempt 2: direct psycopg2 cursor (bypasses pandas/SQLAlchemy entirely)
    try:
        cursor = conn.connection.cursor()
        cursor.execute(sql)
        cols = [d[0] for d in cursor.description]
        df = pd.DataFrame(cursor.fetchall(), columns=cols)
        # psycopg2 returns decimal.Decimal for numeric columns — convert to float
        for col in df.columns:
            if col not in date_cols:
                df[col] = pd.to_numeric(df[col], errors="ignore")
        for col in date_cols:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col])
        return df
    except Exception:
        pass

    # Attempt 3: SQLAlchemy engine
    import sqlalchemy as sa
    with conn.engine.connect() as c:
        df = pd.read_sql_query(sql, c)
        for col in date_cols:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col])
        return df


# ─── Connection ───────────────────────────────────────────────────────────────

def get_wrds_connection(username: str):
    """
    Open a WRDS connection. Returns wrds.Connection or None on failure.
    The wrds package uses pgpass file or interactive login.
    We pass the username so the user only has to enter the password once.
    """
    try:
        import wrds
        conn = wrds.Connection(wrds_username=username)
        return conn
    except Exception as e:
        st.error(f"WRDS connection failed: {e}")
        return None


# ─── Compustat lookup ─────────────────────────────────────────────────────────

# Compustat variable → unified metric name (matches yfinance-style keys in financial_metrics.py)
INCOME_VARS = {
    "sale":   "Total Revenue",
    "revt":   "Total Revenue",       # alternate revenue field
    "gp":     "Gross Profit",
    "cogs":   "Cost Of Revenue",
    "xsga":   "Selling General And Administration",
    "xrd":    "Research And Development",
    "ebit":   "EBIT",
    "oiadp":  "Operating Income",    # operating income after D&A
    "oibdp":  "EBITDA",             # operating income before D&A (≈ EBITDA)
    "xint":   "Interest Expense",
    "pi":     "Pretax Income",
    "txt":    "Tax Provision",
    "ni":     "Net Income",
    "epspx":  "Basic EPS",
    "epsfi":  "Diluted EPS",
    "dp":     "Depreciation And Amortization",
}

BALANCE_VARS = {
    "at":     "Total Assets",
    "act":    "Current Assets",
    "che":    "Cash And Cash Equivalents",
    "rect":   "Receivables",
    "invt":   "Inventory",
    "ppent":  "Net Ppe",
    "lt":     "Total Liabilities Net Minority Interest",
    "lct":    "Current Liabilities",
    "dltt":   "Long Term Debt",
    "dlc":    "Short Term Debt",
    "ceq":    "Stockholders Equity",
    "re":     "Retained Earnings",
    "csho":   "Shares Outstanding",
    "prcc_f": "Fiscal Year Stock Price",
}

CASHFLOW_VARS = {
    "oancf":  "Operating Cash Flow",
    "capx":   "Capital Expenditure",   # note: Compustat capx is positive (outflow)
    "ivncf":  "Investing Cash Flow",
    "fincf":  "Financing Cash Flow",
    "dv":     "Dividends Paid",
}

SCALE = 1_000_000  # Compustat stores values in millions


def _long_to_wide(df: pd.DataFrame, var_map: dict, date_col: str = "datadate") -> pd.DataFrame:
    """
    Convert Compustat long-format row(s) to yfinance-style wide DataFrame.
    Scales numeric values by SCALE (millions → dollars).
    Columns = fiscal year-end dates, most recent first.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.sort_values(date_col, ascending=False).copy()
    result: dict[str, dict] = {}

    for _, row in df.iterrows():
        col = pd.Timestamp(row[date_col])
        for compustat_var, metric_name in var_map.items():
            if compustat_var in row and pd.notna(row[compustat_var]):
                val = float(row[compustat_var])
                # Strings like "sale" are dollar amounts in millions; stock price / EPS are not
                non_scaled = {"epspx", "epsfi", "prcc_f", "csho"}
                if compustat_var in non_scaled:
                    scaled_val = val * (1000 if compustat_var == "csho" else 1)
                else:
                    scaled_val = val * SCALE
                if metric_name not in result:
                    result[metric_name] = {}
                result[metric_name][col] = scaled_val

    if not result:
        return pd.DataFrame()

    wide = pd.DataFrame(result).T
    # Ensure columns (dates) are sorted most-recent first
    wide = wide[sorted(wide.columns, reverse=True)]
    return wide


# ─── Compustat queries ────────────────────────────────────────────────────────

def get_compustat_annual(conn, ticker: str, n_years: int = 5) -> dict:
    """
    Fetch annual fundamentals from Compustat (comp.funda).
    Returns {'income_stmt': df, 'balance_sheet': df, 'cashflow': df, 'info': dict}.
    """
    start_year = datetime.now().year - n_years

    sql = f"""
        SELECT
            tic, gvkey, conm, fyear, datadate, sich, naicsh,
            -- Income statement
            sale, revt, gp, cogs, xsga, xrd,
            ebit, oiadp, oibdp, xint, pi, txt, ni,
            epspx, epsfi, dp,
            -- Balance sheet
            at, act, che, rect, invt, ppent,
            lt, lct, dltt, dlc, ceq, re, csho, prcc_f,
            -- Cash flow
            oancf, capx, ivncf, fincf, dv,
            -- Market
            mkvalt
        FROM comp.funda
        WHERE tic = '{ticker.upper()}'
          AND fyear >= {start_year}
          AND datafmt = 'STD'
          AND indfmt = 'INDL'
          AND popsrc = 'D'
          AND consol = 'C'
        ORDER BY fyear DESC
        LIMIT {n_years}
    """
    try:
        raw = _sql(conn, sql, date_cols=["datadate"])
    except Exception as e:
        st.warning(f"Compustat query failed for {ticker}: {e}")
        return {}

    if raw is None or raw.empty:
        st.warning(f"No Compustat data found for ticker '{ticker}'.")
        return {}

    # yfinance-style wide DataFrames
    income_stmt   = _long_to_wide(raw, INCOME_VARS)
    balance_sheet = _long_to_wide(raw, BALANCE_VARS)
    cashflow      = _long_to_wide(raw, CASHFLOW_VARS)

    # Derived: Total Debt = dltt + dlc
    if "Long Term Debt" in balance_sheet.index and "Short Term Debt" in balance_sheet.index:
        total_debt = balance_sheet.loc["Long Term Debt"].add(
            balance_sheet.loc["Short Term Debt"], fill_value=0
        )
        balance_sheet.loc["Total Debt"] = total_debt

    # Derived: Working Capital = act - lct
    if "Current Assets" in balance_sheet.index and "Current Liabilities" in balance_sheet.index:
        wc = balance_sheet.loc["Current Assets"].sub(
            balance_sheet.loc["Current Liabilities"], fill_value=0
        )
        balance_sheet.loc["Working Capital"] = wc

    # Derived: EBITDA = EBIT + Depreciation (if oibdp not available)
    if "EBITDA" not in income_stmt.index:
        if "EBIT" in income_stmt.index and "Depreciation And Amortization" in income_stmt.index:
            ebitda = income_stmt.loc["EBIT"].add(
                income_stmt.loc["Depreciation And Amortization"], fill_value=0
            )
            income_stmt.loc["EBITDA"] = ebitda

    # Fix CapEx sign: Compustat capx is a positive outflow; yfinance stores as negative
    if "Capital Expenditure" in cashflow.index:
        cashflow.loc["Capital Expenditure"] = -cashflow.loc["Capital Expenditure"].abs()

    # Derived: Free Cash Flow = Operating CF + CapEx (CapEx already negative)
    if "Operating Cash Flow" in cashflow.index and "Capital Expenditure" in cashflow.index:
        fcf = cashflow.loc["Operating Cash Flow"].add(
            cashflow.loc["Capital Expenditure"], fill_value=0
        )
        cashflow.loc["Free Cash Flow"] = fcf

    # Build info dict (from most recent row)
    row0 = raw.iloc[0]
    mkt = row0.get("mkvalt")
    price = row0.get("prcc_f")
    shares = row0.get("csho")
    info = {
        "longName":   row0.get("conm", ticker),
        "shortName":  row0.get("conm", ticker),
        "gvkey":      row0.get("gvkey"),
        "sic":        row0.get("sich"),
        "naics":      row0.get("naicsh"),
        "marketCap":  float(mkt) * SCALE if pd.notna(mkt) else None,
        "currentPrice": float(price) if pd.notna(price) else None,
        "sharesOutstanding": float(shares) * 1000 if pd.notna(shares) else None,
        "source": "WRDS/Compustat",
    }

    return {
        "income_stmt":   income_stmt,
        "balance_sheet": balance_sheet,
        "cashflow":      cashflow,
        "info":          info,
    }


# ─── CRSP stock price history ─────────────────────────────────────────────────

def get_crsp_prices(conn, ticker: str, n_years: int = 5) -> pd.DataFrame:
    """
    Fetch daily stock prices from CRSP via ticker lookup.
    Tries CRSP v2 tables (dsf_v2 / stocknames_v2) first, then falls back
    to the legacy tables (dsf / msenames) for older WRDS subscriptions.
    Returns a DataFrame with columns: Open, High, Low, Close, Volume.
    """
    start_date = (datetime.now() - timedelta(days=365 * n_years)).strftime("%Y-%m-%d")

    # ── Try CRSP v2 first ────────────────────────────────────────────────────
    try:
        permno_sql_v2 = f"""
            SELECT DISTINCT permno
            FROM crsp.stocknames_v2
            WHERE ticker = '{ticker.upper()}'
            ORDER BY permno DESC
            LIMIT 1
        """
        permno_df = _sql(conn, permno_sql_v2)
        if permno_df is not None and not permno_df.empty:
            permno = int(permno_df.iloc[0]["permno"])
            price_sql_v2 = f"""
                SELECT dlycaldt            AS date,
                       ABS(dlyprc)         AS close,
                       ABS(dlyprc)         AS open,
                       ABS(dlyprc) * (1 + COALESCE(dlyret, 0)) AS high,
                       ABS(dlyprc) * (1 - ABS(COALESCE(dlyret, 0))) AS low,
                       dlyvol              AS volume
                FROM crsp.dsf_v2
                WHERE permno = {permno}
                  AND dlycaldt >= '{start_date}'
                ORDER BY dlycaldt
            """
            prices = _sql(conn, price_sql_v2, date_cols=["date"])
            if prices is not None and not prices.empty:
                prices = prices.set_index("date")
                prices.index = pd.to_datetime(prices.index)
                prices.columns = [c.title() for c in prices.columns]
                return prices[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])
    except Exception:
        print("CRSP v2 query failed, trying legacy tables...")
        pass  # v2 tables not available — try legacy
    
    # ── Fallback to legacy tables ────────────────────────────────────────────
    try:
        permno_sql_legacy = f"""
            SELECT DISTINCT permno
            FROM crsp.msenames
            WHERE tic = '{ticker.upper()}'
            ORDER BY permno DESC
            LIMIT 1
        """
        permno_df = _sql(conn, permno_sql_legacy)
        if permno_df is not None and not permno_df.empty:
            permno = int(permno_df.iloc[0]["permno"])
            price_sql_legacy = f"""
                SELECT date, prc AS close, prc AS open,
                       prc * (1 + COALESCE(ret, 0)) AS high,
                       prc * (1 - ABS(COALESCE(ret, 0))) AS low,
                       vol AS volume
                FROM crsp.dsf
                WHERE permno = {permno}
                  AND date >= '{start_date}'
                ORDER BY date
            """
            prices = _sql(conn, price_sql_legacy, date_cols=["date"])
            if prices is not None and not prices.empty:
                prices = prices.set_index("date")
                prices.index = pd.to_datetime(prices.index)
                prices.columns = [c.title() for c in prices.columns]
                return prices[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])
    except Exception as e:
        print(f"Legacy CRSP query failed: {e}")
        pass

    print(f"Could not fetch prices for {ticker}.")
    return pd.DataFrame()

# ─── Peer lookup ──────────────────────────────────────────────────────────────

def get_compustat_peers(conn, ticker: str, n_peers: int = 5) -> list[str]:
    """
    Find peer companies in the same 2-digit SIC industry from Compustat.
    Returns a list of ticker symbols.
    """
    # First get the SIC code of the focal company
    sic_sql = f"""
        SELECT sich FROM comp.funda
        WHERE tic = '{ticker.upper()}'
          AND datafmt = 'STD' AND indfmt = 'INDL'
          AND popsrc = 'D' AND consol = 'C'
        ORDER BY fyear DESC LIMIT 1
    """
    try:
        sic_df = _sql(conn, sic_sql)
        if sic_df is None or sic_df.empty:
            return []
        sic = int(sic_df.iloc[0]["sich"])
        sic_2digit = sic // 100  # 2-digit SIC
    except Exception:
        return []

    peers_sql = f"""
        SELECT DISTINCT tic
        FROM comp.funda
        WHERE FLOOR(sich / 100) = {sic_2digit}
          AND tic != '{ticker.upper()}'
          AND datafmt = 'STD' AND indfmt = 'INDL'
          AND popsrc = 'D' AND consol = 'C'
          AND fyear = (SELECT MAX(fyear) FROM comp.funda WHERE datafmt='STD')
          AND sale > 0
        ORDER BY tic
        LIMIT {n_peers}
    """
    try:
        peer_df = _sql(conn, peers_sql)
        if peer_df is None or peer_df.empty:
            return []
        return peer_df["tic"].dropna().tolist()
    except Exception:
        return []
