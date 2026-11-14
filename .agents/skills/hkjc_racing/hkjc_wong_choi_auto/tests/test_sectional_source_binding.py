"""Full native sectional reader integration; synthetic data, no PIT authority."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from test_auto_outputs import _logic

ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / '.agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts'
TABLE_A = {'standards': {'2026': {f'ST|1200|C4|{i}': 24.0 for i in range(3)}},
           'variant': {}, 'z': {'first_v': [0.0, 1.0], 'total_v': [0.0, 1.0]}}
TABLE_B = deepcopy(TABLE_A)
TABLE_B['standards']['2026'] = {f'ST|1200|C4|{i}': 22.0 for i in range(3)}

DRIVER = r'''
import contextlib, hashlib, io, json, sys
from pathlib import Path
repo, hk, logic_path, sequence_path, mode = map(str, sys.argv[1:])
sys.path[:0] = [repo, str(Path(repo)/'.agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts'),
               str(Path(repo)/'.agents/skills/hkjc_racing/hkjc_race_extractor/scripts')]
import wongchoi_paths
wongchoi_paths.HK_RACING = Path(hk)
import hkjc_auto_orchestrator as auto
from hkjc_racing_engine import pit_sections as ps
# Unrelated display-profile networking is isolated, not certified by this slice.
auto._get_profile_scraper = lambda: None
path = Path(hk)/'HKJC_Sections/pit_sections.json'
sequence = json.loads(Path(sequence_path).read_text())
runner = auto.HKJCAutoOrchestrator(Path(logic_path))
logic = json.loads(Path(logic_path).read_text())
values = []
for table in sequence:
    raw = json.dumps(table, sort_keys=True).encode()
    path.write_bytes(raw)
    if mode in {'bound', 'absent'} and not values:
        ps.load_table()  # Preserve a genuinely populated production cache A.
    if mode == 'absent':
        path.unlink()  # Owned fixture file only.
    kwargs = {} if mode == 'default' else {'sectional_source': ps.SectionalSource(path, None if mode == 'absent' else hashlib.sha256(raw).hexdigest())}
    with contextlib.redirect_stdout(io.StringIO()):
        value = runner.score_logic_data(Path(logic_path), logic, **kwargs)
    assert value is not None
    values.append(value)
assert json.loads(Path(logic_path).read_text()) == logic
print(json.dumps({'values': values, 'cache': ps._TABLE}, ensure_ascii=False, allow_nan=False))
'''


def case(tmp_path):
    hk = tmp_path / 'isolated-hk'
    (hk / 'HKJC_Sections').mkdir(parents=True)
    meeting = tmp_path / '2026-11-08_ShaTin'
    meeting.mkdir()
    path = meeting / 'Race_1_Logic.json'
    logic = _logic()
    logic['race_analysis'].update(race_class='第四班', distance='1200', venue='沙田', race_date='2026-11-08')
    text = ''
    for number, horse in logic['horses'].items():
        horse['_data']['recent_6_detail'] = '第1仗(01/11/2026 第四班) | 第2仗(15/10/2026 第四班)'
        text += f'\n馬號: {number}\n馬名: {horse["horse_name"]}\n負磅: 126\n往績紀錄:\n'
        for i, day in enumerate(['01/11/2026', '15/10/2026'], 1):
            text += f'  [{i}] {day} | 日數: 7 | 沙田 "A" 1200 好\n'
            text += '      負磅: 126 | 名次: 3 / 12\n      分段時間: 23.00, 23.00, 23.00\n'
    path.write_text(json.dumps(logic, ensure_ascii=False))
    (meeting / 'Synthetic Race 1 賽績.md').write_text(text)
    return hk, path


def run_native(tmp_path, hk, path, tables, *, mode='default'):
    sequence = tmp_path / 'sequence.json'
    sequence.write_text(json.dumps(tables))
    result = subprocess.run([sys.executable, '-B', '-c', DRIVER, str(ROOT), str(hk), str(path), str(sequence), mode],
        cwd=tmp_path, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr + result.stdout
    return json.loads(result.stdout)


def test_full_native_explicit_a_b_a_matches_fresh_processes_and_keeps_default_cache(tmp_path):
    hk, path = case(tmp_path)
    a = run_native(tmp_path, hk, path, [TABLE_A])['values'][0]
    b = run_native(tmp_path, hk, path, [TABLE_B])['values'][0]
    # Captured through unmodified d756 native scoring before this seam existed.
    assert a['horses']['1']['python_auto']['ability_score_raw'] == 71.30
    assert b['horses']['1']['python_auto']['ability_score_raw'] == 70.08
    assert a['horses']['1']['_data']['sectional_ft']['points'] > 0
    assert b['horses']['1']['_data']['sectional_ft']['points'] < 0
    assert a['horses']['1']['python_auto']['ability_score_raw'] != b['horses']['1']['python_auto']['ability_score_raw']
    observed = run_native(tmp_path, hk, path, [TABLE_A, TABLE_B, TABLE_A], mode='bound')
    assert observed['values'] == [a, b, a]
    assert observed['cache'] == TABLE_A
    assert sorted(p.name for p in path.parent.iterdir()) == ['Race_1_Logic.json', 'Synthetic Race 1 賽績.md']


def test_existing_production_cache_policy_is_retained(tmp_path):
    hk, path = case(tmp_path)
    observed = run_native(tmp_path, hk, path, [TABLE_A, TABLE_B])
    assert observed['values'][0] == observed['values'][1]
    assert observed['cache'] == TABLE_A


def test_explicit_absence_never_falls_back_to_warm_production_cache(tmp_path):
    hk, path = case(tmp_path)
    observed = run_native(tmp_path, hk, path, [TABLE_A], mode='absent')
    assert observed['cache'] == TABLE_A
    assert 'sectional_ft' not in observed['values'][0]['horses']['1']['_data']
    # Absence binds a resource; it must not silently clear already embedded data.
    logic = json.loads(path.read_text())
    logic['horses']['1']['_data']['sectional_ft'] = {'first_v': 0.2, 'total_v': 0.2, 'points': 0.945}
    path.write_text(json.dumps(logic))
    retained = run_native(tmp_path, hk, path, [TABLE_A], mode='absent')
    assert retained['values'][0]['horses']['1']['_data']['sectional_ft'] == logic['horses']['1']['_data']['sectional_ft']


@pytest.mark.parametrize('fault', ['missing', 'changed_hash', 'symlink', 'parent_symlink',
    'empty', 'oversize', 'truncated', 'duplicate_key', 'nonfinite', 'overflow_float',
    'not_object', 'bad_utf8', 'utf16', 'utf8_bom', 'fifo', 'declared_absent_exists', 'relative', 'bad_hash', 'untyped'])
def test_binding_failure_precedes_all_native_enrichment_and_publication(tmp_path, monkeypatch, fault):
    import hkjc_auto_orchestrator as auto
    from hkjc_racing_engine import pit_sections as ps
    from unittest.mock import Mock
    source_path = tmp_path / 'sections.json'
    raw = json.dumps(TABLE_A).encode()
    source_path.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    if fault == 'missing': source_path.unlink()
    elif fault == 'changed_hash': source_path.write_bytes(json.dumps(TABLE_B).encode())
    elif fault == 'symlink':
        original = tmp_path / 'actual.json'
        source_path.rename(original)
        source_path.symlink_to(original)
    elif fault == 'parent_symlink':
        link = tmp_path / 'linked'
        link.symlink_to(tmp_path, target_is_directory=True)
        source_path = link / 'sections.json'
    elif fault == 'fifo':
        source_path.unlink()
        os.mkfifo(source_path)
    elif fault == 'oversize':
        with source_path.open('r+b') as handle: handle.truncate(ps.MAX_SOURCE_BYTES + 1)
    elif fault in {'empty', 'truncated', 'duplicate_key', 'nonfinite', 'overflow_float', 'not_object', 'bad_utf8', 'utf16', 'utf8_bom'}:
        raw = {'empty': b'', 'truncated': b'{', 'duplicate_key': b'{"z":{},"z":{}}',
               'nonfinite': b'{"z":NaN}', 'overflow_float': b'{"z":1e999}', 'not_object': b'[]', 'bad_utf8': b'{\xff}', 'utf16': json.dumps(TABLE_A).encode('utf-16'), 'utf8_bom': b'\xef\xbb\xbf' + json.dumps(TABLE_A).encode()}[fault]
        source_path.write_bytes(raw)
        digest = hashlib.sha256(raw).hexdigest()
    elif fault == 'declared_absent_exists': digest = None
    elif fault == 'relative': source_path = Path('sections.json')
    elif fault == 'bad_hash': digest = 'A' * 64
    source = {} if fault == 'untyped' else ps.SectionalSource(source_path, digest)
    logic_path = tmp_path / 'Race_1_Logic.json'
    logic = _logic()
    logic_path.write_text(json.dumps(logic))
    before = logic_path.read_bytes()
    entered = Mock()
    monkeypatch.setattr(auto, '_align_runner_headers', entered)
    cache = {'sentinel': True}
    monkeypatch.setattr(ps, '_TABLE', cache)
    with pytest.raises((ValueError, OSError)):
        auto.HKJCAutoOrchestrator(logic_path).score_logic_data(logic_path, logic, sectional_source=source)
    entered.assert_not_called()
    assert ps._TABLE is cache and logic_path.read_bytes() == before
    assert not list(tmp_path.glob('*Auto*')) and not list(tmp_path.glob('*.jsonl'))


@pytest.mark.parametrize('mutation', ['rewrite', 'replace_same_bytes'])
def test_real_descriptor_read_rejects_concurrent_mutation(tmp_path, monkeypatch, mutation):
    from hkjc_racing_engine import pit_sections as ps
    path = tmp_path / 'sections.json'
    raw = json.dumps(TABLE_A).encode()
    path.write_bytes(raw)
    original = ps.os.fdopen
    class DuringRead:
        def __init__(self, handle): self.handle = handle
        def __enter__(self): return self
        def __exit__(self, *args): return self.handle.__exit__(*args)
        def fileno(self): return self.handle.fileno()
        def read(self, size):
            data = self.handle.read(size)
            if mutation == 'rewrite': path.write_bytes(json.dumps(TABLE_B).encode())
            else:
                replacement = tmp_path / 'replacement.json'
                replacement.write_bytes(raw)
                replacement.replace(path)
            return data
    monkeypatch.setattr(ps.os, 'fdopen', lambda *args, **kwargs: DuringRead(original(*args, **kwargs)))
    with pytest.raises(ValueError, match='changed or hash differs'):
        ps.read_bound_table(ps.SectionalSource(path, hashlib.sha256(raw).hexdigest()))
