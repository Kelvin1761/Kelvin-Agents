from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from tennis_wc.props.strategy import (
    LIVE_INTERIM_CHECK_SETTLED,
    LIVE_INTERIM_MIN_ROI,
    LIVE_REVIEW_AFTER_SETTLED,
    LIVE_STOP_DRAWDOWN_UNITS,
    live_stop_state,
)


def test_stop_rule_constants_are_the_pre_registered_numbers():
    assert LIVE_STOP_DRAWDOWN_UNITS == -20.0
    assert LIVE_REVIEW_AFTER_SETTLED == 200
    assert LIVE_INTERIM_CHECK_SETTLED == 100
    assert LIVE_INTERIM_MIN_ROI == -0.10


@pytest.mark.parametrize(
    ("settled", "drawdown", "roi", "action", "review_due"),
    [
        (99, -19.99, -0.50, "CONTINUE", False),
        (100, -19.99, -0.10, "CONTINUE", False),
        (100, -19.99, -0.1001, "PAUSE", False),
        (200, -19.99, 0.01, "CONTINUE", True),
        (100, -20.0, -0.50, "STOP", False),
    ],
)
def test_stop_rule_boundaries(settled, drawdown, roi, action, review_due):
    state = live_stop_state(settled, -1.0, drawdown, roi)

    assert state["action"] == action
    assert state["review_due"] is review_due
    assert state["bets_until_review"] == max(0, 200 - settled)


def test_stop_rule_script_uses_actual_recorded_stake_and_odds():
    script = Path(__file__).resolve().parents[1] / "scripts" / "check_stop_rule.py"
    spec = importlib.util.spec_from_file_location("check_stop_rule", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module._profit_for_live_bet(
        {"stake_units": 0.5, "odds_taken": 2.4, "result_status": "WON"}
    ) == pytest.approx(0.7)
    assert module._profit_for_live_bet(
        {"stake_units": 0.5, "odds_taken": 1.9, "result_status": "LOST"}
    ) == pytest.approx(-0.5)
    with pytest.raises(ValueError):
        module._profit_for_live_bet(
            {"stake_units": 0.0, "odds_taken": 1.9, "result_status": "WON"}
        )
    assert module._phase4_verdict(
        {"action": "CONTINUE", "review_due": False}
    ) == "CONTINUE_ACCUMULATING"
    assert module._phase4_verdict(
        {"action": "CONTINUE", "review_due": True}
    ) == "REVIEW_REQUIRED"
    assert module._phase4_verdict(
        {"action": "PAUSE", "review_due": True}
    ) == "PAUSE_AND_AUDIT"
    assert module._phase4_verdict(
        {"action": "STOP", "review_due": True}
    ) == "STOP"


def test_stop_rule_script_accounts_for_source_join_and_allowlist_rows(tmp_path):
    db = tmp_path / "stop-rule.db"
    with sqlite3.connect(db) as conn:
        conn.executescript(
            """
            CREATE TABLE prop_tracker (
                id INTEGER PRIMARY KEY,
                match_id INTEGER,
                match_date TEXT,
                market_key TEXT,
                stake_units REAL,
                profit_loss_units REAL,
                result_status TEXT,
                is_value INTEGER,
                side TEXT,
                feed_market_key TEXT,
                feed_market_name TEXT
            );
            CREATE TABLE matches (
                id INTEGER PRIMARY KEY, tournament_id INTEGER,
                source_provider TEXT
            );
            CREATE TABLE tournaments (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE tournament_levels (
                id INTEGER PRIMARY KEY, tournament_id INTEGER,
                level TEXT, surface TEXT
            );
            CREATE TABLE clv_tracker (
                source_id INTEGER, recommendation_type TEXT, clv REAL
            );
            CREATE TABLE prop_live_bets (
                prop_id INTEGER, stake_units REAL, odds_taken REAL
            );
            INSERT INTO tournaments VALUES (10, 'ATP Test');
            INSERT INTO tournament_levels VALUES (1, 10, 'ATP_250', 'hard');
            INSERT INTO matches VALUES (1, 10, 'sportsbet');
            INSERT INTO matches VALUES (2, 10, 'sportsbet');
            INSERT INTO prop_tracker VALUES
                (1, 1, '2026-08-12', 'player_win_a_set_7', 1.0, 1.4,
                 'WON', 1, 'over', 'winner_related', 'To Win a Set'),
                (2, 2, '2026-08-12', 'player_game_handicap_8', 1.0, -1.0,
                 'LOST', 1, 'player_b', 'game_handicap', 'Game Handicap'),
                (3, 999, '2026-08-12', 'first_set_winner_9', 1.0, 0.8,
                 'WON', 1, 'player_a', 'winner_related', 'Set 1 Winner'),
                (4, 1, '2026-08-12', 'first_set_winner_10', 1.0, 0.9,
                 'WON', 1, 'player_a', 'winner_related', 'Set 1 Winner');
            INSERT INTO clv_tracker VALUES
                (1, 'PROP_RECOMMENDATION', 0.04),
                (2, 'PROP_RECOMMENDATION', -0.02);
            INSERT INTO prop_live_bets VALUES
                (1, 0.5, 1.92),
                (2, 0.5, 2.00),
                (3, 0.5, 2.20);
            """
        )

    script = Path(__file__).resolve().parents[1] / "scripts" / "check_stop_rule.py"
    result = subprocess.run(
        [sys.executable, str(script), "--db", str(db),
         "--since", "2026-08-12", "--json"],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["row_accounting"] == {
        "settled_value_recommendations": 4,
        "recorded_live_bets": 3,
        "settled_live_bets_with_context": 2,
        "allowlisted_live_rows": 1,
        "pending_live_bets": 0,
        "settled_without_match_context": 1,
        "excluded_by_family": {"player_game_handicap": 1},
    }
    assert payload["state"]["settled"] == 1
    assert payload["state"]["pnl_units"] == pytest.approx(0.46)
    assert payload["verdict"] == "CONTINUE_ACCUMULATING"
    assert payload["clv"] == {"captured": 1, "missing": 0, "average": 0.04}
    assert payload["breakdown"]["side"]["over"]["settled"] == 1
    assert payload["breakdown"]["pricing_path"]["To Win a Set"]["clv"][
        "captured"
    ] == 1
