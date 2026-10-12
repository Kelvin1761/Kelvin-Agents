from copy import deepcopy
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import au_serve_prediction_adapter as adapter
from au_prediction_intake import content_hash, PredictionValidationError


def fixture_bundle(tmp_path):
    logic = tmp_path / "Race_1_Logic.json"
    logic.write_text('{}')
    inp = {"logic_path": str(logic), "runner_ids": ["1", "2", "3", "4"]}
    assets = [{"path": str(logic), "sha256": adapter._file_hash(logic), "audit": "PASS",
               "available_at": "2026-08-05T09:00:00+10:00"}]
    environment = {"PYTHONDONTWRITEBYTECODE": "1", "WC_DISABLE_POST_SUCCESS_DEPLOY": "1"}
    audit_path = tmp_path / "independent-audit.json"
    audit = {"status": "PASS", "scope": "complete_serving_reads", "race_id": "2026-08-05/test/1",
             "input_hash": content_hash(inp), "assets_hash": content_hash(assets),
             "prediction_at": "2026-08-05T12:00:00+10:00", "environment_hash": content_hash(environment)}
    audit_path.write_text(json.dumps(audit))
    inp["serving_bundle"] = {"assets": assets, "audit_artifact": {"path": str(audit_path),
                            "sha256": adapter._file_hash(audit_path)}}
    race = {"race_id": audit["race_id"], "date": "2026-08-05", "prediction_at": audit["prediction_at"], "input": inp}
    code_paths = [Path(adapter.__file__), Path(adapter.__file__).with_name("au_auto_orchestrator.py")]
    profile = {"fitted": False, "environment": environment,
               "serving_code": [{"path": str(p), "sha256": adapter._file_hash(p)} for p in code_paths]}
    return race, profile, audit_path, audit


def test_adapter_isolated_environment_and_safety_ranking(tmp_path, monkeypatch):
    race, profile, _, _ = fixture_bundle(tmp_path)
    before = deepcopy(race)
    result = {"ability": {"1": 70, "2": 69, "3": 68, "4": 67}, "ranking": ["2", "1", "3", "4"]}
    def run(command, **kwargs):
        assert command[-1] == '--worker' and '-B' in command
        assert kwargs['env'] == profile['environment']
        assert kwargs['check'] is True
        assert json.loads(kwargs['input'])['state'] is None
        return SimpleNamespace(stdout=json.dumps(result))
    monkeypatch.setattr(adapter.subprocess, 'run', run)
    actual = adapter.predict_production(race, None, profile)
    assert actual['ranking'] == result['ranking']  # never sort ability to undo the swap
    assert actual['ability'] == result['ability']
    assert race == before


@pytest.mark.parametrize('failure', ['audit_changed', 'source_changed', 'extra_labels', 'fitted_state'])
def test_adapter_fails_before_scorer(tmp_path, monkeypatch, failure):
    race, profile, audit_path, _ = fixture_bundle(tmp_path)
    state = None
    if failure == 'audit_changed':
        audit_path.write_text('{}')
    elif failure == 'source_changed':
        Path(race['input']['logic_path']).write_text('{"changed":true}')
    elif failure == 'extra_labels':
        race['labels'] = {"1": 1}
    else:
        state = {"matrix_weights": {}}
    def forbidden(*args, **kwargs):
        raise AssertionError('scorer launched for invalid input')
    monkeypatch.setattr(adapter.subprocess, 'run', forbidden)
    with pytest.raises(PredictionValidationError):
        adapter.predict_production(race, state, profile)


def test_incomplete_or_future_source_audit_is_rejected(tmp_path, monkeypatch):
    race, profile, audit_path, audit = fixture_bundle(tmp_path)
    audit['scope'] = 'logic_only'
    audit_path.write_text(json.dumps(audit))
    race['input']['serving_bundle']['audit_artifact']['sha256'] = adapter._file_hash(audit_path)
    with pytest.raises(PredictionValidationError, match='serving_source_audit_not_passed'):
        adapter.predict_production(race, None, profile)
    audit['scope'] = 'complete_serving_reads'
    assets = race['input']['serving_bundle']['assets']
    assets[0]['available_at'] = '2026-08-05T13:00:00+10:00'
    audit['assets_hash'] = content_hash(assets)
    audit_path.write_text(json.dumps(audit))
    race['input']['serving_bundle']['audit_artifact']['sha256'] = adapter._file_hash(audit_path)
    with pytest.raises(PredictionValidationError, match='serving_future_or_flagged_source'):
        adapter.predict_production(race, None, profile)


def test_source_change_during_scoring_is_not_fallback(tmp_path, monkeypatch):
    race, profile, _, _ = fixture_bundle(tmp_path)
    def run(*args, **kwargs):
        Path(race['input']['logic_path']).write_text('{"changed":true}')
        return SimpleNamespace(stdout='{}')
    monkeypatch.setattr(adapter.subprocess, 'run', run)
    with pytest.raises(PredictionValidationError, match='serving_asset_changed'):
        adapter.predict_production(race, None, profile)


def test_worker_rejects_dropped_dimensions():
    with pytest.raises(PredictionValidationError, match='serving_dimension_keys_changed'):
        adapter._score_worker({'state': {'matrix_weights': {'unknown': 1}}})


def add_absent_asset(race, audit_path, audit, path, observed_at):
    bundle = race['input']['serving_bundle']
    bundle['assets'].append({'path': str(path), 'state': 'absent', 'sha256': None,
                             'audit': 'PASS', 'observed_absent_at': observed_at})
    audit['assets_hash'] = content_hash(bundle['assets'])
    audit_path.write_text(json.dumps(audit))
    bundle['audit_artifact']['sha256'] = adapter._file_hash(audit_path)


def test_audited_absence_accepted_without_invented_hash(tmp_path, monkeypatch):
    race, profile, audit_path, audit = fixture_bundle(tmp_path)
    add_absent_asset(race, audit_path, audit, tmp_path / 'missing-cache.json',
                     '2026-08-05T09:00:00+10:00')
    monkeypatch.setattr(adapter.subprocess, 'run', lambda *a, **k: SimpleNamespace(stdout='{}'))
    assert adapter.predict_production(race, None, profile)['serving_audit_hash']


def test_absent_asset_appearing_during_scoring_rejected(tmp_path, monkeypatch):
    race, profile, audit_path, audit = fixture_bundle(tmp_path)
    missing = tmp_path / 'missing-cache.json'
    add_absent_asset(race, audit_path, audit, missing, '2026-08-05T09:00:00+10:00')
    def run(*args, **kwargs):
        missing.write_text('{}')
        return SimpleNamespace(stdout='{}')
    monkeypatch.setattr(adapter.subprocess, 'run', run)
    with pytest.raises(PredictionValidationError, match='absent_serving_asset_appeared'):
        adapter.predict_production(race, None, profile)


def test_future_absence_observation_rejected(tmp_path, monkeypatch):
    race, profile, audit_path, audit = fixture_bundle(tmp_path)
    add_absent_asset(race, audit_path, audit, tmp_path / 'missing-cache.json',
                     '2026-08-05T13:00:00+10:00')
    def forbidden(*args, **kwargs):
        raise AssertionError('scorer launched for future absence observation')
    monkeypatch.setattr(adapter.subprocess, 'run', forbidden)
    with pytest.raises(PredictionValidationError, match='serving_future_or_flagged_source'):
        adapter.predict_production(race, None, profile)


def test_unknown_asset_state_rejected(tmp_path, monkeypatch):
    race, profile, audit_path, audit = fixture_bundle(tmp_path)
    assets = race['input']['serving_bundle']['assets']
    assets[0]['state'] = 'optional_ignore'
    audit['assets_hash'] = content_hash(assets)
    audit_path.write_text(json.dumps(audit))
    race['input']['serving_bundle']['audit_artifact']['sha256'] = adapter._file_hash(audit_path)
    with pytest.raises(PredictionValidationError, match='invalid_serving_asset_state'):
        adapter.predict_production(race, None, profile)
