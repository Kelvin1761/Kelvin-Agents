"""Synthetic metadata tests; never read real blind candidate outcomes."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import subprocess

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import au_shadow_state as state  # noqa: E402
import au_speed_shadow_monitor as speed  # noqa: E402
import au_speed_recency_shadow as recency  # noqa: E402


def hashed(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize('corruption', ['missing_hash', 'wrong_payload', 'missing_config', 'bad_count', 'missing_visible'])
def test_started_collection_cannot_accept_unbound_config(corruption):
    current = speed.config()
    existing = {'config': copy.deepcopy(current), 'races_collected': 1, 'outcomes_visible': False}
    if corruption == 'missing_hash':
        existing['config'].pop('config_sha256')
    elif corruption == 'wrong_payload':
        existing['config']['target_races'] += 1
    elif corruption == 'missing_config':
        existing.pop('config')
    elif corruption == 'bad_count':
        existing['races_collected'] = True
    else:
        existing.pop('outcomes_visible')
    with pytest.raises(ValueError):
        state.validate_config_record(existing, current)


def test_valid_existing_hash_and_empty_precollection_policy_are_preserved():
    cfg = speed.config()
    state.validate_config_record({'config': cfg, 'races_collected': 1, 'outcomes_visible': False}, cfg)
    state.validate_config_record({'config': {'config_sha256': 'old'}, 'races_collected': 0, 'outcomes_visible': False}, cfg)
    state.validate_config_record({}, cfg)


@pytest.fixture(params=['speed', 'recency'])
def monitor(request, monkeypatch):
    module = speed if request.param == 'speed' else recency
    monkeypatch.setattr(module, 'TARGET_RACES', 2)
    rows = [
        {'date': '2026-09-27', 'venue': 'Fixture', 'race': 1, 'runners': []},
        {'date': '2026-09-28', 'venue': 'Fixture', 'race': 1, 'runners': []},
        {'date': '2026-09-28', 'venue': 'Fixture', 'race': 2, 'runners': []},
    ]
    if module is speed:
        monkeypatch.setattr(speed, 'scored_meeting_index', lambda root: [])
        monkeypatch.setattr(speed, 'collect_reference_races', lambda root: ([], 0))
        monkeypatch.setattr(speed, 'build_asof_standards', lambda *args: {})
        monkeypatch.setattr(speed, 'load_races', lambda *args: copy.deepcopy(rows))
        monkeypatch.setattr(speed, 'race_rows', lambda value: value)
    else:
        monkeypatch.setattr(recency, 'load_terminal', lambda root: copy.deepcopy(rows))
    return module, rows


def evaluator(module, monkeypatch, path, fail):
    def evaluate(rows, **kwargs):
        blind = json.loads(path.read_text())
        assert blind['state'] == 'terminal_frozen'
        assert blind['outcomes_visible'] is False and 'evaluation' not in blind
        assert blind['sample_payload_sha256'] == state.content_hash(rows)
        if fail:
            raise RuntimeError('injected evaluation failure')
        if module is speed:
            keys = [speed.race_key(row) for row in rows]
            return {'config': speed.config(), 'state': 'ready_for_manual_stage4_review',
                    'outcomes_visible': True, 'races_collected': len(rows),
                    'date_to': rows[-1]['date'], 'locked_race_keys': keys,
                    'sample_sha256': state.keys_hash(keys)}
        return {'synthetic_metadata_fixture': True}
    monkeypatch.setattr(module, 'build_status' if module is speed else 'evaluate', evaluate)


def test_failure_seals_whole_day_and_resume_ignores_later_rows(monitor, tmp_path, monkeypatch):
    module, rows = monitor
    path = tmp_path / 'status.json'
    evaluator(module, monkeypatch, path, True)
    with pytest.raises(RuntimeError, match='injected'):
        module.run(tmp_path, path)
    first = json.loads(path.read_text())
    assert first['races_collected'] == 3
    assert first['locked_through_date'] == '2026-09-28'
    rows.append({'date': '2026-09-29', 'venue': 'Fixture', 'race': 1, 'runners': []})
    evaluator(module, monkeypatch, path, False)
    final = module.run(tmp_path, path)
    assert final['locked_race_keys'] == first['locked_race_keys']
    assert final['sample_sha256'] == first['sample_sha256']
    assert final['sample_payload_sha256'] == first['sample_payload_sha256']
    assert final['races_collected'] == 3
    original_hash = hashed(path)
    def forbidden(*args, **kwargs):
        raise AssertionError('already-revealed monitor must not load/evaluate/rewrite')
    monkeypatch.setattr(module, 'collect_reference_races' if module is speed else 'load_terminal', forbidden)
    monkeypatch.setattr(module, 'build_status' if module is speed else 'evaluate', forbidden)
    assert module.run(tmp_path, path) == final
    assert hashed(path) == original_hash


def test_changed_frozen_input_fails_without_overwriting_checkpoint(monitor, tmp_path, monkeypatch):
    module, rows = monitor
    path = tmp_path / 'status.json'
    evaluator(module, monkeypatch, path, True)
    with pytest.raises(RuntimeError):
        module.run(tmp_path, path)
    first_hash = hashed(path)
    rows[0]['new_input'] = 'changed'
    with pytest.raises(ValueError, match='payload changed'):
        module.run(tmp_path, path)
    assert hashed(path) == first_hash


def test_duplicate_race_identity_is_rejected_before_evaluation(monitor, tmp_path, monkeypatch):
    module, rows = monitor
    rows.append(copy.deepcopy(rows[0]))
    path = tmp_path / 'status.json'
    evaluator(module, monkeypatch, path, True)
    with pytest.raises(ValueError, match='identity duplicate'):
        module.run(tmp_path, path)
    assert not path.exists()


def test_legacy_reveal_is_retained_without_manufacturing_payload_seal(monitor, tmp_path, monkeypatch):
    module, _ = monitor
    path = tmp_path / 'status.json'
    legacy = {'config': module.config(), 'races_collected': 2, 'outcomes_visible': True,
              'state': 'revealed', 'date_to': '2026-09-28', 'sample_sha256': 'a' * 64,
              'evaluation': {'legacy_fixture_not_recalculated': True}}
    path.write_text(json.dumps(legacy))
    original_hash = hashed(path)
    def forbidden(*args, **kwargs):
        raise AssertionError('legacy reveal cannot be automatically rerun')
    monkeypatch.setattr(module, 'collect_reference_races' if module is speed else 'load_terminal', forbidden)
    assert module.run(tmp_path, path) == legacy
    assert 'sample_payload_sha256' not in module.run(tmp_path, path)
    assert hashed(path) == original_hash


def test_sealed_keys_cannot_disappear_silently():
    rows = [{'date': '2026-09-27', 'venue': 'Fixture', 'race': 1}]
    with pytest.raises(ValueError, match='keys missing'):
        state.freeze_complete_day_sample(rows, {'state': 'terminal_frozen'}, 1,
                                         key_fn=speed.race_key, day_selector=speed.select_complete_date_sample)


def test_os_lock_rejects_parallel_owner_and_releases_on_error(tmp_path):
    path = tmp_path / 'status.json'
    with pytest.raises(RuntimeError, match='injected owner error'):
        with state.exclusive_status_lock(path):
            with pytest.raises(RuntimeError, match='owned by another'):
                with state.exclusive_status_lock(path):
                    raise AssertionError('parallel owner entered')
            raise RuntimeError('injected owner error')
    # Persistent lock-file presence is not an active lock.
    with state.exclusive_status_lock(path):
        assert not path.exists()


def test_actual_monitor_refuses_locked_status_before_loading(monitor, tmp_path):
    module, _ = monitor
    path = tmp_path / 'status.json'
    with state.exclusive_status_lock(path):
        with pytest.raises(RuntimeError, match='owned by another'):
            module.run(tmp_path, path)
    assert not path.exists()


def test_lock_blocks_a_separate_process(tmp_path):
    path = tmp_path / 'status.json'
    code = '''
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from au_shadow_state import exclusive_status_lock
try:
    with exclusive_status_lock(Path(sys.argv[2])):
        raise AssertionError('second process entered locked status')
except RuntimeError as exc:
    assert 'owned by another' in str(exc)
print('PASS: independent process blocked')
'''
    with state.exclusive_status_lock(path):
        child = subprocess.run([sys.executable, '-B', '-c', code,
                                str(Path(state.__file__).parent), str(path)],
                               env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'),
                               text=True, capture_output=True)
    assert child.returncode == 0, child.stdout + child.stderr
