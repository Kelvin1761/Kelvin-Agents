"""Offline measurements must not borrow forecasts or labels from the future."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sqlite3

import pytest

from tennis_wc.evaluation.match_corpus import earliest_match_odds, prematch_outcomes


@pytest.fixture
def conn():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE matches (id INTEGER PRIMARY KEY, match_date TEXT,
            start_time_utc TEXT, player_a_id INTEGER, player_b_id INTEGER,
            tour TEXT, tournament_id INTEGER, round TEXT);
        CREATE TABLE predictions (id INTEGER PRIMARY KEY, match_id INTEGER,
            selection_player_id INTEGER, model_probability REAL,
            created_at TEXT, pricing_json TEXT);
        CREATE TABLE match_results (id INTEGER PRIMARY KEY, match_id INTEGER,
            winner_player_id INTEGER, score_json TEXT, created_at TEXT);
        CREATE TABLE odds_snapshots (id INTEGER PRIMARY KEY, match_id INTEGER,
            player_a_odds REAL, player_b_odds REAL, fetched_at TEXT);
        INSERT INTO matches VALUES (1,'2026-06-01','2026-06-01T12:00:00Z',
                                    10,20,'ATP',1,'R1');
        INSERT INTO predictions VALUES
            (1,1,10,0.6,'2026-06-01T09:00:00Z','{}'),
            (2,1,20,0.9,'2026-06-01T13:00:00Z','{}');
        INSERT INTO match_results VALUES
            (1,1,10,'{"player_a_games":12,"player_b_games":4}',
             '2026-06-01T15:00:00Z');
        INSERT INTO odds_snapshots VALUES
            (1,1,1.8,2.1,'2026-06-01T08:00:00Z'),
            (2,1,1.1,8.0,'2026-06-01T13:00:00Z');
    """)
    yield db
    db.close()


def _script(name):
    path = Path(__file__).resolve().parents[1] / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rebuild_cannot_replace_the_recorded_forecast(conn):
    row, = prematch_outcomes(conn)
    assert row["prediction_id"] == 1
    assert row["model_p"] == 0.6
    conn.execute("UPDATE predictions SET selection_player_id=20 WHERE id=1")
    assert prematch_outcomes(conn)[0]["model_p"] == pytest.approx(0.4)


@pytest.mark.parametrize("stamp", [None, "", "unknown", "2026-06-01T08:00:00Z"])
def test_unverifiable_or_post_start_forecasts_are_not_evidence(conn, stamp):
    conn.execute("UPDATE matches SET start_time_utc=?", (stamp,))
    assert prematch_outcomes(conn) == []


def test_multiple_result_sources_are_one_sample_and_conflicts_are_excluded(conn):
    conn.execute("INSERT INTO match_results SELECT 2,match_id,winner_player_id,"
                 "score_json,created_at FROM match_results WHERE id=1")
    assert len(prematch_outcomes(conn)) == 1
    conn.execute("UPDATE match_results SET winner_player_id=20 WHERE id=2")
    assert prematch_outcomes(conn) == []


def test_calibration_cutoff_is_when_the_label_arrived(conn, monkeypatch):
    from tennis_wc.modelling import probability_calibration

    seen = []
    monkeypatch.setattr(probability_calibration, "fit",
                        lambda samples: seen.extend(samples) or probability_calibration.IDENTITY)
    conn.execute("UPDATE match_results SET created_at='2026-07-01T00:00:00Z'")
    probability_calibration.fit_as_of(conn, "2026-06-02")
    assert seen == []
    probability_calibration.fit_as_of(conn, "2026-07-02")
    assert seen == [(0.6, 1.0)]


def test_first_odds_are_one_pair_and_must_be_pre_start(conn):
    assert earliest_match_odds(conn)[1]["player_a_odds"] == 1.8
    assert earliest_match_odds(conn)[1]["player_b_odds"] == 2.1
    conn.execute("UPDATE odds_snapshots SET fetched_at='2026-06-01T12:00:00Z' WHERE id=1")
    assert earliest_match_odds(conn) == {}


def test_margin_fit_is_deduplicated_and_cannot_use_a_post_start_rebuild(conn):
    holdout = _script("holdout_validation")
    conn.execute("INSERT INTO match_results SELECT 2,match_id,winner_player_id,"
                 "score_json,created_at FROM match_results WHERE id=1")
    assert holdout._margin_rows(conn) == [(0.6, 8.0)]
    conn.execute("UPDATE match_results SET score_json="
                 "'{\"player_a_games\":12,\"player_b_games\":8}' WHERE id=2")
    assert holdout._margin_rows(conn) == []


@pytest.mark.parametrize("payload", [{"retired": True}, {"walkover": True},
                                     {"player_a_sets": 1, "player_b_sets": 1}, []])
def test_non_completed_results_cannot_validate_a_model(conn, payload):
    conn.execute("UPDATE match_results SET score_json=?", (json.dumps(payload),))
    assert prematch_outcomes(conn) == []


def test_elo_baseline_uses_the_actual_forecasts_backbone():
    measure = _script("measure_match_model")
    payload = {"pricing": {"model": {"elo_base_logit": 1.0, "components": [
        {"name": "overall_elo_edge", "active": True}]}}}
    assert measure._recorded_elo_probability(json.dumps(payload)) == pytest.approx(0.73105858)
    assert measure._recorded_elo_probability("{}") is None
    assert measure._auc([(0.5, 1), (0.5, 0)]) == 0.5
    assert measure._auc([(0.8, 1), (0.2, 0)]) == 1.0


def test_warehouse_audit_runs_on_a_query_only_connection(tmp_path, monkeypatch):
    from conftest import configure_test_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.database.migrations import init_db

    configure_test_db(tmp_path, monkeypatch)
    init_db()
    with get_connection() as db:
        db.execute("PRAGMA query_only=ON")
        result = _script("audit_model_data").audit(db)
        assert result["status"] == "checks_passed"
        assert result["live_prop_bets"] == [{"n": 0}]
        assert db.execute("PRAGMA query_only").fetchone()[0] == 1
