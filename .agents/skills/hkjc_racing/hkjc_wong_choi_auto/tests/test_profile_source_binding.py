"""Native profile-cache source binding; synthetic full-scorer parity only."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest
from test_sectional_source_binding import ROOT, case


def cache(rating=70, *, timestamp=None):
    result = {}
    for number in ['1', '2']:
        identity = 'HK_SYNTH_' + number
        result[identity] = {'_ts': time.time() if timestamp is None else timestamp,
            'data': {'horse_id': identity, 'entries': [
                {'date': '01/11/2026', 'class_grade': '4', 'placing': 1, 'rating': rating,
                 'running_positions': [1, 2, 3], 'jockey': '何澤堯'},
                {'date': '15/10/2026', 'class_grade': '4', 'placing': 3, 'rating': rating - 5,
                 'running_positions': [8, 6, 3], 'jockey': '潘頓'},
                {'date': '09/11/2026', 'class_grade': '4', 'placing': 1, 'rating': 999,
                 'running_positions': [1, 1, 1], 'jockey': '潘頓'}], 'error': None}}
    return result


DRIVER = r'''
import contextlib, hashlib, io, json, sys
from pathlib import Path
repo, hk, logic_path, sequence_path, mode = sys.argv[1:]
sys.path[:0] = [repo, str(Path(repo)/'.agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts'),
               str(Path(repo)/'.agents/skills/hkjc_racing/hkjc_race_extractor/scripts')]
import wongchoi_paths
wongchoi_paths.HK_RACING = Path(hk)
import requests
calls = []
def no_network(*args, **kwargs):
    calls.append('network')
    raise AssertionError('unexpected network')
requests.get = no_network
import hkjc_auto_orchestrator as auto
payload = json.loads(Path(sequence_path).read_text())
sequence, sectionals = payload['profiles'], payload['sectionals']
logic = json.loads(Path(logic_path).read_text())
runner = auto.HKJCAutoOrchestrator(Path(logic_path))
path = (Path.cwd()/'.hkjc_cache/profile_cache.json' if mode in {'default', 'bound', 'absent_warm'}
        else Path.cwd()/'explicit-profile.json')
path.parent.mkdir(exist_ok=True)
values = []
initial_cache = None
for index, item in enumerate(sequence):
    raw = json.dumps(item, sort_keys=True).encode()
    path.write_bytes(raw)
    if mode in {'bound', 'absent_warm'} and not values:
        auto._get_profile_scraper()  # Actual legacy import/cache load A, no lookup.
        import scrape_hkjc_horse_profile as legacy
        initial_cache = json.loads(json.dumps(legacy._profile_cache))
    kwargs = {}
    if mode in {'bound', 'clean_bound', 'combined', 'absent', 'absent_warm'}:
        from hkjc_racing_engine.native_sources import JsonSource
        if mode in {'absent', 'absent_warm'}:
            path.unlink()  # Owned fixture file only.
        kwargs['profile_source'] = JsonSource(path, None if mode in {'absent', 'absent_warm'} else hashlib.sha256(raw).hexdigest())
    if sectionals is not None:
        section_raw = json.dumps(sectionals[index], sort_keys=True).encode()
        if mode == 'default':
            (Path(hk)/'HKJC_Sections/pit_sections.json').write_bytes(section_raw)
        else:
            from hkjc_racing_engine.native_sources import JsonSource
            section_path = Path(hk)/'explicit-sections.json'
            section_path.write_bytes(section_raw)
            kwargs['sectional_source'] = JsonSource(section_path, hashlib.sha256(section_raw).hexdigest())
    with contextlib.redirect_stdout(io.StringIO()):
        value = runner.score_logic_data(Path(logic_path), logic, **kwargs)
    assert value is not None
    observation = value['python_auto_run_contract'].pop('bound_source_observation', None)
    assert (observation is not None) == bool(kwargs)
    if observation is not None:
        assert observation['schema_version'] == 'native-source-observation/v1'
        assert set(observation['source_names']) == {key[:-7] for key in kwargs}
        assert observation['bytes_read'] >= sum(row['size'] for row in observation['files'].values())
        assert all(len(row['sha256']) == 64 and len(row['observed_identity']) == 6 for row in observation['files'].values())
    values.append(value)
assert not calls, 'native reader attempted network fallback'
assert json.loads(Path(logic_path).read_text()) == logic
legacy = sys.modules.get('scrape_hkjc_horse_profile')
print(json.dumps({'values': values, 'initial_cache': initial_cache,
    'cache': legacy._profile_cache if legacy else None, 'scraper_imported': legacy is not None,
    'cwd_cache_exists': (Path.cwd()/'.hkjc_cache').exists(),
    'sectional_cache': __import__('hkjc_racing_engine.pit_sections', fromlist=['_TABLE'])._TABLE}, ensure_ascii=False, allow_nan=False))
'''


def profile_case(tmp_path):
    hk, path = case(tmp_path)
    logic = json.loads(path.read_text())
    for number, horse in logic['horses'].items():
        horse['trackwork']['horseid'] = 'HK_SYNTH_' + number
    path.write_text(json.dumps(logic))
    return hk, path


def run_profiles(tmp_path, hk, path, sequence, *, mode='default', sectionals=None):
    request = tmp_path / 'profile-sequence.json'
    request.write_text(json.dumps({'profiles': sequence, 'sectionals': sectionals}))
    proc = subprocess.run([sys.executable, '-B', '-c', DRIVER, str(ROOT), str(hk), str(path), str(request), mode],
        cwd=tmp_path, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}, capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    return json.loads(proc.stdout)


def test_explicit_profile_a_b_a_keeps_full_native_results_and_legacy_cache(tmp_path):
    hk, path = profile_case(tmp_path)
    a, b = cache(70), cache(40)
    reference_a = run_profiles(tmp_path, hk, path, [a])['values'][0]
    reference_b = run_profiles(tmp_path, hk, path, [b])['values'][0]
    assert reference_a['horses']['1']['_data']['rating_high_3s'] == 70
    assert reference_b['horses']['1']['_data']['rating_high_3s'] == 40
    # Explicit byte-bound sources do not consult the live scraper's TTL policy.
    a_old, b_old = cache(70, timestamp=0), cache(40, timestamp=0)
    observed = run_profiles(tmp_path, hk, path, [a_old, b_old, a_old], mode='bound')
    assert observed['values'] == [reference_a, reference_b, reference_a]
    assert observed['cache'] == observed['initial_cache'] == a_old


def test_clean_explicit_profile_does_not_import_scraper_or_create_cache(tmp_path):
    hk, path = profile_case(tmp_path)
    observed = run_profiles(tmp_path, hk, path, [cache(timestamp=0)], mode='clean_bound')
    assert observed['values'][0]['horses']['1']['_data']['rating_high_3s'] == 70
    assert observed['scraper_imported'] is False and observed['cwd_cache_exists'] is False
    assert sorted(p.name for p in path.parent.iterdir()) == ['Race_1_Logic.json', 'Synthetic Race 1 賽績.md']


def test_existing_profile_import_cache_policy_remains_unchanged(tmp_path):
    hk, path = profile_case(tmp_path)
    a, b = cache(70), cache(40)
    observed = run_profiles(tmp_path, hk, path, [a, b])
    assert observed['values'][0] == observed['values'][1]
    assert observed['cache'] == a and observed['cwd_cache_exists'] is True


def test_combined_profile_and_sectional_binding_matches_fresh_full_native_references(tmp_path):
    from test_sectional_source_binding import TABLE_A, TABLE_B
    hk, path = profile_case(tmp_path)
    a, b = cache(70), cache(40)
    ref_a = run_profiles(tmp_path, hk, path, [a], sectionals=[TABLE_A])['values'][0]
    ref_b = run_profiles(tmp_path, hk, path, [b], sectionals=[TABLE_B])['values'][0]
    assert ref_a['horses']['1']['python_auto']['ability_score_raw'] == 71.30
    assert ref_b['horses']['1']['python_auto']['ability_score_raw'] == 70.08
    result = run_profiles(tmp_path, hk, path, [cache(70, timestamp=0), cache(40, timestamp=0), cache(70, timestamp=0)],
                          mode='combined', sectionals=[TABLE_A, TABLE_B, TABLE_A])
    assert result['values'] == [ref_a, ref_b, ref_a]
    assert result['sectional_cache'] is None and result['scraper_imported'] is False


@pytest.mark.parametrize('warm', [False, True])
def test_explicit_profile_absence_does_not_fall_back_or_clear_embedded_fields(tmp_path, warm):
    hk, path = profile_case(tmp_path)
    logic = json.loads(path.read_text())
    logic['horses']['1']['_data']['rating_high_3s'] = 777
    path.write_text(json.dumps(logic))
    result = run_profiles(tmp_path, hk, path, [cache(70)], mode='absent_warm' if warm else 'absent')
    assert result['values'][0]['horses']['1']['_data']['rating_high_3s'] == 777
    assert 'rating_high_3s' not in result['values'][0]['horses']['2']['_data']
    assert result['scraper_imported'] is warm and result['cwd_cache_exists'] is warm
    if warm: assert result['cache'] == result['initial_cache']


@pytest.mark.parametrize('fault', ['missing_file', 'hash_changed', 'bad_hash', 'symlink',
    'truncated', 'duplicate_key', 'nonfinite', 'utf16', 'missing_horse', 'wrong_horse',
    'record_not_object', 'boolean_timestamp', 'data_not_object', 'entries_not_list',
    'invalid_entry', 'unknown_cutoff', 'declared_absence_exists', 'untyped_source'])
def test_profile_binding_rejects_before_native_enrichment(tmp_path, monkeypatch, fault):
    from unittest.mock import Mock
    import hkjc_auto_orchestrator as auto
    from hkjc_racing_engine.native_sources import JsonSource
    hk, logic_path = profile_case(tmp_path)
    body = cache()
    record = body['HK_SYNTH_1']
    if fault == 'missing_horse': del body['HK_SYNTH_1']
    elif fault == 'wrong_horse': record['data']['horse_id'] = 'HK_OTHER'
    elif fault == 'record_not_object': body['HK_SYNTH_1'] = []
    elif fault == 'boolean_timestamp': record['_ts'] = True
    elif fault == 'data_not_object': record['data'] = None
    elif fault == 'entries_not_list': record['data']['entries'] = {}
    elif fault == 'invalid_entry': record['data']['entries'] = ['not a row']
    raw = json.dumps(body).encode()
    if fault == 'truncated': raw = b'{'
    elif fault == 'duplicate_key': raw = b'{"x":1,"x":2}'
    elif fault == 'nonfinite': raw = b'{"x":NaN}'
    elif fault == 'utf16': raw = json.dumps(body).encode('utf-16')
    source_path = tmp_path / 'profile.json'
    source_path.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    if fault == 'missing_file': source_path.unlink()
    elif fault == 'hash_changed': source_path.write_bytes(json.dumps(cache(30)).encode())
    elif fault == 'bad_hash': digest = 'not-a-hash'
    elif fault == 'symlink':
        actual = tmp_path / 'profile-actual.json'
        source_path.rename(actual)
        source_path.symlink_to(actual)
    elif fault == 'declared_absence_exists': digest = None
    logic = json.loads(logic_path.read_text())
    if fault == 'unknown_cutoff':
        logic['race_analysis'].pop('race_date')
        # The original fixture parent names a date; move to an undated location.
        logic_path = tmp_path / 'Race_1_Logic.json'
        logic_path.write_text(json.dumps(logic))
    source = {} if fault == 'untyped_source' else JsonSource(source_path, digest)
    before = logic_path.read_bytes()
    enriched, live_reader, events = Mock(), Mock(side_effect=AssertionError('live lookup')), Mock()
    monkeypatch.setattr(auto, '_align_runner_headers', enriched)
    monkeypatch.setattr(auto, '_get_profile_scraper', live_reader)
    monkeypatch.chdir(tmp_path)
    with pytest.raises((ValueError, OSError)):
        auto.HKJCAutoOrchestrator(logic_path).score_logic_data(logic_path, logic,
            event_sink=events, profile_source=source)
    enriched.assert_not_called()
    live_reader.assert_not_called()
    events.assert_not_called()
    assert logic_path.read_bytes() == before and not (tmp_path / '.hkjc_cache').exists()


def test_strict_profile_lookup_error_is_not_swallowed_and_never_calls_live_reader(monkeypatch):
    from unittest.mock import Mock
    import hkjc_auto_orchestrator as auto
    live_reader = Mock(side_effect=AssertionError('live reader must not run'))
    monkeypatch.setattr(auto, '_get_profile_scraper', live_reader)
    def failed(identity): raise ValueError('bound lookup failed')
    with pytest.raises(ValueError, match='bound lookup failed'):
        auto._enrich_profile_history({'1': {'trackwork': {'horseid': 'HK_SYNTH_1'}}}, profile_reader=failed)
    live_reader.assert_not_called()
