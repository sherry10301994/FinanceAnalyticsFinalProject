"""Page 4 – Risk Analysis"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from utils.sidebar import render_sidebar
from utils.data_fetcher import fetch_ticker_data, fetch_market_history
from utils.financial_metrics import calculate_ratios
from utils.risk_models import altman_z_score, beneish_m_score, capm_analysis

st.set_page_config(page_title="Risk Analysis · FinSight", layout="wide")
ticker, peers = render_sidebar()

with st.spinner(f"Loading {ticker}…"):
    data        = fetch_ticker_data(ticker)
    mkt_history = fetch_market_history()

info          = data["info"]
income_stmt   = data["income_stmt"]
balance_sheet = data["balance_sheet"]
cashflow      = data["cashflow"]
history       = data["history"]
market_cap    = info.get("marketCap")

company_name = info.get("longName", ticker)
st.title(f"Risk Analysis · {company_name} ({ticker})")

with st.spinner("Running risk models…"):
    z_result = altman_z_score(income_stmt, balance_sheet, market_cap)
    m_result = beneish_m_score(income_stmt, balance_sheet, cashflow)
    capm     = capm_analysis(history, mkt_history)

# ─── Gauge helper ─────────────────────────────────────────────────────────────
def gauge_chart(value, title, min_val, max_val, boundaries, colors):
    steps = [{"range": [boundaries[i], boundaries[i+1]], "color": colors[i]}
             for i in range(len(boundaries) - 1)]
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        number={"font": {"size": 36}},
        title={"text": title, "font": {"size": 16}},
        gauge={
            "axis": {"range": [min_val, max_val]},
            "bar":  {"color": "black", "thickness": 0.03},
            "steps": steps,
            "threshold": {"line": {"color": "black", "width": 4},
                          "thickness": 0.75, "value": value},
        },
    ))
    fig.update_layout(height=250, margin={"l": 20, "r": 20, "t": 40, "b": 20})
    return fig

BADGE = {"green": "#2ecc71", "orange": "#f39c12", "red": "#e74c3c"}

# ─── Altman Z-Score ───────────────────────────────────────────────────────────
st.subheader("Altman Z-Score — Financial Distress Risk")
col1, col2 = st.columns(2)

with col1:
    if "error" in z_result:
        st.error(z_result["error"])
    else:
        z     = z_result["z_score"]
        color = BADGE[z_result["zone_color"]]
        st.markdown(
            f"<h2 style='text-align:center'>Z = "
            f"<span style='color:{color}'>{z:.3f}</span> "
            f"<span style='font-size:0.6em;background:{color};color:white;"
            f"padding:4px 10px;border-radius:6px'>{z_result['zone']}</span></h2>",
            unsafe_allow_html=True,
        )
        st.plotly_chart(gauge_chart(
            min(z, 5.0), "Altman Z-Score", 0, 5,
            [0, 1.81, 2.99, 5], ["#e74c3c", "#f39c12", "#2ecc71", "#2ecc71"]
        ), use_container_width=True)
        st.markdown(f"> {z_result['explanation']}")

with col2:
    if "error" not in z_result:
        st.markdown("**Component Breakdown**")
        weights = [1.2, 1.4, 3.3, 0.6, 1.0]
        labels  = ["X1 · Working Capital/Assets", "X2 · Retained Earnings/Assets",
                   "X3 · EBIT/Assets", "X4 · Market Cap/Total Debt", "X5 · Revenue/Assets"]
        keys    = ["x1_working_capital", "x2_retained_earnings",
                   "x3_ebit", "x4_market_equity", "x5_revenue"]
        rows = [{"Component": lbl, "Value": round(z_result[k], 4),
                 "Weight": w, "Contribution": round(z_result[k] * w, 4)}
                for lbl, k, w in zip(labels, keys, weights) if z_result.get(k) is not None]
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        if z_result.get("missing_inputs"):
            st.warning(f"Missing (substituted 0): {', '.join(z_result['missing_inputs'])}")

st.markdown("**Zones:** Z > 2.99 = Safe · 1.81–2.99 = Grey · Z < 1.81 = Distress")
st.divider()

# ─── Beneish M-Score ──────────────────────────────────────────────────────────
st.subheader("Beneish M-Score — Earnings Manipulation Detection")
col1, col2 = st.columns(2)

with col1:
    if "error" in m_result:
        st.error(m_result["error"])
    else:
        m     = m_result["m_score"]
        color = BADGE[m_result["zone_color"]]
        st.markdown(
            f"<h2 style='text-align:center'>M = "
            f"<span style='color:{color}'>{m:.3f}</span> "
            f"<span style='font-size:0.6em;background:{color};color:white;"
            f"padding:4px 10px;border-radius:6px'>{m_result['zone']}</span></h2>",
            unsafe_allow_html=True,
        )
        st.plotly_chart(gauge_chart(
            max(min(m, -1.0), -5.0), "Beneish M-Score", -5, -1,
            [-5, -2.22, -1.78, -1], ["#2ecc71", "#f39c12", "#e74c3c", "#e74c3c"]
        ), use_container_width=True)
        st.markdown(f"> {m_result['explanation']}")

with col2:
    if "error" not in m_result:
        comp_info = {
            "DSRI": "Days Sales Receivable Index — ↑ signals inflated receivables",
            "GMI":  "Gross Margin Index — ↑ signals deteriorating margins",
            "AQI":  "Asset Quality Index — ↑ signals intangible asset inflation",
            "SGI":  "Sales Growth Index — ↑ signals aggressive growth pressure",
            "DEPI": "Depreciation Index — ↑ signals slowed depreciation",
            "SGAI": "SG&A Index — ↑ signals rising overhead",
            "TATA": "Total Accruals/Assets — ↑ signals high accruals vs. cash",
            "LVGI": "Leverage Index — ↑ signals rising leverage",
        }
        rows = [{"Index": k, "Value": f"{m_result[k]:.4f}" if m_result.get(k) else "N/A",
                 "Meaning": v}
                for k, v in comp_info.items()]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        if m_result.get("missing_inputs"):
            st.warning(f"Neutral default used for: {', '.join(m_result['missing_inputs'])}")

st.markdown("**Threshold:** M > -1.78 = possible manipulation · M < -2.22 = unlikely manipulator")
st.divider()

# ─── CAPM ─────────────────────────────────────────────────────────────────────
st.subheader("CAPM & Market Risk")
if "error" in capm:
    st.error(capm["error"])
else:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Beta (β)",              f"{capm['beta']:.3f}")
    c2.metric("Expected Return (CAPM)", f"{capm['expected_return_pct']:.2f}%")
    c3.metric("Realized Annual Return", f"{capm['ann_return_pct']:.2f}%")
    c4.metric("Annualized Volatility",  f"{capm['ann_volatility_pct']:.2f}%")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Jensen's Alpha",  f"{capm['alpha_annual_pct']:.2f}%")
    c2.metric("R-Squared",       f"{capm['r_squared']:.4f}")
    c3.metric("Sharpe Ratio",    f"{capm['sharpe_ratio']:.3f}" if capm.get("sharpe_ratio") else "N/A")
    c4.metric("Period",          f"~{capm['n_days']} trading days")

    beta = capm["beta"]
    interp = (
        "Inverse market correlation — rare (e.g. gold stocks)." if beta < 0 else
        "Low sensitivity — defensive stock." if beta < 0.5 else
        "Below-market volatility — relatively defensive." if beta < 1.0 else
        "Slightly above market risk — moderate growth exposure." if beta < 1.5 else
        "High sensitivity — aggressive / cyclical stock."
    )
    st.info(f"**Beta interpretation:** {interp}")

st.divider()

# ─── Red-Flag Summary ─────────────────────────────────────────────────────────
st.subheader("Red-Flag Summary")
ratios = calculate_ratios(income_stmt, balance_sheet, cashflow, info)
flags: list[tuple[str, str, str]] = []

# Z-Score
if "error" not in z_result:
    z = z_result["z_score"]
    if z < 1.81:
        flags.append(("🔴", f"Altman Z = {z:.2f} — Distress zone",
                      "Review liquidity and debt. Potential bankruptcy risk."))
    elif z < 2.99:
        flags.append(("🟡", f"Altman Z = {z:.2f} — Grey zone", "Monitor leverage trends."))
    else:
        flags.append(("🟢", f"Altman Z = {z:.2f} — Safe zone", ""))

# M-Score
if "error" not in m_result:
    m = m_result["m_score"]
    if m > -1.78:
        flags.append(("🔴", f"Beneish M = {m:.2f} — Possible manipulation",
                      "Scrutinize revenue recognition and accruals."))
    elif m > -2.22:
        flags.append(("🟡", f"Beneish M = {m:.2f} — Grey zone", "Some signals; compare with peers."))
    else:
        flags.append(("🟢", f"Beneish M = {m:.2f} — Unlikely manipulator", ""))

# Beta
if "error" not in capm:
    b = capm["beta"]
    if b > 1.5:
        flags.append(("🔴", f"Beta {b:.2f} — Elevated market risk", "Stock amplifies market moves."))
    elif b > 1.0:
        flags.append(("🟡", f"Beta {b:.2f} — Above-market volatility", ""))
    else:
        flags.append(("🟢", f"Beta {b:.2f} — Normal range", ""))

# Current ratio
cr = ratios.get("current_ratio")
if cr is not None:
    if cr < 1.0:
        flags.append(("🔴", f"Current ratio {cr:.2f}x — Liquidity warning",
                      "Current liabilities exceed current assets."))
    elif cr < 1.5:
        flags.append(("🟡", f"Current ratio {cr:.2f}x — Below ideal", ""))
    else:
        flags.append(("🟢", f"Current ratio {cr:.2f}x — Healthy", ""))

# Interest coverage
ic = ratios.get("interest_coverage")
if ic is not None:
    if ic < 1.5:
        flags.append(("🔴", f"Interest coverage {ic:.1f}x — Debt service risk",
                      "Operating income barely covers interest payments."))
    elif ic < 3.0:
        flags.append(("🟡", f"Interest coverage {ic:.1f}x — Below 3x", ""))
    else:
        flags.append(("🟢", f"Interest coverage {ic:.1f}x — Healthy", ""))

for emoji, title, detail in flags:
    if emoji == "🔴":
        with st.expander(f"{emoji} {title}", expanded=True):
            if detail:
                st.write(detail)
    elif emoji == "🟡":
        with st.expander(f"{emoji} {title}", expanded=False):
            if detail:
                st.write(detail)
    else:
        st.success(f"{emoji} {title}")
