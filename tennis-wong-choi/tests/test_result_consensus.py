"""Disputed source results must not choose a winner or rewrite saved bets."""
from __future__ import annotations

import json

import pytest


@pytest.fixture
def db(tmp_path, monkeypatch):
    from conftest import configure_test_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.database.migrations import init_db

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
    from tennis_wc.props.settlement import record_prop
    record_prop(conn, match_id=1, match_date="2026-06-01", match_label="P1 vs P2",
                market_key="player_total_games_1_10.5", line=10.5, selection="P1 Over 10.5",
                side="over", prop_scope="player_games", subject_player_id=1,
                decimal_odds=1.9, model_prob=0.7, model_prob_raw=0.7,
                market_prob_fair=0.5, blended_prob=0.6, edge=0.1, ev=0.14,
                predicted_mean=12, stake_units=1, is_value=True)
    conn.execute("UPDATE prop_tracker SET is_point_in_time=1,recorded_at='2026-06-01T09:00:00Z'")
    conn.commit()
    yield conn
    conn.close()


def test_disputed_pending_prop_stays_pending_until_sources_agree(db):
    from tennis_wc.props.settlement import settle_props
    from tennis_wc.validation.checks import check_conflicting_results

    result = settle_props(db)
    assert result["held_conflicting_results"] == 1
    assert result["graded"] == result["voided"] == 0
    assert db.execute("SELECT result_status FROM prop_tracker").fetchone()[0] == "PENDING"
    assert not check_conflicting_results(db).passed
    db.execute("UPDATE match_results SET winner_player_id=1 WHERE source_provider='b'")
    result = settle_props(db)
    assert result["graded"] == 1
    assert db.execute("SELECT result_status FROM prop_tracker").fetchone()[0] == "WON"


def test_disputed_saved_outcome_is_preserved_but_cannot_supply_decision_evidence(db):
    from tennis_wc.props.settlement import settle_props, model_vs_market_scorecard, prop_roi_report
    from tennis_wc.props.calibration import family_reliability

    db.execute("UPDATE prop_tracker SET result_status='WON',actual_value=12,profit_loss_units=0.9")
    saved = dict(db.execute("SELECT * FROM prop_tracker").fetchone())
    settle_props(db)
    assert dict(db.execute("SELECT * FROM prop_tracker").fetchone()) == saved
    assert model_vs_market_scorecard(db)["settled"] == 0
    assert prop_roi_report(db)["overall"]["settled"] == 0
    assert family_reliability(db, "player_total_games").settled == 0


def test_conflicted_combo_leg_has_no_resolved_result(db):
    from tennis_wc.betting.ledger import _combo_result_row

    assert _combo_result_row(db, {"match_id": 1}) is None
    db.execute("DELETE FROM match_results WHERE source_provider='b'")
    assert _combo_result_row(db, {"match_id": 1})["winner_player_id"] == 1


def test_native_ledger_and_prop_linked_clv_hold_disputed_settlement(db):
    from tennis_wc.betting.ledger import settle_bets_for_date

    db.execute("UPDATE prop_tracker SET result_status='WON',profit_loss_units=.9")
    prop_id=db.execute("SELECT id FROM prop_tracker").fetchone()[0]
    db.execute("INSERT INTO bet_ledger (prediction_id,match_id,selection_player_id,selection_name,"
               "odds_taken,stake_units,status,recorded_at) VALUES (1,1,1,'P1',1.9,1,'PENDING','now')")
    db.execute("INSERT INTO clv_tracker (recommendation_type,source_id,match_id,match_date,"
               "selection_name,market_key,market_name,tier,odds_taken,result_status,recorded_at,updated_at) "
               "VALUES ('PROP_RECOMMENDATION',?,1,'2026-06-01','P1 Over 10.5','total','Games',"
               "'PROP',1.9,'PENDING','now','now')",(prop_id,))
    db.commit()
    result=settle_bets_for_date('2026-06-01',auto_refresh=False)
    assert result['held_conflicting_results']==1
    assert result['tracker_settlement']['held_conflicting_results']==1
    assert db.execute("SELECT status FROM bet_ledger").fetchone()[0]=='PENDING'
    assert db.execute("SELECT result_status FROM clv_tracker").fetchone()[0]=='PENDING'
    db.execute("UPDATE match_results SET winner_player_id=1")
    db.commit()
    result=settle_bets_for_date('2026-06-01',auto_refresh=False)
    assert result['settled']==1
    assert db.execute("SELECT status FROM bet_ledger").fetchone()[0]=='WON'
    assert db.execute("SELECT result_status FROM clv_tracker").fetchone()[0]=='WON'
