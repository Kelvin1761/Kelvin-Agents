from __future__ import annotations

import pytest


def test_backtest_empty_range(tmp_path, monkeypatch):
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.modelling.backtester import run_backtest

    init_db()
    result = run_backtest("2026-05-08", "2026-05-08")
    assert result["total_predictions"] == 0


def test_backtest_ledger_is_scoped_to_its_window(tmp_path, monkeypatch):
    from conftest import configure_test_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.database.migrations import init_db
    from tennis_wc.modelling.backtester import run_backtest

    configure_test_db(tmp_path, monkeypatch)
    init_db()
    with get_connection() as conn:
        for match_id, day, status, profit in (
            (1, "2026-06-01", "WON", 0.9),
            (2, "2026-06-01", "PENDING", None),
            (3, "2026-07-01", "LOST", -1.0),
        ):
            conn.execute(
                "INSERT INTO matches (id,provider_match_id,tour,match_date,tournament_id,"
                "player_a_id,player_b_id,round,source_provider,created_at,updated_at) "
                "VALUES (?,?,'ATP',?,1,1,2,'R1','test','now','now')", (match_id,str(match_id),day))
            prediction_id = conn.execute(
                "INSERT INTO predictions (match_id,feature_set_version,selection_player_id,"
                "selection_name,model_probability,decision,stake_units,confidence,risk,"
                "pricing_json,created_at) VALUES (?,'v1',1,'A',0.6,'BET',1,70,'low','{}','now')",
                (match_id,),
            ).lastrowid
            conn.execute(
                "INSERT INTO bet_ledger (prediction_id,match_id,selection_player_id,"
                "selection_name,odds_taken,stake_units,status,profit_loss_units,recorded_at) "
                "VALUES (?,?,1,'A',1.9,1,?,?,'now')",
                (prediction_id,match_id,status,profit))
    result = run_backtest("2026-06-01", "2026-06-01")
    assert result["total_predictions"] == 2, "missing tournament metadata must not drop predictions"
    assert result["ledger"]["total_bets"] == 2
    assert result["ledger"]["settled_stake_units"] == 1
    assert result["ledger"]["profit_loss_units"] == 0.9
    assert result["ledger"]["roi"] == 0.9
    assert 'not point-in-time' in result['note']
    with get_connection() as conn:
        for level,surface in [('ATP_250','clay'),('ATP_500','hard')]:
            conn.execute('INSERT INTO tournament_levels (tournament_id,tour,level,surface,'
                         'source_provider,raw_response_id,created_at,updated_at) '
                         "VALUES (1,'ATP',?,?,?,0,'now','now')",(level,surface,'test-'+level))
    latest=run_backtest('2026-06-01','2026-06-01')
    assert latest['total_predictions']==2, 'multiple metadata rows must not duplicate forecasts'
    assert latest['performance_by_tournament_level'][0]['level']=='ATP_500'


def test_backtest_rejects_reversed_date_window():
    from tennis_wc.modelling.backtester import run_backtest

    with pytest.raises(ValueError,match='start_date'):
        run_backtest('2026-07-01','2026-06-01')


@pytest.mark.parametrize('start,end',[
    ('not-a-date','2026-06-01'),('2026-02-30','2026-06-01'),('2026-06-01',''),
])
def test_backtest_rejects_invalid_calendar_dates(start,end):
    from tennis_wc.modelling.backtester import run_backtest

    with pytest.raises(ValueError):
        run_backtest(start,end)
