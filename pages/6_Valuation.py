"""Page 6 — DCF Valuation Model"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from utils.data_fetcher import fetch_ticker_data, year_label
from utils.dcf import (
    calc_beta_from_history, calc_wacc, extract_dcf_inputs,
    fit_linear, fit_log_linear, project_fcff, run_dcf, sensitivity_table,
)
from utils.sidebar import render_sidebar

st.set_page_config(page_title="Valuation · FinSight", layout="wide")
ticker, peers = render_sidebar()

with st.spinner(f"Loading {ticker}…"):
    data = fetch_ticker_data(ticker)

# Fetch CRSP market returns from WRDS for beta regression
# Re-fetch if previously cached as None (e.g. page was loaded before WRDS connected)
_mkt_cache = "crsp_mkt_returns"
_cached_mkt = st.session_state.get(_mkt_cache)
if _cached_mkt is None or (hasattr(_cached_mkt, "empty") and _cached_mkt.empty):
    conn = st.session_state.get("wrds_conn")
    if conn is not None:
        from utils.wrds_fetcher import get_crsp_market_returns
        _fetched = get_crsp_market_returns(conn)
        if _fetched is not None and not _fetched.empty:
            st.session_state[_mkt_cache] = _fetched
market_returns = st.session_state.get(_mkt_cache)

info          = data.get("info", {})
income_stmt   = data.get("income_stmt", pd.DataFrame())
balance_sheet = data.get("balance_sheet", pd.DataFrame())
cashflow      = data.get("cashflow", pd.DataFrame())
history       = data.get("history", pd.DataFrame())
company_name  = info.get("longName", ticker)

st.title(f"DCF Valuation · {company_name} ({ticker})")
st.caption("Projections use OLS regression on historical Compustat data. All inputs are editable.")

if income_stmt.empty or balance_sheet.empty or cashflow.empty:
    st.warning("Financial data not available. Connect to WRDS in the sidebar.")
    st.stop()

# ─── Extract historical series ─────────────────────────────────────────────────
hist = extract_dcf_inputs(income_stmt, balance_sheet, cashflow)
rev_series = hist["revenue"].dropna()

if len(rev_series) < 2:
    st.warning("At least 2 years of historical data required for regression.")
    st.stop()

# ─── Fit regressions ───────────────────────────────────────────────────────────
rev_reg       = fit_log_linear(rev_series)
ebit_m_reg    = fit_linear(hist["ebit_margin"].dropna())
da_reg        = fit_linear(hist["da_pct"].dropna())
capex_reg     = fit_linear(hist["capex_pct"].dropna())

tax_rate_hist = hist["tax_rate"].dropna()
tax_median    = float(tax_rate_hist.median()) if not tax_rate_hist.empty else 21.0
nwc_median    = float(hist["nwc_pct"].dropna().median()) if not hist["nwc_pct"].dropna().empty else 2.0

last_revenue  = float(rev_series.iloc[-1])
last_year     = year_label(rev_series.index[-1])

# ─── Section 1: Historical financials ─────────────────────────────────────────
st.subheader("Historical Performance")

hist_years  = [year_label(i) for i in rev_series.index]
fcf_series  = hist["fcf"].dropna()

col_tbl, col_chart = st.columns([2, 3])

with col_tbl:
    def fmt_b(v):
        if pd.isna(v): return "—"
        return f"${v/1e9:.2f}B" if abs(v) >= 1e9 else f"${v/1e6:.0f}M"

    rows = []
    for yr in hist_years:
        rev_v  = hist["revenue"].get(next((i for i in hist["revenue"].index if year_label(i) == yr), None))
        ebit_v = hist["ebit"].get(next((i for i in hist["ebit"].index if year_label(i) == yr), None))
        fcf_v  = hist["fcf"].get(next((i for i in hist["fcf"].index if year_label(i) == yr), None)) if not hist["fcf"].empty else None
        rows.append({
            "Year":         yr,
            "Revenue":      fmt_b(rev_v) if rev_v is not None else "—",
            "EBIT Margin":  f"{hist['ebit_margin'].get(next((i for i in hist['ebit_margin'].index if year_label(i) == yr), None), float('nan')):.1f}%" if not pd.isna(hist['ebit_margin'].get(next((i for i in hist['ebit_margin'].index if year_label(i) == yr), None), float('nan'))) else "—",
            "FCF":          fmt_b(fcf_v) if fcf_v is not None else "—",
        })
    st.dataframe(pd.DataFrame(rows).set_index("Year"), use_container_width=True)

with col_chart:
    fig = go.Figure()
    if not hist["ocf"].dropna().empty:
        years_cf = [year_label(i) for i in hist["ocf"].dropna().index]
        fig.add_trace(go.Bar(
            name="Operating CF", x=years_cf,
            y=hist["ocf"].dropna().values / 1e9,
            marker_color="#3b82f6", opacity=0.85,
        ))
    if not fcf_series.empty:
        years_fcf = [year_label(i) for i in fcf_series.index]
        fig.add_trace(go.Bar(
            name="Free CF", x=years_fcf,
            y=fcf_series.values / 1e9,
            marker_color="#10b981", opacity=0.85,
        ))
    fig.update_layout(
        title="Cash Flow History ($B)", barmode="group", height=260,
        margin=dict(l=0, r=0, t=36, b=40),
        legend=dict(orientation="h", y=1.12),
        plot_bgcolor="white", paper_bgcolor="white",
        yaxis=dict(showgrid=True, gridcolor="#f0f0f0", title="$B"),
        xaxis=dict(showgrid=False),
    )
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ─── Section 2: Regression fits ───────────────────────────────────────────────
st.subheader("OLS Regression Fits")
st.caption("Solid line = historical fit · Dashed line = projection · Dots = actual data")


hist_years_list = [year_label(i) for i in rev_series.index]
proj_years_list = [str(int(hist_years_list[-1]) + i + 1) for i in range(5)]

def _make_reg_fig(title, hist_x, hist_y, fitted_y, proj_x, proj_y, r2, y_title):
    """All inputs in the same units. fitted_y and proj_y must already be scaled."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=hist_x, y=hist_y, mode="markers", name="Actual",
        marker=dict(color="#1e3a5f", size=10),
    ))
    fig.add_trace(go.Scatter(
        x=hist_x, y=fitted_y, mode="lines",
        name=f"OLS fit (R²={r2:.2f})" if r2 is not None else "OLS fit",
        line=dict(color="#3b82f6", width=2),
    ))
    fig.add_trace(go.Scatter(
        x=[hist_x[-1]] + proj_x,
        y=[fitted_y[-1]] + proj_y,
        mode="lines+markers", name="Projection",
        line=dict(color="#f59e0b", width=2, dash="dash"),
        marker=dict(size=8, symbol="circle-open"),
    ))
    fig.update_layout(
        height=340, margin=dict(l=0, r=0, t=45, b=40),
        plot_bgcolor="white", paper_bgcolor="white",
        legend=dict(orientation="h", yanchor="bottom", y=-0.25, x=0),
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor="#f0f0f0", title=y_title),
        title=dict(text=title, font=dict(size=13)),
    )
    return fig

col_r1, col_r2 = st.columns(2)

with col_r1:
    if rev_reg.get("slope") is not None:
        n = len(hist_years_list)
        slope, intercept = rev_reg["slope"], rev_reg["intercept"]
        # fitted in same units as hist_y (billions)
        fitted_rev = [np.exp(intercept + slope * i) / 1e9 for i in range(n)]
        proj_rev   = [v / 1e9 for v in rev_reg["projected"]]
        st.plotly_chart(_make_reg_fig(
            title    = "Revenue — Log-Linear OLS",
            hist_x   = hist_years_list,
            hist_y   = list(rev_series.values / 1e9),
            fitted_y = fitted_rev,
            proj_x   = proj_years_list,
            proj_y   = proj_rev,
            r2       = rev_reg.get("r2"),
            y_title  = "$B",
        ), use_container_width=True)

with col_r2:
    ebit_hist     = hist["ebit_margin"].reindex(rev_series.index).dropna()
    ebit_years    = [year_label(i) for i in ebit_hist.index]
    ebit_proj_yrs = [str(int(ebit_years[-1]) + i + 1) for i in range(5)] if ebit_years else []
    if len(ebit_years) >= 2 and ebit_m_reg.get("slope") is not None:
        ne = len(ebit_years)
        slope_e, intercept_e = ebit_m_reg["slope"], ebit_m_reg["intercept"]
        fitted_ebit = [intercept_e + slope_e * i for i in range(ne)]
        proj_ebit   = list(ebit_m_reg["projected"])
        st.plotly_chart(_make_reg_fig(
            title    = "EBIT Margin — Linear OLS",
            hist_x   = ebit_years,
            hist_y   = list(ebit_hist.values),
            fitted_y = fitted_ebit,
            proj_x   = ebit_proj_yrs,
            proj_y   = proj_ebit,
            r2       = ebit_m_reg.get("r2"),
            y_title  = "%",
        ), use_container_width=True)

# R² summary row
r2_cols = st.columns(4)
for col, (name, method, reg) in zip(r2_cols, [
    ("Revenue", "Log-linear", rev_reg),
    ("EBIT Margin", "Linear", ebit_m_reg),
    ("D&A % Rev",  "Linear",  da_reg),
    ("CapEx % Rev","Linear",  capex_reg),
]):
    r2 = reg.get("r2")
    col.metric(f"{name}", f"R² = {r2:.2f}" if r2 is not None else "R² = N/A",
               help=f"{method} OLS")

st.divider()

# ─── Section 3: Assumptions ────────────────────────────────────────────────────
st.subheader("Model Assumptions")
st.caption("Pre-filled from regression. Adjust to reflect your investment thesis.")

col_ops, col_cap, col_wacc = st.columns(3)

with col_ops:
    st.markdown("**Operations**")
    rev_cagr = st.slider(
        "Revenue CAGR (%)",
        min_value=-5.0, max_value=30.0,
        value=round(float(rev_reg["cagr"] * 100) if rev_reg["cagr"] else 5.0, 1),
        step=0.5, help=f"Regression implied: {rev_reg['cagr']*100:.1f}%"
    )
    ebit_margin = st.slider(
        "EBIT Margin — Year 5 (%)",
        min_value=-10.0, max_value=50.0,
        value=round(float(np.clip(ebit_m_reg["projected"][-1], -10, 50)), 1),
        step=0.5, help=f"Regression implied Y+5: {ebit_m_reg['projected'][-1]:.1f}%"
    )
    ebit_margin_now = round(float(np.clip(ebit_m_reg["projected"][0], -10, 50)), 1)
    tax_rate = st.slider(
        "Tax Rate (%)",
        min_value=0.0, max_value=40.0,
        value=round(min(tax_median, 40.0), 1),
        step=0.5, help=f"Historical median: {tax_median:.1f}%"
    )

with col_cap:
    st.markdown("**Capital**")
    da_pct = st.slider(
        "Depreciation (% of Revenue)",
        min_value=0.0, max_value=20.0,
        value=round(float(np.clip(da_reg["projected"][0], 0, 20)), 1),
        step=0.1, help=f"Used in Net CapEx = CapEx − Depreciation. Regression implied: {da_reg['projected'][0]:.1f}%"
    )
    capex_pct = st.slider(
        "CapEx (% of Revenue)",
        min_value=0.0, max_value=25.0,
        value=round(float(np.clip(capex_reg["projected"][0], 0, 25)), 1),
        step=0.1, help=f"Gross CapEx. Regression implied: {capex_reg['projected'][0]:.1f}%"
    )
    nwc_chg_pct = st.slider(
        "ΔWorking Capital (% of Revenue Change)",
        min_value=-10.0, max_value=20.0,
        value=round(float(np.clip(nwc_median, -10, 20)), 1),
        step=0.5, help="WC = Current Assets − Current Liabilities. Positive = WC grows with revenue."
    )
    terminal_growth = st.slider(
        "Terminal Growth Rate (%)",
        min_value=0.0, max_value=5.0, value=2.5, step=0.25
    )

with col_wacc:
    st.markdown("**WACC**")
    risk_free = st.slider("Risk-Free Rate (%)", 0.0, 8.0, 4.3, 0.1,
                           help="10-year US Treasury yield")
    erp = st.slider("Equity Risk Premium (%)", 3.0, 8.0, 5.5, 0.25,
                     help="Historical ERP ~5-6%")

    # Beta: regression first, then info dict, then default
    with st.spinner("Estimating beta…"):
        beta_calc = None
        if not history.empty:
            beta_calc = calc_beta_from_history(history, market_returns)
    beta_default = beta_calc or info.get("beta") or 1.0
    beta = st.slider("Beta", 0.1, 3.0, round(float(beta_default), 2), 0.05,
                      help=f"{'Regression from CRSP vs SPY' if beta_calc else 'From yfinance / default'}: {beta_default:.2f}")

    # Cost of debt from financials
    cod_hist = hist["cost_of_debt"].dropna()
    cod_default = float(cod_hist.median()) if not cod_hist.empty else 4.5
    cost_of_debt = st.slider(
        "Cost of Debt (%, pre-tax)", 0.0, 15.0,
        round(min(cod_default, 15.0), 1), 0.1,
        help=f"Estimated from financials: {cod_default:.1f}%"
    )

st.divider()

# ─── Build WACC ────────────────────────────────────────────────────────────────
latest_debt   = float(hist["total_debt"].dropna().iloc[-1])  if not hist["total_debt"].dropna().empty  else 0.0
latest_cash   = float(hist["cash"].dropna().iloc[-1])        if not hist["cash"].dropna().empty        else 0.0
latest_equity = float(hist["equity"].dropna().iloc[-1])      if not hist["equity"].dropna().empty      else 1.0
net_debt      = latest_debt - latest_cash

market_cap = info.get("marketCap") or (latest_equity * 1.5)   # rough fallback
shares     = info.get("sharesOutstanding") or info.get("sharesOutstanding") or 1.0

wacc = calc_wacc(
    beta=beta,
    risk_free=risk_free / 100,
    erp=erp / 100,
    cost_of_debt_pct=cost_of_debt / 100,
    tax_rate_pct=tax_rate / 100,
    total_debt=latest_debt,
    equity_value=market_cap,
)

# ─── Build revenue & margin projections (linear interp from now → Y5) ─────────
rev_proj = [last_revenue * (1 + rev_cagr / 100) ** i for i in range(1, 6)]
ebit_margins_proj = np.linspace(ebit_margin_now, ebit_margin, 5).tolist()

# Override regression dicts with user inputs
rev_override   = {"projected": rev_proj,            "r2": rev_reg.get("r2"),   "cagr": rev_cagr / 100}
ebit_override  = {"projected": ebit_margins_proj,   "r2": ebit_m_reg.get("r2")}
da_override    = {"projected": [da_pct] * 5,        "r2": da_reg.get("r2")}
capex_override = {"projected": [capex_pct] * 5,     "r2": capex_reg.get("r2")}

# ─── Section 4: Projected FCFF ─────────────────────────────────────────────────
proj_df = project_fcff(
    last_revenue     = last_revenue,
    rev_reg          = rev_override,
    ebit_margin_reg  = ebit_override,
    da_pct_reg       = da_override,
    capex_pct_reg    = capex_override,
    nwc_pct_median   = nwc_chg_pct,
    tax_rate         = tax_rate / 100,
)

st.subheader("Projected Free Cash Flow to Firm")

def fmt_row(v):
    if pd.isna(v): return "—"
    return f"${v/1e9:.2f}B" if abs(v) >= 1e9 else f"${v/1e6:.0f}M"

display_df = proj_df.copy().applymap(fmt_row)
st.dataframe(display_df, use_container_width=True)

st.divider()

# ─── Section 5: Valuation output ──────────────────────────────────────────────
st.subheader("Valuation")

fcff_list = proj_df["FCFF"].tolist()
result    = run_dcf(fcff_list, terminal_growth / 100, wacc, net_debt, shares)

if not result:
    st.error("WACC must be greater than terminal growth rate.")
    st.stop()

current_price = info.get("currentPrice") or info.get("regularMarketPrice")

col_a, col_b, col_c, col_d, col_e = st.columns(5)
col_a.metric("WACC",                f"{wacc*100:.2f}%")
col_b.metric("Sum PV FCFFs",        fmt_row(result["sum_pv_fcff"]))
col_c.metric("PV Terminal Value",   fmt_row(result["pv_terminal_value"]))
col_d.metric("Enterprise Value",    fmt_row(result["enterprise_value"]))
col_e.metric("Equity Value",        fmt_row(result["equity_value"]))

st.divider()

implied = result.get("implied_price")
col_price, col_updown, col_bridge = st.columns([1, 1, 3])

with col_price:
    st.metric("Implied Share Price", f"${implied:.2f}" if implied else "N/A")

with col_updown:
    if implied and current_price:
        updown = (implied - current_price) / current_price * 100
        delta_label = f"{updown:+.1f}% vs ${current_price:.2f}"
        st.metric("Upside / Downside", f"${implied:.2f}", delta=delta_label)
    else:
        st.info("No current price available for comparison.")

with col_bridge:
    # EV bridge waterfall
    bridge_vals = [
        result["sum_pv_fcff"],
        result["pv_terminal_value"],
        -net_debt,
    ]
    bridge_labels = ["PV FCFFs", "PV Terminal Value", "Less Net Debt"]
    colors = ["#3b82f6", "#6366f1", "#f59e0b" if net_debt > 0 else "#10b981"]
    fig_bridge = go.Figure(go.Bar(
        x=bridge_labels, y=[v / 1e9 for v in bridge_vals],
        marker_color=colors, text=[f"${v/1e9:.1f}B" for v in bridge_vals],
        textposition="outside",
    ))
    fig_bridge.update_layout(
        title="EV Bridge ($B)", height=260,
        margin=dict(l=0, r=0, t=36, b=40),
        plot_bgcolor="white", paper_bgcolor="white",
        yaxis=dict(showgrid=True, gridcolor="#f0f0f0"),
        showlegend=False,
    )
    st.plotly_chart(fig_bridge, use_container_width=True)

st.divider()

# ─── Section 6: Sensitivity table ─────────────────────────────────────────────
st.subheader("Sensitivity Analysis — Implied Price")
st.caption("Rows = Terminal Growth Rate, Columns = WACC")

wacc_range = [wacc - 0.02, wacc - 0.01, wacc, wacc + 0.01, wacc + 0.02]
wacc_range = [max(w, terminal_growth / 100 + 0.01) for w in wacc_range]
tg_range   = [0.005, 0.01, 0.015, 0.02, 0.025, 0.03]

sens = sensitivity_table(fcff_list, net_debt, shares, wacc_range, tg_range)

def color_cell(val):
    if implied is None or pd.isna(val):
        return ""
    pct = (val - implied) / implied
    if pct > 0.15:    return "background-color: #bbf7d0; color: #14532d"
    elif pct > 0.05:  return "background-color: #d1fae5; color: #065f46"
    elif pct > -0.05: return "background-color: #fef9c3; color: #713f12"
    elif pct > -0.15: return "background-color: #fed7aa; color: #7c2d12"
    else:             return "background-color: #fecaca; color: #7f1d1d"

sens_fmt = sens.applymap(lambda v: f"${v:.2f}" if v is not None and not pd.isna(v) else "—")
st.dataframe(
    sens_fmt.style.applymap(
        lambda v: color_cell(float(v.replace("$", "").replace(",", "")) if v != "—" else np.nan)
    ),
    use_container_width=True,
)

st.caption(
    f"Base case WACC = {wacc*100:.2f}% (highlighted column). "
    f"Green = >5% upside vs base case implied price. Red = >5% downside."
)

# ─── Methodology note ─────────────────────────────────────────────────────────
with st.expander("Methodology", expanded=False):
    st.markdown(f"""
**Data source:** WRDS / Compustat annual financials (`comp.funda`), {len(rev_series)} years of history.

**Revenue projection:** Log-linear OLS on historical revenue — fits ln(Revenue) = a + b·t, implying constant CAGR.
Revenue R² = {f"{rev_reg['r2']:.2f}" if rev_reg.get('r2') is not None else 'N/A'}.

**EBIT margin:** Linear OLS trend — captures margin expansion/compression trajectory.
R² = {f"{ebit_m_reg['r2']:.2f}" if ebit_m_reg.get('r2') is not None else 'N/A'}.

**FCFF formula:** EBIT(1−t) − Net CapEx + ΔWorking Capital, where Net CapEx = CapEx − Depreciation. Matches course definition.

**WACC:** CAPM for cost of equity (Ke = Rf + β × ERP). Beta estimated by OLS regression of daily
CRSP stock returns against CRSP value-weighted market returns (`crsp.dsi`). Falls back to reported
beta or 1.0 if WRDS unavailable. Cost of debt = interest expense / total debt (Compustat).

**Terminal value:** Gordon Growth Model — FCF₅ × (1 + g) / (WACC − g).
""")
