"""
Risk model implementations for FinSight.
  - Altman Z-Score (1968)
  - Beneish M-Score (1999)
  - CAPM beta / expected return
"""

import numpy as np
import pandas as pd
from utils.data_fetcher import safe_get
from utils.financial_metrics import (
    REVENUE_KEYS, NET_INCOME_KEYS, EBIT_KEYS,
    TOTAL_ASSETS_KEYS, CURRENT_ASSETS_KEYS, CURRENT_LIABILITIES_KEYS,
    RETAINED_EARNINGS_KEYS, TOTAL_DEBT_KEYS, EQUITY_KEYS,
    WORKING_CAPITAL_KEYS, COGS_KEYS, GROSS_PROFIT_KEYS,
    RECEIVABLES_KEYS, PPE_NET_KEYS, DEPRECIATION_KEYS,
    SGA_KEYS, OPERATING_CF_KEYS, PRETAX_KEYS, LT_DEBT_KEYS,
)


# ─── Altman Z-Score ──────────────────────────────────────────────────────────

def altman_z_score(
    income_stmt: pd.DataFrame,
    balance_sheet: pd.DataFrame,
    market_cap: float | None,
) -> dict:
    """
    Classic Altman Z-Score (1968) for public manufacturing companies.
    Z = 1.2*X1 + 1.4*X2 + 3.3*X3 + 0.6*X4 + 1.0*X5

    X1 = Working Capital / Total Assets
    X2 = Retained Earnings / Total Assets
    X3 = EBIT / Total Assets
    X4 = Market Cap / Book Value of Total Debt
    X5 = Revenue / Total Assets

    Zones:
        Z > 2.99   → Safe
        1.81–2.99  → Grey (caution)
        Z < 1.81   → Distress

    Returns a dict with component values, total Z, zone, and explanation.
    """
    g = lambda df, keys, i=0: safe_get(df, keys, i)

    total_assets = g(balance_sheet, TOTAL_ASSETS_KEYS)
    if not total_assets or total_assets == 0:
        return {"error": "Insufficient balance sheet data"}

    # Working capital
    current_assets = g(balance_sheet, CURRENT_ASSETS_KEYS)
    current_liabilities = g(balance_sheet, CURRENT_LIABILITIES_KEYS)
    working_capital = g(balance_sheet, WORKING_CAPITAL_KEYS)
    if working_capital is None and current_assets and current_liabilities:
        working_capital = current_assets - current_liabilities

    retained_earnings = g(balance_sheet, RETAINED_EARNINGS_KEYS)
    ebit = g(income_stmt, EBIT_KEYS)
    revenue = g(income_stmt, REVENUE_KEYS)
    total_debt = g(balance_sheet, TOTAL_DEBT_KEYS)

    missing = []
    if working_capital is None:  missing.append("Working Capital")
    if retained_earnings is None: missing.append("Retained Earnings")
    if ebit is None:              missing.append("EBIT")
    if revenue is None:           missing.append("Revenue")
    if total_debt is None:        missing.append("Total Debt")
    if market_cap is None:        missing.append("Market Cap")

    # Compute components, substituting 0 for missing (with a flag)
    wc = working_capital or 0
    re = retained_earnings or 0
    eb = ebit or 0
    rv = revenue or 0
    mc = market_cap or 0
    td = total_debt if total_debt else 1  # avoid /0

    x1 = wc / total_assets
    x2 = re / total_assets
    x3 = eb / total_assets
    x4 = mc / td
    x5 = rv / total_assets

    z = 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5

    if z > 2.99:
        zone = "Safe"
        zone_color = "green"
        explanation = "Low financial distress risk. The company appears financially healthy."
    elif z > 1.81:
        zone = "Grey"
        zone_color = "orange"
        explanation = "Moderate distress risk. Monitor closely for deterioration."
    else:
        zone = "Distress"
        zone_color = "red"
        explanation = "High financial distress risk. Potential bankruptcy concerns."

    return {
        "z_score": round(z, 3),
        "zone": zone,
        "zone_color": zone_color,
        "explanation": explanation,
        "x1_working_capital": round(x1, 4),
        "x2_retained_earnings": round(x2, 4),
        "x3_ebit": round(x3, 4),
        "x4_market_equity": round(x4, 4),
        "x5_revenue": round(x5, 4),
        "missing_inputs": missing,
    }


# ─── Beneish M-Score ──────────────────────────────────────────────────────────

def beneish_m_score(
    income_stmt: pd.DataFrame,
    balance_sheet: pd.DataFrame,
    cashflow: pd.DataFrame,
) -> dict:
    """
    Beneish M-Score (1999): detects earnings manipulation.
    M = -4.84 + 0.92*DSRI + 0.528*GMI + 0.404*AQI
            + 0.892*SGI + 0.115*DEPI - 0.172*SGAI
            + 4.679*TATA - 0.327*LVGI

    Thresholds:
        M > -1.78  → Likely manipulator
        M < -2.22  → Unlikely manipulator
        Between    → Grey zone

    Requires 2 years of data (current = col 0, prior = col 1).
    """
    g = lambda df, keys, i: safe_get(df, keys, i)

    # Current year (0) and prior year (1)
    def _get(df, keys):
        return g(df, keys, 0), g(df, keys, 1)

    rev_c, rev_p   = _get(income_stmt, REVENUE_KEYS)
    cogs_c, cogs_p = _get(income_stmt, COGS_KEYS)
    rec_c, rec_p   = _get(balance_sheet, RECEIVABLES_KEYS)
    ta_c, ta_p     = _get(balance_sheet, TOTAL_ASSETS_KEYS)
    ca_c, ca_p     = _get(balance_sheet, CURRENT_ASSETS_KEYS)
    ppe_c, ppe_p   = _get(balance_sheet, PPE_NET_KEYS)
    dep_c, dep_p   = _get(cashflow, DEPRECIATION_KEYS)
    sga_c, sga_p   = _get(income_stmt, SGA_KEYS)
    cl_c, cl_p     = _get(balance_sheet, CURRENT_LIABILITIES_KEYS)
    ltd_c, ltd_p   = _get(balance_sheet, LT_DEBT_KEYS)
    pretax_c, _    = _get(income_stmt, PRETAX_KEYS)
    cfo_c, _       = _get(cashflow, OPERATING_CF_KEYS)

    missing = []

    def safe_ratio(a, b):
        if a is None or b is None or b == 0:
            return None
        return a / b

    # DSRI = (Receivables_t/Revenue_t) / (Receivables_{t-1}/Revenue_{t-1})
    dsri = safe_ratio(safe_ratio(rec_c, rev_c), safe_ratio(rec_p, rev_p))
    if dsri is None: missing.append("DSRI")

    # GMI = Gross Margin_{t-1} / Gross Margin_t
    gm_c = (rev_c - cogs_c) / rev_c if (rev_c and cogs_c and rev_c != 0) else None
    gm_p = (rev_p - cogs_p) / rev_p if (rev_p and cogs_p and rev_p != 0) else None
    gmi = safe_ratio(gm_p, gm_c)
    if gmi is None: missing.append("GMI")

    # AQI = [1 - (CA_t + PPE_t)/TA_t] / [1 - (CA_{t-1} + PPE_{t-1})/TA_{t-1}]
    aqi_c = (1 - (ca_c + ppe_c) / ta_c) if (ca_c and ppe_c and ta_c) else None
    aqi_p = (1 - (ca_p + ppe_p) / ta_p) if (ca_p and ppe_p and ta_p) else None
    aqi = safe_ratio(aqi_c, aqi_p)
    if aqi is None: missing.append("AQI")

    # SGI = Revenue_t / Revenue_{t-1}
    sgi = safe_ratio(rev_c, rev_p)
    if sgi is None: missing.append("SGI")

    # DEPI = (Dep_{t-1}/(Dep_{t-1}+PPE_{t-1})) / (Dep_t/(Dep_t+PPE_t))
    depi_c = dep_c / (dep_c + ppe_c) if (dep_c and ppe_c) else None
    depi_p = dep_p / (dep_p + ppe_p) if (dep_p and ppe_p) else None
    depi = safe_ratio(depi_p, depi_c)
    if depi is None: missing.append("DEPI")

    # SGAI = (SGA_t/Rev_t) / (SGA_{t-1}/Rev_{t-1})
    sgai = safe_ratio(safe_ratio(sga_c, rev_c), safe_ratio(sga_p, rev_p))
    if sgai is None: missing.append("SGAI")

    # TATA = (Pretax Income - CFO) / Total Assets
    tata = ((pretax_c - cfo_c) / ta_c) if (pretax_c is not None and cfo_c is not None and ta_c) else None
    if tata is None: missing.append("TATA")

    # LVGI = [(CL_t + LTD_t)/TA_t] / [(CL_{t-1} + LTD_{t-1})/TA_{t-1}]
    lev_c = (cl_c + ltd_c) / ta_c if (cl_c and ltd_c and ta_c) else None
    lev_p = (cl_p + ltd_p) / ta_p if (cl_p and ltd_p and ta_p) else None
    lvgi = safe_ratio(lev_c, lev_p)
    if lvgi is None: missing.append("LVGI")

    # Fall back to 1.0 for missing components (neutral)
    def fallback(v, name):
        return v if v is not None else 1.0

    m = (
        -4.84
        + 0.920 * fallback(dsri, "DSRI")
        + 0.528 * fallback(gmi, "GMI")
        + 0.404 * fallback(aqi, "AQI")
        + 0.892 * fallback(sgi, "SGI")
        + 0.115 * fallback(depi, "DEPI")
        - 0.172 * fallback(sgai, "SGAI")
        + 4.679 * fallback(tata, "TATA")
        - 0.327 * fallback(lvgi, "LVGI")
    )

    if m > -1.78:
        zone = "Likely Manipulator"
        zone_color = "red"
        explanation = "Earnings may be manipulated. Scrutinize revenue recognition and accruals."
    elif m > -2.22:
        zone = "Grey Zone"
        zone_color = "orange"
        explanation = "Some manipulation signals present. Further investigation warranted."
    else:
        zone = "Unlikely Manipulator"
        zone_color = "green"
        explanation = "Low probability of earnings manipulation based on financial ratios."

    return {
        "m_score": round(m, 3),
        "zone": zone,
        "zone_color": zone_color,
        "explanation": explanation,
        "DSRI": round(dsri, 4) if dsri is not None else None,
        "GMI":  round(gmi, 4)  if gmi  is not None else None,
        "AQI":  round(aqi, 4)  if aqi  is not None else None,
        "SGI":  round(sgi, 4)  if sgi  is not None else None,
        "DEPI": round(depi, 4) if depi is not None else None,
        "SGAI": round(sgai, 4) if sgai is not None else None,
        "TATA": round(tata, 4) if tata is not None else None,
        "LVGI": round(lvgi, 4) if lvgi is not None else None,
        "missing_inputs": missing,
    }


# ─── CAPM ────────────────────────────────────────────────────────────────────

def capm_analysis(
    stock_history: pd.DataFrame,
    market_history: pd.DataFrame,
    rf: float = 0.045,
) -> dict:
    """
    Estimate CAPM parameters using 3-year daily returns.
    rf: annual risk-free rate (default 4.5%, approximating 10-yr Treasury)

    Returns beta, alpha, expected annual return, R-squared, Sharpe ratio.
    """
    if stock_history is None or stock_history.empty:
        return {"error": "No stock price history"}
    if market_history is None or market_history.empty:
        return {"error": "No market history"}

    try:
        # Daily returns
        stock_ret = stock_history["Close"].pct_change().dropna()
        mkt_ret = market_history["Close"].pct_change().dropna()

        # Align on common dates (last 3 years)
        common = stock_ret.index.intersection(mkt_ret.index)
        # Keep last ~756 trading days (≈3 years)
        common = common[-756:]

        sr = stock_ret.loc[common].values
        mr = mkt_ret.loc[common].values

        # Daily rf
        rf_daily = rf / 252

        # Excess returns
        er_s = sr - rf_daily
        er_m = mr - rf_daily

        # OLS: er_s = alpha + beta * er_m
        cov_matrix = np.cov(er_s, er_m)
        beta = cov_matrix[0, 1] / cov_matrix[1, 1]
        alpha_daily = np.mean(er_s) - beta * np.mean(er_m)
        alpha_annual = alpha_daily * 252 * 100  # in %

        # Expected annual return (CAPM)
        market_premium = 0.055  # historical equity risk premium ~5.5%
        expected_return = (rf + beta * market_premium) * 100

        # R-squared
        corr = np.corrcoef(er_s, er_m)[0, 1]
        r_squared = corr ** 2

        # Sharpe ratio (annualized)
        excess_annual = np.mean(er_s) * 252
        vol_annual = np.std(er_s) * np.sqrt(252)
        sharpe = excess_annual / vol_annual if vol_annual != 0 else None

        # Annualized stock return and volatility
        ann_return = np.mean(sr) * 252 * 100
        ann_vol = np.std(sr) * np.sqrt(252) * 100

        return {
            "beta": round(beta, 3),
            "alpha_annual_pct": round(alpha_annual, 2),
            "expected_return_pct": round(expected_return, 2),
            "r_squared": round(r_squared, 4),
            "sharpe_ratio": round(sharpe, 3) if sharpe else None,
            "ann_return_pct": round(ann_return, 2),
            "ann_volatility_pct": round(ann_vol, 2),
            "rf_used_pct": rf * 100,
            "market_premium_pct": market_premium * 100,
            "n_days": len(common),
        }
    except Exception as e:
        return {"error": str(e)}
