"""
Financial metrics and ratio calculations for FinSight.
All functions accept yfinance-style DataFrames (index=metric, columns=dates).
"""

import pandas as pd
from utils.data_fetcher import safe_get, get_metric_series, year_label


# ─── Key name aliases ─────────────────────────────────────────────────────────
# Each list contains both yfinance names AND Compustat-derived names (from wrds_fetcher.py).
# The first match in safe_get() / get_metric_series() wins.

# Each list covers yfinance names, Compustat-derived names, and Alpha Vantage names.
REVENUE_KEYS          = ["Total Revenue", "Operating Revenue"]
COGS_KEYS             = ["Cost Of Revenue", "Reconciled Cost Of Revenue"]
GROSS_PROFIT_KEYS     = ["Gross Profit"]
OPERATING_INCOME_KEYS = ["Operating Income", "Total Operating Income As Reported"]
NET_INCOME_KEYS       = ["Net Income", "Net Income Common Stockholders",
                          "Net Income From Continuing And Discontinued Operation"]
EBIT_KEYS             = ["EBIT", "Operating Income"]
EBITDA_KEYS           = ["EBITDA", "Normalized EBITDA"]
RD_KEYS               = ["Research And Development"]
SGA_KEYS              = ["Selling General And Administration", "Selling General Administrative"]
INTEREST_EXP_KEYS     = ["Interest Expense", "Interest Expense Non Operating"]
TAX_KEYS              = ["Tax Provision"]
PRETAX_KEYS           = ["Pretax Income"]
EPS_DILUTED_KEYS      = ["Diluted EPS"]
EPS_BASIC_KEYS        = ["Basic EPS"]
DEPRECIATION_KEYS     = ["Depreciation And Amortization", "Reconciled Depreciation",
                          "Depreciation Amortization Depletion"]

TOTAL_ASSETS_KEYS        = ["Total Assets"]
CURRENT_ASSETS_KEYS      = ["Current Assets"]
CASH_KEYS                = ["Cash And Cash Equivalents",
                             "Cash Cash Equivalents And Short Term Investments"]
RECEIVABLES_KEYS         = ["Receivables", "Accounts Receivable", "Net Receivables"]
INVENTORY_KEYS           = ["Inventory", "Inventories"]
PPE_NET_KEYS             = ["Net Ppe", "Property Plant And Equipment Net"]
TOTAL_LIABILITIES_KEYS   = ["Total Liabilities Net Minority Interest", "Total Liab"]
CURRENT_LIABILITIES_KEYS = ["Current Liabilities", "Total Current Liabilities"]
TOTAL_DEBT_KEYS          = ["Total Debt"]
LT_DEBT_KEYS             = ["Long Term Debt", "Long Term Debt And Capital Lease Obligation"]
EQUITY_KEYS              = ["Stockholders Equity", "Common Stock Equity",
                             "Total Equity Gross Minority Interest"]
RETAINED_EARNINGS_KEYS   = ["Retained Earnings"]
WORKING_CAPITAL_KEYS     = ["Working Capital"]

OPERATING_CF_KEYS = ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"]
CAPEX_KEYS        = ["Capital Expenditure"]
FREE_CF_KEYS      = ["Free Cash Flow"]


# ─── Single-year ratios ────────────────────────────────────────────────────────

def calculate_ratios(
    income_stmt: pd.DataFrame,
    balance_sheet: pd.DataFrame,
    cashflow: pd.DataFrame,
    info: dict,
    col_idx: int = 0,
) -> dict:
    """
    Compute a broad set of financial ratios for the year at col_idx (0 = most recent).
    Returns a flat dict of metric_name → float | None.
    """
    g = lambda df, keys: safe_get(df, keys, col_idx)

    revenue = g(income_stmt, REVENUE_KEYS)
    cogs = g(income_stmt, COGS_KEYS)
    gross_profit = g(income_stmt, GROSS_PROFIT_KEYS)
    operating_income = g(income_stmt, OPERATING_INCOME_KEYS)
    net_income = g(income_stmt, NET_INCOME_KEYS)
    ebit = g(income_stmt, EBIT_KEYS)
    ebitda = g(income_stmt, EBITDA_KEYS)
    interest_exp = g(income_stmt, INTEREST_EXP_KEYS)
    tax = g(income_stmt, TAX_KEYS)
    pretax = g(income_stmt, PRETAX_KEYS)
    eps_diluted = g(income_stmt, EPS_DILUTED_KEYS)
    rd = g(income_stmt, RD_KEYS)
    sga = g(income_stmt, SGA_KEYS)

    total_assets = g(balance_sheet, TOTAL_ASSETS_KEYS)
    current_assets = g(balance_sheet, CURRENT_ASSETS_KEYS)
    cash = g(balance_sheet, CASH_KEYS)
    receivables = g(balance_sheet, RECEIVABLES_KEYS)
    inventory = g(balance_sheet, INVENTORY_KEYS)
    current_liabilities = g(balance_sheet, CURRENT_LIABILITIES_KEYS)
    total_debt = g(balance_sheet, TOTAL_DEBT_KEYS)
    equity = g(balance_sheet, EQUITY_KEYS)
    retained_earnings = g(balance_sheet, RETAINED_EARNINGS_KEYS)
    working_capital = g(balance_sheet, WORKING_CAPITAL_KEYS)

    operating_cf = g(cashflow, OPERATING_CF_KEYS)
    capex = g(cashflow, CAPEX_KEYS)
    free_cf = g(cashflow, FREE_CF_KEYS)

    market_cap = info.get("marketCap")
    pe_trailing = info.get("trailingPE")
    pb = info.get("priceToBook")
    ps = info.get("priceToSalesTrailing12Months")
    beta = info.get("beta")
    dividend_yield = info.get("dividendYield")

    def pct(num, denom):
        return (num / denom * 100) if (num is not None and denom) else None

    def ratio(num, denom):
        return (num / denom) if (num is not None and denom) else None

    # Derived working capital if not directly available
    if working_capital is None and current_assets is not None and current_liabilities is not None:
        working_capital = current_assets - current_liabilities

    # Free cash flow fallback
    if free_cf is None and operating_cf is not None and capex is not None:
        free_cf = operating_cf + capex  # capex is usually negative in yfinance

    # Tax rate
    tax_rate = None
    if tax is not None and pretax and pretax != 0:
        tax_rate = tax / pretax * 100

    # Interest coverage
    interest_coverage = None
    if ebit is not None and interest_exp and interest_exp != 0:
        interest_coverage = abs(ebit / interest_exp)

    return {
        # Income
        "revenue": revenue,
        "gross_profit": gross_profit,
        "operating_income": operating_income,
        "net_income": net_income,
        "ebitda": ebitda,
        "rd_expense": rd,
        "sga_expense": sga,
        # Margins (%)
        "gross_margin": pct(gross_profit, revenue),
        "operating_margin": pct(operating_income, revenue),
        "net_margin": pct(net_income, revenue),
        "ebitda_margin": pct(ebitda, revenue),
        "rd_pct_revenue": pct(rd, revenue),
        # Returns (%)
        "roe": pct(net_income, equity),
        "roa": pct(net_income, total_assets),
        "roic": pct(operating_income, (equity + total_debt) if (equity and total_debt) else None),
        # Asset efficiency
        "asset_turnover": ratio(revenue, total_assets),
        "receivables_turnover": ratio(revenue, receivables),
        "inventory_turnover": ratio(cogs, inventory),
        # Liquidity
        "current_ratio": ratio(current_assets, current_liabilities),
        "quick_ratio": ratio(
            (current_assets - (inventory or 0)) if current_assets else None,
            current_liabilities,
        ),
        "cash_ratio": ratio(cash, current_liabilities),
        "working_capital": working_capital,
        # Leverage
        "debt_to_equity": ratio(total_debt, equity),
        "debt_to_assets": ratio(total_debt, total_assets),
        "equity_multiplier": ratio(total_assets, equity),
        "interest_coverage": interest_coverage,
        "net_debt": (total_debt - cash) if (total_debt and cash) else None,
        # Cash flow
        "operating_cf": operating_cf,
        "free_cf": free_cf,
        "capex": capex,
        "fcf_margin": pct(free_cf, revenue),
        "fcf_yield": ratio(free_cf, market_cap) * 100 if (free_cf and market_cap) else None,
        # Per share & valuation
        "eps_diluted": eps_diluted,
        "pe_ratio": pe_trailing,
        "pb_ratio": pb,
        "ps_ratio": ps,
        "market_cap": market_cap,
        "beta": beta,
        "dividend_yield": (dividend_yield * 100) if dividend_yield else None,
        "tax_rate": tax_rate,
        # Balance sheet items (raw)
        "total_assets": total_assets,
        "total_debt": total_debt,
        "equity": equity,
        "retained_earnings": retained_earnings,
        "cash": cash,
        "current_assets": current_assets,
        "current_liabilities": current_liabilities,
        "receivables": receivables,
        "inventory": inventory,
    }


# ─── Multi-year time series ────────────────────────────────────────────────────

def build_trend_df(income_stmt: pd.DataFrame,
                   balance_sheet: pd.DataFrame,
                   cashflow: pd.DataFrame) -> pd.DataFrame:
    """
    Build a tidy DataFrame with key metrics over all available years.
    Rows = years (oldest first), columns = metric names.
    """
    if income_stmt is None or income_stmt.empty:
        return pd.DataFrame()

    # Use income_stmt columns as the date spine (usually 4 years)
    years = [year_label(c) for c in income_stmt.columns][::-1]  # oldest first

    def series(df, keys):
        s = get_metric_series(df, keys)
        # Re-index to year strings matching `years`
        s.index = [year_label(i) for i in s.index]
        return s.reindex(years)

    data = {
        "Year": years,
        "Revenue": series(income_stmt, REVENUE_KEYS).values,
        "Gross Profit": series(income_stmt, GROSS_PROFIT_KEYS).values,
        "Operating Income": series(income_stmt, OPERATING_INCOME_KEYS).values,
        "Net Income": series(income_stmt, NET_INCOME_KEYS).values,
        "EBITDA": series(income_stmt, EBITDA_KEYS).values,
        "Total Assets": series(balance_sheet, TOTAL_ASSETS_KEYS).values,
        "Total Debt": series(balance_sheet, TOTAL_DEBT_KEYS).values,
        "Equity": series(balance_sheet, EQUITY_KEYS).values,
        "Operating CF": series(cashflow, OPERATING_CF_KEYS).values,
        "Free CF": series(cashflow, FREE_CF_KEYS).values,
        "CapEx": series(cashflow, CAPEX_KEYS).values,
    }

    df = pd.DataFrame(data).set_index("Year")

    # Derived margin columns
    rev = df["Revenue"]
    df["Gross Margin %"] = df["Gross Profit"] / rev * 100
    df["Operating Margin %"] = df["Operating Income"] / rev * 100
    df["Net Margin %"] = df["Net Income"] / rev * 100
    df["ROE %"] = df["Net Income"] / df["Equity"] * 100
    df["ROA %"] = df["Net Income"] / df["Total Assets"] * 100
    df["Debt/Equity"] = df["Total Debt"] / df["Equity"]

    # YoY growth
    df["Revenue Growth %"] = df["Revenue"].pct_change() * 100
    df["Net Income Growth %"] = df["Net Income"].pct_change() * 100

    return df


# ─── DuPont decomposition ─────────────────────────────────────────────────────

def dupont_analysis(income_stmt: pd.DataFrame, balance_sheet: pd.DataFrame) -> dict:
    """
    3-factor DuPont: ROE = Net Margin × Asset Turnover × Equity Multiplier.
    Returns {year_str: {net_margin, asset_turnover, equity_multiplier, roe}}.
    """
    if income_stmt is None or income_stmt.empty:
        return {}

    result = {}
    n_years = min(len(income_stmt.columns), len(balance_sheet.columns))

    for i in range(n_years):
        year = year_label(income_stmt.columns[i])

        revenue = safe_get(income_stmt, REVENUE_KEYS, i)
        net_income = safe_get(income_stmt, NET_INCOME_KEYS, i)
        total_assets = safe_get(balance_sheet, TOTAL_ASSETS_KEYS, i)
        equity = safe_get(balance_sheet, EQUITY_KEYS, i)

        if not all([revenue, net_income, total_assets, equity]):
            continue
        if revenue == 0 or total_assets == 0 or equity == 0:
            continue

        net_margin = net_income / revenue * 100
        asset_turnover = revenue / total_assets
        equity_multiplier = total_assets / equity
        roe = net_margin * asset_turnover * equity_multiplier / 100  # in %

        result[year] = {
            "net_margin": net_margin,
            "asset_turnover": asset_turnover,
            "equity_multiplier": equity_multiplier,
            "roe": roe,
        }

    return result
