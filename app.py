"""FinSight — entry point and navigation router"""

import streamlit as st

pg = st.navigation(
    {
        "FinSight": [
            st.Page("pages/0_Overview.py", title="Overview", icon="🏠"),
        ],
        "Analysis": [
            st.Page("pages/1_📊_KPI_Dashboard.py",    title="KPI Dashboard"),
            st.Page("pages/2_📈_Trend_Analysis.py",   title="Trend Analysis"),
            st.Page("pages/3_🏢_Peer_Benchmarking.py", title="Peer Benchmarking"),
            st.Page("pages/4_⚠️_Risk_Analysis.py",    title="Risk Analysis"),
            st.Page("pages/5_📰_News_Filings.py",     title="News & Filings"),
        ],
    }
)
pg.run()
