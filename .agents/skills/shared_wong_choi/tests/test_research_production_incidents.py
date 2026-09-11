"""A Stage 4 'settled' label alone is neither a result nor a live sample."""
from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared_wong_choi.contracts import Domain
from shared_wong_choi.evidence import EvidenceRecord, EvidenceStore, RecordKind, ArtifactRef

NOW = datetime(2026, 8, 31, 12, tzinfo=timezone.utc)
STAMP = '2026-08-29T08:57:30+00:00'


def source(tmp_path, *, domain=Domain.NBA, event='2026-10-21', artifacts=()):
    store = EvidenceStore(tmp_path / 'production-evidence')
    prefix = f'wc:{domain.value}'
    records = (
        EvidenceRecord(prefix + ':model-release:fixture', RecordKind.MODEL_RELEASE, domain, STAMP,
                       {'release_stage': 'shadow', 'code_commit': 'a' * 40, 'evaluation_contract_version': 'v1'}),
        EvidenceRecord(prefix + ':prediction:fixture', RecordKind.PREDICTION, domain, STAMP,
                       {'event_id': event, 'source_cutoff_at': STAMP, 'recommendations': []},
                       {'model_release_id': prefix + ':model-release:fixture'}),
        EvidenceRecord(prefix + ':decision:fixture', RecordKind.DECISION, domain, STAMP,
                       {'decision_state': 'shadow'}, {'prediction_id': prefix + ':prediction:fixture'}),
        EvidenceRecord(prefix + ':settlement:fixture', RecordKind.SETTLEMENT, domain, STAMP,
                       {'event_id': event, 'settlement_state': 'settled', 'settled_at': STAMP},
                       {'decision_id': prefix + ':decision:fixture'}, artifacts),
    )
    for record in records:
        store.append(record)
    return store


def collect(store, domain=Domain.NBA):
    from shared_wong_choi.research_production_incidents import collect_production_incidents
    return collect_production_incidents(root=store.root, domain=domain, as_of=NOW)


def test_real_record_shape_exposes_future_event_and_missing_outcome(tmp_path):
    store = source(tmp_path)
    before = {p: p.read_bytes() for p in store.root.rglob('*.json')}
    report = collect(store)
    assert report['findings'][0]['codes'] == ['settlement_event_after_settled_at', 'settlement_outcome_artifacts_missing']
    assert len(report['events']) == 1
    assert report['verified_monitoring_samples'] is None
    assert before == {p: p.read_bytes() for p in store.root.rglob('*.json')}


def test_metadata_consistent_is_not_pit_or_complete_source_coverage(tmp_path):
    artifact = ArtifactRef('/unread/result.json', '1' * 64, STAMP, 'nba_settlement')
    report = collect(source(tmp_path, event='2026-08-28', artifacts=(artifact,)))
    assert report['events'] == []
    assert report['artifact_contents_verified'] is False
    assert report['source_coverage_complete'] is False
    assert report['verified_monitoring_samples'] is None


def test_missing_store_is_not_an_empty_healthy_store(tmp_path):
    with pytest.raises((ValueError, RuntimeError)):
        collect(EvidenceStore(tmp_path / 'missing'))


def test_source_event_identity_is_stable_across_review_times(tmp_path):
    from shared_wong_choi.research_production_incidents import collect_production_incidents
    store = source(tmp_path)
    one = collect(store)
    two = collect_production_incidents(root=store.root, domain=Domain.NBA,
                                      as_of=datetime(2026, 9, 1, tzinfo=timezone.utc))
    assert one['events'] == two['events']


def test_review_consumes_source_not_caller_incident_booleans(tmp_path):
    from test_research_review_runtime import setup
    from test_research_index import clock_args
    from shared_wong_choi.research_review_runtime import ResearchReviewRunner
    import json
    store = source(tmp_path)
    runtime, registry = setup(tmp_path)
    result = ResearchReviewRunner(runtime, registry).run(
        **{**clock_args(), 'domain': Domain.NBA}, production_evidence_root=store.root,
        estimated_bytes=1024, timeout_seconds=15)
    assert result.status == 'reviewed_freeze_required', result
    summary = json.loads(result.report_path.read_bytes())
    assert summary['freeze_research_required'] is True
    assert summary['sample_evidence_status'] == 'not_integrated'
    assert summary['production_incidents']['events']
    assert (runtime.state_root / 'research-incident-freezes/nba.json').is_file()


def test_cursor_pins_source_and_incident_is_not_mislabelled_ruler_expiry(tmp_path):
    from test_research_review_runtime import setup
    from test_research_index import clock_args
    from shared_wong_choi.research_review_cursor import ResearchReviewCursorRunner
    from shared_wong_choi.research_guard import research_gate_status
    from shared_wong_choi.research_runner import ResearchDisposition
    from dataclasses import replace
    store = source(tmp_path)
    runtime, registry = setup(tmp_path)
    (runtime.state_root / 'research-review-cursors').mkdir(parents=True)
    cursor = ResearchReviewCursorRunner(runtime, registry)
    clock = {**clock_args(), 'domain': Domain.NBA}
    path = cursor.initialize(domain=Domain.NBA, initial_window_start=clock['window_start'],
                             ruler_digest=clock['ruler_digest'], ruler_released_at=clock['ruler_released_at'],
                             production_evidence_root=store.root)
    runtime = replace(runtime, clock=lambda: clock['now'])
    assert research_gate_status(runtime, registry, Domain.NBA, '1' * 64) == 'research_source_review_required'
    options = {key: value for key, value in clock.items() if key != 'window_start'}
    result = cursor.run(**options, production_evidence_root=store.root, estimated_bytes=1024, timeout_seconds=15)
    assert result.disposition is ResearchDisposition.SUCCEEDED, result
    assert not path.with_suffix('.freeze.json').exists(), 'source incident masqueraded as 90-day expiry'
    assert research_gate_status(runtime, registry, Domain.NBA, '1' * 64) == 'research_frozen_production_evidence'
    omitted = cursor.run(**options, estimated_bytes=1024, timeout_seconds=15)
    assert omitted.disposition is ResearchDisposition.BLOCKED


def test_later_clean_source_review_does_not_clear_incident(tmp_path):
    from test_research_review_runtime import setup
    from test_research_index import clock_args
    from shared_wong_choi.research_review_runtime import ResearchReviewRunner
    from shared_wong_choi.research_guard import research_gate_status
    import json
    store = source(tmp_path)
    runtime, registry = setup(tmp_path)
    runner = ResearchReviewRunner(runtime, registry)
    options = {**clock_args(), 'domain': Domain.NBA, 'production_evidence_root': store.root,
               'estimated_bytes': 1024, 'timeout_seconds': 15}
    assert runner.run(**options).status == 'reviewed_freeze_required'
    record = store.path_for(RecordKind.SETTLEMENT, 'wc:nba:settlement:fixture')
    record.rename(tmp_path / 'retained-old-settlement.json')
    result = runner.run(**options)
    assert result.status == 'reviewed_freeze_required', result
    summary = json.loads(result.report_path.read_bytes())
    assert summary['production_incidents']['events'] == []
    assert summary['production_freeze']['events']
    assert research_gate_status(runtime, registry, Domain.NBA, '1' * 64) == 'research_frozen_production_evidence'


def test_old_clean_cursor_proof_still_allows_reviewing_new_incident(tmp_path):
    from test_research_review_runtime import setup
    from test_research_index import clock_args
    from shared_wong_choi.research_review_cursor import ResearchReviewCursorRunner
    from shared_wong_choi.research_review_runtime import ResearchReviewRunner
    from shared_wong_choi.research_runner import ResearchDisposition
    artifact = ArtifactRef('/unread/result.json', '1' * 64, STAMP, 'nba_settlement')
    store = source(tmp_path, event='2026-08-28', artifacts=(artifact,))
    runtime, registry = setup(tmp_path)
    (runtime.state_root / 'research-review-cursors').mkdir(parents=True)
    cursor = ResearchReviewCursorRunner(runtime, registry)
    clock = {**clock_args(), 'domain': Domain.NBA}
    cursor.initialize(domain=Domain.NBA, initial_window_start=clock['window_start'],
                      ruler_digest=clock['ruler_digest'], ruler_released_at=clock['ruler_released_at'],
                      production_evidence_root=store.root)
    options = {key: value for key, value in clock.items() if key != 'window_start'}
    options.update(production_evidence_root=store.root, estimated_bytes=1024, timeout_seconds=15)
    assert cursor.run(**options).status == 'reviews_recorded'
    store.append(EvidenceRecord('wc:nba:settlement:later-incident', RecordKind.SETTLEMENT, Domain.NBA, STAMP,
                                {'event_id': '2026-10-21', 'settlement_state': 'settled', 'settled_at': STAMP},
                                {'decision_id': 'wc:nba:decision:fixture'}))
    assert ResearchReviewRunner(runtime, registry).run(**options, window_start=clock['window_start']).status == 'reviewed_freeze_required'
    result = cursor.run(**options)
    assert result.disposition is ResearchDisposition.SUCCEEDED, result
    assert result.status == 'reviewed_freeze_required'


@pytest.mark.parametrize('domain,event', [(Domain.AU, '2026-10-21 Venue Race 1-7'),
                                         (Domain.HKJC, '2026-10-21|ShaTin'),
                                         (Domain.TENNIS, '2026-10-21'), (Domain.NBA, '2026-10-21')])
def test_supported_date_prefixed_event_cannot_settle_before_its_day(tmp_path, domain, event):
    report = collect(source(tmp_path, domain=domain, event=event), domain)
    assert 'settlement_event_after_settled_at' in report['findings'][0]['codes']


@pytest.mark.parametrize('fault', ['hash', 'missing_parent', 'filename', 'symlink', 'size'])
def test_inconsistent_store_never_becomes_clean_metadata(tmp_path, fault):
    store = source(tmp_path)
    path = store.path_for(RecordKind.SETTLEMENT, 'wc:nba:settlement:fixture')
    if fault == 'hash':
        path.write_text(path.read_text().replace('2026-10-21', '2026-08-28'))
    elif fault == 'missing_parent':
        store.path_for(RecordKind.PREDICTION, 'wc:nba:prediction:fixture').rename(tmp_path / 'retained-prediction.json')
    elif fault == 'filename':
        path.rename(path.with_name(path.name.replace('%3A', '%3a')))
    elif fault == 'symlink':
        saved = tmp_path / 'retained.json'
        path.rename(saved)
        path.symlink_to(saved)
    else:
        path.write_bytes(b'x' * (1048576 + 1))
    with pytest.raises((ValueError, RuntimeError, OSError)):
        collect(store)


@pytest.mark.parametrize('fault', ['events', 'samples', 'scope', 'count'])
def test_parent_rejects_inconsistent_incident_projection(tmp_path, fault):
    from shared_wong_choi.research_production_incidents import verify_production_incidents
    from shared_wong_choi.research_index import _hash
    report = collect(source(tmp_path))
    if fault == 'events':
        report['events'] = []
    elif fault == 'samples':
        report['verified_monitoring_samples'] = 1
    elif fault == 'scope':
        report['domain'] = 'au'
    else:
        report['records_seen'] = True
    report['content_hash'] = _hash({key: value for key, value in report.items() if key != 'content_hash'})
    with pytest.raises((ValueError, RuntimeError)):
        verify_production_incidents(report, root=tmp_path / 'production-evidence', domain=Domain.NBA, as_of=NOW)


def test_unreadable_source_latches_unknown_not_healthy_then_stays_frozen(tmp_path):
    from test_research_review_runtime import setup
    from test_research_index import clock_args
    from shared_wong_choi.research_review_runtime import ResearchReviewRunner
    from shared_wong_choi.research_guard import production_incident_status
    from shared_wong_choi.research_runner import ResearchDisposition
    runtime, registry = setup(tmp_path)
    root = tmp_path / 'production-evidence'
    options = {**clock_args(), 'domain': Domain.NBA, 'production_evidence_root': root,
               'estimated_bytes': 1024, 'timeout_seconds': 15}
    first = ResearchReviewRunner(runtime, registry).run(**options)
    assert first.disposition is ResearchDisposition.FAILED
    assert production_incident_status(runtime, registry, Domain.NBA) == 'research_frozen_production_evidence'
    artifact = ArtifactRef('/unread/result.json', '1' * 64, STAMP, 'nba_settlement')
    source(tmp_path, event='2026-08-28', artifacts=(artifact,))
    assert ResearchReviewRunner(runtime, registry).run(**options).status == 'reviewed_freeze_required'


def test_production_preemption_is_not_relabelled_a_data_incident(tmp_path):
    import fcntl
    from test_research_review_runtime import setup
    from test_research_index import clock_args
    from shared_wong_choi.research_review_runtime import ResearchReviewRunner
    runtime, registry = setup(tmp_path)
    store = source(tmp_path)
    with runtime.production_lock_paths[0].open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        result = ResearchReviewRunner(runtime, registry).run(
            **clock_args(), production_evidence_root=store.root, estimated_bytes=1024, timeout_seconds=15)
    assert result.status == 'production_active'
    assert not (runtime.state_root / 'research-incident-freezes').exists()


def test_worker_crash_after_latch_cannot_lose_freeze(tmp_path):
    from dataclasses import replace
    from test_research_review_runtime import setup
    from test_research_index import clock_args
    from shared_wong_choi.research_review_runtime import ResearchReviewRunner
    from shared_wong_choi.research_guard import production_incident_status
    from shared_wong_choi.research_runner import SubprocessResearchExecutor, ResearchDisposition
    runtime, registry = setup(tmp_path)
    store = source(tmp_path)
    script = '''import os,sys
from pathlib import Path
import shared_wong_choi.research_guard as guard
from shared_wong_choi.research_supervision import _worker
original = guard.persist_production_incident
def crash(*args, **kwargs):
    original(*args, **kwargs)
    os._exit(77)
guard.persist_production_incident = crash
_worker(Path(sys.argv[1]))
'''
    class CrashExecutor:
        def run(self, invocation, **kwargs):
            return SubprocessResearchExecutor(poll_seconds=.02).run(
                replace(invocation, argv=(sys.executable, '-c', script, invocation.argv[-1])), **kwargs)
    result = ResearchReviewRunner(replace(runtime, executor=CrashExecutor()), registry).run(
        **{**clock_args(), 'domain': Domain.NBA}, production_evidence_root=store.root,
        estimated_bytes=1024, timeout_seconds=15)
    assert result.disposition is ResearchDisposition.FAILED
    assert production_incident_status(runtime, registry, Domain.NBA) == 'research_frozen_production_evidence'
    assert not (result.attempt_path / 'completed.json').exists()


def test_duplicate_identity_across_kinds_is_not_silently_overwritten(tmp_path):
    store = source(tmp_path)
    store.append(EvidenceRecord('wc:nba:settlement:fixture', RecordKind.MODEL_RELEASE, Domain.NBA, STAMP,
                                {'release_stage': 'shadow', 'code_commit': 'a' * 40,
                                 'evaluation_contract_version': 'v1'}))
    with pytest.raises((ValueError, RuntimeError), match='duplicate'):
        collect(store)


@pytest.mark.parametrize('body_change,code', [
    ({'settled_at': '2026-08-28T12:00:00+00:00'}, 'settlement_before_decision'),
    ({'settled_at': '2026-08-30T12:00:00+00:00'}, 'settlement_time_after_record'),
    ({'event_id': '2026-08-27'}, 'settlement_event_mismatch'),
])
def test_settlement_chronology_and_parent_event_are_checked(tmp_path, body_change, code):
    artifact = ArtifactRef('/unread/result.json', '1' * 64, STAMP, 'nba_settlement')
    store = source(tmp_path, event='2026-08-28', artifacts=(artifact,))
    body = {'event_id': '2026-08-28', 'settlement_state': 'settled', 'settled_at': STAMP, **body_change}
    store.append(EvidenceRecord('wc:nba:settlement:changed', RecordKind.SETTLEMENT, Domain.NBA, STAMP, body,
                                {'decision_id': 'wc:nba:decision:fixture'}, (artifact,)))
    assert collect(store)['findings'][0]['codes'] == [code]
