from __future__ import annotations

import pytest


def _seed_prop(tmp_path, monkeypatch, *, market_key="player_win_a_set_1"):
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.db import get_connection
    from tennis_wc.database.migrations import init_db
    from tennis_wc.props.settlement import record_prop

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
        record_prop(
            conn,
            match_id=1,
            match_date="2026-08-14",
            match_label="A v B",
            market_key=market_key,
            line=0.5,
            selection="A",
            side="over",
            prop_scope="player_win_set",
            subject_player_id=1,
            decimal_odds=1.90,
            model_prob=0.60,
            market_prob_fair=0.52,
            blended_prob=0.56,
            edge=0.08,
            ev=0.14,
            predicted_mean=0.60,
            stake_units=1.0,
            is_value=True,
        )
        return int(conn.execute("SELECT id FROM prop_tracker").fetchone()[0])


def test_live_prop_ledger_records_only_an_already_placed_manual_bet(
    tmp_path, monkeypatch
):
    prop_id = _seed_prop(tmp_path, monkeypatch)
    from tennis_wc.database.db import get_connection
    from tennis_wc.props.live_bets import record_live_prop_bet

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
    from tennis_wc.props.live_bets import record_live_prop_bet

    with pytest.raises(ValueError, match="exceeds.*0.5u"):
        record_live_prop_bet(prop_id=prop_id, odds_taken=1.90, stake_aud=1.00)
    record_live_prop_bet(prop_id=prop_id, odds_taken=1.90, stake_aud=0.50)
    with pytest.raises(ValueError, match="already recorded"):
        record_live_prop_bet(prop_id=prop_id, odds_taken=1.90, stake_aud=0.50)


def test_live_prop_ledger_refuses_a_held_back_family(tmp_path, monkeypatch):
    prop_id = _seed_prop(
        tmp_path, monkeypatch, market_key="player_game_handicap_1"
    )
    from tennis_wc.props.live_bets import record_live_prop_bet

    with pytest.raises(ValueError, match="not on the live family allowlist"):
        record_live_prop_bet(prop_id=prop_id, odds_taken=1.90, stake_aud=0.50)
