"""A BO3 prop distribution cannot price a men's Slam main-draw match."""
from __future__ import annotations

import pytest

from tennis_wc.features.bo_format import detect_match_format


@pytest.mark.parametrize("round_name", ["Qualifying", "Q1", "Q2", "Q3", "QR1"])
def test_slam_qualifying_is_best_of_three(round_name):
    assert detect_match_format({"tour": "ATP", "level": "GRAND_SLAM", "round": round_name}) == "BO3"


def test_slam_main_draw_and_wta_have_distinct_formats():
    assert detect_match_format({"tour": "ATP", "level": "GRAND_SLAM", "round": "R128"}) == "BO5"
    assert detect_match_format({"tour": "WTA", "level": "GRAND_SLAM", "round": "F"}) == "BO3"


def test_bo5_is_reported_and_never_priced_or_logged(tmp_path, monkeypatch):
    from conftest import configure_test_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.database.migrations import init_db
    from tennis_wc.props import daily
    from tennis_wc.reports.daily_report import _reference_prop_board_lines

    configure_test_db(tmp_path, monkeypatch)
    init_db()
    for pid in (1, 2):
        with get_connection() as conn:
            conn.execute("INSERT INTO players (id,name,tour,source_provider,created_at,updated_at) "
                         "VALUES (?,?,'ATP','test','now','now')", (pid, f"P{pid}"))
    with get_connection() as conn:
        conn.execute("INSERT INTO matches (id,provider_match_id,tour,match_date,tournament_id,"
                     "player_a_id,player_b_id,round,source_provider,created_at,updated_at) "
                     "VALUES (1,'M','ATP','2026-09-01',1,1,2,'R128','test','now','now')")
        conn.execute("INSERT INTO tournament_levels (tournament_id,tour,level,source_provider,"
                     "raw_response_id,created_at,updated_at) VALUES (1,'ATP','GRAND_SLAM','test',0,'now','now')")
        conn.commit()
        monkeypatch.setattr(daily, "_rows_for_date", lambda *a, **k: [
            {"match_id": 1, "market_key": "set_handicap", "market_name": "Set Handicap",
             "selection_name": "P1 -2.5", "line": -2.5, "odds": 1.9, "id": 1}])
        monkeypatch.setattr(daily, "_match_prob_map", lambda *a: {1: 0.9})
        monkeypatch.setattr(daily, "_set_joint_probabilities", lambda *a: pytest.fail("BO3 pricing reached"))
        boards = daily.price_ace_props_for_date(conn, "2026-09-01", log=True)
        assert len(boards) == 1
        assert boards[0].unsupported_reason == "unsupported_match_format_BO5"
        assert boards[0].set_handicap == []
        assert conn.execute("SELECT COUNT(*) FROM prop_tracker").fetchone()[0] == 0
        assert "五盤三勝" in "\n".join(_reference_prop_board_lines({"boards": boards}))


def test_integrity_check_failure_remains_visible(monkeypatch):
    from tennis_wc.reports.daily_report import _integrity_warnings
    from tennis_wc.database import db
    from tennis_wc.validation import checks
    from contextlib import nullcontext

    def unavailable(*args, **kwargs):
        raise RuntimeError("unavailable")

    monkeypatch.setattr(checks, "run_checks", unavailable)
    monkeypatch.setattr(db, "get_connection", lambda: nullcontext(None))
    assert _integrity_warnings()
