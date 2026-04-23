"""FinSight — Company Overview (home page)"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from utils.sidebar import render_sidebar
from utils.data_fetcher import fetch_ticker_data
from utils.financial_metrics import calculate_ratios, dupont_analysis

st.set_page_config(
    page_title="FinSight",
    page_icon="F",
    layout="wide",
    initial_sidebar_state="expanded",
)

ticker, peers = render_sidebar()

with st.spinner(f"Loading {ticker}…"):
    data = fetch_ticker_data(ticker)

info          = data.get("info", {})
income_stmt   = data.get("income_stmt", pd.DataFrame())
balance_sheet = data.get("balance_sheet", pd.DataFrame())
cashflow      = data.get("cashflow", pd.DataFrame())
history       = data.get("history", pd.DataFrame())
source        = data.get("source", "yfinance")

company_name = info.get("longName", ticker)
sector       = info.get("sector", "—")
industry     = info.get("industry", "—")
market_cap   = info.get("marketCap")
country      = info.get("country", "—")
website      = info.get("website", "")
exchange     = info.get("exchange", "—")

st.title(f"{company_name}")
col_h1, col_h2 = st.columns([4, 1])
with col_h1:
    st.caption(f"**{ticker}** · {exchange} · {sector} · {industry} · {country}")
    if website:
        st.markdown(f"[🌐 {website}]({website})")
with col_h2:
    src_badge = "🟢 WRDS" if source == "WRDS" else "🟡 Yahoo Finance"
    st.caption(f"Data: {src_badge}")

st.divider()

ratios = calculate_ratios(income_stmt, balance_sheet, cashflow, info)

def fmt_val(v):
    return f"{v:.1f}%" if v is not None else "N/A"

def fmt_big(v):
    if v is None: return "N/A"
    if abs(v) >= 1e12: return f"${v/1e12:.2f}T"
    if abs(v) >= 1e9:  return f"${v/1e9:.2f}B"
    if abs(v) >= 1e6:  return f"${v/1e6:.1f}M"
    return f"${v:,.0f}"

ret_1y = None
if not history.empty and len(history) >= 252:
    p_now  = float(history["Close"].iloc[-1])
    p_1y   = float(history["Close"].iloc[-252])
    ret_1y = (p_now - p_1y) / p_1y * 100
elif not history.empty and len(history) > 1:
    p_now  = float(history["Close"].iloc[-1])
    p_1y   = float(history["Close"].iloc[0])
    ret_1y = (p_now - p_1y) / p_1y * 100

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Market Cap",    fmt_big(market_cap))
c2.metric("Revenue (TTM)", fmt_big(ratios.get("revenue")))
c3.metric("Net Margin",    fmt_val(ratios.get("net_margin")))
c4.metric("ROE",           fmt_val(ratios.get("roe")))
c5.metric("Debt / Equity",
          f"{ratios['debt_to_equity']:.2f}x" if ratios.get("debt_to_equity") else "N/A")
c6.metric("1-Year Return",
          fmt_val(ret_1y) if ret_1y is not None else "N/A",
          delta=f"{ret_1y:.1f}%" if ret_1y is not None else None)

st.divider()

col_left, col_right = st.columns([3, 2], gap="large")

with col_left:
    st.subheader("Stock Price History (5Y)")
    if not history.empty:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=history.index, y=history["Close"].round(2),
            mode="lines", name=ticker,
            line=dict(color="#1f77b4", width=2),
            fill="tozeroy", fillcolor="rgba(31,119,180,0.08)",
        ))
        fig.update_layout(
            height=320, margin=dict(l=0, r=0, t=10, b=0),
            xaxis_title=None, yaxis_title="Price (USD)",
            hovermode="x unified",
            plot_bgcolor="white", paper_bgcolor="white",
            xaxis=dict(showgrid=False),
            yaxis=dict(showgrid=True, gridcolor="#f0f0f0"),
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No historical price data available.")

with col_right:
    st.subheader("DuPont Decomposition")
    dp = dupont_analysis(income_stmt, balance_sheet)
    if dp:
        rows = []
        for year, v in sorted(dp.items(), reverse=True)[:4]:
            rows.append({
                "Year": year,
                "Net Margin": f"{v['net_margin']:.1f}%",
                "× Asset T/O": f"{v['asset_turnover']:.2f}x",
                "× Eq. Mult.": f"{v['equity_multiplier']:.2f}x",
                "= ROE": f"{v['roe']:.1f}%",
            })
        st.dataframe(pd.DataFrame(rows).set_index("Year"), use_container_width=True)
        st.caption("ROE = Net Margin × Asset Turnover × Equity Multiplier")
    else:
        st.info("Not enough data for DuPont analysis.")

st.divider()

description = info.get("longBusinessSummary", "")
if description:
    st.subheader("Business Overview")
    with st.expander("Read full description", expanded=False):
        st.write(description)

st.subheader("Quick Interview Snapshot")
col_a, col_b = st.columns(2)

with col_a:
    st.markdown("**Profitability**")
    lines = []
    for label, key, sfx in [
        ("Gross margin",     "gross_margin",     "%"),
        ("Operating margin", "operating_margin", "%"),
        ("Net margin",       "net_margin",       "%"),
        ("ROE",              "roe",              "%"),
        ("ROA",              "roa",              "%"),
    ]:
        v = ratios.get(key)
        if v is not None:
            lines.append(f"- {label}: **{v:.1f}{sfx}**")
    st.markdown("\n".join(lines) if lines else "_Data unavailable_")

with col_b:
    st.markdown("**Risk & Capital Structure**")
    lines = []
    for label, key, fmt_fn in [
        ("Debt/Equity",       "debt_to_equity",    lambda v: f"{v:.2f}x"),
        ("Current ratio",     "current_ratio",     lambda v: f"{v:.2f}x"),
        ("Interest coverage", "interest_coverage", lambda v: f"{v:.1f}x"),
        ("Free cash flow",    "free_cf",           lambda v: fmt_big(v)),
        ("P/E ratio",         "pe_ratio",          lambda v: f"{v:.1f}x"),
    ]:
        v = ratios.get(key)
        if v is not None:
            lines.append(f"- {label}: **{fmt_fn(v)}**")
    st.markdown("\n".join(lines) if lines else "_Data unavailable_")
