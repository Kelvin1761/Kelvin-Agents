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
import nba_availability as availability
import nba_sgm_quote as q
from nba_engine import publish, report as engine_report
from nba_engine.legs import Leg

NOW = datetime(2026, 10, 23, 1, tzinfo=timezone.utc)
PLAYERS = [('Jayson Tatum', 'BOS'), ('LeBron James', 'LAL')]


def inputs():
    legs = [dict(player=name, team=team, market='reb', line=5.0, side='over') for name, team in PLAYERS]
    odds = {'away_team': 'BOS', 'home_team': 'LAL', 'event_start_time': (NOW + timedelta(hours=2)).isoformat(),
            'extraction_time': NOW.isoformat(),
            'player_props': {'rebounds': {name: {'lines': {'5': '1.8'}} for name, _ in PLAYERS}},
            'sgm_pricing': {'class_external_id': 16, 'competition_external_id': 1, 'event_external_id': 2,
                            'outcomes': {'rebounds': {leg['player']: {'5': {'market_external_id': 10 + i,
                                                                            'outcome_external_id': 20 + i}}
                                                      for i, leg in enumerate(legs)}}}}
    return odds, legs


def post_price(price):
    return lambda body: (200, {'price': {'numerator': price - 1, 'denominator': 1, 'quoteId': 'q-fixture'}})


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
    changed_legs[0]['line'] = 6.0
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


def engine_legs():
    return [Leg(player=name, team=team, opponent='LAL' if team == 'BOS' else 'BOS', stat='REB', line=5.0,
                price=1.8, l10=[8.0] * 10, minutes_l10=34.0, hit_l10=0.8, hit_l5=0.8, hit_l3=1.0, avg=8.0,
                median=8.0, l3_avg=8.0, cov=0.2, market=1 / 1.8, p_c=0.8, p_s=0.8, p_ms=0.8,
                availability='ok', flags=[]) for name, team in PLAYERS]


def package(odds):
    from nba_data_contract import NBA_STATISTICS_CONTRACT
    maps = {team: availability.InjuryMap({}, [name, *[f'Roster Member {i}' for i in range(4)]], NOW.isoformat())
            for name, team in PLAYERS}
    packet = availability.apply_availability({'meta': {
        'date': odds['event_start_time'], 'away': {'abbr': 'BOS'}, 'home': {'abbr': 'LAL'},
        'statistics_contract': NBA_STATISTICS_CONTRACT, 'stat_source': 'espn'}, 'players': {}}, maps)
    return {'meta': packet['meta'], 'injuries': packet.get('injuries') or {}}


def _quoted_report(tmp_path, folder=None):
    odds, legs = inputs()
    quoted = q.quote_combo(odds, legs, now=NOW, post=post_price(2))
    combo, pkg = engine_legs(), package(odds)
    diag = {'rule': 'banker'}
    text = engine_report.render(odds, pkg, combo, combo, quoted.quote, diag)
    folder = folder or tmp_path
    report = folder/'Game_BOS_LAL_Full_Analysis.md'
    source = folder/'Sportsbet_Odds_BOS_LAL.json'; source.write_text(json.dumps(odds))
    engine_report.write(str(report), text, engine_report.sidecar(text, odds, pkg, combo, combo, quoted.quote, diag))
    return odds, text, report, source, Path(str(report)+'.market_legs.json')


def test_publication_needs_a_live_quote_and_current_availability(tmp_path):
    odds, text, report, source, sidecar = _quoted_report(tmp_path)
    assert publish.validate(report, source, now=NOW) == (True, [])
    passed, blocks = publish.validate(report, source, now=NOW + timedelta(minutes=6))
    assert not passed and any('quote' in b for b in blocks)
    payload = json.loads(sidecar.read_text())
    payload['availability'] = None
    sidecar.write_text(json.dumps(payload))
    passed, blocks = publish.validate(report, source, now=NOW)
    assert not passed and any('availability' in b for b in blocks)


def test_publication_rejects_a_leg_sportsbet_no_longer_offers(tmp_path):
    odds, text, report, source, _ = _quoted_report(tmp_path)
    odds['player_props']['rebounds']['LeBron James']['lines'] = {'6': '2.4'}
    source.write_text(json.dumps(odds))
    passed, blocks = publish.validate(report, source, now=NOW)
    assert not passed and any('LeBron James' in b for b in blocks)


def test_dashboard_exports_frozen_sgm_price_and_probability(tmp_path):
    sys.path.insert(0, str(NBA.parents[2] / 'Horse_Racing_Dashboard/backend'))
    from services.multisport_exporter import export_nba_snapshot, nba_no_firewall
    folder = tmp_path/'2026-10-23 NBA Analysis'; folder.mkdir()
    _, _, report, source, sidecar = _quoted_report(tmp_path, folder)
    odds = json.loads(source.read_text())
    odds.update(target_analysis_date='2026-10-23', game_tag='BOS_LAL', source='sportsbet.com.au')
    source.write_text(json.dumps(odds))
    snapshot = export_nba_snapshot(tmp_path, target_date='2026-10-23', firewall=nba_no_firewall)
    combo = next(row for row in snapshot['recommendations'] if row['bet_type'] == 'combo')
    assert combo['odds'] == 2 and combo['odds_status'] == 'sportsbet_sgm_quoted'
    assert combo['metrics']['model_probability'] == pytest.approx(.64)
    assert combo['metrics']['expected_value'] == pytest.approx(.28)
    assert combo['quote_expires_at'] == json.loads(sidecar.read_text())['combos'][0]['sgm_quote']['expires_at']
    assert [leg['player'] for leg in combo['legs']] == [name for name, _ in PLAYERS]


def test_expired_quote_is_renewed_in_place_only_at_the_published_price(tmp_path):
    odds, text, report, source, sidecar = _quoted_report(tmp_path)
    later = NOW + timedelta(minutes=20)
    assert not publish.validate(report, source, now=later)[0]
    before = sidecar.read_text()
    for moved in (2.1, 1.9):
        assert not q.requote_sidecar(report, odds, post=post_price(moved), now=later)
        assert sidecar.read_text() == before
    assert not q.requote_sidecar(report, odds, post=lambda body: (500, {}), now=later)
    assert sidecar.read_text() == before
    assert q.requote_sidecar(report, odds, post=post_price(2), now=later)
    assert report.read_text() == text
    renewed = json.loads(sidecar.read_text())['combos'][0]
    assert q.quote_valid(renewed['sgm_quote'], odds, renewed['legs'], now=later)


def test_requote_refuses_a_report_that_no_longer_matches_its_sidecar(tmp_path):
    odds, text, report, source, sidecar = _quoted_report(tmp_path)
    report.write_text(text + 'edited')
    before = sidecar.read_text()
    assert not q.requote_sidecar(report, odds, post=post_price(2), now=NOW + timedelta(minutes=20))
    assert sidecar.read_text() == before


def test_report_cache_renews_same_price_quote_instead_of_regenerating(tmp_path, monkeypatch):
    import nba_orchestrator as orchestrator
    odds, text, report, source, _ = _quoted_report(tmp_path)
    stats = tmp_path/'stats.json'; stats.write_text('{}')
    monkeypatch.setattr(orchestrator, 'report_inputs', lambda *args: {'fixture': True})
    Path(str(report)+'.inputs.json').write_text(json.dumps({'inputs': {'fixture': True}, 'report': hashlib.sha256(text.encode()).hexdigest()}))
    later = NOW + timedelta(minutes=20)
    real = publish.validate
    monkeypatch.setattr(publish, 'validate', lambda r, s, **kw: real(r, s, now=later))
    real_requote = q.requote_sidecar
    for price, reused in ((2.2, False), (2, True)):
        monkeypatch.setattr(q, 'requote_sidecar', lambda path, data, price=price: real_requote(path, data, post=post_price(price), now=later))
        assert orchestrator.report_cache_current(str(report), str(source), str(stats)) is reused
