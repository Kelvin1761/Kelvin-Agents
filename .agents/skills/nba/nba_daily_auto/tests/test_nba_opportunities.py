"""Future opportunity rows remain separate from betting probabilities."""
import json
from pathlib import Path
import sys
from datetime import datetime
from unittest import mock
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import nba_opportunities as op

TIP = '2026-10-26T00:00:00Z'
CUTOFF = '10/24/2026'
CAPTURE = '2026-10-25T05:00:00Z'


def bundle():
    common = {'PLAYER_ID': 1, 'TEAM_ID': 10, 'TEAM_ABBREVIATION': 'GS', 'GP': 2, 'MIN': 30}
    rows = {
        'passing': {**common, 'POTENTIAL_AST': 12, 'AST': 6},
        'rebounding': {**common, 'OREB_CHANCES': 4, 'DREB_CHANCES': 10, 'OREB': 2, 'DREB': 5, 'REB_CONTEST_PCT': .4},
        'possessions': {**common, 'GP': 1, 'TOUCHES': 60, 'TIME_OF_POSS': 6},
        'catch_shoot': {**common, 'CATCH_SHOOT_FG3A': 4},
        'pull_up': {**common, 'PULL_UP_FG3A': 2},
        'player_base': {**common, 'FGA': 20, 'FGM': 10, 'FG3A': 6, 'FG3M': 2, 'FTA': 4, 'FTM': 3},
        'team_base': {'TEAM_ID': 20, 'GP': 3, 'MIN': 48, 'FGA': 90, 'FGM': 40, 'OREB': 9},
    }
    return {'contract': op.CONTRACT, 'sources': {name: {'season': '2026-27', 'history_date_to': CUTOFF,
            'status': 'available', 'unit': 'Per100Possessions' if name == 'team_base' else 'PerGame',
            'captured_at': CAPTURE, 'rows': [row]} for name, row in rows.items()}}


def player():
    return {'player_id': 1, 'advanced': {'USG_PCT': 25, 'AST_PCT': 30},
            'gamelog': {'l10_dates': ['2026-10-23', '2026-10-21'], 'MIN': [30, 30],
                        'FGA': [20, 20], 'FGM': [10, 10], 'FG3A': [6, 6], 'FG3M': [2, 2],
                        'FTA': [4, 4], 'FTM': [3, 3]}}


def features(data=None, p=None, **kwargs):
    return op.build_features(p or player(), 'GSW', 20, data or bundle(), tip=TIP, season='2026-27', cutoff=CUTOFF, **kwargs)


def test_prop_inputs_have_separate_denominators_and_opponent_meanings():
    f = features()
    assert f['model_input_enabled'] is False
    assert f['props']['PTS']['two_pa_per_min'] == pytest.approx(28 / 60)
    assert f['props']['AST']['potential_ast_per_min'] == .4
    assert f['props']['AST']['potential_ast_conversion'] == .5
    assert f['props']['AST']['touches_per_min'] == 2  # separate GP; no mixed GP conversion
    assert f['props']['REB']['opponent_own_fg_misses_per100'] == 50
    assert f['props']['REB']['dreb_chances_per_min'] == 1 / 3
    assert f['props']['FG3M']['catch_shoot_3pa_per_min'] == 4 / 30
    assert 'potential_ast_per_min' not in f['props']['PTS']
    assert 'usage_pct' not in f['props']['REB']
    assert not any('prob' in key or 'ev' in key for key in f)


@pytest.mark.parametrize('mutation,status', [('late', 'not_verified_pregame'), ('season', 'wrong_season_or_cutoff'),
                                            ('cutoff', 'wrong_season_or_cutoff'), ('team', 'identity_missing_or_ambiguous'),
                                            ('duplicate', 'identity_missing_or_ambiguous'), ('sample', 'insufficient_sample')])
def test_invalid_tracking_rows_cannot_supply_a_signal(mutation, status):
    b = bundle(); source = b['sources']['passing']
    if mutation == 'late': source['captured_at'] = TIP
    if mutation == 'season': source['season'] = '2025-26'
    if mutation == 'cutoff': source['history_date_to'] = '10/23/2026'
    if mutation == 'team': source['rows'][0]['TEAM_ABBREVIATION'] = 'BOS'
    if mutation == 'duplicate': source['rows'] *= 2
    if mutation == 'sample': source['rows'][0]['GP'] = 0
    f = features(b)
    assert f['sources']['passing']['status'] == status
    assert f['props']['AST']['potential_ast_per_min'] is None


def test_missing_player_id_never_matches_unique_team_row():
    p = player();p.pop('player_id')
    assert features(p=p)['sources']['passing']['status'] == 'player_id_missing'


def test_zero_opportunities_unknown_conversion_and_no_infinite_value():
    b = bundle();b['sources']['passing']['rows'][0].update(AST=0, POTENTIAL_AST=0)
    f = features(b)
    assert f['props']['AST']['potential_ast_per_min'] == 0
    assert f['props']['AST']['potential_ast_conversion'] is None
    json.dumps(f, allow_nan=False)


def test_unknown_or_current_game_history_does_not_create_scoring_rates():
    p = player();p['gamelog']['l10_dates'][0] = '2026-10-25'
    f = features(p=p)
    assert f['history_reference']['status'] == 'unverified'
    assert f['props']['PTS']['two_pa_per_min'] == pytest.approx(14 / 30)
    assert f['box_reference']['source'] == 'current_season_base'
    b = bundle(); b['sources']['player_base']['status'] = 'unavailable'
    assert features(b, p)['props']['PTS']['two_pa_per_min'] is None


def test_opponent_allowed_rows_need_own_provenance_and_remain_distinct():
    stats = {'opponent_stats': {'season': '2026-27', 'history_date_to': CUTOFF, 'captured_at': CAPTURE,
             'modes': {'per_100_possessions': {'status': 'available', 'games': 3, 'values': {'OPP_REB': 42}}}}}
    f = features(opponent_stats=stats)
    assert f['props']['REB']['opponent_rebounds_allowed_per100'] == 42
    assert f['props']['REB']['opponent_own_fg_misses_per100'] == 50
    stats['opponent_stats']['season'] = '2025-26'
    assert features(opponent_stats=stats)['props']['REB']['opponent_rebounds_allowed_per100'] is None


def test_cache_reuses_only_same_hash_matched_season_cutoff_and_age(tmp_path):
    source = bundle();source.update(season='2026-27', history_date_to=CUTOFF, captured_at=CAPTURE)
    source['sources_sha256'] = op.digest(source['sources'])
    path = tmp_path / 'cache.json';path.write_text(json.dumps(source))
    now = datetime.fromisoformat(CAPTURE.replace('Z', '+00:00'))
    with mock.patch.object(op, 'request_table', side_effect=AssertionError('must use cache')):
        assert op.fetch_sources('2026-27', CUTOFF, path, now=now) == source
    source['sources']['passing']['rows'][0]['GP'] = 999
    path.write_text(json.dumps(source))
    with mock.patch.object(op, 'request_table', return_value={'status': 'unavailable'}) as fetch:
        result = op.fetch_sources('2026-27', CUTOFF, path, now=now)
    assert fetch.call_count == 7 and result['sources']['passing']['status'] == 'unavailable'


def test_request_preserves_all_fields_and_failure_is_explicit():
    payload = {'resultSets': [{'headers': ['PLAYER_ID', 'TEAM_ID', 'TEAM_ABBREVIATION', 'GP', 'MIN', 'POTENTIAL_AST'],
                               'rowSet': [[1, 10, 'GSW', 2, 30, 12]]}]}
    api = mock.Mock(return_value=mock.Mock(get_dict=lambda: payload))
    source = op.request_table('passing', '2026-27', CUTOFF, api)
    assert source['rows'][0]['POTENTIAL_AST'] == 12
    assert source['params']['date_to_nullable'] == CUTOFF
    assert source['params']['per_mode_simple'] == 'PerGame'
    assert op.request_table('passing', '2026-27', CUTOFF, mock.Mock(side_effect=TimeoutError()))['status'] == 'unavailable'


def test_disabling_new_capture_does_not_call_endpoints_or_write_cache(tmp_path, monkeypatch):
    monkeypatch.setenv('WC_NBA_OPPORTUNITIES', '0')
    with mock.patch.object(op, 'request_table', side_effect=AssertionError('no query')):
        result = op.fetch_sources('2026-27', CUTOFF, tmp_path / 'cache.json')
    assert result['status'] == 'disabled' and not list(tmp_path.iterdir())


def test_same_event_us_day_is_never_a_valid_history_cutoff():
    b = bundle(); b['sources']['passing']['history_date_to'] = '10/25/2026'
    result = op.verified_row(b, 'passing', tip=TIP, season='2026-27', cutoff='10/25/2026', player_id=1, team='GSW')
    assert result['status'] == 'history_not_prior_to_event'


def test_health_exposes_missing_sources_instead_of_claiming_complete():
    b = bundle();b['sources']['passing']['status'] = 'unavailable'
    f = features(b)
    health = op.summarize({'GSW': [{'opportunity_features': f}]})
    assert health['source_status_counts']['passing'] == {'source_unavailable': 1}
    assert health['nonmissing_by_prop']['AST']['potential_ast_per_min'] == 0
    assert health['model_input_enabled'] is False


def test_normal_extractor_attaches_features_and_coverage_without_changing_advanced_inputs():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'nba_data_extractor/scripts'))
    import nba_extractor as extractor
    game = {'name': 'Golden State Warriors at Los Angeles Lakers', 'date': TIP,
            'away': {'name': 'Golden State Warriors', 'abbreviation': 'GSW'},
            'home': {'name': 'Los Angeles Lakers', 'abbreviation': 'LAL'}}
    roster = [{'name': 'Synthetic Test', 'player_id': 1, 'position': 'G', 'age': 25}]
    advanced = {1: {'USG_PCT': 25}}
    with mock.patch.object(extractor, 'fetch_team_roster', side_effect=lambda name, *args, **kwargs: roster if 'Golden State' in name or name == 'GSW' else []), \
         mock.patch.object(extractor, 'fetch_team_injuries', return_value={}), \
         mock.patch.object(extractor, 'fetch_nba_news', return_value=[]), \
         mock.patch.object(extractor, 'fetch_player_gamelog', return_value=player()['gamelog']), \
         mock.patch.object(extractor, 'fetch_player_splits', return_value={}), \
         mock.patch.object(extractor, 'fetch_player_h2h', return_value=None), \
         mock.patch.object(extractor, 'compute_prop_analytics', return_value={}), \
         mock.patch.object(extractor, 'compute_fatigue_adjustment', return_value={}):
        package = extractor.extract_single_game(game, advanced, {}, {}, {}, {}, opportunity_sources=bundle())
    entry = package['players']['GSW'][0]
    assert entry['opportunity_features']['props']['AST']['potential_ast_per_min'] == .4
    assert entry['advanced'] == advanced[1]
    assert package['meta']['opportunity_health']['nonmissing_by_prop']['AST']['potential_ast_per_min'] == 1
