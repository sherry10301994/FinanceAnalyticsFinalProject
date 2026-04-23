"""Page 1 – KPI Dashboard"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from utils.sidebar import render_sidebar
from utils.data_fetcher import fetch_ticker_data
from utils.financial_metrics import calculate_ratios, build_trend_df

st.set_page_config(page_title="KPI Dashboard · FinSight", layout="wide")
ticker, peers = render_sidebar()

with st.spinner(f"Loading {ticker}…"):
    data = fetch_ticker_data(ticker)

info          = data["info"]
income_stmt   = data["income_stmt"]
balance_sheet = data["balance_sheet"]
cashflow      = data["cashflow"]

company_name = info.get("longName", ticker)
st.title(f"KPI Dashboard · {company_name} ({ticker})")

def fmt(v, suffix="", decimals=2):
    return f"{v:,.{decimals}f}{suffix}" if v is not None else "N/A"

def big(v):
    if v is None: return "N/A"
    if abs(v) >= 1e12: return f"${v/1e12:.2f}T"
    if abs(v) >= 1e9:  return f"${v/1e9:.2f}B"
    if abs(v) >= 1e6:  return f"${v/1e6:.1f}M"
    return f"${v:,.0f}"

# Compute ratios for all available years
n_years = min(
    len(income_stmt.columns) if not income_stmt.empty else 0,
    len(balance_sheet.columns) if not balance_sheet.empty else 0,
    4,
)
all_ratios = {}
year_labels = []
for i in range(n_years):
    col = income_stmt.columns[i] if not income_stmt.empty else None
    yr  = str(pd.Timestamp(col).year) if col is not None else str(i)
    year_labels.append(yr)
    all_ratios[yr] = calculate_ratios(income_stmt, balance_sheet, cashflow, info, col_idx=i)

most_recent = all_ratios[year_labels[0]] if year_labels else {}

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Profitability", "Efficiency", "Liquidity", "Leverage", "Summary Table"
])

# ── Tab 1: Profitability ─────────────────────────────────────────────────────
with tab1:
    st.subheader("Profitability Metrics")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Gross Margin",     fmt(most_recent.get("gross_margin"),     "%", 1))
    c2.metric("Operating Margin", fmt(most_recent.get("operating_margin"), "%", 1))
    c3.metric("Net Margin",       fmt(most_recent.get("net_margin"),       "%", 1))
    c4.metric("EBITDA Margin",    fmt(most_recent.get("ebitda_margin"),    "%", 1))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("ROE",           fmt(most_recent.get("roe"),         "%", 1))
    c2.metric("ROA",           fmt(most_recent.get("roa"),         "%", 1))
    c3.metric("ROIC",          fmt(most_recent.get("roic"),        "%", 1))
    c4.metric("EPS (Diluted)", f"${most_recent['eps_diluted']:.2f}" if most_recent.get("eps_diluted") else "N/A")

    st.divider()
    trend_df = build_trend_df(income_stmt, balance_sheet, cashflow)
    if not trend_df.empty:
        fig = go.Figure()
        for col, color, name in [
            ("Gross Margin %",     "#2ecc71", "Gross Margin"),
            ("Operating Margin %", "#3498db", "Operating Margin"),
            ("Net Margin %",       "#e74c3c", "Net Margin"),
        ]:
            if col in trend_df.columns:
                fig.add_trace(go.Scatter(
                    x=trend_df.index, y=trend_df[col].round(1),
                    mode="lines+markers", name=name,
                    line=dict(width=2.5),
                ))
        fig.update_layout(
            title="Margin Trends (%)", yaxis_title="%", height=320,
            margin=dict(l=0, r=0, t=40, b=0),
            plot_bgcolor="white", paper_bgcolor="white",
            xaxis=dict(showgrid=False),
            yaxis=dict(showgrid=True, gridcolor="#f0f0f0"),
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)

# ── Tab 2: Efficiency ────────────────────────────────────────────────────────
with tab2:
    st.subheader("Efficiency & Asset Utilization")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Asset Turnover",       fmt(most_recent.get("asset_turnover"),       "x"))
    c2.metric("Receivables Turnover", fmt(most_recent.get("receivables_turnover"), "x"))
    c3.metric("Inventory Turnover",   fmt(most_recent.get("inventory_turnover"),   "x"))
    c4.metric("FCF Margin",           fmt(most_recent.get("fcf_margin"),           "%", 1))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Operating CF",  big(most_recent.get("operating_cf")))
    c2.metric("Free CF",       big(most_recent.get("free_cf")))
    c3.metric("CapEx",         big(most_recent.get("capex")))
    c4.metric("FCF Yield",     fmt(most_recent.get("fcf_yield"), "%", 1))

    st.divider()
    trend_df = build_trend_df(income_stmt, balance_sheet, cashflow)
    if not trend_df.empty and "Revenue" in trend_df.columns:
        fig2 = go.Figure()
        for col, name, color in [
            ("Revenue",    "Revenue",    "#3498db"),
            ("Operating CF","Operating CF","#2ecc71"),
            ("Free CF",    "Free CF",    "#e74c3c"),
        ]:
            if col in trend_df.columns:
                fig2.add_trace(go.Bar(
                    x=trend_df.index, y=(trend_df[col] / 1e9).round(2),
                    name=name, marker_color=color
                ))
        fig2.update_layout(
            title="Revenue vs. Cash Flows ($B)", barmode="group", height=320,
            margin=dict(l=0, r=0, t=40, b=0),
            plot_bgcolor="white", paper_bgcolor="white",
        )
        st.plotly_chart(fig2, use_container_width=True)

# ── Tab 3: Liquidity ─────────────────────────────────────────────────────────
with tab3:
    st.subheader("Liquidity Metrics")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Current Ratio",   fmt(most_recent.get("current_ratio"),  "x"))
    c2.metric("Quick Ratio",     fmt(most_recent.get("quick_ratio"),    "x"))
    c3.metric("Cash Ratio",      fmt(most_recent.get("cash_ratio"),     "x"))
    c4.metric("Working Capital", big(most_recent.get("working_capital")))

    c1, c2, c3 = st.columns(3)
    c1.metric("Cash & Equiv.",       big(most_recent.get("cash")))
    c2.metric("Current Assets",      big(most_recent.get("current_assets")))
    c3.metric("Current Liabilities", big(most_recent.get("current_liabilities")))

    st.info("**Rule of thumb:** Current ratio > 1.5 is healthy; < 1 may indicate short-term stress.")

# ── Tab 4: Leverage ──────────────────────────────────────────────────────────
with tab4:
    st.subheader("Leverage & Capital Structure")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Debt / Equity",     fmt(most_recent.get("debt_to_equity"),    "x"))
    c2.metric("Debt / Assets",     fmt(most_recent.get("debt_to_assets"),    "x"))
    c3.metric("Equity Multiplier", fmt(most_recent.get("equity_multiplier"), "x"))
    c4.metric("Interest Coverage", fmt(most_recent.get("interest_coverage"), "x"))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Debt",   big(most_recent.get("total_debt")))
    c2.metric("Net Debt",     big(most_recent.get("net_debt")))
    c3.metric("Equity",       big(most_recent.get("equity")))
    c4.metric("Total Assets", big(most_recent.get("total_assets")))

    st.divider()
    ta = most_recent.get("total_assets")
    eq = most_recent.get("equity")
    td = most_recent.get("total_debt")
    if ta and eq and td:
        other_liab = max(0, ta - eq - td)
        fig3 = go.Figure(go.Pie(
            labels=["Equity", "Total Debt", "Other Liabilities"],
            values=[eq, td, other_liab], hole=0.4,
            marker=dict(colors=["#2ecc71", "#e74c3c", "#f39c12"]),
        ))
        fig3.update_layout(
            title="Capital Structure (Latest Year)", height=300,
            margin=dict(l=0, r=0, t=40, b=0),
        )
        st.plotly_chart(fig3, use_container_width=True)

# ── Tab 5: Summary Table ─────────────────────────────────────────────────────
with tab5:
    st.subheader("Multi-Year Financial Summary")
    trend_df = build_trend_df(income_stmt, balance_sheet, cashflow)
    if not trend_df.empty:
        display_cols = [
            "Revenue", "Net Income", "EBITDA",
            "Gross Margin %", "Operating Margin %", "Net Margin %",
            "ROE %", "ROA %", "Total Assets", "Total Debt", "Equity",
            "Operating CF", "Free CF", "Revenue Growth %", "Debt/Equity",
        ]
        cols_ok = [c for c in display_cols if c in trend_df.columns]
        disp = trend_df[cols_ok].copy()
        for col in ["Revenue","Net Income","EBITDA","Total Assets","Total Debt","Equity","Operating CF","Free CF"]:
            if col in disp.columns:
                disp[col] = disp[col].apply(lambda x: f"${x/1e9:.2f}B" if pd.notna(x) else "N/A")
        for col in [c for c in disp.columns if "%" in c or "/" in c]:
            disp[col] = disp[col].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "N/A")
        st.dataframe(disp.T, use_container_width=True)
    else:
        st.info("No multi-year data available.")
