"""Page 3 – Peer Benchmarking"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from utils.sidebar import render_sidebar
from utils.data_fetcher import fetch_ticker_data, safe_get
from utils.financial_metrics import calculate_ratios, REVENUE_KEYS

st.set_page_config(page_title="Peer Benchmarking · FinSight", layout="wide")
ticker, peers = render_sidebar()

st.title(f"Peer Benchmarking · {ticker} vs. Peers")

# ─── Load all data ─────────────────────────────────────────────────────────────
all_tickers = [ticker] + [p for p in peers if p != ticker]

progress = st.progress(0, text="Loading peer data…")
all_data: dict = {}
for i, t in enumerate(all_tickers):
    all_data[t] = fetch_ticker_data(t)
    progress.progress((i + 1) / len(all_tickers), text=f"Loaded {t}")
progress.empty()

# ─── Build comparison DataFrame ───────────────────────────────────────────────
rows = []
for t in all_tickers:
    d = all_data[t]
    r = calculate_ratios(d["income_stmt"], d["balance_sheet"], d["cashflow"], d["info"])
    mc = d["info"].get("marketCap")
    rows.append({
        "Ticker":          t,
        "Company":         d["info"].get("shortName", t),
        "Market Cap ($B)": round(mc / 1e9, 1) if mc else None,
        "Revenue ($B)":    round(r["revenue"] / 1e9, 2) if r.get("revenue") else None,
        "Gross Margin %":  round(r["gross_margin"], 1) if r.get("gross_margin") else None,
        "Op. Margin %":    round(r["operating_margin"], 1) if r.get("operating_margin") else None,
        "Net Margin %":    round(r["net_margin"], 1) if r.get("net_margin") else None,
        "ROE %":           round(r["roe"], 1) if r.get("roe") else None,
        "ROA %":           round(r["roa"], 1) if r.get("roa") else None,
        "Debt/Equity":     round(r["debt_to_equity"], 2) if r.get("debt_to_equity") else None,
        "Current Ratio":   round(r["current_ratio"], 2) if r.get("current_ratio") else None,
        "P/E":             round(r["pe_ratio"], 1) if r.get("pe_ratio") else None,
        "Asset Turnover":  round(r["asset_turnover"], 3) if r.get("asset_turnover") else None,
        "Beta":            round(d["info"].get("beta", 0) or 0, 3),
    })

comp_df = pd.DataFrame(rows).set_index("Ticker")

# Revenue growth (requires 2 years)
for t in all_tickers:
    stmt = all_data[t]["income_stmt"]
    if stmt is not None and not stmt.empty and len(stmt.columns) >= 2:
        rev0 = safe_get(stmt, REVENUE_KEYS, 0)
        rev1 = safe_get(stmt, REVENUE_KEYS, 1)
        if rev0 and rev1 and rev1 != 0:
            comp_df.loc[t, "Revenue Growth %"] = round((rev0 - rev1) / abs(rev1) * 100, 1)

# 1-year return
for t in all_tickers:
    h = all_data[t]["history"]
    if h is not None and not h.empty and len(h) >= 252:
        ret = (h["Close"].iloc[-1] - h["Close"].iloc[-252]) / h["Close"].iloc[-252] * 100
        comp_df.loc[t, "1Y Return %"] = round(ret, 1)

# ─── Summary table ─────────────────────────────────────────────────────────────
st.subheader("Comparison Table")
display_cols = [
    "Company", "Market Cap ($B)", "Revenue ($B)", "Revenue Growth %",
    "Gross Margin %", "Op. Margin %", "Net Margin %",
    "ROE %", "ROA %", "Debt/Equity", "Current Ratio", "P/E",
]
disp = comp_df[[c for c in display_cols if c in comp_df.columns]].copy()

def highlight_focal(row):
    return ["background-color: #d6eaf8; font-weight: bold"
            if row.name == ticker else "" for _ in row]

st.dataframe(disp.style.apply(highlight_focal, axis=1), use_container_width=True)
st.divider()

# ─── Bar chart helper ──────────────────────────────────────────────────────────
def bar_compare(metric: str, title: str, suffix: str = "%"):
    vals = comp_df[metric].dropna() if metric in comp_df.columns else pd.Series()
    if vals.empty:
        st.info(f"No data for {metric}")
        return
    colors = ["#e74c3c" if t == ticker else "#3498db" for t in vals.index]
    fig = go.Figure(go.Bar(
        x=vals.index, y=vals,
        marker_color=colors,
        text=[f"{v}{suffix}" for v in vals],
        textposition="outside",
    ))
    fig.update_layout(
        title=title, height=300, showlegend=False,
        margin=dict(l=0, r=0, t=40, b=0),
        plot_bgcolor="white", paper_bgcolor="white",
        yaxis=dict(showgrid=True, gridcolor="#f0f0f0"),
    )
    st.plotly_chart(fig, use_container_width=True)

# ─── Profitability ─────────────────────────────────────────────────────────────
st.subheader("Profitability")
c1, c2, c3 = st.columns(3)
with c1: bar_compare("Gross Margin %",    "Gross Margin (%)")
with c2: bar_compare("Op. Margin %",      "Operating Margin (%)")
with c3: bar_compare("Net Margin %",      "Net Margin (%)")

c1, c2, c3 = st.columns(3)
with c1: bar_compare("ROE %",            "Return on Equity (%)")
with c2: bar_compare("ROA %",            "Return on Assets (%)")
with c3: bar_compare("Revenue Growth %", "Revenue Growth YoY (%)")

st.divider()

# ─── Leverage & Valuation ──────────────────────────────────────────────────────
st.subheader("🏗️ Leverage & Valuation")
c1, c2, c3 = st.columns(3)
with c1: bar_compare("Debt/Equity",   "Debt / Equity (x)", "x")
with c2: bar_compare("Current Ratio", "Current Ratio (x)",  "x")
with c3: bar_compare("P/E",           "P/E Ratio (x)",       "x")

st.divider()

# ─── Scatter plots ─────────────────────────────────────────────────────────────
st.subheader("Scatter Analysis")
tab_s1, tab_s2, tab_s3 = st.tabs([
    "ROE vs Revenue Growth", "Margin vs Asset Turnover", "Risk vs Return"
])

def scatter(x_col, y_col, x_label, y_label, title):
    plot_df = comp_df[[x_col, y_col]].dropna() if (x_col in comp_df and y_col in comp_df.columns) else pd.DataFrame()
    if plot_df.empty:
        st.info("Insufficient data for scatter plot.")
        return
    fig = go.Figure()
    for t_name, row in plot_df.iterrows():
        fig.add_trace(go.Scatter(
            x=[row[x_col]], y=[row[y_col]],
            mode="markers+text", text=[t_name], textposition="top center",
            marker={
                "size":   18 if t_name == ticker else 12,
                "color":  "#e74c3c" if t_name == ticker else "#3498db",
                "symbol": "star" if t_name == ticker else "circle",
            },
            name=t_name, showlegend=False,
        ))
    fig.update_layout(
        title=title, xaxis_title=x_label, yaxis_title=y_label,
        height=380, margin=dict(l=0, r=0, t=40, b=0),
        plot_bgcolor="white", paper_bgcolor="white",
        xaxis=dict(showgrid=True, gridcolor="#f0f0f0"),
        yaxis=dict(showgrid=True, gridcolor="#f0f0f0"),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(f"★ = {ticker} (focal company)")

with tab_s1:
    scatter("Revenue Growth %", "ROE %", "Revenue Growth (%)", "ROE (%)",
            "ROE vs. Revenue Growth")
with tab_s2:
    scatter("Asset Turnover", "Net Margin %", "Asset Turnover (x)", "Net Margin (%)",
            "Net Margin vs. Asset Turnover (DuPont components)")
with tab_s3:
    scatter("Beta", "1Y Return %", "Beta (Market Risk)", "1-Year Return (%)",
            "Risk vs. Return")
