"""Settled combination evidence must survive later recommendation refreshes."""
from __future__ import annotations

import sqlite3

import pytest

from tennis_wc.betting.ledger import _upsert_combo_tracker


def tracker():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE combo_tracker (
        id INTEGER PRIMARY KEY, combo_key TEXT UNIQUE, match_id INTEGER,
        match_date TEXT, match_label TEXT, tier TEXT, legs_json TEXT,
        combo_odds REAL, adjusted_confidence INTEGER, adjusted_edge REAL,
        stake_units REAL, result_status TEXT, profit_loss_units REAL,
        recorded_at TEXT, updated_at TEXT, settled_at TEXT)""")
    return conn


def combination():
    return {"legs": [{"id": "leg1", "match_id": 1, "selection_name": "A",
                      "market_key": "match_winner"}], "combo_odds": 2, "stake_units": 1}


@pytest.mark.parametrize("state,settled_at", [
    ("WON", "2026-01-02"), ("LOST", "2026-01-02"), ("VOID", "2026-01-02"),
    ("WON", None), ("PENDING", "2026-01-02"),
])
def test_refresh_cannot_mutate_settled_combo_evidence(state, settled_at):
    with tracker() as conn:
        combo = combination()
        assert _upsert_combo_tracker(conn, combo, "2026-01-01", "first") == 1
        conn.execute("UPDATE combo_tracker SET result_status=?,settled_at=?,profit_loss_units=1",
                     (state, settled_at))
        before = dict(conn.execute("SELECT * FROM combo_tracker").fetchone())
        changed = {**combo, "combo_odds": 3, "stake_units": 6, "tier": "new",
                   "legs": [{**combo["legs"][0], "selection_name": "B"}]}
        assert _upsert_combo_tracker(conn, changed, "2026-01-01", "later") == 0
        assert dict(conn.execute("SELECT * FROM combo_tracker").fetchone()) == before


def test_unsettled_combo_can_refresh_without_changing_original_recording_time():
    with tracker() as conn:
        combo = combination()
        _upsert_combo_tracker(conn, combo, "2026-01-01", "first")
        assert _upsert_combo_tracker(conn, {**combo, "combo_odds": 3, "stake_units": 2},
                                    "2026-01-01", "later") == 1
        row = conn.execute("SELECT * FROM combo_tracker").fetchone()
        assert row["combo_odds"] == 3 and row["stake_units"] == 2
        assert row["recorded_at"] == "first" and row["updated_at"] == "later"


def test_settlement_does_not_regrade_a_timestamped_record(monkeypatch):
    from contextlib import nullcontext
    from tennis_wc.betting import ledger

    with tracker() as conn:
        _upsert_combo_tracker(conn, combination(), "2026-01-01", "first")
        conn.execute("UPDATE combo_tracker SET settled_at='2026-01-02',profit_loss_units=1")
        before = dict(conn.execute("SELECT * FROM combo_tracker").fetchone())
        monkeypatch.setattr(ledger, "_ensure_tracking_schema", lambda: None)
        monkeypatch.setattr(ledger, "get_connection", lambda: nullcontext(conn))
        assert ledger.settle_combo_tracker_for_date("2026-01-01")["settled"] == 0
        assert dict(conn.execute("SELECT * FROM combo_tracker").fetchone()) == before
