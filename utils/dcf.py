"""
DCF valuation helpers for FinSight.

Approach:
  - Revenue projection: log-linear OLS on historical revenue (captures exponential growth)
  - Margin / CapEx / D&A: linear OLS on historical ratios (captures trend direction)
  - Tax rate: historical median (too volatile for trend regression)
  - NWC change: historical median as % of revenue change
  - Beta: regression of daily stock returns on market returns (CRSP vs SPY)
  - FCFF = NOPAT + D&A - CapEx - ΔNWC
"""

import numpy as np
import pandas as pd
from scipy import stats

from utils.data_fetcher import get_metric_series
from utils.financial_metrics import (
    REVENUE_KEYS, EBIT_KEYS, DEPRECIATION_KEYS,
    TAX_KEYS, PRETAX_KEYS, CAPEX_KEYS, OPERATING_CF_KEYS, FREE_CF_KEYS,
    CURRENT_ASSETS_KEYS, CASH_KEYS, CURRENT_LIABILITIES_KEYS,
    TOTAL_DEBT_KEYS, EQUITY_KEYS, INTEREST_EXP_KEYS,
)


# ─── Regression helpers ────────────────────────────────────────────────────────

def _linreg(x: np.ndarray, y: np.ndarray):
    """OLS. Returns (slope, intercept, r2)."""
    mask = np.isfinite(x) & np.isfinite(y)
    if mask.sum() < 2:
        return None, None, None
    x_, y_ = x[mask], y[mask]
    slope, intercept, r, *_ = stats.linregress(x_, y_)
    return slope, intercept, r ** 2


def fit_log_linear(values: pd.Series, n_project: int = 5) -> dict:
    """
    Log-linear regression: ln(y) = a + b*t.
    Projects n_project steps beyond the last observed point.
    Returns dict with r2, projected list, and implied CAGR.
    """
    y = values.dropna().values.astype(float)
    if len(y) < 2 or np.any(y <= 0):
        return {"r2": None, "projected": [float(y[-1])] * n_project if len(y) else [], "cagr": None}
    x = np.arange(len(y), dtype=float)
    slope, intercept, r2 = _linreg(x, np.log(y))
    if slope is None:
        return {"r2": None, "projected": [float(y[-1])] * n_project, "cagr": None}
    n = len(y)
    projected = [np.exp(intercept + slope * (n + i)) for i in range(n_project)]
    cagr = np.exp(slope) - 1
    return {"r2": r2, "projected": projected, "cagr": cagr, "slope": slope, "intercept": intercept, "n": n}


def fit_linear(values: pd.Series, n_project: int = 5) -> dict:
    """
    Linear regression: y = a + b*t.
    Projects n_project steps beyond the last observed point.
    """
    y = values.dropna().values.astype(float)
    if len(y) < 2:
        fallback = float(y[-1]) if len(y) else 0.0
        return {"r2": None, "projected": [fallback] * n_project, "slope": 0.0}
    x = np.arange(len(y), dtype=float)
    slope, intercept, r2 = _linreg(x, y)
    if slope is None:
        return {"r2": None, "projected": [float(y[-1])] * n_project, "slope": 0.0}
    n = len(y)
    projected = [intercept + slope * (n + i) for i in range(n_project)]
    return {"r2": r2, "projected": projected, "slope": slope, "intercept": intercept, "n": n}


# ─── Historical data extraction ────────────────────────────────────────────────

def extract_dcf_inputs(income_stmt: pd.DataFrame,
                        balance_sheet: pd.DataFrame,
                        cashflow: pd.DataFrame) -> dict[str, pd.Series]:
    """
    Extract annual time series needed for DCF (oldest first).
    Returns dict of named Series; missing data returns empty Series.
    """
    def s(df, keys): return get_metric_series(df, keys)

    revenue    = s(income_stmt,   REVENUE_KEYS)
    ebit       = s(income_stmt,   EBIT_KEYS)
    da         = s(income_stmt,   DEPRECIATION_KEYS)
    tax        = s(income_stmt,   TAX_KEYS)
    pretax     = s(income_stmt,   PRETAX_KEYS)
    interest   = s(income_stmt,   INTEREST_EXP_KEYS)
    capex      = s(cashflow,      CAPEX_KEYS)       # already negative (yfinance/WRDS)
    ocf        = s(cashflow,      OPERATING_CF_KEYS)
    fcf        = s(cashflow,      FREE_CF_KEYS)
    cur_assets = s(balance_sheet, CURRENT_ASSETS_KEYS)
    cash_bs    = s(balance_sheet, CASH_KEYS)
    cur_liab   = s(balance_sheet, CURRENT_LIABILITIES_KEYS)
    total_debt = s(balance_sheet, TOTAL_DEBT_KEYS)
    equity     = s(balance_sheet, EQUITY_KEYS)

    # Operating NWC (exclude cash from current assets)
    op_nwc = (cur_assets - cash_bs) - cur_liab

    # Derived ratios (aligned to revenue index)
    common_idx = revenue.index
    def align(s): return s.reindex(common_idx)

    rev = align(revenue)
    ebit_margin = align(ebit) / rev * 100          # %
    da_pct      = align(da).abs() / rev * 100       # %
    capex_pct   = align(capex).abs() / rev * 100    # %

    # Tax rate per year
    tax_rate = (align(tax) / align(pretax) * 100).clip(0, 50)

    # NWC change as % of revenue change
    nwc_aligned = align(op_nwc)
    delta_nwc   = nwc_aligned.diff()                # change in NWC (positive = cash use)
    delta_rev   = rev.diff()
    nwc_pct     = (delta_nwc / delta_rev * 100).replace([np.inf, -np.inf], np.nan)

    # Cost of debt
    cost_of_debt = (align(interest).abs() / align(total_debt) * 100).replace([np.inf, -np.inf], np.nan)

    return {
        "revenue":      revenue,
        "ebit":         align(ebit),
        "da":           align(da).abs(),
        "capex":        align(capex).abs(),
        "ocf":          align(ocf),
        "fcf":          fcf,
        "tax_rate":     tax_rate,
        "ebit_margin":  ebit_margin,
        "da_pct":       da_pct,
        "capex_pct":    capex_pct,
        "nwc_pct":      nwc_pct,
        "total_debt":   align(total_debt),
        "cash":         align(cash_bs),
        "equity":       align(equity),
        "cost_of_debt": cost_of_debt,
        "interest":     align(interest).abs(),
    }


# ─── Beta from price history ───────────────────────────────────────────────────

def _normalize_index(s: pd.Series) -> pd.Series:
    """Strip timezone and normalize to midnight so CRSP and yfinance dates align."""
    idx = pd.to_datetime(s.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    s = s.copy()
    s.index = idx.normalize()
    return s


def calc_beta_from_history(stock_history: pd.DataFrame,
                            market_returns: pd.Series | None = None) -> float | None:
    """
    Regress daily stock returns on market returns (OLS).
    market_returns: daily return Series from crsp.dsi (value-weighted).
    Falls back to fetching SPY via yfinance if market_returns not provided.
    Returns beta or None on failure.
    """
    try:
        stk_ret = _normalize_index(stock_history["Close"].astype(float)).pct_change().dropna()

        if market_returns is not None and not market_returns.empty:
            # CRSP returns are already daily return values
            mkt_ret = _normalize_index(market_returns).dropna()
        else:
            # Fallback: yfinance SPY prices → convert to returns
            import yfinance as yf
            spy = yf.Ticker("SPY").history(period="5y")
            if spy.empty:
                return None
            mkt_ret = _normalize_index(spy["Close"].astype(float)).pct_change().dropna()

        joined = pd.concat([stk_ret.rename("stk"), mkt_ret.rename("mkt")], axis=1).dropna()
        if len(joined) < 60:
            return None
        slope, *_ = stats.linregress(joined["mkt"], joined["stk"])
        return round(float(slope), 3)
    except Exception:
        return None


# ─── WACC ─────────────────────────────────────────────────────────────────────

def calc_wacc(beta: float, risk_free: float, erp: float,
              cost_of_debt_pct: float, tax_rate_pct: float,
              total_debt: float, equity_value: float) -> float:
    """
    WACC = (E/V)*Ke + (D/V)*Kd*(1-t)
    All rate inputs in decimal (e.g. 0.043 for 4.3%).
    """
    total = total_debt + equity_value
    if total <= 0:
        return 0.10  # fallback
    ke   = risk_free + beta * erp
    kd   = cost_of_debt_pct * (1 - tax_rate_pct)
    wacc = (equity_value / total) * ke + (total_debt / total) * kd
    return wacc


# ─── FCFF projection ───────────────────────────────────────────────────────────

def project_fcff(
    last_revenue: float,
    rev_reg: dict,
    ebit_margin_reg: dict,
    da_pct_reg: dict,
    capex_pct_reg: dict,
    nwc_pct_median: float,
    tax_rate: float,
    n_years: int = 5,
) -> pd.DataFrame:
    """
    Build projected FCFF table using course formula:
      FCFF = EBIT(1-t) - Net CapEx + ΔWorking Capital
      Net CapEx = CapEx - Depreciation
      ΔWC = change in (Current Assets - Current Liabilities)
    """
    rows = []
    prev_rev = last_revenue
    for i in range(n_years):
        rev     = rev_reg["projected"][i]
        ebit_m  = ebit_margin_reg["projected"][i] / 100
        da_m    = da_pct_reg["projected"][i] / 100
        capex_m = capex_pct_reg["projected"][i] / 100

        ebit      = rev * ebit_m
        ebit_at   = ebit * (1 - tax_rate)          # EBIT(1-t)
        da_       = rev * da_m                      # Depreciation
        capex_    = rev * capex_m                   # Gross CapEx
        net_capex = capex_ - da_                    # Net CapEx = CapEx - Depreciation
        delta_wc  = (rev - prev_rev) * (nwc_pct_median / 100)  # ΔWorking Capital
        fcff      = ebit_at - net_capex + delta_wc

        rows.append({
            "Year":             f"Y+{i+1}",
            "Revenue":          rev,
            "EBIT":             ebit,
            "EBIT(1-t)":        ebit_at,
            "Net CapEx":        net_capex,
            "ΔWorking Capital": delta_wc,
            "FCFF":             fcff,
        })
        prev_rev = rev

    return pd.DataFrame(rows).set_index("Year")


# ─── DCF valuation ─────────────────────────────────────────────────────────────

def run_dcf(fcff_list: list[float], terminal_growth: float,
            wacc: float, net_debt: float, shares: float) -> dict:
    """
    Discount FCFFs + terminal value. Returns valuation bridge dict.
    """
    if wacc <= terminal_growth:
        return {}

    pv_fcffs = [fcf / (1 + wacc) ** t for t, fcf in enumerate(fcff_list, 1)]
    tv        = fcff_list[-1] * (1 + terminal_growth) / (wacc - terminal_growth)
    pv_tv     = tv / (1 + wacc) ** len(fcff_list)
    ev        = sum(pv_fcffs) + pv_tv
    eq_value  = ev - net_debt
    price     = eq_value / shares if shares and shares > 0 else None

    return {
        "pv_fcffs":          pv_fcffs,
        "sum_pv_fcff":       sum(pv_fcffs),
        "terminal_value":    tv,
        "pv_terminal_value": pv_tv,
        "enterprise_value":  ev,
        "equity_value":      eq_value,
        "implied_price":     price,
    }


# ─── Sensitivity table ─────────────────────────────────────────────────────────

def sensitivity_table(fcff_list: list[float], net_debt: float, shares: float,
                       wacc_range: list[float], tg_range: list[float]) -> pd.DataFrame:
    """
    Implied price grid: rows = terminal growth, columns = WACC.
    """
    data = {}
    for tg in tg_range:
        row = {}
        for wacc in wacc_range:
            res = run_dcf(fcff_list, tg, wacc, net_debt, shares)
            row[f"{wacc*100:.1f}%"] = res.get("implied_price")
        data[f"{tg*100:.1f}%"] = row
    return pd.DataFrame(data).T
