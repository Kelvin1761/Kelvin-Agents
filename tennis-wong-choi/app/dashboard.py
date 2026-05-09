from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tennis_wc.database.db import get_connection
from tennis_wc.betting.ledger import ledger_summary
from tennis_wc.reports.performance_report import prediction_summary


st.set_page_config(page_title="Tennis Wong Choi", layout="wide")
st.title("Tennis Wong Choi")

db_url = os.getenv("DATABASE_URL", "sqlite:///tennis_wc.db")
st.caption(f"Database: {db_url}")

page = st.sidebar.radio(
    "Page",
    [
        "Daily Matches",
        "Recommended Bets",
        "Watchlist",
        "Data Quality",
        "Feature Provenance",
        "Bet Ledger",
        "CLV Report",
        "Backtest Report",
    ],
)


def load_predictions() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT p.*, m.match_date, m.round, t.name AS tournament_name, tl.level, tl.surface
            FROM predictions p
            JOIN matches m ON m.id = p.match_id
            JOIN tournaments t ON t.id = m.tournament_id
            JOIN tournament_levels tl ON tl.tournament_id = m.tournament_id AND tl.tour = m.tour
            WHERE p.id IN (SELECT MAX(id) FROM predictions GROUP BY match_id)
            ORDER BY m.match_date DESC, p.edge DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


rows = load_predictions()

if page == "Daily Matches":
    st.subheader("Daily Matches")
    st.dataframe(rows, use_container_width=True)

elif page == "Recommended Bets":
    st.subheader("Recommended Bets")
    st.dataframe([row for row in rows if row["decision"] == "BET"], use_container_width=True)

elif page == "Watchlist":
    st.subheader("Watchlist")
    st.dataframe([row for row in rows if row["decision"] == "WATCHLIST"], use_container_width=True)

elif page == "Data Quality":
    st.subheader("Data Quality")
    st.json(prediction_summary())

elif page == "Feature Provenance":
    st.subheader("Feature Provenance")
    selected = st.selectbox("Prediction", [row["id"] for row in rows]) if rows else None
    if selected:
        row = next(item for item in rows if item["id"] == selected)
        st.json(json.loads(row["pricing_json"]))

elif page == "Bet Ledger":
    st.subheader("Bet Ledger")
    with get_connection() as conn:
        ledger_rows = conn.execute("SELECT * FROM bet_ledger ORDER BY recorded_at DESC").fetchall()
    st.json(ledger_summary())
    st.dataframe([dict(row) for row in ledger_rows], use_container_width=True)

elif page == "CLV Report":
    st.subheader("CLV Report")
    with get_connection() as conn:
        clv_rows = conn.execute(
            "SELECT id, prediction_id, selection_name, odds_taken, closing_odds, clv, status FROM bet_ledger ORDER BY recorded_at DESC"
        ).fetchall()
    st.dataframe([dict(row) for row in clv_rows], use_container_width=True)

elif page == "Backtest Report":
    st.subheader("Backtest Report")
    with get_connection() as conn:
        runs = conn.execute("SELECT * FROM backtest_runs ORDER BY created_at DESC").fetchall()
    st.dataframe([dict(row) for row in runs], use_container_width=True)
