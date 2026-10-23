"""Exact-price publication boundary, without betting or network access."""
import copy
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

NBA = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(NBA))
sys.path.insert(0, str(NBA / 'nba_wong_choi/scripts'))
import nba_sgm_quote as q
import generate_nba_reports as r
import validate_nba_output as v

NOW = datetime(2026, 10, 23, 1, tzinfo=timezone.utc)


def inputs():
    legs = [dict(market_type=r.PLAYER_MARKET, player=name, team=team, category='REB', line_val=5,
                 line_display='5+', odds=1.8, estimated_prob=80, hit_l10=80, hit_l10_count='8/10',
                 hit_l5=80, hit_l3=100, implied_prob=55.6, edge=24.4, ev_pct=44, cov=.2, cov_grade='穩定',
                 avg=8, med=8, sd=1.6, l10=[8,9,4,7,10,8,9,4,8,9], base_rate=80,
                 edge_grade='正值', desc=f'{name} ({team}) REB 5+', det_prob=78,
                 engine='calibrated', probability_model_id='calibrated:fixture', adj_line='10-Factor 診斷')
            for name, team in [('Jayson Tatum', 'BOS'), ('LeBron James', 'LAL')]]
    odds = {'event_start_time': (NOW + timedelta(hours=2)).isoformat(), 'sgm_pricing': {
        'class_external_id': 16, 'competition_external_id': 1, 'event_external_id': 2,
        'outcomes': {'rebounds': {leg['player']: {'5': {'market_external_id': 10+i, 'outcome_external_id': 20+i}}
                                  for i, leg in enumerate(legs)}}}}
    return odds, legs


def post_price(price):
    return lambda body: (200, {'price': {'numerator': price - 1, 'denominator': 1, 'quoteId': 'q-fixture'}})


def test_actual_sgm_price_can_reverse_positive_product_ev():
    odds, legs = inputs()
    assert r._combo_passes_positive_ev_gate(legs)
    quoted = q.quote_combo(odds, legs, now=NOW, post=post_price(1.4))
    assert q.quote_valid(quoted.quote, odds, legs, now=NOW)
    ev = r.compute_combo_ev(quoted)
    assert ev['product_of_leg_prices'] == 3.24
    assert ev['combo_decimal_odds'] == 1.4
    assert ev['combo_ev_pct'] == pytest.approx(-10.4)
    assert not r._combo_passes_positive_ev_gate(quoted)


def test_quote_binds_exact_event_and_legs_with_bounded_lifetime():
    odds, legs = inputs()
    quoted = q.quote_combo(odds, legs, now=NOW, post=post_price(2))
    assert q.quote_valid(quoted.quote, odds, list(reversed(legs)), now=NOW)
    for delta in (-1, 301, 7200):
        assert not q.quote_valid(quoted.quote, odds, legs, now=NOW + timedelta(seconds=delta))
    changed = copy.deepcopy(odds)
    changed['sgm_pricing']['event_external_id'] = 123
    assert not q.quote_valid(quoted.quote, changed, legs, now=NOW)
    assert not q.quote_valid(quoted.quote, odds, legs[:1], now=NOW)
    changed_legs = copy.deepcopy(legs)
    changed_legs[0]['line_val'] = 6
    assert not q.quote_valid(quoted.quote, odds, changed_legs, now=NOW)


@pytest.mark.parametrize('reply', [(503, {}), (200, {'price': {'numerator': float('nan'), 'denominator': 1, 'quoteId': 'q'}}),
    (200, {'price': {'numerator': 1, 'denominator': 0, 'quoteId': 'q'}}),
    (200, {'price': {'numerator': -1, 'denominator': -1, 'quoteId': 'q'}}),
    (200, {'price': {'numerator': 1, 'denominator': 1}})])
def test_invalid_source_quote_never_becomes_publishable(reply):
    odds, legs = inputs()
    quoted = q.quote_combo(odds, legs, now=NOW, post=lambda body: reply)
    assert not q.quote_valid(quoted.quote, odds, legs, now=NOW)


def test_missing_ids_started_game_and_duplicate_legs_do_not_make_requests():
    odds, legs = inputs()
    fail = lambda body: pytest.fail('must not request')
    for source, selected, now in [({}, legs, NOW), (odds, legs, NOW+timedelta(hours=3)),
                                   (odds, [legs[0], legs[0]], NOW)]:
        assert q.quote_combo(source, selected, now=now, post=fail).quote['status'] != 'ok'


def test_render_and_sidecar_use_identical_actual_price_probability_and_kelly(tmp_path):
    odds, legs = inputs()
    quoted = q.quote_combo(odds, legs, now=NOW, post=post_price(2))
    text = r.gen_combo_section('組合 1: 穩膽 SGM (Low Risk)', '🛡️', '', quoted)
    assert '組合賠率 @2.0' in text and '**$100 回報**: **$200**' in text
    assert '**Combo EV%**: +28.0%' in text
    assert '14.0% bankroll' in text
    assert '8-Factor' not in text and 'calibrated:fixture' in text
    assert '→ 10-Factor 診斷: 78%' in text
    sidecar = r.build_market_eval_sidecar(text, odds, {}, [], {'combos': {'1': quoted}}, 'hybrid')
    assert sidecar['combos'][0]['sportsbet_sgm_price'] == 2
    assert sidecar['combos'][0]['product_of_leg_prices'] == 3.24
    report = tmp_path / 'Game_BOS_LAL_Full_Analysis.md'
    report.write_text(text)
    sidecar_path = Path(str(report)+'.market_legs.json')
    sidecar_path.write_text(json.dumps(sidecar))
    source = tmp_path/'odds.json'; source.write_text(json.dumps(odds))
    assert not v.check_fw13_sgm_quotes(text, report, source, now=NOW)
    assert v.check_fw13_sgm_quotes(text, report, source, now=NOW+timedelta(minutes=6))
    assert v.check_fw13_sgm_quotes(text+'changed', report, source, now=NOW)
    sidecar['combos'][0]['sportsbet_sgm_price'] = 3.24
    sidecar_path.write_text(json.dumps(sidecar))
    assert v.check_fw13_sgm_quotes(text, report, source, now=NOW)


def test_unquoted_combo_cannot_render_formal_recommendation():
    _, legs = inputs()
    assert '組合賠率 @' not in r.gen_combo_section('組合 1: test', '', '', legs)


@pytest.mark.parametrize('price,published', [(2.0, True), (1.4, False)])
def test_real_report_selection_uses_quote_before_rendering(monkeypatch, price, published):
    odds, legs = inputs()
    now = datetime.now(timezone.utc)
    odds['event_start_time'] = (now + timedelta(hours=2)).isoformat()
    monkeypatch.setattr(r, 'build_leg_candidates', lambda *args, **kwargs: [])
    monkeypatch.setattr(r, 'select_combo_1', lambda candidates: legs)
    for name in ('select_combo_2', 'select_combo_3', 'select_combo_x_value_bomb'):
        monkeypatch.setattr(r, name, lambda candidates: [])
    monkeypatch.setattr(r, 'quote_combo', lambda source, selected: q.quote_combo(source, selected, now=now, post=post_price(price)))
    capture = {}
    meta = {'away': {'abbr': 'BOS', 'name': 'Boston'}, 'home': {'abbr': 'LAL', 'name': 'LA'}}
    text = r.gen_full_report(meta, {}, {}, {}, {}, [], now.isoformat(), capture=capture, sportsbet_odds=odds)
    assert bool(capture['combos']['1']) is published
    assert ('組合賠率 @2.0' in text) is published
    assert capture['quote_attempts']['1']['decimal_odds'] == price


def test_live_cache_reprices_expired_sgm_without_changing_stat_inputs(tmp_path, monkeypatch):
    import nba_orchestrator as orchestrator
    odds, legs = inputs()
    quoted = q.quote_combo(odds, legs, now=NOW, post=post_price(2))
    text = r.gen_combo_section('組合 1: test', '', '', quoted)
    report = tmp_path/'Game_BOS_LAL_Full_Analysis.md'; report.write_text(text)
    source = tmp_path/'Sportsbet_Odds_BOS_LAL.json'; source.write_text(json.dumps(odds))
    stats = tmp_path/'stats.json'; stats.write_text('{}')
    Path(str(report)+'.market_legs.json').write_text(json.dumps(r.build_market_eval_sidecar(text, odds, {}, [], {'combos': {'1': quoted}}, 'hybrid')))
    monkeypatch.setattr(orchestrator, 'report_inputs', lambda *args: {'fixture': True})
    Path(str(report)+'.inputs.json').write_text(json.dumps({'inputs': {'fixture': True}, 'report': hashlib.sha256(text.encode()).hexdigest()}))
    # Expiry is tested against a fixed future clock in the cache's actual verifier.
    import nba_wong_choi.scripts.validate_nba_output as cache_validator
    real = cache_validator.check_fw13_sgm_quotes
    monkeypatch.setattr(cache_validator, 'check_fw13_sgm_quotes', lambda *args: real(*args, now=NOW+timedelta(minutes=6)))
    assert not orchestrator.report_cache_current(str(report), str(source), str(stats), False)


def test_dashboard_exports_frozen_sgm_price_and_adjusted_probability(tmp_path):
    sys.path.insert(0, str(NBA.parents[2] / 'Horse_Racing_Dashboard/backend'))
    from services.multisport_exporter import export_nba_snapshot, nba_no_firewall
    odds, legs = inputs()
    odds.update(target_analysis_date='2026-10-23', game_tag='BOS_LAL', source='sportsbet.com.au',
                player_props={'points': {'Jayson Tatum': {'lines': {'20': '1.8'}}}})
    quoted = q.quote_combo(odds, legs, now=NOW, post=post_price(2))
    text = ('**odds_source**: SPORTSBET_LIVE\nPython Auto-Selection\n' +
            r.gen_combo_section('組合 1: test', '', '', quoted) + '\n未填寫項目 殘留: 0')
    folder = tmp_path/'2026-10-23 NBA Analysis'; folder.mkdir()
    report = folder/'Game_BOS_LAL_Full_Analysis.md'; report.write_text(text)
    (folder/'Sportsbet_Odds_BOS_LAL.json').write_text(json.dumps(odds))
    Path(str(report)+'.market_legs.json').write_text(json.dumps(r.build_market_eval_sidecar(text, odds, {}, [], {'combos': {'1': quoted}}, 'hybrid')))
    # Historical parser opt-out: the publication verifier is tested above.
    snapshot = export_nba_snapshot(tmp_path, target_date='2026-10-23', firewall=nba_no_firewall)
    combo = next(row for row in snapshot['recommendations'] if row['bet_type'] == 'combo')
    assert combo['odds'] == 2 and combo['odds_status'] == 'sportsbet_sgm_quoted'
    assert combo['metrics']['model_probability'] == pytest.approx(.64)
    assert combo['metrics']['expected_value'] == pytest.approx(.28)
    assert combo['quote_expires_at'] == quoted.quote['expires_at']
    banker = next(row for row in snapshot['recommendations'] if row['bet_type'] == 'single')
    assert banker['odds_status'] == 'sportsbet_extracted'
