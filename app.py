"""FinSight — entry point and navigation router"""

import streamlit as st

# ── Global styles ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Sidebar dark theme ─────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0d1b2a 0%, #1b2d45 100%);
    border-right: 1px solid #1e3a5f;
}
/* Hide Streamlit's auto-generated app logo / favicon header entirely */
[data-testid="stSidebarHeader"] { display: none !important; }

/* Sidebar base text */
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] label { color: #cbd5e1 !important; }
[data-testid="stSidebar"] .stMarkdown { color: #cbd5e1 !important; }

/* Nav section headings */
[data-testid="stSidebarNavSeparator"] p {
    color: #475569 !important;
    font-size: 0.68rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.1em !important;
    text-transform: uppercase !important;
}

/* Nav links */
[data-testid="stSidebarNavLink"] {
    border-radius: 6px !important;
    margin: 1px 6px !important;
    padding: 7px 12px !important;
    color: #94a3b8 !important;
    transition: background 0.15s, color 0.15s !important;
}
[data-testid="stSidebarNavLink"]:hover {
    background: rgba(255,255,255,0.06) !important;
    color: #e2e8f0 !important;
}
[data-testid="stSidebarNavLink"][aria-selected="true"] {
    background: rgba(59,130,246,0.15) !important;
    border-left: 3px solid #3b82f6 !important;
    color: #93c5fd !important;
    font-weight: 600 !important;
}

/* Sidebar — inputs (use section tag for higher specificity) */
section[data-testid="stSidebar"] div[data-baseweb="input"],
section[data-testid="stSidebar"] div[data-baseweb="base-input"],
section[data-testid="stSidebar"] div[data-baseweb="textarea"] {
    background-color: #162538 !important;
    border-color: #3a5a80 !important;
    border-radius: 6px !important;
}
section[data-testid="stSidebar"] input,
section[data-testid="stSidebar"] textarea {
    background-color: transparent !important;
    color: #f1f5f9 !important;
    caret-color: #f1f5f9 !important;
}
section[data-testid="stSidebar"] input::placeholder,
section[data-testid="stSidebar"] textarea::placeholder { color: #64748b !important; }

/* Sidebar selectbox */
section[data-testid="stSidebar"] div[data-baseweb="select"] > div:first-child {
    background-color: #162538 !important;
    border-color: #3a5a80 !important;
    border-radius: 6px !important;
}

/* Expander — collapsed and open */
[data-testid="stSidebar"] [data-testid="stExpander"] {
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid #2d4a6a !important;
    border-radius: 8px !important;
}
[data-testid="stSidebar"] [data-testid="stExpander"] summary {
    background: transparent !important;
}
[data-testid="stSidebar"] [data-testid="stExpander"] summary p,
[data-testid="stSidebar"] [data-testid="stExpander"] summary span,
[data-testid="stSidebar"] details summary p {
    color: #e2e8f0 !important;
    font-weight: 500 !important;
}

/* Input labels */
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
[data-testid="stSidebar"] label p {
    color: #e2e8f0 !important;
    font-weight: 500 !important;
}

/* Sidebar buttons */
[data-testid="stSidebar"] .stButton > button {
    background: rgba(59,130,246,0.15) !important;
    border: 1px solid #3b82f680 !important;
    color: #93c5fd !important;
    border-radius: 6px !important;
    font-weight: 500 !important;
    width: 100% !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(59,130,246,0.28) !important;
    color: #bfdbfe !important;
}

/* Success/error/warning in sidebar */
[data-testid="stSidebar"] [data-testid="stAlert"] {
    background: rgba(255,255,255,0.05) !important;
    border-radius: 6px !important;
}

/* ── Main content area ──────────────────────────────────────────────────── */
.main .block-container {
    padding-top: 1.8rem;
    max-width: 1200px;
}

/* Page title */
h1 {
    color: #0f172a !important;
    font-weight: 700 !important;
    font-size: 1.75rem !important;
    letter-spacing: -0.02em;
}
h2 { color: #1e293b !important; font-weight: 600 !important; font-size: 1.2rem !important; }
h3 { color: #334155 !important; font-weight: 600 !important; font-size: 1rem !important; }

/* Divider */
hr { border: none; border-top: 1px solid #e2e8f0; margin: 1.25rem 0; }

/* ── Metric cards ────────────────────────────────────────────────────────── */
[data-testid="stMetric"] {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 1rem 1.2rem !important;
    box-shadow: 0 1px 4px rgba(15,23,42,0.05);
}
[data-testid="stMetricLabel"] > div {
    color: #64748b !important;
    font-size: 0.72rem !important;
    font-weight: 600 !important;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}
[data-testid="stMetricValue"] {
    color: #0f172a !important;
    font-size: 1.45rem !important;
    font-weight: 700 !important;
    letter-spacing: -0.01em;
}
[data-testid="stMetricDelta"] { font-size: 0.82rem !important; }

/* ── Tabs ────────────────────────────────────────────────────────────────── */
[data-testid="stTabs"] [role="tablist"] {
    border-bottom: 2px solid #e2e8f0;
    gap: 0.25rem;
}
[data-testid="stTabs"] [role="tab"] {
    color: #64748b !important;
    font-weight: 500 !important;
    font-size: 0.88rem !important;
    padding: 8px 16px !important;
    border-radius: 6px 6px 0 0 !important;
    border: none !important;
    background: transparent !important;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
    color: #1e3a5f !important;
    font-weight: 600 !important;
    border-bottom: 2px solid #1e3a5f !important;
    background: transparent !important;
}
[data-testid="stTabs"] [role="tab"]:hover { background: #f1f5f9 !important; }

/* ── Primary buttons ─────────────────────────────────────────────────────── */
.stButton > button[kind="primary"],
button[kind="primary"] {
    background: #1e3a5f !important;
    color: white !important;
    border: none !important;
    border-radius: 7px !important;
    font-weight: 600 !important;
    letter-spacing: 0.01em;
    transition: background 0.2s !important;
}
.stButton > button[kind="primary"]:hover { background: #2563eb !important; }

/* ── Expanders ────────────────────────────────────────────────────────────── */
[data-testid="stExpander"] {
    border: 1px solid #e2e8f0 !important;
    border-radius: 8px !important;
    overflow: hidden;
}
[data-testid="stExpander"] summary {
    background: #f8fafc !important;
    font-weight: 500 !important;
    color: #334155 !important;
}

/* ── Dataframes ────────────────────────────────────────────────────────────── */
[data-testid="stDataFrame"] { border-radius: 8px; overflow: hidden; }

/* ── Alert/info boxes ──────────────────────────────────────────────────────── */
[data-testid="stAlert"] { border-radius: 8px !important; }

/* ── Plotly chart border ────────────────────────────────────────────────────── */
[data-testid="stPlotlyChart"] {
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    overflow: hidden;
    padding: 4px;
}
</style>
""", unsafe_allow_html=True)

pg = st.navigation(
    {
        "FinSight": [
            st.Page("pages/0_Overview.py", title="Overview"),
        ],
        "Analysis": [
            st.Page("pages/1_KPI_Dashboard.py",    title="KPI Dashboard"),
            st.Page("pages/2_Trend_Analysis.py",   title="Trend Analysis"),
            st.Page("pages/3_Peer_Benchmarking.py", title="Peer Benchmarking"),
            st.Page("pages/4_Risk_Analysis.py",    title="Risk Analysis"),
            st.Page("pages/5_News_Filings.py",     title="News & Filings"),
        ],
    }
)
pg.run()
