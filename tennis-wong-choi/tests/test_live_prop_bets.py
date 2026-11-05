from __future__ import annotations

import pytest


def _seed_prop(tmp_path, monkeypatch, *, market_key="player_win_a_set_1", featured=True):
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.db import get_connection
    from tennis_wc.database.migrations import init_db

    init_db()
    now = "2026-08-13T00:00:00Z"
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO players (id,name,tour,source_provider,created_at,updated_at) "
            "VALUES (1,'A','ATP','test',?,?),(2,'B','ATP','test',?,?)",
            (now, now, now, now),
        )
        conn.execute(
            "INSERT INTO tournaments (id,name,tour,external_id,source_provider,"
            "created_at,updated_at) VALUES (1,'ATP Test','ATP','t1','test',?,?)",
            (now, now),
        )
        conn.execute(
            "INSERT INTO matches (id,provider_match_id,tour,match_date,tournament_id,"
            "player_a_id,player_b_id,round,source_provider,created_at,updated_at) "
            "VALUES (1,'m1','ATP','2026-08-14',1,1,2,'R32','test',?,?)",
            (now, now),
        )
        conn.execute(
            "INSERT INTO prop_tracker (prop_key,match_id,match_date,match_label,market_key,line,"
            "selection,side,prop_scope,subject_player_id,decimal_odds,model_prob,market_prob_fair,"
            "blended_prob,edge,ev,predicted_mean,stake_units,is_value,result_status,recorded_at,updated_at) "
            "VALUES ('k',1,'2026-08-14','A v B',?,0.5,'A','over','player_win_set',1,1.9,0.6,0.52,0.56,"
            "0.08,0.14,0.6,1.0,1,'PENDING',?,?)", (market_key, now, now))
        prop_id = int(conn.execute("SELECT id FROM prop_tracker").fetchone()[0])
        if featured:
            conn.execute(
                "INSERT INTO featured_picks (prop_id,match_id,match_date,rank,run_label,market_key,selection,"
                "start_time_utc,odds,featured_at) VALUES (?,1,'2026-08-14',1,'21:00',?,'A',"
                "'2026-08-14T10:00:00Z',1.9,?)", (prop_id, market_key, now))
        return prop_id


def test_live_prop_ledger_records_only_an_already_placed_manual_bet(
    tmp_path, monkeypatch
):
    prop_id = _seed_prop(tmp_path, monkeypatch)
    from tennis_wc.database.db import get_connection
    from tennis_wc.store.live_bets import record_live_prop_bet

    payload = record_live_prop_bet(
        prop_id=prop_id,
        odds_taken=1.92,
        stake_aud=0.50,
        placed_at="2026-08-13T23:05:00Z",
    )

    assert payload["stake_units"] == 0.5
    assert payload["stake_aud"] == 0.5
    assert payload["currency"] == "AUD"
    assert payload["wager_placed_by_software"] is False
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM prop_live_bets").fetchone()
    assert row["prop_id"] == prop_id
    assert row["odds_taken"] == pytest.approx(1.92)


def test_live_prop_ledger_refuses_duplicate_or_oversized_records(
    tmp_path, monkeypatch
):
    prop_id = _seed_prop(tmp_path, monkeypatch)
    from tennis_wc.store.live_bets import record_live_prop_bet

    with pytest.raises(ValueError, match="exceeds.*0.5u"):
        record_live_prop_bet(prop_id=prop_id, odds_taken=1.90, stake_aud=1.00)
    record_live_prop_bet(prop_id=prop_id, odds_taken=1.90, stake_aud=0.50)
    with pytest.raises(ValueError, match="already recorded"):
        record_live_prop_bet(prop_id=prop_id, odds_taken=1.90, stake_aud=0.50)


def test_live_prop_ledger_refuses_a_prop_that_is_not_featured(tmp_path, monkeypatch):
    prop_id = _seed_prop(tmp_path, monkeypatch, featured=False)
    from tennis_wc.store.live_bets import record_live_prop_bet

    with pytest.raises(ValueError, match="only 精選 picks"):
        record_live_prop_bet(prop_id=prop_id, odds_taken=1.90, stake_aud=0.50)
