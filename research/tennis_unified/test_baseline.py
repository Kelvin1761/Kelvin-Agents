"""Evidence fidelity and failure cases, independent of model efficacy."""
import json
import math
import sqlite3

import pytest

from research.tennis_unified import baseline


def pricing():
    return {'selection_side': 'player_b', 'segment_risk_discount': .5,
            'no_vig_market_probability': .4,
            'model': {'elo_base_logit': math.log(4), 'total_nudge_logit': 0,
                      'components': [{'name': name, 'active': True, 'weight': 1., 'probability': .5}
                                     for name in (*baseline.NUDGES, 'surface_elo_edge', 'overall_elo_edge')]}}


def test_saved_orientation_and_discount_are_required_for_final_probability():
    result = baseline.replay(pricing())
    assert result['raw_a'] == pytest.approx(.8)
    assert result['selected_final'] == pytest.approx(.3)
    wrong = pricing()
    wrong.pop('segment_risk_discount')
    with pytest.raises(KeyError):
        baseline.replay(wrong)


def test_saved_component_mismatch_and_inactive_elo_are_rejected():
    value = pricing()
    value['model']['components'][0]['probability'] = .8
    with pytest.raises(ValueError, match='nudge_reconstruction_mismatch'):
        baseline.replay(value)
    for part in value['model']['components']:
        part['active'] = False
    with pytest.raises(ValueError, match='no_active_elo'):
        baseline.replay(value)


def test_price_clock_requires_receipt_before_forecast_and_aware_time():
    first = {'fetched_at': '2026-10-28T10:00:00Z', 'created_at': '2026-10-28T10:01:00Z',
             'source_provider': 'sportsbet', 'player_a_odds': 1.5, 'player_b_odds': 2.8}
    start = baseline.instant('2026-10-28T22:00:00+11:00')
    forecast = baseline.instant('2026-10-28T10:02:00Z')
    assert baseline.price_exclusion(first, start, forecast) is None
    assert baseline.price_exclusion({**first, 'created_at': '2026-10-28T10:03:00Z'}, start, forecast)
    assert baseline.price_exclusion({**first, 'fetched_at': '2026-10-28T10:00:00'}, start, forecast)
    assert baseline.price_exclusion({**first, 'player_a_odds': float('nan')}, start, forecast)


def test_corrupt_payload_cannot_inherit_previous_match_fixture(monkeypatch):
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript('''
        CREATE TABLE matches(id,source_provider,fixture_status,player_a_id,player_b_id,match_date,start_time_utc,tour);
        CREATE TABLE predictions(id,match_id,created_at,pricing_json,model_probability,selection_player_id);
        CREATE TABLE odds_snapshots(id,match_id,market,source_provider,bookmaker,fetched_at,created_at,player_a_odds,player_b_odds);
    ''')
    frozen = {'id': 1, 'player_a_id': 10, 'player_b_id': 20, 'match_date': '2026-10-28',
              'start_time_utc': '2026-10-28T12:00:00Z', 'fixture_status': 'ACTIVE'}
    for mid in (1, 2):
        conn.execute('INSERT INTO matches VALUES(?,?,?,?,?,?,?,?)',
                     (mid, 'sportsbet', 'ACTIVE', 10, 20, '2026-10-28', frozen['start_time_utc'], 'ATP'))
        raw = json.dumps({'pricing': pricing(), 'fixture_at_prediction': frozen}) if mid == 1 else 'broken json'
        conn.execute('INSERT INTO predictions VALUES(?,?,?,?,?,?)', (mid, mid, '2026-10-28T10:01:00Z', raw, .3, 20))
        conn.execute('INSERT INTO odds_snapshots VALUES(?,?,?,?,?,?,?,?,?)',
                     (mid, mid, 'match_winner', 'sportsbet', 'Sportsbet', '2026-10-28T10:00:00Z',
                      '2026-10-28T10:00:01Z', 1.5, 2.8))
    forecasts = [{'match_id': mid, 'prediction_id': mid, 'start_time_utc': frozen['start_time_utc'],
                  'winner_player_id': 10, 'model_p': .7} for mid in (1, 2)]
    monkeypatch.setattr(baseline, 'prematch_outcomes', lambda _: forecasts)
    rows, _, counts = baseline.collect(conn)
    conn.close()
    assert rows[0]['frozen_fixture_verified'] is True
    assert rows[1]['frozen_fixture_verified'] is False
    assert counts['faithful_parity'] == 1
    assert rows[1]['parity_exclusion'] is not None


def test_metrics_are_match_paired_and_equal_model_has_zero_gain():
    rows = [{'stored_a': p, 'market_a': p, 'outcome_a': y} for p, y in ((.8, 1), (.2, 0), (.6, 0))]
    result = baseline.score(rows)
    assert result['n'] == 3
    assert result['gain_ll_ci95'] == [0., 0.]
    assert result['gain_brier_ci95'] == [0., 0.]
