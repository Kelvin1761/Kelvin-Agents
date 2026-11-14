from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared_wong_choi.immutable_snapshot import create_immutable_snapshot
from shared_wong_choi.contracts import Domain
from shared_wong_choi.domain_evidence import record_prediction_decision
from shared_wong_choi.evidence import DecisionState
from shared_wong_choi.research_prediction_artifacts import inspect_prediction_artifacts
from test_domain_evidence import register_model


NAME = 'Research_Source_File_Metadata.json'
AT = datetime(2026, 8, 26, 10, tzinfo=timezone.utc)


def hkjc_writer():
    root = Path(__file__).resolve().parents[4]
    path = root / '.agents/skills/hkjc_racing/hkjc_daily_auto/hkjc_daily_schedule.py'
    spec = importlib.util.spec_from_file_location('hkjc_replay_metadata_schedule', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.create_prediction_snapshot


def test_au_prospective_metadata_binds_mtime_and_preserves_prior_capture(tmp_path):
    source = tmp_path / 'Race_1_Facts.md'
    source.write_bytes(b'facts\n')
    os.chmod(source, 0o640)
    os.utime(source, ns=(1700000000000000000, 1700000000123456789))
    def capture(at):
        return create_immutable_snapshot(tmp_path, domain='au', event_id='fixture',
            patterns=['*.md'], at=at, capture_file_metadata=True)
    first = capture(AT)
    raw = (first / NAME).read_bytes()
    item = json.loads(raw)['files'][0]
    assert item == {'name': source.name, 'bytes': 6,
                    'sha256': hashlib.sha256(b'facts\n').hexdigest(),
                    'mtime_ns': 1700000000123456789, 'mode': 0o640}
    assert capture(AT + timedelta(seconds=1)) == first
    os.utime(source, ns=(1700000000000000000, 1700000001123456789))
    second = capture(AT + timedelta(seconds=2))
    assert second != first
    assert (first / NAME).read_bytes() == raw
    assert (first / source.name).stat().st_mtime_ns == item['mtime_ns']
    assert (second / source.name).stat().st_mtime_ns == source.stat().st_mtime_ns


def test_actual_hkjc_future_writer_emits_hash_bound_source_metadata(tmp_path):
    meeting = tmp_path / '2026-09-06_ShaTin'; meeting.mkdir()
    (meeting / 'Race_1_Logic.json').write_bytes(b'{"horses":{}}\n')
    source = meeting / '08-26 Race 1 Facts.md'; source.write_bytes(b'facts\n')
    snapshot = hkjc_writer()(meeting, at=AT)
    metadata = json.loads((snapshot / NAME).read_bytes())
    assert metadata['domain'] == 'hkjc'
    assert metadata['files'][0]['mtime_ns'] == source.stat().st_mtime_ns
    manifest = json.loads((snapshot / 'manifest.json').read_bytes())
    entry = next(item for item in manifest['files'] if item['name'] == NAME)
    assert entry['sha256'] == hashlib.sha256((snapshot / NAME).read_bytes()).hexdigest()
    assert manifest['immutable_prediction_snapshot'] is True


def test_actual_hkjc_output_mtime_does_not_duplicate_but_input_mtime_does(tmp_path):
    meeting = tmp_path / '2026-09-06_ShaTin'; meeting.mkdir()
    logic = meeting / 'Race_1_Logic.json'; logic.write_bytes(b'{"horses":{}}\n')
    facts = meeting / '08-26 Race 1 Facts.md'; facts.write_bytes(b'facts\n')
    writer = hkjc_writer(); first = writer(meeting, at=AT)
    original = (first / NAME).read_bytes()
    os.utime(logic, ns=(logic.stat().st_atime_ns, logic.stat().st_mtime_ns + 1000000000))
    assert writer(meeting, at=AT + timedelta(seconds=1)) == first
    os.utime(facts, ns=(facts.stat().st_atime_ns, facts.stat().st_mtime_ns + 1000000000))
    assert writer(meeting, at=AT + timedelta(seconds=2)) != first
    assert (first / NAME).read_bytes() == original


def test_actual_hkjc_keeps_literal_bracketed_source_names(tmp_path):
    meeting = tmp_path / '2026-09-06_ShaTin'; meeting.mkdir()
    facts = meeting / '08-26 [source] Race 1 Facts.md'; facts.write_bytes(b'facts\n')
    (meeting / 'Race_1_Logic.json').write_bytes(b'{"horses":{}}\n')
    snapshot = hkjc_writer()(meeting, at=AT)
    assert (snapshot / facts.name).read_bytes() == facts.read_bytes()
    assert json.loads((snapshot / NAME).read_bytes())['files'][0]['name'] == facts.name


def test_actual_hkjc_return_to_prior_outputs_creates_a_new_latest_capture(tmp_path):
    meeting = tmp_path / '2026-09-06_ShaTin'; meeting.mkdir()
    logic = meeting / 'Race_1_Logic.json'; original = b'{"horses":{}}\n'
    logic.write_bytes(original)
    (meeting / '08-26 Race 1 Facts.md').write_bytes(b'facts\n')
    writer = hkjc_writer()
    first = writer(meeting, at=AT)
    logic.write_bytes(b'{"horses":{"1":{}}}\n')
    second = writer(meeting, at=AT + timedelta(seconds=1))
    logic.write_bytes(original)
    third = writer(meeting, at=AT + timedelta(seconds=2))
    assert third not in {first, second}
    assert third == sorted((meeting / 'Prediction_Snapshots').iterdir())[-1]
    assert (second / logic.name).read_bytes() != original


def test_actual_hkjc_keeps_literal_output_and_decoy_files_separate(tmp_path):
    meeting = tmp_path / '2026-09-06_ShaTin'; meeting.mkdir()
    (meeting / 'Race_1_Logic.json').write_bytes(b'{"horses":{}}\n')
    literal = meeting / 'Race_[1]_Auto_Analysis.md'; literal.write_bytes(b'literal\n')
    decoy = meeting / 'Race_1_Auto_Analysis.md'; decoy.write_bytes(b'decoy\n')
    snapshot = hkjc_writer()(meeting, at=AT)
    assert (snapshot / literal.name).read_bytes() == b'literal\n'
    assert (snapshot / decoy.name).read_bytes() == b'decoy\n'


@pytest.mark.parametrize('fault', ['missing', 'hash', 'mtime'])
def test_metadata_capture_never_reuses_a_corrupt_snapshot(tmp_path, fault):
    source = tmp_path / 'Facts.md'; source.write_bytes(b'facts\n')
    def capture():
        return create_immutable_snapshot(tmp_path, domain='au', event_id='fixture',
            patterns=['*.md'], capture_file_metadata=True, at=AT)
    first = capture(); original_manifest = (first / 'manifest.json').read_bytes()
    if fault == 'missing':
        (first / NAME).unlink()
    elif fault == 'hash':
        (first / source.name).write_bytes(b'other\n')
    else:
        current = (first / source.name).stat()
        os.utime(first / source.name, ns=(current.st_atime_ns, current.st_mtime_ns + 1000000000))
    before = {p.name: p.read_bytes() for p in first.iterdir()}
    with pytest.raises((ValueError, RuntimeError, OSError)):
        capture()
    assert {p.name: p.read_bytes() for p in first.iterdir()} == before
    assert (first / 'manifest.json').read_bytes() == original_manifest


@pytest.mark.parametrize('fault', ['recommendations_missing', 'recommendations_changed',
                                 'recommendations_type', 'files_type', 'clock'])
def test_metadata_reuse_checks_manifest_contents_not_advertised_signature(tmp_path, fault):
    (tmp_path / 'Facts.md').write_bytes(b'x')
    def capture():
        return create_immutable_snapshot(tmp_path, domain='au', event_id='fixture', patterns=['*.md'],
            recommendations=[{'id': 1}], capture_file_metadata=True, at=AT)
    first = capture(); path = first / 'manifest.json'; manifest = json.loads(path.read_bytes())
    if fault == 'recommendations_missing':
        del manifest['recommendations']
    elif fault == 'recommendations_changed':
        manifest['recommendations'] = [{'id': 2}]
    elif fault == 'recommendations_type':
        manifest['recommendations'] = [{'id': True}]
    elif fault == 'files_type':
        next(item for item in manifest['files'] if item['name'] == 'Facts.md')['bytes'] = True
    else:
        manifest['created_at'] = (AT - timedelta(days=1)).isoformat()
    path.write_text(json.dumps(manifest))
    before = path.read_bytes()
    with pytest.raises((ValueError, RuntimeError)):
        capture()
    assert path.read_bytes() == before


def test_capture_stops_reading_before_total_source_budget_is_exceeded(tmp_path, monkeypatch):
    from shared_wong_choi import immutable_snapshot as native
    (tmp_path / 'a.md').write_bytes(b'a' * 12)
    (tmp_path / 'b.md').write_bytes(b'b' * 12)
    monkeypatch.setattr(native, 'MAX_TOTAL_SOURCE_BYTES', 20)
    original_read = native.os.read; lengths = []
    def read(*args):
        raw = original_read(*args); lengths.append(len(raw)); return raw
    monkeypatch.setattr(native.os, 'read', read)
    with pytest.raises((ValueError, RuntimeError)):
        create_immutable_snapshot(tmp_path, domain='au', event_id='fixture',
            patterns=['*.md'], capture_file_metadata=True, at=AT)
    assert sum(lengths) == 12


def test_actual_hkjc_future_writer_is_admitted_by_existing_bundle_verifier(tmp_path):
    meeting = tmp_path / '2026-09-06_ShaTin'; meeting.mkdir()
    (meeting / 'Race_1_Logic.json').write_bytes(b'{"horses":{}}\n')
    snapshot = hkjc_writer()(meeting, at=AT)
    evidence = tmp_path / 'evidence'; model = register_model(evidence, Domain.HKJC)
    record_prediction_decision(domain=Domain.HKJC, event_id=meeting.name, snapshot=snapshot,
        evidence_root=evidence, decision_state=DecisionState.SHADOW, model_release_id=model)
    report = inspect_prediction_artifacts(root=evidence, domain=Domain.HKJC, as_of=AT + timedelta(hours=1))
    assert report['records'][0]['snapshot_bundle_verified'] is True
    assert report['normalized_source_verified'] is False
    assert report['verified_monitoring_samples'] is None
    assert report['model_promotion_allowed'] is False


@pytest.mark.parametrize('fault', ['source_changed_during_copy', 'metadata_name_collision'])
def test_metadata_capture_rejects_conflicts_before_publishing(tmp_path, monkeypatch, fault):
    from shared_wong_choi import immutable_snapshot as native
    source = tmp_path / 'Facts.md'; source.write_bytes(b'before\n')
    if fault == 'source_changed_during_copy':
        original = native.shutil.copy2
        def copy(*args, **kwargs):
            source.write_bytes(b'after!\n')
            return original(*args, **kwargs)
        monkeypatch.setattr(native.shutil, 'copy2', copy)
        additional = None
    else:
        additional = {NAME: b'{}\n'}
    with pytest.raises((ValueError, RuntimeError)):
        create_immutable_snapshot(tmp_path, domain='au', event_id='fixture', patterns=['*.md'],
            capture_file_metadata=True, additional_files=additional)
    root = tmp_path / '_prediction_snapshots'
    assert not root.exists() or not list(root.glob('*/manifest.json'))
