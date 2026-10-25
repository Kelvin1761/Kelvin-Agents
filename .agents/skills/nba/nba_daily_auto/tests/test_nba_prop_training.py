from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
import nba_market_ledger as ledger
import nba_prop_training as training

TIP = datetime(2026, 10, 22, 23, tzinfo=timezone.utc)
CUTOFF = TIP - timedelta(hours=4)
DAY, TAG = '2026-10-23', 'BOS_LAL'
LEG = dict(player='Test Star', team='BOS', market='pts', line=20., side='over', price=1.8,
           p_final=.72, probability_model_id='calibrated:test', picked=True)


def setup_snapshot(folder):
    source = dict(status='available', season='2026-27', sample_games=2,
                  captured_at=(CUTOFF-timedelta(minutes=2)).isoformat(), history_date_to='10/21/2026',
                  source_sha256='a'*64, row_sha256='b'*64)
    game = {'meta': {'date': TIP.isoformat(), 'away': {'abbr': 'BOS'}, 'home': {'abbr': 'LAL'}},
            'players': {'BOS': [{'name': 'Test Star', 'player_id': 123,
                'gamelog': {'PTS': [25]*8+[10]*2, 'MIN': [30]*10,
                            'l10_dates': [f'2026-10-{d}' for d in range(21, 11, -1)]},
                'opportunity_features': {'contract': 'nba-opportunities/v1',
                    'sources': {'player_base': source}, 'opponent_source': deepcopy(source),
                    'props': {'PTS': {'two_pa_per_min': .4, 'ft_conversion': None}},
                    'history_reference': {'status': 'dated_prior_history'}}}]}}
    folder.mkdir()
    path = folder/f'nba_game_data_{TAG}.json'
    path.write_text(json.dumps(game))
    manifest = {'created_at': CUTOFF.isoformat(), 'game_tags': [TAG], 'snapshot_role': 'production',
                'files': [{'name': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}]}
    (folder/'manifest.json').write_text(json.dumps(manifest))
    report = folder/f'Game_{TAG}_Full_Analysis.md'
    report.write_text('synthetic full report')
    (folder/(report.name+ledger.SIDECAR_SUFFIX)).write_text(json.dumps({
        'report_sha256': hashlib.sha256(report.read_bytes()).hexdigest(), 'legs': [LEG],
        'odds_extraction_time': (CUTOFF-timedelta(minutes=1)).isoformat()}))
    (folder/f'Sportsbet_Odds_{TAG}.json').write_text(json.dumps({
        'target_analysis_date': DAY, 'event_start_time': TIP.isoformat(),
        'extraction_time': (CUTOFF-timedelta(minutes=1)).isoformat(), 'player_props': {}}))
    return training.snapshot_source(folder, manifest, TAG, TIP, tip_source='official_schedule'), manifest


def model_row(feature, **changes):
    return dict(row_type='model_obs', target_date=DAY, game_tag=TAG, player=LEG['player'], market='pts',
                line=20., side='over', snapshot_id='snap1', snapshot_role='production',
                snapshot_created_at=CUTOFF.isoformat(), recorded_at=(CUTOFF+timedelta(minutes=1)).isoformat(),
                odds_captured_at=(CUTOFF-timedelta(minutes=1)).isoformat(), tip_off=TIP.isoformat(),
                tip_source='official_schedule',
                post_tip=False, late_write=False, tip_unknown=False, prop_training=feature,
                p_final=.72, price_at_model=1.8, probability_model_id='calibrated:test', picked=True, **changes)


def settlement(**changes):
    return dict(row_type='settlement', target_date=DAY, game_tag=TAG, player=LEG['player'], market='pts',
                line=20., side='over', outcome='hit', y=1, settled_at=(TIP+timedelta(hours=3)).isoformat(),
                results_sha256='c'*64, verify_status='✅ HIT') | changes


def test_native_snapshot_capture_and_separate_final_target(tmp_path):
    source, _ = setup_snapshot(tmp_path/'snap')
    feature = training.observation(source, LEG)
    assert feature['status'] == 'opportunity_captured'
    assert feature['eligible_80_80'] and feature['inputs']['hit_l10'] == .8
    assert feature['inputs']['opportunity']['ft_conversion'] is None
    rows, excluded = training.dataset([model_row(feature), settlement()])
    assert not excluded and rows[0]['target']['y'] == 1
    assert rows[0]['baseline']['probability'] == .72
    assert not any(k in rows[0]['inputs'] for k in ['y', 'p_final', 'price'])


def test_real_extractor_month_name_dates_and_recomputed_threshold(tmp_path):
    source, _ = setup_snapshot(tmp_path/'snap')
    gl = source['game']['players']['BOS'][0]['gamelog']
    gl['l10_dates'] = [datetime.fromisoformat(d).strftime('%b %d, %Y').upper() for d in gl['l10_dates']]
    assert training.observation(source, LEG)['eligible_80_80']
    gl['PTS'][0] = 1
    assert not training.observation(source, LEG)['eligible_80_80']


@pytest.mark.parametrize('change', ['same_day', 'duplicate_date', 'wrong_player', 'wrong_team', 'half_line'])
def test_history_and_identity_fail_closed(tmp_path, change):
    source, _ = setup_snapshot(tmp_path/'snap')
    leg = deepcopy(LEG)
    gl = source['game']['players']['BOS'][0]['gamelog']
    if change == 'same_day': gl['l10_dates'][0] = '2026-10-22'
    if change == 'duplicate_date': gl['l10_dates'][0] = gl['l10_dates'][1]
    if change == 'wrong_player': leg['player'] = 'Other Star'
    if change == 'wrong_team': leg['team'] = 'LAL'
    if change == 'half_line': leg['line'] = 20.5
    assert training.observation(source, leg)['status'] != 'opportunity_captured'


@pytest.mark.parametrize('change', ['future_capture', 'same_day_cutoff', 'wrong_season', 'zero_GP', 'bad_hash'])
def test_opportunity_provenance_masks_inputs(tmp_path, change):
    source, _ = setup_snapshot(tmp_path/'snap')
    record = source['game']['players']['BOS'][0]['opportunity_features']['sources']['player_base']
    if change == 'future_capture': record['captured_at'] = TIP.isoformat()
    if change == 'same_day_cutoff': record['history_date_to'] = '10/22/2026'
    if change == 'wrong_season': record['season'] = '2025-26'
    if change == 'zero_GP': record['sample_games'] = 0
    if change == 'bad_hash': record['source_sha256'] = 'bad'
    out = training.observation(source, LEG)
    assert out['status'] == 'base_only' and not out['inputs']['opportunity']


def test_manifest_hash_and_tip_identity(tmp_path):
    source, manifest = setup_snapshot(tmp_path/'snap')
    assert source['status'] == 'bound'
    assert training.snapshot_source(tmp_path/'snap', manifest, TAG, TIP+timedelta(hours=1), tip_source='official_schedule')['status'] != 'bound'
    (tmp_path/'snap'/f'nba_game_data_{TAG}.json').write_text('{}')
    assert training.snapshot_source(tmp_path/'snap', manifest, TAG, TIP, tip_source='official_schedule')['status'] == 'game_hash_mismatch'


def test_latest_missing_feature_does_not_resurrect_older(tmp_path):
    source, _ = setup_snapshot(tmp_path/'snap')
    old = model_row(training.observation(source, LEG))
    new = dict(old, snapshot_id='snap2', snapshot_created_at=(CUTOFF+timedelta(minutes=1)).isoformat(),
               prop_training={'status': 'not_captured'})
    assert not training.dataset([old, new, settlement()])[0]


@pytest.mark.parametrize('change', ['late', 'warmup', 'no_prediction', 'malformed_timestamps', 'bookie_tip'])
def test_unpublished_rows_never_train(tmp_path, change):
    source, _ = setup_snapshot(tmp_path/'snap')
    row = model_row(training.observation(source, LEG))
    rows = [row, settlement()]
    if change == 'late': row.update(late_write=True)
    if change == 'warmup': row.update(snapshot_role='warmup')
    if change == 'malformed_timestamps': row.update(recorded_at=None)
    if change == 'bookie_tip': row.update(tip_source='sportsbet_event_start')
    if change == 'no_prediction': rows.append(dict(row_type='no_prediction', target_date=DAY, game_tag=None))
    assert not training.dataset(rows)[0]


@pytest.mark.parametrize('target', [settlement(outcome='void', y=None), settlement(results_sha256='bad'),
                                  settlement(settled_at=CUTOFF.isoformat()), settlement(verify_status=None)])
def test_void_or_unverified_target_not_a_loss(tmp_path, target):
    source, _ = setup_snapshot(tmp_path/'snap')
    row = model_row(training.observation(source, LEG))
    records, _ = training.dataset([row, target])
    assert records[0]['target']['y'] is None


def test_labels_available_after_calibration_cutoff_stay_unknown(tmp_path):
    source, _ = setup_snapshot(tmp_path/'snap')
    row = model_row(training.observation(source, LEG))
    records, _ = training.dataset([row, settlement()], as_of=TIP+timedelta(hours=1))
    assert records[0]['target']['y'] is None


def test_broken_optional_schema_is_visible_and_does_not_break_predictions(tmp_path):
    source, manifest = setup_snapshot(tmp_path/'snap')
    manifest['files'] = None
    assert training.snapshot_source(tmp_path/'snap', manifest, TAG, TIP, tip_source='official_schedule')['status'] == 'snapshot_source_error'
    source['game']['players']['BOS'][0]['gamelog']['PTS'] = 7
    observed = training.observation(source, LEG)
    assert observed['status'] == 'observation_error'
    summary = training.summary([model_row(observed)])
    assert summary['excluded']['feature_status:observation_error'] == 1


def test_standalone_bookie_time_cannot_be_official_proof(tmp_path):
    _, manifest = setup_snapshot(tmp_path/'snap')
    assert training.snapshot_source(tmp_path/'snap', manifest, TAG, TIP)['status'] == 'official_schedule_missing'


def test_normal_record_snapshot_wiring_and_c_metrics_parity(tmp_path, monkeypatch):
    snap = tmp_path/'snap'
    setup_snapshot(snap)
    root = tmp_path/'ledger'
    monkeypatch.setenv(ledger.ENV_ROOT, str(root))
    ledger.record_snapshot(snap, DAY, event_starts={TAG: TIP}, now=CUTOFF+timedelta(minutes=1), root=root)
    rows = ledger.read_rows(root, DAY)
    model = next(r for r in rows if r['row_type'] == 'model_obs')
    assert model['prop_training']['status'] == 'opportunity_captured'
    before = ledger.evaluate(root=root)
    stripped = [{k: v for k, v in r.items() if k != 'prop_training'} for r in rows]
    monkeypatch.setattr(ledger, 'read_rows', lambda *a: stripped)
    after = ledger.evaluate(root=root)
    assert before['overall'] == after['overall']
    assert before['by_probability_model'] == after['by_probability_model']
    assert before['prop_training_evidence']['feature_rows'] == 1
    assert after['prop_training_evidence']['feature_rows'] == 0
