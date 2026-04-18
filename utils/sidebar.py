"""
Shared sidebar component for all FinSight pages.
Handles WRDS login, ticker input, and peer input.
"""

import streamlit as st
from utils.data_fetcher import invalidate_cache


def render_sidebar(default_ticker: str = "AAPL",
                   default_peers: list | None = None) -> tuple[str, list]:
    """
    Render the shared sidebar.  Returns (ticker, peers).
    Also manages WRDS connection in st.session_state["wrds_conn"].
    """
    if default_peers is None:
        default_peers = ["MSFT", "GOOGL", "META"]

    with st.sidebar:
        st.title("📊 FinSight")
        st.caption("Financial Analytics for Interview Prep")

        # ── WRDS Connection ──────────────────────────────────────────────────
        st.divider()
        st.markdown("**🔗 Data Source**")

        conn = st.session_state.get("wrds_conn")

        if conn:
            source_label = "🟢 WRDS connected"
        else:
            source_label = "🔴 Not connected — use WRDS Login below"
        st.caption(source_label)

        # ── WRDS Connection ──────────────────────────────────────────────────
        with st.expander("WRDS Login (optional)", expanded=False):
            wrds_user = st.text_input(
                "WRDS Username",
                value=st.session_state.get("wrds_username", ""),
                placeholder="your_bu_username",
                key="wrds_user_input",
            )
            wrds_pass = st.text_input(
                "WRDS Password",
                type="password",
                placeholder="••••••••",
                key="wrds_pass_input",
            )
            col1, col2 = st.columns(2)
            if col1.button("Connect", use_container_width=True):
                if wrds_user and wrds_pass:
                    _connect_wrds(wrds_user, wrds_pass)
                else:
                    st.warning("Enter username and password.")
            if col2.button("Disconnect", use_container_width=True):
                st.session_state.pop("wrds_conn", None)
                invalidate_cache()
                st.rerun()

        # ── News & AI API Keys ───────────────────────────────────────────────
        with st.expander("News & AI Keys", expanded=False):
            fh_input = st.text_input(
                "Finnhub API Key",
                value=st.session_state.get("finnhub_key", ""),
                type="password",
                placeholder="your Finnhub key",
                key="finnhub_key_input",
            )
            oai_input = st.text_input(
                "Anthropic API Key",
                value=st.session_state.get("openai_key", ""),
                type="password",
                placeholder="sk-ant-...",
                key="openai_key_input",
            )
            if st.button("Save Keys", use_container_width=True):
                if fh_input.strip():
                    st.session_state["finnhub_key"] = fh_input.strip()
                if oai_input.strip():
                    st.session_state["openai_key"] = oai_input.strip()
                st.success("Keys saved!")
                st.rerun()
            st.caption("Finnhub: finnhub.io · Anthropic: console.anthropic.com")

        # ── Ticker & Peers ───────────────────────────────────────────────────
        st.divider()
        ticker_input = st.text_input(
            "Ticker Symbol",
            value=st.session_state.get("ticker", default_ticker),
            placeholder="e.g. AAPL, MSFT, TSLA",
        ).upper().strip()

        peers_raw = st.text_area(
            "Peer Tickers (one per line)",
            value="\n".join(st.session_state.get("peers", default_peers)),
            height=100,
        )

        if st.button("🔍 Analyze", type="primary", use_container_width=True):
            new_peers = [p.strip().upper() for p in peers_raw.splitlines() if p.strip()]
            ticker_changed = ticker_input != st.session_state.get("ticker")
            if ticker_changed:
                invalidate_cache(ticker_input)
                finnhub_key = st.session_state.get("finnhub_key", "")
                if finnhub_key:
                    from utils.finnhub_news import get_peer_tickers
                    auto_peers = get_peer_tickers(ticker_input, finnhub_key)
                    st.session_state["peers"] = auto_peers if auto_peers else []
                else:
                    st.session_state["peers"] = []
            else:
                st.session_state["peers"] = new_peers
            st.session_state["ticker"] = ticker_input
            st.rerun()

        # Set defaults on first run
        if "ticker" not in st.session_state:
            st.session_state["ticker"] = ticker_input
        if "peers" not in st.session_state:
            st.session_state["peers"] = [
                p.strip().upper() for p in peers_raw.splitlines() if p.strip()
            ]

        st.divider()
        st.caption("Source: WRDS/Compustat + CRSP")
        st.caption("SEC EDGAR always used for filings")

    return (
        st.session_state.get("ticker", default_ticker),
        st.session_state.get("peers", default_peers),
    )


def _connect_wrds(username: str, password: str):
    """Attempt WRDS connection and store in session_state."""
    try:
        import wrds
        import os, tempfile

        # Write pgpass so wrds package doesn't prompt interactively
        pgpass_path = os.path.expanduser("~/.pgpass")
        pgpass_entry = f"wrds-pgdata.wharton.upenn.edu:9737:*:{username}:{password}\n"
        existing = ""
        if os.path.exists(pgpass_path):
            with open(pgpass_path, "r") as f:
                existing = f.read()
        if username not in existing:
            with open(pgpass_path, "a") as f:
                f.write(pgpass_entry)
            os.chmod(pgpass_path, 0o600)

        conn = wrds.Connection(wrds_username=username)
        st.session_state["wrds_conn"]      = conn
        st.session_state["wrds_username"]  = username
        invalidate_cache()
        st.success("✅ Connected to WRDS!")
        st.rerun()
    except Exception as e:
        st.error(f"Connection failed: {e}")
