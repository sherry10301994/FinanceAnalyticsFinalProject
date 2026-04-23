"""FinSight — entry point and navigation router"""

import streamlit as st

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
