from __future__ import annotations

import sqlite3

import pytest


def test_broken_integrity_query_cannot_report_a_healthy_empty_warehouse():
    from tennis_wc.validation import checks

    with sqlite3.connect(":memory:") as conn:
        with pytest.raises(sqlite3.OperationalError):
            checks.run_checks(conn)


def test_integrity_check_exception_blocks_instead_of_silent_pass(monkeypatch):
    from tennis_wc.database import db
    from tennis_wc.reports import daily_report

    def unavailable():
        raise sqlite3.OperationalError("database unavailable")

    monkeypatch.setattr(db, "get_connection", unavailable)
    warnings = daily_report._integrity_warnings()
    assert warnings and "無法完成" in warnings[0]
    lines = daily_report._recommended_bets_lines(
        {"validated_singles": [{"strategy_tier": "EARLY_MAIN_SINGLE"}]}, []
    )
    assert "正式注單 0 注" in "\n".join(lines)
    assert not any(line.startswith("### 注 ") for line in lines)


def test_critical_failure_suppresses_even_family_qualified_bets(monkeypatch):
    from tennis_wc.reports import daily_report

    prop = {
        "strategy": {"enabled_families": ["player_aces"]},
        "value_legs": [{"id": "research", "market_key": "player_aces"}],
    }
    monkeypatch.setattr(
        daily_report, "_integrity_warnings", lambda: ["⚠️ PIT integrity failed"]
    )
    picks = {
        "validated_singles": [{"strategy_tier": "VALIDATED_SINGLE"}],
        "validated_two_leg": {"legs": [{}, {}]},
    }
    text = "\n".join(daily_report._recommended_bets_lines(picks, [], prop))
    assert "PIT integrity failed" in text and "正式注單 0 注" in text
    assert "VALIDATED_SINGLE" not in text and "### 注 " not in text
    assert prop["value_legs"][0]["id"] == "research"
    assert picks["validated_singles"][0]["strategy_tier"] == "VALIDATED_SINGLE"


def test_healthy_integrity_keeps_existing_no_bet_message(monkeypatch):
    from tennis_wc.reports import daily_report

    monkeypatch.setattr(daily_report, "_integrity_warnings", lambda: [])
    text = "\n".join(daily_report._recommended_bets_lines({}, []))
    assert "今日無清晰好注" in text
    assert "資料完整性未通過" not in text
