"""Disputed source results must not choose a winner or rewrite saved bets."""
from __future__ import annotations

import json

import pytest


@pytest.fixture
def db(tmp_path, monkeypatch):
    from conftest import configure_test_db
    from tennis_wc.store.db import get_connection
    from tennis_wc.store.migrations import init_db

    configure_test_db(tmp_path, monkeypatch)
    init_db()
    conn = get_connection()
    for pid in (1, 2):
        conn.execute("INSERT INTO players (id,name,tour,source_provider,created_at,updated_at) "
                     "VALUES (?,?,'ATP','test','now','now')", (pid, f"P{pid}"))
    conn.execute("INSERT INTO matches (id,provider_match_id,tour,match_date,tournament_id,"
                 "player_a_id,player_b_id,round,source_provider,created_at,updated_at,start_time_utc) "
                 "VALUES (1,'M','ATP','2026-06-01',1,1,2,'R1','test','now','now','2026-06-01T12:00:00Z')")
    for provider, winner in (("a", 1), ("b", 2)):
        conn.execute("INSERT INTO match_results (match_id,winner_player_id,source_provider,"
                     "score_json,created_at) VALUES (1,?,?,?,'2026-06-01T15:00:00Z')",
                     (winner, provider, json.dumps({"player_a_games": 12, "player_b_games": 7,
                                                    "player_a_sets": 2, "player_b_sets": 0})))
    from tennis_wc.store.ledger import record_rows
    record_rows(conn, [dict(
        match_id=1, match_date="2026-06-01", match_label="P1 vs P2",
        market_key="player_total_games_1_10.5", line=10.5, selection="P1 Over 10.5",
        side="over", prop_scope="player_games", subject_player_id=1,
        decimal_odds=1.9, model_prob=0.7, model_prob_raw=0.7, temper_strength=0.9,
        market_prob_fair=0.5, blended_prob=0.6, edge=0.1, ev=0.14,
        predicted_mean=12, stake_units=1, is_value=True, feed_market_key=None,
        feed_market_name=None, feed_selection_name=None, feed_line=None,
        pricing_evidence_json='{"version": 1, "source_quality": 0.9}')], "2026-06-01T09:00:00Z")
    conn.execute("UPDATE prop_tracker SET is_point_in_time=1,recorded_at='2026-06-01T09:00:00Z'")
    conn.commit()
    yield conn
    conn.close()


def test_disputed_pending_prop_stays_pending_until_sources_agree(db):
    from tennis_wc.settle.props import settle_props

    result = settle_props(db, today='2026-06-02')
    assert result["held_conflicting_results"] == 1
    assert result["graded"] == result["voided"] == 0
    assert db.execute("SELECT result_status FROM prop_tracker").fetchone()[0] == "PENDING"
    db.execute("UPDATE match_results SET winner_player_id=1 WHERE source_provider='b'")
    result = settle_props(db, today='2026-06-02')
    assert result["graded"] == 1
    assert db.execute("SELECT result_status FROM prop_tracker").fetchone()[0] == "WON"


def test_disputed_saved_outcome_is_preserved_but_cannot_supply_decision_evidence(db):
    from tennis_wc.model.market import DEFAULT_MODEL_WEIGHT, family_weight
    from tennis_wc.settle.props import settle_props
    from tennis_wc.store.results import result_agreement_clause

    db.execute("UPDATE prop_tracker SET result_status='WON',actual_value=12,profit_loss_units=0.9")
    saved = dict(db.execute("SELECT * FROM prop_tracker").fetchone())
    settle_props(db)
    assert dict(db.execute("SELECT * FROM prop_tracker").fetchone()) == saved
    assert db.execute(f"SELECT COUNT(*) FROM prop_tracker p WHERE {result_agreement_clause()}").fetchone()[0] == 0
    assert family_weight(db, "player_total_games", "2026-12-31") == DEFAULT_MODEL_WEIGHT


def test_same_winner_different_score_stays_pending_and_out_of_evidence(db):
    from tennis_wc.store.results import conflicting_result_matches,result_agreement_clause
    from tennis_wc.settle.props import settle_props
    db.execute('UPDATE match_results SET winner_player_id=1')
    db.execute("UPDATE match_results SET score_json=? WHERE source_provider='b'",
               (json.dumps({'player_a_games':13,'player_b_games':7,'player_a_sets':2,'player_b_sets':0}),))
    assert conflicting_result_matches(db)=={1}
    assert settle_props(db, today='2026-06-02')['held_conflicting_results']==1
    assert db.execute(f'SELECT COUNT(*) FROM prop_tracker p WHERE {result_agreement_clause()}').fetchone()[0]==0
    db.execute("UPDATE match_results SET score_json=? WHERE source_provider='b'",
               (json.dumps({'player_a_games':12,'player_b_games':7,'player_a_sets':2,'player_b_sets':0}),))
    assert conflicting_result_matches(db)==set()
    assert settle_props(db, today='2026-06-02')['graded']==1


def test_partial_extra_fields_do_not_manufacture_a_score_conflict(db):
    from tennis_wc.store.results import conflicting_result_matches
    db.execute('UPDATE match_results SET winner_player_id=1')
    db.execute("UPDATE match_results SET score_json='{}' WHERE source_provider='b'")
    assert conflicting_result_matches(db)==set()


@pytest.mark.parametrize('payload',['broken','[]'])
def test_malformed_source_score_is_held_without_sql_json_failure(db,payload):
    from tennis_wc.store.results import conflicting_result_matches,result_agreement_clause
    db.execute('UPDATE match_results SET winner_player_id=1')
    db.execute("UPDATE match_results SET score_json=? WHERE source_provider='b'",(payload,))
    assert conflicting_result_matches(db)=={1}
    assert db.execute(f'SELECT COUNT(*) FROM prop_tracker p WHERE {result_agreement_clause()}').fetchone()[0]==0


def test_a_single_result_with_wrong_winner_orientation_is_not_consensus(db):
    from tennis_wc.store.results import conflicting_result_matches
    db.execute("DELETE FROM match_results WHERE source_provider='a'")
    # Source b labels player 2 the winner but its score says player 1 won 2-0.
    assert conflicting_result_matches(db)=={1}


def test_a_dispute_still_open_after_21_days_is_voided_and_revives_if_sources_agree(db):
    from tennis_wc.settle.props import settle_props

    assert settle_props(db, today="2026-06-20")["held_conflicting_results"] == 1
    result = settle_props(db, today="2026-06-22")
    assert result["voided_disputed"] == 1 and result["held_conflicting_results"] == 0
    assert db.execute("SELECT result_status FROM prop_tracker").fetchone()[0] == "VOID"
    db.execute("UPDATE match_results SET winner_player_id=1 WHERE source_provider='b'")
    settle_props(db, today="2026-06-23")
    assert db.execute("SELECT result_status FROM prop_tracker").fetchone()[0] == "WON"
