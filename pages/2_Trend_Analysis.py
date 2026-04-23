"""Page 2 – Trend Analysis"""

import streamlit as st
import plotly.graph_objects as go
import numpy as np

from utils.sidebar import render_sidebar
from utils.data_fetcher import fetch_ticker_data
from utils.financial_metrics import build_trend_df

st.set_page_config(page_title="Trend Analysis · FinSight", layout="wide")
ticker, peers = render_sidebar()

with st.spinner(f"Loading {ticker}…"):
    data = fetch_ticker_data(ticker)

info          = data["info"]
income_stmt   = data["income_stmt"]
balance_sheet = data["balance_sheet"]
cashflow      = data["cashflow"]
history       = data["history"]

company_name = info.get("longName", ticker)
st.title(f"Trend Analysis · {company_name} ({ticker})")

trend_df = build_trend_df(income_stmt, balance_sheet, cashflow)

COLORS = ["#3498db", "#e74c3c", "#2ecc71", "#f39c12", "#9b59b6"]

def line_chart(df, cols, title, y_label, scale=1e9, height=320):
    fig = go.Figure()
    for col, color in zip(cols, COLORS):
        if col in df.columns:
            vals = df[col] / scale if scale else df[col]
            fig.add_trace(go.Scatter(
                x=df.index, y=vals.round(2),
                mode="lines+markers", name=col.replace(" %", ""),
                line=dict(color=color, width=2.5),
                marker=dict(size=7),
            ))
    fig.update_layout(
        title=title, yaxis_title=y_label, height=height,
        margin=dict(l=0, r=0, t=40, b=0),
        plot_bgcolor="white", paper_bgcolor="white",
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor="#f0f0f0"),
        hovermode="x unified",
        legend=dict(orientation="h", y=-0.2),
    )
    return fig

tab1, tab2, tab3, tab4 = st.tabs([
    "Income & Growth", "Margins & Returns", "Stock Price", "Balance Sheet"
])

# ── Tab 1 ─────────────────────────────────────────────────────────────────────
with tab1:
    if trend_df.empty:
        st.info("No financial statement data available.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(line_chart(
                trend_df, ["Revenue", "Gross Profit", "Operating Income", "Net Income"],
                "Income Statement ($B)", "$ Billion"
            ), use_container_width=True)
        with col2:
            if "Revenue Growth %" in trend_df.columns:
                vals = trend_df["Revenue Growth %"].dropna()
                colors = ["#2ecc71" if v >= 0 else "#e74c3c" for v in vals]
                fig2 = go.Figure(go.Bar(
                    x=vals.index, y=vals.round(1), marker_color=colors,
                    text=vals.round(1).astype(str) + "%", textposition="outside",
                ))
                fig2.update_layout(
                    title="Revenue Growth YoY (%)", yaxis_title="%", height=320,
                    margin=dict(l=0, r=0, t=40, b=0),
                    plot_bgcolor="white", paper_bgcolor="white", showlegend=False,
                )
                st.plotly_chart(fig2, use_container_width=True)

        col3, col4 = st.columns(2)
        with col3:
            st.plotly_chart(line_chart(trend_df, ["EBITDA"], "EBITDA ($B)", "$ Billion"),
                            use_container_width=True)
        with col4:
            if "Operating CF" in trend_df.columns:
                fig4 = go.Figure()
                for col, name in [("Operating CF", "Operating CF"),
                                   ("Free CF", "Free CF"), ("CapEx", "CapEx")]:
                    if col in trend_df.columns:
                        fig4.add_trace(go.Bar(
                            x=trend_df.index, y=(trend_df[col] / 1e9).round(2), name=name
                        ))
                fig4.update_layout(
                    title="Cash Flows ($B)", barmode="group", height=320,
                    margin=dict(l=0, r=0, t=40, b=0),
                    plot_bgcolor="white", paper_bgcolor="white",
                )
                st.plotly_chart(fig4, use_container_width=True)

# ── Tab 2 ─────────────────────────────────────────────────────────────────────
with tab2:
    if trend_df.empty:
        st.info("No financial statement data available.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(line_chart(
                trend_df, ["Gross Margin %", "Operating Margin %", "Net Margin %"],
                "Profit Margins", "Percent (%)", scale=1
            ), use_container_width=True)
        with col2:
            st.plotly_chart(line_chart(
                trend_df, ["ROE %", "ROA %"], "Return Ratios", "Percent (%)", scale=1
            ), use_container_width=True)

        if "Debt/Equity" in trend_df.columns:
            fig3 = go.Figure(go.Scatter(
                x=trend_df.index, y=trend_df["Debt/Equity"].round(2),
                mode="lines+markers",
                line=dict(color="#e74c3c", width=2.5),
                fill="tozeroy", fillcolor="rgba(231,76,60,0.1)",
            ))
            fig3.update_layout(
                title="Debt / Equity Ratio", yaxis_title="x", height=280,
                margin=dict(l=0, r=0, t=40, b=0),
                plot_bgcolor="white", paper_bgcolor="white",
            )
            st.plotly_chart(fig3, use_container_width=True)

# ── Tab 3 ─────────────────────────────────────────────────────────────────────
with tab3:
    if history is None or history.empty:
        st.info("No historical price data available.")
    else:
        period_opt = st.radio("Time Period", ["1Y", "2Y", "5Y"], horizontal=True, index=2)
        n_days = {"1Y": 252, "2Y": 504, "5Y": 1260}[period_opt]
        h = history.tail(n_days)

        fig = go.Figure(go.Candlestick(
            x=h.index, open=h["Open"], high=h["High"], low=h["Low"], close=h["Close"],
            increasing_line_color="#2ecc71", decreasing_line_color="#e74c3c",
        ))
        fig.update_layout(
            title=f"{ticker} Stock Price ({period_opt})", yaxis_title="Price (USD)",
            height=400, margin=dict(l=0, r=0, t=40, b=0),
            plot_bgcolor="white", paper_bgcolor="white",
            xaxis_rangeslider_visible=False,
        )
        st.plotly_chart(fig, use_container_width=True)

        cum_ret = (h["Close"] / h["Close"].iloc[0] - 1) * 100
        fig2 = go.Figure(go.Scatter(
            x=h.index, y=cum_ret.round(2), mode="lines",
            line=dict(color="#3498db", width=2),
            fill="tozeroy", fillcolor="rgba(52,152,219,0.1)",
        ))
        fig2.add_hline(y=0, line_dash="dash", line_color="#999")
        fig2.update_layout(
            title="Cumulative Return", yaxis_title="%", height=260,
            margin=dict(l=0, r=0, t=40, b=0),
            plot_bgcolor="white", paper_bgcolor="white",
        )
        st.plotly_chart(fig2, use_container_width=True)

        c1, c2, c3, c4 = st.columns(4)
        vol_30d = h["Close"].pct_change().rolling(30).std().iloc[-1] * np.sqrt(252) * 100
        c1.metric("Current Price",     f"${h['Close'].iloc[-1]:.2f}")
        c2.metric(f"{period_opt} High", f"${h['High'].max():.2f}")
        c3.metric(f"{period_opt} Low",  f"${h['Low'].min():.2f}")
        c4.metric("30-Day Ann. Vol",    f"{vol_30d:.1f}%" if not np.isnan(vol_30d) else "N/A")

# ── Tab 4 ─────────────────────────────────────────────────────────────────────
with tab4:
    if trend_df.empty:
        st.info("No balance sheet data available.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(line_chart(
                trend_df, ["Total Assets", "Equity", "Total Debt"],
                "Balance Sheet ($B)", "$ Billion"
            ), use_container_width=True)
        with col2:
            if all(c in trend_df.columns for c in ["Equity", "Total Debt", "Total Assets"]):
                fig2 = go.Figure()
                other = (trend_df["Total Assets"] - trend_df["Equity"] - trend_df["Total Debt"]).clip(lower=0)
                for vals, name, color in [
                    (trend_df["Equity"] / 1e9,   "Equity",           "#2ecc71"),
                    (trend_df["Total Debt"] / 1e9,"Total Debt",       "#e74c3c"),
                    (other / 1e9,                 "Other Liabilities","#f39c12"),
                ]:
                    fig2.add_trace(go.Bar(x=trend_df.index, y=vals.round(2),
                                         name=name, marker_color=color))
                fig2.update_layout(
                    title="Capital Structure ($B)", barmode="stack", height=320,
                    margin=dict(l=0, r=0, t=40, b=0),
                    plot_bgcolor="white", paper_bgcolor="white",
                )
                st.plotly_chart(fig2, use_container_width=True)
