"""Complete native CSV + daily-result reader parity, using synthetic data only."""
import csv
import io
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from test_sectional_source_binding import ROOT, case


def database_files(version='A'):
    use_variant = version == 'V'
    if use_variant: version = 'A'
    files = {}
    columns = ['Date', 'Venue', 'Track', 'Distance', 'RaceNo', 'RaceClass', 'Horse',
               'HorseID', 'Rank', 'FinishTimeSec', 'Jockey', 'Trainer', 'Win', 'Place', 'Odds', 'Profit']
    for season, day, code, seconds in [('24_25', '2024-11-01', 'A001', 72 if version == 'A' else 75),
                                      ('25_26', '2025-11-01', 'A002', 73)]:
        row = [day, '沙田', 'Turf', 1200, 1, '第四班', f'合成({code})', code, 1,
               seconds, '測試騎師', '測試練馬師', 1, 1, 2.0, 1.0]
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(columns); writer.writerow(row)
        files[f'comprehensive_stats/{season}/race_results_{season}.csv'] = stream.getvalue()
    for day, times in [('2026-11-01', ('1:11.00', '1:12.00') if version == 'A' else ('1:14.00', '1:10.00')),
                       ('2026-11-09', ('1:00.00', '1:01.00'))]:
        payload = {'1': {'race_no': 1, 'venue': 'ShaTin',
            'sectional_times': [['第四班 - 1200米 - (60-40)', '場地狀況 :', '好地'],
                                ['合成讓賽', '賽道 :', '草地 - "A" 賽道']],
            'results': [{'pos': str(index), 'horse_name': f'合成(A00{index})',
                         'finish_time': seconds, 'jockey': '測試騎師', 'trainer': '測試練馬師', 'win_odds': '2.0'}
                        for index, seconds in enumerate(times, 1)]}}
        files[f'hkjc results 2026 27/{day}/full_day_results.json'] = json.dumps(payload, ensure_ascii=False)
    if use_variant:
        for season in ['24_25', '25_26']:
            key = f'comprehensive_stats/{season}/race_results_{season}.csv'
            records = list(csv.DictReader(io.StringIO(files[key])))
            for record in records:
                record['Horse'] = '背景(Z999)'; record['HorseID'] = 'Z999'
            if season == '24_25':
                for index in range(10):
                    row = dict(records[0])
                    row.update(Date=f'2024-10-{index + 1:02d}', Horse=f'背景(Z{index:03d})',
                               HorseID=f'Z{index:03d}', FinishTimeSec='70.0')
                    records.append(row)
            stream = io.StringIO(); writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader(); writer.writerows(records); files[key] = stream.getvalue()
    return files


def history_case(tmp_path):
    hk, path = case(tmp_path)
    logic = json.loads(path.read_text())
    for number, horse in logic['horses'].items(): horse['horse_code'] = 'A00' + number
    path.write_text(json.dumps(logic))
    return hk, path


DRIVER = r'''
import contextlib, io, json, sys
from pathlib import Path
repo, hk, logic_path, request_path, mode = sys.argv[1:]
sys.path[:0] = [repo, str(Path(repo)/'.agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts'),
               str(Path(repo)/'.agents/skills/hkjc_racing/hkjc_race_extractor/scripts')]
import wongchoi_paths
wongchoi_paths.HK_RACING = Path(hk)
import hkjc_auto_orchestrator as auto
# The profile reader is outside this slice; its networking is explicitly isolated.
auto._get_profile_scraper = lambda: None
logic = json.loads(Path(logic_path).read_text())
root = Path(hk)/'HKJC_Race_Results_Database'
results = []
initial_history = None
for files in json.loads(Path(request_path).read_text()):
    for relative, content in files.items():
        path = root/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    kwargs = {}
    if mode in {'bound', 'absent_warm'}:
        import hkjc_same_course_times as same_course
        if not results:
            with contextlib.redirect_stdout(io.StringIO()):
                same_course._history()  # Populate actual default A before strict calls.
            initial_history = json.loads(json.dumps(same_course._HISTORY))
            def forbidden(): raise AssertionError('strict route used default HOT loader')
            same_course._load_rows = forbidden
        from hkjc_racing_engine.completed_sources import CompletedRowsSource, observe_catalog_sha256
        kwargs['same_course_source'] = (CompletedRowsSource(root, observe_catalog_sha256(root)) if mode == 'bound'
                                       else CompletedRowsSource(root.parent/'missing-db', None))
    with contextlib.redirect_stdout(io.StringIO()):
        value = auto.HKJCAutoOrchestrator(Path(logic_path)).score_logic_data(Path(logic_path), logic, **kwargs)
    assert value is not None
    observation = value['python_auto_run_contract'].pop('bound_source_observation', None)
    assert (observation is not None) == bool(kwargs)
    if observation is not None:
        assert observation['schema_version'] == 'native-source-observation/v1'
        assert set(observation['source_names']) == {key[:-7] for key in kwargs}
        assert observation['bytes_read'] >= sum(row['size'] for row in observation['files'].values())
        assert all(len(row['sha256']) == 64 and len(row['observed_identity']) == 6 for row in observation['files'].values())
    results.append(value)
assert json.loads(Path(logic_path).read_text()) == logic
import hkjc_same_course_times as same_course
print(json.dumps({'values': results, 'initial_history': initial_history, 'history': same_course._HISTORY},
                 ensure_ascii=False, allow_nan=False))
'''


def run_history(tmp_path, hk, path, versions, *, mode="default"):
    request = tmp_path / 'history-sequence.json'
    request.write_text(json.dumps([database_files(v) for v in versions]))
    process = subprocess.run([sys.executable, '-B', '-c', DRIVER, str(ROOT), str(hk), str(path), str(request), mode],
        cwd=tmp_path, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}, capture_output=True, text=True, timeout=30)
    assert process.returncode == 0, process.stderr + process.stdout
    return json.loads(process.stdout)


def test_existing_same_course_cache_policy_is_retained(tmp_path):
    hk, path = history_case(tmp_path)
    results = run_history(tmp_path, hk, path, ['A', 'B'])['values']
    assert results[0] == results[1]
    assert '1:11.00' in results[0]['horses']['1']['_data']['same_course_best_time']
    assert '1:00.00' not in results[0]['horses']['1']['_data']['same_course_best_time']


def test_bound_native_history_a_b_a_matches_fresh_csv_and_daily_outputs(tmp_path):
    hk, path = history_case(tmp_path)
    a = run_history(tmp_path, hk, path, ['A'])['values'][0]
    b = run_history(tmp_path, hk, path, ['B'])['values'][0]
    assert '1:11.00' in a['horses']['1']['_data']['same_course_best_time']
    assert '1:14.00' in b['horses']['1']['_data']['same_course_best_time']
    assert '全場第 2/2' in b['horses']['1']['_data']['same_course_best_time']
    observed = run_history(tmp_path, hk, path, ['A', 'B', 'A'], mode='bound')
    assert observed['values'] == [a, b, a]
    assert observed['history'] == observed['initial_history']
    assert sorted(p.name for p in path.parent.iterdir()) == ['Race_1_Logic.json', 'Synthetic Race 1 賽績.md']


def write_database(root, version='A'):
    for relative, content in database_files(version).items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)


def test_actual_standard_and_variant_branch_matches_full_native_output(tmp_path):
    hk, path = history_case(tmp_path)
    reference = run_history(tmp_path, hk, path, ['V'])['values'][0]
    observed = run_history(tmp_path, hk, path, ['V'], mode='bound')['values'][0]
    assert observed == reference
    text = reference['horses']['1']['_data']['same_course_best_time']
    assert '最佳 1:11.00（扣場地快慢 1:10.00' in text


@pytest.mark.parametrize('fault', ['add_season', 'add_day', 'missing_base', 'base_cutoff_changed',
    'daily_changed', 'missing_daily', 'malformed_daily', 'symlink', 'unreadable', 'untyped', 'bad_hash'])
def test_catalog_changes_or_failures_block_before_native_enrichment(tmp_path, monkeypatch, fault):
    from unittest.mock import Mock
    import hkjc_auto_orchestrator as auto
    from hkjc_racing_engine import completed_sources as source
    hk, logic_path = history_case(tmp_path)
    root = hk / 'HKJC_Race_Results_Database'
    write_database(root)
    binding = source.CompletedRowsSource(root, source.observe_catalog_sha256(root))
    daily = root / 'hkjc results 2026 27/2026-11-01/full_day_results.json'
    if fault == 'add_season': (root / 'hkjc results 2027 28').mkdir()
    elif fault == 'add_day': (root / 'hkjc results 2026 27/zz-extra').mkdir()
    elif fault == 'missing_base': (root / 'comprehensive_stats/24_25/race_results_24_25.csv').unlink()
    elif fault == 'base_cutoff_changed':
        base = root / 'comprehensive_stats/24_25/race_results_24_25.csv'
        base.write_text(base.read_text().replace('2024-11-01', '2027-11-01'))
    elif fault == 'daily_changed': daily.write_text('{}')
    elif fault == 'missing_daily': daily.unlink()
    elif fault == 'malformed_daily': daily.write_text('{')
    elif fault == 'symlink':
        moved = root / 'actual.json'; daily.rename(moved); daily.symlink_to(moved)
    elif fault == 'unreadable':
        original = source.capture_source_file
        def denied(path, **kwargs):
            if Path(path) == daily: raise PermissionError('fixture unreadable')
            return original(path, **kwargs)
        monkeypatch.setattr(source, 'capture_source_file', denied)
    elif fault == 'untyped': binding = {}
    elif fault == 'bad_hash': binding = source.CompletedRowsSource(root, 'bad')
    entered, events = Mock(), Mock()
    monkeypatch.setattr(auto, '_align_runner_headers', entered)
    before = logic_path.read_bytes()
    with pytest.raises((ValueError, OSError, RuntimeError)):
        auto.HKJCAutoOrchestrator(logic_path).score_logic_data(logic_path, json.loads(before),
            same_course_source=binding, event_sink=events)
    entered.assert_not_called(); events.assert_not_called()
    assert logic_path.read_bytes() == before and not list(logic_path.parent.glob('*Auto*'))


def test_missing_daily_is_bound_absence_and_its_later_appearance_blocks(tmp_path, monkeypatch):
    from unittest.mock import Mock
    import hkjc_auto_orchestrator as auto
    from hkjc_racing_engine import completed_sources as source
    hk, logic_path = history_case(tmp_path)
    root = hk / 'HKJC_Race_Results_Database'
    write_database(root)
    missing = root / 'hkjc results 2026 27/zz-extra/full_day_results.json'
    missing.parent.mkdir()
    binding = source.CompletedRowsSource(root, source.observe_catalog_sha256(root))
    assert not source.read_bound_rows(binding).empty
    missing.write_text('{}')
    entered = Mock(); monkeypatch.setattr(auto, '_align_runner_headers', entered)
    with pytest.raises(ValueError, match='hash differs'):
        auto.HKJCAutoOrchestrator(logic_path).score_logic_data(logic_path, json.loads(logic_path.read_text()),
                                                           same_course_source=binding)
    entered.assert_not_called()


def test_catalog_does_not_read_large_unrelated_file(tmp_path, monkeypatch):
    from hkjc_racing_engine import completed_sources as source
    hk, _path = history_case(tmp_path)
    root = hk / 'HKJC_Race_Results_Database'
    write_database(root)
    unrelated = root / 'unused-large.bin'
    with unrelated.open('wb') as handle: handle.truncate(17 * 1024 * 1024)
    original = source.capture_source_file
    observed = []
    def checked(path, **kwargs):
        assert Path(path) != unrelated
        observed.append(Path(path)); return original(path, **kwargs)
    monkeypatch.setattr(source, 'capture_source_file', checked)
    digest = source.observe_catalog_sha256(root)
    assert len(observed) == 4
    assert not source.read_bound_rows(source.CompletedRowsSource(root, digest)).empty


def test_native_loader_import_never_resolves_default_data_root(tmp_path):
    script = ROOT / '.agents/scripts/hkjc_completed_rows.py'
    code = r"""
import builtins, importlib.util, sys
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name in {'wongchoi_paths', 'build_comprehensive_stats'}:
        raise AssertionError('default data discovery during import')
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
spec = importlib.util.spec_from_file_location('isolated_native_rows', sys.argv[1])
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
assert not hasattr(module, 'DB_ROOT') and not hasattr(module, 'SEASONS')
"""
    result = subprocess.run([sys.executable, '-B', '-c', code, str(script)], cwd=tmp_path,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_capture_rechecks_selected_inode_and_namespaces(tmp_path, monkeypatch):
    from hkjc_racing_engine import completed_sources as source
    hk, _path = history_case(tmp_path)
    root = hk / 'HKJC_Race_Results_Database'
    write_database(root)
    target = root / 'comprehensive_stats/24_25/race_results_24_25.csv'
    original = source.capture_source_file
    def replaced(path, **kwargs):
        value = original(path, **kwargs)
        if Path(path) == target:
            replacement = root / 'replacement.csv'
            replacement.write_bytes(target.read_bytes()); replacement.replace(target)
        return value
    monkeypatch.setattr(source, 'capture_source_file', replaced)
    with pytest.raises(ValueError, match='changed during capture'):
        source.observe_catalog_sha256(root)


def test_base_csv_cutoff_uses_native_comparison_without_date_pattern_filter(tmp_path, monkeypatch):
    from hkjc_racing_engine import completed_sources as source
    hk, _path = history_case(tmp_path)
    root = hk / 'HKJC_Race_Results_Database'
    write_database(root)
    old = root / 'hkjc results 2024 25/2024-10-31/full_day_results.json'
    selected = root / 'hkjc results 2024 25/2024-11-02/full_day_results.json'
    old.parent.mkdir(parents=True); old.write_text('{')  # Native cutoff excludes it.
    selected.parent.mkdir(parents=True); selected.write_text('{}')
    original = source.capture_source_file
    observed = []
    def recorded(path, **kwargs): observed.append(Path(path)); return original(path, **kwargs)
    monkeypatch.setattr(source, 'capture_source_file', recorded)
    digest = source.observe_catalog_sha256(root)
    assert selected in observed and old not in observed
    base = root / 'comprehensive_stats/24_25/race_results_24_25.csv'
    base.write_text(base.read_text().replace('2024-11-01', '2024-12-01'))
    selected.write_text('{')  # Newly excluded after holding the changed CSV cutoff.
    with pytest.raises(ValueError, match='hash differs'):
        source.read_bound_rows(source.CompletedRowsSource(root, digest))
    observed.clear()
    newer = source.observe_catalog_sha256(root)
    assert selected not in observed and old not in observed
    assert not source.read_bound_rows(source.CompletedRowsSource(root, newer)).empty


@pytest.mark.parametrize('bound', ['entries', 'bytes'])
def test_catalog_capacity_rejects_without_partial_output(tmp_path, monkeypatch, bound):
    from unittest.mock import Mock
    import hkjc_auto_orchestrator as auto
    from hkjc_racing_engine import completed_sources as source
    hk, path = history_case(tmp_path)
    root = hk / 'HKJC_Race_Results_Database'; write_database(root)
    binding = source.CompletedRowsSource(root, source.observe_catalog_sha256(root))
    monkeypatch.setattr(source, 'MAX_ENTRIES' if bound == 'entries' else 'MAX_CATALOG_BYTES', 1)
    entered = Mock(); monkeypatch.setattr(auto, '_align_runner_headers', entered)
    with pytest.raises(ValueError, match='bound'):
        auto.HKJCAutoOrchestrator(path).score_logic_data(path, json.loads(path.read_text()), same_course_source=binding)
    entered.assert_not_called()


def test_held_rows_remain_independent_after_source_files_change(tmp_path):
    import hkjc_completed_rows as native
    from hkjc_racing_engine import completed_sources as source
    hk, _path = history_case(tmp_path)
    root = hk / 'HKJC_Race_Results_Database'; write_database(root)
    context, _digest = source._capture(root)
    original = native.load_all_completed_rows(context)
    write_database(root, 'B')
    assert native.load_all_completed_rows(context).equals(original)


def test_explicit_absence_never_consults_warmed_history_or_clears_embedded_fields(tmp_path):
    hk, path = history_case(tmp_path)
    logic = json.loads(path.read_text())
    logic['horses']['1']['_data']['same_course_best_time'] = 'already embedded'
    path.write_text(json.dumps(logic))
    observed = run_history(tmp_path, hk, path, ['A'], mode='absent_warm')
    result = observed['values'][0]
    assert result['horses']['1']['_data']['same_course_best_time'] == 'already embedded'
    assert 'same_course_best_time' not in result['horses']['2']['_data']
    assert observed['history'] == observed['initial_history']


@pytest.mark.parametrize('alias_first', [False, True])
def test_ambiguous_season_aliases_reject_before_any_file_read(tmp_path, monkeypatch, alias_first):
    from hkjc_racing_engine import completed_sources as source
    hk, _path = history_case(tmp_path)
    root = hk / 'HKJC_Race_Results_Database'
    alias = root / ' hkjc results 2026 27'
    if alias_first: alias.mkdir(parents=True)
    write_database(root)
    if not alias_first: alias.mkdir()
    calls = []
    original = source.capture_source_file
    def recorded(path, **kwargs): calls.append(path); return original(path, **kwargs)
    monkeypatch.setattr(source, 'capture_source_file', recorded)
    with pytest.raises(ValueError, match='ambiguous'):
        source.observe_catalog_sha256(root)
    assert calls == []


def test_cumulative_budget_stops_before_consuming_second_file(tmp_path, monkeypatch):
    from hkjc_racing_engine import completed_sources as source, native_sources
    hk, _path = history_case(tmp_path)
    root = hk / 'HKJC_Race_Results_Database'; write_database(root)
    first = root / 'comprehensive_stats/24_25/race_results_24_25.csv'
    second = root / 'comprehensive_stats/25_26/race_results_25_26.csv'
    monkeypatch.setattr(source, 'MAX_CATALOG_BYTES', first.stat().st_size + 1)
    original = native_sources.os.fdopen
    consumed = []
    class Reader:
        def __init__(self, handle): self.handle = handle
        def __enter__(self): return self
        def __exit__(self, *args): return self.handle.__exit__(*args)
        def fileno(self): return self.handle.fileno()
        def read(self, size):
            consumed.append(os.fstat(self.fileno()).st_ino)
            return self.handle.read(size)
    monkeypatch.setattr(native_sources.os, 'fdopen', lambda *a, **k: Reader(original(*a, **k)))
    with pytest.raises(ValueError, match='bound'):
        source.observe_catalog_sha256(root)
    assert first.stat().st_ino in consumed and second.stat().st_ino not in consumed


@pytest.mark.parametrize('version,expected', [
    ('A', 'f113ac9b0b10f3963a0c0e4d8c01b0770588bf2a6716e77129485509ab17e17b'),
    ('B', '4ea703a529fadd6174835ce63d631fa88f79755a40c2935bcce0e00c6f956eee'),
    ('V', '3e5b5389f57d140db70453483dad16baf836d68b7cf6bb8e5ce753bd0e7724e6'),
])
def test_full_native_output_matches_clean_pre_extraction_a6_source(tmp_path, version, expected):
    import hashlib
    # Captured from clean a6c21a96, not from this extracted implementation.
    hk, path = history_case(tmp_path)
    value = run_history(tmp_path, hk, path, [version])['values'][0]
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    assert hashlib.sha256(raw).hexdigest() == expected
