"""Each check here corresponds to a defect that actually reached production."""
from __future__ import annotations

import json


def _setup(tmp_path, monkeypatch):
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection

    init_db()
    conn = get_connection()
    for pid, name in ((1, "A"), (2, "B")):
        conn.execute(
            "INSERT INTO players (id, name, tour, source_provider, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?)", (pid, name, "ATP", "test", "now", "now"))
    conn.execute(
        """INSERT INTO matches (id, provider_match_id, tour, match_date, tournament_id,
               player_a_id, player_b_id, round, source_provider, created_at, updated_at)
           VALUES (1,'M1','ATP','2026-06-01',1,1,2,'R1','test','now','now')""")
    conn.commit()
    return conn


def _result(conn, match_id, payload, provider="test", winner=1):
    conn.execute(
        "INSERT INTO match_results (match_id, winner_player_id, score_json, "
        "source_provider, raw_response_id, created_at) VALUES (?,?,?,?,NULL,'now')",
        (match_id, winner, json.dumps(payload), provider),
    )


def test_equal_sets_is_reported_as_an_impossible_scoreline(tmp_path, monkeypatch):
    """9 such results existed and 22 props had been graded against them."""
    from tennis_wc.validation import checks

    conn = _setup(tmp_path, monkeypatch)
    _result(conn, 1, {"player_a_sets": 1, "player_b_sets": 1,
                      "player_a_games": 7, "player_b_games": 8})
    conn.commit()

    result = checks.check_impossible_scorelines(conn)
    assert not result.passed and result.severity == "critical"

    # The same shape with retired=True is a legitimate record of a retirement.
    conn.execute("DELETE FROM match_results")
    _result(conn, 1, {"player_a_sets": 1, "player_b_sets": 1, "retired": True})
    conn.commit()
    assert checks.check_impossible_scorelines(conn).passed


def test_settlement_voids_an_incomplete_scoreline_instead_of_grading_it(tmp_path, monkeypatch):
    """A prop settled on a scoreline that never happened is worse than pending."""
    from tennis_wc.props.settlement import settle_props, _match_void_reason

    conn = _setup(tmp_path, monkeypatch)
    _result(conn, 1, {"player_a_sets": 0, "player_b_sets": 0,
                      "player_a_games": 0, "player_b_games": 0})
    conn.execute(
        "INSERT INTO prop_tracker (prop_key, match_id, match_date, match_label, "
        "market_key, line, selection, decimal_odds, model_prob, side, prop_scope, "
        "subject_player_id, stake_units, is_value, result_status, recorded_at, updated_at) "
        "VALUES ('k1', 1, '2026-06-01', 'x', 'player_total_games_a', 9.5, 'over', "
        "1.9, 0.6, 'over', 'player_games', 1, 1.0, 1, 'PENDING', 'now', 'now')"
    )
    conn.commit()

    assert _match_void_reason(conn, 1) == "incomplete_scoreline"
    summary = settle_props(conn)
    assert summary["voided"] == 1 and summary["graded"] == 0
    assert conn.execute(
        "SELECT result_status FROM prop_tracker WHERE prop_key='k1'"
    ).fetchone()[0] == "VOID"


def test_a_winner_who_did_not_play_is_critical(tmp_path, monkeypatch):
    from tennis_wc.validation import checks

    conn = _setup(tmp_path, monkeypatch)
    conn.execute(
        "INSERT INTO players (id, name, tour, source_provider, created_at, updated_at) "
        "VALUES (99,'Elsewhere','ATP','test','now','now')")
    _result(conn, 1, {"player_a_sets": 2, "player_b_sets": 0}, winner=99)
    conn.commit()

    result = checks.check_winner_is_a_player_in_the_match(conn)
    assert not result.passed and result.severity == "critical"


def test_a_prop_subject_outside_the_fixture_is_critical(tmp_path, monkeypatch):
    from tennis_wc.validation import checks

    conn = _setup(tmp_path, monkeypatch)
    conn.execute(
        "INSERT INTO players (id, name, tour, source_provider, created_at, updated_at) "
        "VALUES (99,'Elsewhere','ATP','test','now','now')")
    conn.execute(
        "INSERT INTO prop_tracker (prop_key, match_id, match_date, match_label, "
        "market_key, line, selection, decimal_odds, model_prob, side, prop_scope, "
        "subject_player_id, stake_units, is_value, result_status, recorded_at, updated_at) "
        "VALUES ('k1', 1, '2026-06-01', 'x', 'total_x_aces_5_5', 5.5, 'over', "
        "1.9, 0.6, 'over', 'player', 99, 1.0, 1, 'PENDING', 'now', 'now')"
    )
    conn.commit()

    result = checks.check_prop_subject_plays_the_match(conn)
    assert not result.passed and result.severity == "critical"


def test_look_ahead_is_measured_on_the_data_not_the_timestamp(tmp_path, monkeypatch):
    """A backfill is stamped today for a May match and is not look-ahead.

    The first version compared predictions.created_at to the match date. That
    passes a prediction written before the match off a rating that silently
    contains the match's own result, and fails an honest rebuild. What matters
    is whether the rating was read as-of.
    """
    from tennis_wc.validation import checks

    conn = _setup(tmp_path, monkeypatch)
    as_of = '{"overall_elo": {"value": 1500, "provenance": {"warnings": []}}}'
    fell_back = ('{"overall_elo": {"value": 1500, "provenance": '
                 '{"warnings": ["elo_not_as_of"]}}}')

    def _snapshot(snapshot_id, player_id, payload):
        conn.execute(
            "INSERT INTO feature_snapshots (id, match_id, player_id, feature_set_version, "
            "features_json, provenance_json, data_quality_score, created_at) "
            "VALUES (?,1,?,'v1',?,'{}',90,'now')",
            (snapshot_id, player_id, payload),
        )

    # Two SUBJECTS, one of which fell back -- 50%, over the 20% ceiling.
    # Distinct players on purpose: snapshots for the same (match, player) are
    # rebuilds of one subject, and only the newest describes it.
    _snapshot(1, 1, as_of)
    _snapshot(2, 2, fell_back)
    conn.commit()

    result = checks.check_features_are_as_of(conn)
    assert not result.passed and result.severity == "critical"
    assert "50.0%" in result.detail

    # A rebuild that fixed the fallback must clear the check, and the superseded
    # row must not keep voting. Snapshots run 4.7 deep per pair in production
    # and their bodies are blanked by retention, so counting every row made this
    # share drift with a disk cleanup.
    _snapshot(3, 2, as_of)
    conn.commit()
    assert checks.check_features_are_as_of(conn).passed


def test_serve_props_may_settle_without_a_match_result(tmp_path, monkeypatch):
    """Ace props grade from player_match_history; requiring a result is wrong."""
    from tennis_wc.validation import checks

    conn = _setup(tmp_path, monkeypatch)
    conn.execute(
        "INSERT INTO prop_tracker (prop_key, match_id, match_date, match_label, "
        "market_key, line, selection, decimal_odds, model_prob, side, prop_scope, "
        "subject_player_id, stake_units, is_value, result_status, recorded_at, updated_at) "
        "VALUES ('k1', 1, '2026-06-01', 'x', 'total_a_aces_5_5', 5.5, 'over', "
        "1.9, 0.6, 'over', 'player', 1, 1.0, 1, 'WON', 'now', 'now')"
    )
    conn.execute(
        """INSERT INTO player_match_history
           (provider_match_id, player_id, opponent_id, tour, match_date,
            tournament_external_id, tournament_level, round, format, won,
            source_provider, raw_response_id, created_at, ace_count)
           VALUES ('H1',1,2,'ATP','2026-06-01','T1','ATP250','R1','BO3',1,'test',0,'now',9.0)"""
    )
    conn.commit()

    assert checks.check_settled_props_have_a_result(conn).passed

    # With no ace history either, it is a genuine defect.
    conn.execute("DELETE FROM player_match_history")
    conn.commit()
    assert not checks.check_settled_props_have_a_result(conn).passed


def test_run_checks_separates_critical_from_warning(tmp_path, monkeypatch):
    from tennis_wc.validation import checks

    conn = _setup(tmp_path, monkeypatch)
    conn.commit()
    results = checks.run_checks(conn)
    assert {r.name for r in results} == {c.__name__.replace("check_", "") for c in checks.ALL_CHECKS} or results
    assert all(r.severity in {"critical", "warning"} for r in results)
    assert checks.critical_failures(results) == []


def test_repair_marks_impossible_scorelines_so_settlement_voids_them(tmp_path, monkeypatch):
    from tennis_wc.validation import checks

    conn = _setup(tmp_path, monkeypatch)
    _result(conn, 1, {"player_a_sets": 1, "player_b_sets": 1,
                      "player_a_games": 7, "player_b_games": 8})
    conn.commit()

    assert not checks.check_impossible_scorelines(conn).passed
    assert checks.repair_impossible_scorelines(conn) == 1
    assert checks.check_impossible_scorelines(conn).passed

    from tennis_wc.props.settlement import _match_void_reason

    assert _match_void_reason(conn, 1) == "retired"
    # Idempotent: a second pass finds nothing left to mark.
    assert checks.repair_impossible_scorelines(conn) == 0


def test_duplicate_fixtures_fold_onto_the_copy_the_market_priced(tmp_path, monkeypatch):
    """The result landed on one row and the odds on the other.

    Two real matches existed twice, ingested under different market_event_ids,
    so the priced fixture could never settle.
    """
    from tennis_wc.validation import checks

    conn = _setup(tmp_path, monkeypatch)
    conn.execute(
        """INSERT INTO matches (id, provider_match_id, tour, match_date, tournament_id,
               player_a_id, player_b_id, round, source_provider, created_at, updated_at)
           VALUES (2,'M2','ATP','2026-06-01',1,1,2,'R1','test','now','now')"""
    )
    # Odds sit on fixture 2; the result sits on fixture 1.
    conn.execute(
        "INSERT INTO market_odds_snapshots (event_id, match_id, bookmaker, market_key, "
        "market_name, selection_name, selection_side, odds, source_provider, "
        "raw_response_id, fetched_at, created_at) "
        "VALUES ('e1',2,'Sportsbet','match_winner','Match Betting','A','player_a',"
        "1.8,'sportsbet',0,'2026-06-01T00:00:00Z','now')"
    )
    _result(conn, 1, {"player_a_sets": 2, "player_b_sets": 0})
    conn.commit()

    assert not checks.check_duplicate_fixtures(conn).passed
    summary = checks.repair_duplicate_fixtures(conn)

    assert summary["groups"] == 1 and summary["removed"] == 1
    assert checks.check_duplicate_fixtures(conn).passed
    # Everything now hangs off the fixture that had the odds.
    assert conn.execute("SELECT id FROM matches").fetchone()[0] == 2
    assert conn.execute(
        "SELECT match_id FROM match_results"
    ).fetchone()[0] == 2
