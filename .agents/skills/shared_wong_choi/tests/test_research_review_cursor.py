from __future__ import annotations

import fcntl
import json
import multiprocessing
import os
import sqlite3
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared_wong_choi.contracts import Domain
from shared_wong_choi.research_runner import ResearchDisposition, SubprocessResearchExecutor
from shared_wong_choi.research_review_cursor import ResearchReviewCursorRunner
from shared_wong_choi.research_index import _hash
from test_research_review_runtime import liveness_fixture, setup
from test_research_index import clock_args
from test_research_racing_monitoring_samples import _au_source as racing_au_source
from test_research_tennis_monitoring_samples import settled_source as tennis_sample_source
from test_research_tennis_settlement_source import END as TENNIS_SAMPLE_END


def fixture(tmp_path):
    runtime, registry = setup(tmp_path)
    root = runtime.state_root / 'research-review-cursors'
    root.mkdir(parents=True)
    runner = ResearchReviewCursorRunner(runtime, registry)
    clock = clock_args()
    path = runner.initialize(domain=clock['domain'], initial_window_start=clock['window_start'],
                             ruler_digest=clock['ruler_digest'], ruler_released_at=clock['ruler_released_at'])
    return runner, path


def state(path):
    with sqlite3.connect(f'file:{path}?mode=ro', uri=True) as db:
        return json.loads(db.execute('SELECT payload FROM cursor_state WHERE id=1').fetchone()[0])


def sample_state(path):
    with sqlite3.connect(f'file:{path}?mode=ro', uri=True) as db:
        return json.loads(db.execute(
            'SELECT payload FROM racing_sample_state WHERE id=1'
        ).fetchone()[0])


def storage_state(path):
    with sqlite3.connect(f'file:{path}?mode=ro', uri=True) as db:
        return json.loads(db.execute(
            'SELECT payload FROM storage_evidence_state WHERE id=1'
        ).fetchone()[0])


def liveness_state(path):
    with sqlite3.connect(f'file:{path}?mode=ro', uri=True) as db:
        return json.loads(db.execute(
            'SELECT payload FROM liveness_evidence_state WHERE id=1'
        ).fetchone()[0])


def run(runner, **updates):
    clock = {key: value for key, value in clock_args().items() if key != 'window_start'}
    return runner.run(**{**clock, 'estimated_bytes':1048576, 'timeout_seconds':15, **updates})


def test_cursor_resumes_in_fresh_instance_and_does_not_mean_delivery(tmp_path):
    runner, path = fixture(tmp_path)
    first = run(runner)
    assert first.disposition is ResearchDisposition.SUCCEEDED, first
    assert first.advanced is True
    saved = state(path)
    assert saved['window_start'] == clock_args()['now'].isoformat()
    assert saved['generation'] == 1
    assert saved['telegram_delivery_confirmed'] is False
    fresh = ResearchReviewCursorRunner(runner.runtime, runner.registry)
    second = run(fresh, now=clock_args()['now'] + timedelta(days=1))
    assert second.disposition is ResearchDisposition.SUCCEEDED, second
    summary = json.loads(second.review.report_path.read_bytes())
    assert summary['window_start'] == saved['window_start']
    assert summary['created_reviews'] == 0
    assert state(path)['generation'] == 2


def test_racing_sample_baseline_and_no_growth_advance_atomically_with_review(tmp_path):
    runtime, registry = setup(tmp_path)
    evidence, as_of, _result = racing_au_source(tmp_path / 'source')
    (runtime.state_root / 'research-review-cursors').mkdir(parents=True)
    runner = ResearchReviewCursorRunner(runtime, registry)
    path = runner.initialize(
        domain=Domain.AU,
        initial_window_start=as_of - timedelta(days=1),
        ruler_digest='1' * 64,
        ruler_released_at=as_of - timedelta(days=30),
    )
    runner.initialize_racing_samples(
        domain=Domain.AU,
        evidence_root=evidence,
    )

    first = runner.run(
        domain=Domain.AU, now=as_of, ruler_digest='1' * 64,
        ruler_released_at=as_of - timedelta(days=30),
        estimated_bytes=1048576, timeout_seconds=20,
    )
    assert first.disposition is ResearchDisposition.SUCCEEDED, first
    first_summary = json.loads(first.review.report_path.read_bytes())
    first_sample = sample_state(path)
    assert first_sample['generation'] == 1
    assert first_sample['last_report'] == first_summary['racing_sample_current']
    assert first_summary['racing_sample_previous'] is None
    assert first_summary['sample_growth_observed'] is False
    assert first_summary['progress_only'] is True

    second = runner.run(
        domain=Domain.AU, now=as_of + timedelta(minutes=1),
        ruler_digest='1' * 64,
        ruler_released_at=as_of - timedelta(days=30),
        estimated_bytes=1048576, timeout_seconds=20,
    )
    assert second.disposition is ResearchDisposition.SUCCEEDED, second
    second_summary = json.loads(second.review.report_path.read_bytes())
    assert sample_state(path)['generation'] == 2
    assert second_summary['racing_sample_previous'] == first_sample['last_report']
    assert second_summary['sample_growth_observed'] is False
    assert second_summary['progress_only'] is True
    assert second_summary['reevaluate_promotion_allowed'] is False


def test_racing_sample_and_calendar_cursor_roll_back_together_on_commit_failure(
        tmp_path, monkeypatch):
    import shared_wong_choi.research_review_cursor as module
    runtime, registry = setup(tmp_path)
    evidence, as_of, _result = racing_au_source(tmp_path / 'source')
    (runtime.state_root / 'research-review-cursors').mkdir(parents=True)
    runner = ResearchReviewCursorRunner(runtime, registry)
    path = runner.initialize(
        domain=Domain.AU,
        initial_window_start=as_of - timedelta(days=1),
        ruler_digest='1' * 64,
        ruler_released_at=as_of - timedelta(days=30),
    )
    runner.initialize_racing_samples(domain=Domain.AU, evidence_root=evidence)
    repo, source_state = tmp_path / 'repo', tmp_path / 'storage-source'
    hot, warm = tmp_path / 'hot', tmp_path / 'warm-archive'
    for item in (repo, source_state, hot, warm):
        item.mkdir()
    monkeypatch.setenv('WC_HOT_DATA_ROOT', str(hot))
    monkeypatch.setenv('WC_WARM_ARCHIVE_ROOT', str(warm))
    runner.initialize_storage_evidence(
        domain=Domain.AU, repo_root=repo, storage_state_root=source_state,
    )
    before_cursor, before_sample = state(path), sample_state(path)
    before_storage = storage_state(path)
    original = sqlite3.connect

    class DiskFull(sqlite3.Connection):
        def execute(self, sql, parameters=()):
            if sql == 'COMMIT':
                raise sqlite3.OperationalError('disk full')
            return super().execute(sql, parameters)

    with monkeypatch.context() as patcher:
        patcher.setattr(
            module.sqlite3, 'connect',
            lambda *a, **k: original(*a, **k, factory=DiskFull),
        )
        result = runner.run(
            domain=Domain.AU, now=as_of, ruler_digest='1' * 64,
            ruler_released_at=as_of - timedelta(days=30),
            estimated_bytes=1048576, timeout_seconds=20,
        )
    assert result.disposition is ResearchDisposition.BLOCKED
    assert state(path) == before_cursor
    assert sample_state(path) == before_sample
    assert storage_state(path) == before_storage


def test_tennis_family_sample_watermark_advances_with_calendar_in_one_commit(tmp_path):
    runtime, registry = setup(tmp_path)
    evidence, _snapshot, _outcome = tennis_sample_source(tmp_path / "source")
    (runtime.state_root / 'research-review-cursors').mkdir(parents=True)
    runner = ResearchReviewCursorRunner(runtime, registry)
    path = runner.initialize(
        domain=Domain.TENNIS,
        initial_window_start=TENNIS_SAMPLE_END - timedelta(days=1),
        ruler_digest='1' * 64,
        ruler_released_at=TENNIS_SAMPLE_END - timedelta(days=30),
    )
    runner.initialize_monitoring_samples(
        domain=Domain.TENNIS,
        evidence_root=evidence,
    )

    result = runner.run(
        domain=Domain.TENNIS,
        now=TENNIS_SAMPLE_END,
        ruler_digest='1' * 64,
        ruler_released_at=TENNIS_SAMPLE_END - timedelta(days=30),
        estimated_bytes=1048576,
        timeout_seconds=20,
    )
    assert result.disposition is ResearchDisposition.SUCCEEDED, result
    summary = json.loads(result.review.report_path.read_bytes())
    saved = sample_state(path)
    assert saved['generation'] == 1
    assert saved['last_report'] == summary['racing_sample_current']
    assert saved['last_report']['scope_counts'] == {'match_winner_atp': 1}
    assert state(path)['generation'] == 1


def test_storage_evidence_and_calendar_cursor_advance_in_one_transaction(
        tmp_path, monkeypatch):
    runtime, registry = setup(tmp_path)
    repo, source_state = tmp_path / "repo", tmp_path / "storage-source"
    hot, warm = tmp_path / "hot", tmp_path / "warm-archive"
    for item in (repo, source_state, hot, warm):
        item.mkdir()
    monkeypatch.setenv("WC_HOT_DATA_ROOT", str(hot))
    monkeypatch.setenv("WC_WARM_ARCHIVE_ROOT", str(warm))
    monkeypatch.delenv("WC_COLD_MIRROR_ROOT", raising=False)
    (runtime.state_root / 'research-review-cursors').mkdir(parents=True)
    runner = ResearchReviewCursorRunner(runtime, registry)
    clock = clock_args()
    path = runner.initialize(
        domain=Domain.AU,
        initial_window_start=clock['window_start'],
        ruler_digest=clock['ruler_digest'],
        ruler_released_at=clock['ruler_released_at'],
    )
    runner.initialize_storage_evidence(
        domain=Domain.AU, repo_root=repo, storage_state_root=source_state,
    )

    result = run(runner)
    assert result.disposition is ResearchDisposition.SUCCEEDED, result
    summary = json.loads(result.review.report_path.read_bytes())
    saved = storage_state(path)
    assert state(path)['generation'] == 1
    assert saved['generation'] == 1
    assert saved['last_report'] == summary['storage_evidence']
    assert summary['storage_evidence_status'] == 'verified_attention'
    assert summary['process_liveness_verified'] is False
    assert summary['live_drift_verified'] is False

    warm.rmdir()
    second = run(runner, now=clock['now'] + timedelta(minutes=1))
    assert second.disposition is ResearchDisposition.SUCCEEDED, second
    second_summary = json.loads(second.review.report_path.read_bytes())
    assert storage_state(path)['generation'] == 2
    assert second_summary['storage_evidence']['storage_health'] == 'attention'


def test_liveness_evidence_and_calendar_cursor_advance_in_one_transaction(
        tmp_path):
    runtime, registry = setup(tmp_path)
    clock = clock_args()
    queue, leases, _initial = liveness_fixture(
        tmp_path, runtime, registry, clock['now'],
    )
    (runtime.state_root / 'research-review-cursors').mkdir(parents=True)
    runner = ResearchReviewCursorRunner(runtime, registry)
    path = runner.initialize(
        domain=Domain.AU,
        initial_window_start=clock['window_start'],
        ruler_digest=clock['ruler_digest'],
        ruler_released_at=clock['ruler_released_at'],
        queue_root=queue.root,
    )
    runner.initialize_liveness_evidence(
        domain=Domain.AU, queue_root=queue.root, lease_root=leases,
    )

    result = run(runner, queue_root=queue.root)

    assert result.disposition is ResearchDisposition.SUCCEEDED, result
    summary = json.loads(result.review.report_path.read_bytes())
    saved = liveness_state(path)
    assert state(path)['generation'] == 1
    assert saved['generation'] == 1
    assert saved['last_report'] == summary['process_liveness']
    assert summary['process_liveness_verified'] is True
    assert summary['process_liveness']['counts']['running_verified'] == 1
    assert saved['model_promotion_allowed'] is False
    assert saved['queue_mutation_allowed'] is False


def test_liveness_and_calendar_cursor_roll_back_together_on_commit_failure(
        tmp_path, monkeypatch):
    import shared_wong_choi.research_review_cursor as module
    runtime, registry = setup(tmp_path)
    clock = clock_args()
    queue, leases, _initial = liveness_fixture(
        tmp_path, runtime, registry, clock['now'],
    )
    (runtime.state_root / 'research-review-cursors').mkdir(parents=True)
    runner = ResearchReviewCursorRunner(runtime, registry)
    path = runner.initialize(
        domain=Domain.AU,
        initial_window_start=clock['window_start'],
        ruler_digest=clock['ruler_digest'],
        ruler_released_at=clock['ruler_released_at'],
        queue_root=queue.root,
    )
    runner.initialize_liveness_evidence(
        domain=Domain.AU, queue_root=queue.root, lease_root=leases,
    )
    before_cursor, before_liveness = state(path), liveness_state(path)
    original = sqlite3.connect

    class DiskFull(sqlite3.Connection):
        def execute(self, sql, parameters=()):
            if sql == 'COMMIT':
                raise sqlite3.OperationalError('disk full')
            return super().execute(sql, parameters)

    with monkeypatch.context() as patcher:
        patcher.setattr(
            module.sqlite3, 'connect',
            lambda *a, **k: original(*a, **k, factory=DiskFull),
        )
        result = run(runner, queue_root=queue.root)

    assert result.disposition is ResearchDisposition.BLOCKED
    assert state(path) == before_cursor
    assert liveness_state(path) == before_liveness


def test_sample_storage_and_calendar_commit_one_verified_review(
        tmp_path, monkeypatch):
    runtime, registry = setup(tmp_path)
    evidence, as_of, _result = racing_au_source(tmp_path / 'source')
    repo, source_state = tmp_path / "repo", tmp_path / "storage-source"
    hot, warm = tmp_path / "hot", tmp_path / "warm-archive"
    for item in (repo, source_state, hot, warm):
        item.mkdir()
    monkeypatch.setenv("WC_HOT_DATA_ROOT", str(hot))
    monkeypatch.setenv("WC_WARM_ARCHIVE_ROOT", str(warm))
    (runtime.state_root / 'research-review-cursors').mkdir(parents=True)
    runner = ResearchReviewCursorRunner(runtime, registry)
    path = runner.initialize(
        domain=Domain.AU,
        initial_window_start=as_of - timedelta(days=1),
        ruler_digest='1' * 64,
        ruler_released_at=as_of - timedelta(days=30),
        production_evidence_root=evidence,
    )
    runner.initialize_monitoring_samples(domain=Domain.AU, evidence_root=evidence)
    runner.initialize_storage_evidence(
        domain=Domain.AU, repo_root=repo, storage_state_root=source_state,
    )

    result = runner.run(
        domain=Domain.AU, now=as_of, ruler_digest='1' * 64,
        ruler_released_at=as_of - timedelta(days=30),
        estimated_bytes=1048576, timeout_seconds=20,
        production_evidence_root=evidence,
    )
    assert result.disposition is ResearchDisposition.SUCCEEDED, result
    summary = json.loads(result.review.report_path.read_bytes())
    assert sample_state(path)['last_report'] == summary['racing_sample_current']
    assert storage_state(path)['last_report'] == summary['storage_evidence']
    assert summary['production_incidents']['root'] == str(evidence)
    assert state(path)['generation'] == 1


def test_racing_sample_initialization_never_overwrites_existing_watermark(tmp_path):
    runtime, registry = setup(tmp_path)
    evidence, as_of, _result = racing_au_source(tmp_path / 'source')
    (runtime.state_root / 'research-review-cursors').mkdir(parents=True)
    runner = ResearchReviewCursorRunner(runtime, registry)
    path = runner.initialize(
        domain=Domain.AU,
        initial_window_start=as_of - timedelta(days=1),
        ruler_digest='1' * 64,
        ruler_released_at=as_of - timedelta(days=30),
    )
    runner.initialize_racing_samples(domain=Domain.AU, evidence_root=evidence)
    before = sample_state(path)

    with pytest.raises(sqlite3.OperationalError):
        runner.initialize_racing_samples(
            domain=Domain.AU,
            evidence_root=tmp_path / 'different-source',
        )
    assert sample_state(path) == before


def test_legacy_single_scope_racing_watermark_migrates_only_after_verified_review(tmp_path):
    runtime, registry = setup(tmp_path)
    evidence, as_of, _result = racing_au_source(tmp_path / 'source')
    (runtime.state_root / 'research-review-cursors').mkdir(parents=True)
    runner = ResearchReviewCursorRunner(runtime, registry)
    path = runner.initialize(
        domain=Domain.AU,
        initial_window_start=as_of - timedelta(days=1),
        ruler_digest='1' * 64,
        ruler_released_at=as_of - timedelta(days=30),
    )
    runner.initialize_racing_samples(domain=Domain.AU, evidence_root=evidence)
    first = runner.run(
        domain=Domain.AU, now=as_of, ruler_digest='1' * 64,
        ruler_released_at=as_of - timedelta(days=30),
        estimated_bytes=1048576, timeout_seconds=20,
    )
    assert first.disposition is ResearchDisposition.SUCCEEDED
    legacy = sample_state(path)
    reference = legacy['last_report']
    legacy['last_report'] = {
        key: value for key, value in reference.items() if key != 'scope_counts'
    }
    legacy['last_report']['sample_count'] = reference['scope_counts']['all']
    legacy.pop('content_hash')
    legacy['content_hash'] = _hash(legacy)
    with sqlite3.connect(path) as db:
        db.execute(
            'UPDATE racing_sample_state SET payload=? WHERE id=1',
            (json.dumps(legacy),),
        )

    second = runner.run(
        domain=Domain.AU, now=as_of + timedelta(minutes=1),
        ruler_digest='1' * 64,
        ruler_released_at=as_of - timedelta(days=30),
        estimated_bytes=1048576, timeout_seconds=20,
    )
    assert second.disposition is ResearchDisposition.SUCCEEDED, second
    assert sample_state(path)['last_report'].get('scope_counts') == {'all': 1}
    assert 'sample_count' not in sample_state(path)['last_report']


def test_review_backlog_does_not_consume_racing_sample_watermark(tmp_path):
    runtime, registry = setup(tmp_path)
    evidence, as_of, _result = racing_au_source(tmp_path / 'source')
    (runtime.state_root / 'research-review-cursors').mkdir(parents=True)
    runner = ResearchReviewCursorRunner(runtime, registry)
    path = runner.initialize(
        domain=Domain.AU,
        initial_window_start=as_of - timedelta(days=1),
        ruler_digest='1' * 64,
        ruler_released_at=as_of - timedelta(days=30),
    )
    runner.initialize_racing_samples(domain=Domain.AU, evidence_root=evidence)

    first = runner.run(
        domain=Domain.AU, now=as_of, ruler_digest='1' * 64,
        ruler_released_at=as_of - timedelta(days=30),
        estimated_bytes=1048576, timeout_seconds=20, max_reviews=1,
    )
    first_summary = json.loads(first.review.report_path.read_bytes())
    assert first.disposition is ResearchDisposition.SUCCEEDED
    assert first_summary['remaining_requests'] > 0
    assert sample_state(path)['generation'] == 0
    assert sample_state(path)['last_report'] is None

    second = runner.run(
        domain=Domain.AU, now=as_of, ruler_digest='1' * 64,
        ruler_released_at=as_of - timedelta(days=30),
        estimated_bytes=1048576, timeout_seconds=20, max_reviews=50,
    )
    assert second.disposition is ResearchDisposition.SUCCEEDED
    assert json.loads(second.review.report_path.read_bytes())['remaining_requests'] == 0
    assert sample_state(path)['generation'] == 1


def test_changed_racing_source_blocks_both_cursors_without_rewriting_history(tmp_path):
    runtime, registry = setup(tmp_path)
    evidence, as_of, result_path = racing_au_source(tmp_path / 'source')
    (runtime.state_root / 'research-review-cursors').mkdir(parents=True)
    runner = ResearchReviewCursorRunner(runtime, registry)
    path = runner.initialize(
        domain=Domain.AU,
        initial_window_start=as_of - timedelta(days=1),
        ruler_digest='1' * 64,
        ruler_released_at=as_of - timedelta(days=30),
    )
    runner.initialize_racing_samples(domain=Domain.AU, evidence_root=evidence)
    first = runner.run(
        domain=Domain.AU, now=as_of, ruler_digest='1' * 64,
        ruler_released_at=as_of - timedelta(days=30),
        estimated_bytes=1048576, timeout_seconds=20,
    )
    assert first.disposition is ResearchDisposition.SUCCEEDED
    before_cursor, before_sample = state(path), sample_state(path)

    result_path.write_text('# changed after settlement\n', encoding='utf-8')
    blocked = runner.run(
        domain=Domain.AU, now=as_of + timedelta(minutes=1),
        ruler_digest='1' * 64,
        ruler_released_at=as_of - timedelta(days=30),
        estimated_bytes=1048576, timeout_seconds=20,
    )
    assert blocked.disposition is ResearchDisposition.BLOCKED
    assert state(path) == before_cursor
    assert sample_state(path) == before_sample


def test_backlog_keeps_window_and_second_pass_completes_without_duplicate(tmp_path):
    runner, path = fixture(tmp_path)
    first = run(runner, max_reviews=1)
    assert first.disposition is ResearchDisposition.SUCCEEDED
    assert first.advanced is False
    assert state(path)['window_start'] == clock_args()['window_start'].isoformat()
    second = run(ResearchReviewCursorRunner(runner.runtime, runner.registry), max_reviews=1)
    assert second.advanced is True
    summary = json.loads(second.review.report_path.read_bytes())
    assert summary['created_reviews'] == 1
    assert summary['already_recorded_reviews'] == 1


@pytest.mark.parametrize('fault', ['missing', 'production', 'offline', 'busy'])
def test_unavailable_cursor_or_resources_never_advance(tmp_path, fault):
    runner, path = fixture(tmp_path)
    before = state(path)
    handle = connection = None
    if fault == 'missing':
        path.rename(path.with_suffix('.saved'))
    elif fault == 'offline':
        runner.runtime.warm_root.rename(tmp_path / 'offline')
    elif fault == 'production':
        handle = runner.runtime.production_lock_paths[0].open('a')
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    elif fault == 'busy':
        connection = sqlite3.connect(path)
        connection.execute('BEGIN IMMEDIATE')
    try:
        result = run(runner)
    finally:
        if connection:
            connection.close()
        if handle:
            handle.close()
    assert result.disposition in {ResearchDisposition.BLOCKED, ResearchDisposition.DEFERRED}
    assert result.advanced is False
    if fault == 'missing':
        assert not path.exists()
    else:
        assert state(path) == before


@pytest.mark.parametrize('fault', ['ruler', 'release', 'registry', 'clock'])
def test_changed_scope_and_backward_clock_fail_closed(tmp_path, fault):
    runner, path = fixture(tmp_path)
    assert run(runner).advanced
    before = state(path)
    updates = {}
    if fault == 'ruler':
        updates['ruler_digest'] = 'a' * 64
    elif fault == 'release':
        updates['ruler_released_at'] = clock_args()['ruler_released_at'] - timedelta(days=1)
    elif fault == 'registry':
        from shared_wong_choi.research_registry import ExperimentRegistry
        runner = ResearchReviewCursorRunner(runner.runtime, ExperimentRegistry(tmp_path / 'other-registry'))
    else:
        updates['now'] = clock_args()['window_start']
    result = run(runner, **updates)
    assert result.disposition is ResearchDisposition.BLOCKED
    assert state(path) == before


def test_rehashed_cursor_cannot_skip_beyond_verified_summary(tmp_path):
    runner, path = fixture(tmp_path)
    assert run(runner).advanced
    forged = state(path)
    forged['window_start'] = (clock_args()['now'] + timedelta(days=2)).isoformat()
    forged.pop('content_hash')
    forged['content_hash'] = _hash(forged)
    with sqlite3.connect(path) as db:
        db.execute('UPDATE cursor_state SET payload=? WHERE id=1', (json.dumps(forged),))
    result = run(runner, now=clock_args()['now'] + timedelta(days=3))
    assert result.disposition is ResearchDisposition.BLOCKED
    assert state(path) == forged


def test_initialization_is_explicit_and_never_overwrites_existing_cursor(tmp_path):
    runner, path = fixture(tmp_path)
    before = path.read_bytes()
    clock = clock_args()
    with pytest.raises(FileExistsError):
        runner.initialize(domain=Domain.AU, initial_window_start=clock['window_start'],
                          ruler_digest=clock['ruler_digest'], ruler_released_at=clock['ruler_released_at'])
    assert path.read_bytes() == before


def test_worker_crash_after_receipt_does_not_advance_and_resume_dedups(tmp_path):
    runner, path = fixture(tmp_path)
    before = state(path)
    class Crash(SubprocessResearchExecutor):
        def run(self, invocation, **kwargs):
            program = (
                'from pathlib import Path; import os,sys; '
                'import shared_wong_choi.research_review_runtime as r; '
                'import shared_wong_choi.research_supervision as s; original=r.record_review; '
                'r.record_review=lambda **k: (original(**k),os._exit(77)); s._worker(Path(sys.argv[1]))'
            )
            return super().run(replace(invocation, argv=(sys.executable, '-c', program, invocation.argv[-1])), **kwargs)
    failed = run(ResearchReviewCursorRunner(replace(runner.runtime, executor=Crash()), runner.registry))
    assert failed.disposition is ResearchDisposition.FAILED
    assert state(path) == before
    resumed = run(runner)
    assert resumed.advanced
    summary = json.loads(resumed.review.report_path.read_bytes())
    assert summary['created_reviews'] == 1 and summary['already_recorded_reviews'] == 1


def _cursor_crash_child(state_root, warm_root, lock_paths, registry_root, point):
    # Fresh interpreter: never inherit SQLite/native library state via fork on
    # macOS. Reconstruct only trusted fixture configuration, not live settings.
    from shared_wong_choi.research_runner import ResearchRuntime
    from shared_wong_choi.research_registry import ExperimentRegistry
    import shared_wong_choi.research_review_cursor as module
    runtime = ResearchRuntime(state_root=Path(state_root), warm_root=Path(warm_root),
                              production_lock_paths=tuple(Path(p) for p in lock_paths),
                              executor=SubprocessResearchExecutor(poll_seconds=.02, terminate_grace=.1))
    child_runner = ResearchReviewCursorRunner(runtime, ExperimentRegistry(Path(registry_root)))
    if point == 'proof':
        original = module.ResearchReviewCursorRunner._proof
        def crash_proof(*args, **kwargs):
            original(*args, **kwargs)
            os._exit(77)
        module.ResearchReviewCursorRunner._proof = crash_proof
    else:
        original = sqlite3.connect
        class CrashConnection(sqlite3.Connection):
            def execute(self, sql, parameters=()):
                result = super().execute(sql, parameters)
                if (point == 'update' and sql.startswith('UPDATE cursor_state')) or (point == 'commit' and sql == 'COMMIT'):
                    os._exit(77)
                return result
        module.sqlite3.connect = lambda *args, **kwargs: original(*args, **kwargs, factory=CrashConnection)
    run(child_runner)


@pytest.mark.parametrize('point', ['proof', 'update', 'commit'])
def test_parent_process_crash_has_atomic_cursor_and_receipts_survive(tmp_path, point):
    runner, path = fixture(tmp_path)
    before = state(path)
    process = multiprocessing.get_context('spawn').Process(
        target=_cursor_crash_child,
        args=(str(runner.runtime.state_root), str(runner.runtime.warm_root),
              [str(p) for p in runner.runtime.production_lock_paths], str(runner.registry.root), point))
    process.start()
    process.join(20)
    try:
        assert not process.is_alive()
        assert process.exitcode == 77
    finally:
        if process.is_alive():
            process.terminate()
            process.join(5)
    saved = state(path)  # SQLite recovers a hot rollback journal, if present.
    assert saved['generation'] == (1 if point == 'commit' else 0)
    if point != 'commit':
        assert saved == before
    resumed = run(runner, now=clock_args()['now'] + timedelta(days=1))
    assert resumed.disposition is ResearchDisposition.SUCCEEDED, resumed
    summary = json.loads(resumed.review.report_path.read_bytes())
    assert summary['created_reviews'] == 0 and summary['already_recorded_reviews'] == 2


def test_simultaneous_callers_run_one_worker_and_other_defers(tmp_path):
    runner, path = fixture(tmp_path)
    ready, release = threading.Event(), threading.Event()
    class Paused(SubprocessResearchExecutor):
        def run(self, invocation, **kwargs):
            ready.set()
            assert release.wait(5)
            return super().run(invocation, **kwargs)
    slow = ResearchReviewCursorRunner(replace(runner.runtime, executor=Paused()), runner.registry)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(run, slow)
        try:
            assert ready.wait(5)
            second = run(runner)
            assert second.disposition is ResearchDisposition.DEFERRED
            assert second.status == 'review_cursor_busy'
        finally:
            release.set()
        assert first.result(timeout=20).disposition is ResearchDisposition.SUCCEEDED
    assert state(path)['generation'] == 1


def test_late_registered_event_before_cursor_is_not_lost(tmp_path):
    from test_research_registry import run as run_record
    runner, path = fixture(tmp_path)
    assert run(runner).advanced
    record = run_record()
    runner.registry.append(replace(record, record_id=record.record_id + '-late'))
    result = run(runner, now=clock_args()['now'] + timedelta(days=1))
    summary = json.loads(result.review.report_path.read_bytes())
    assert summary['created_reviews'] == 1 and summary['run_completion_events'] == 2
    assert state(path)['window_start'] == summary['as_of']


@pytest.mark.parametrize('fault', ['symlink', 'oversized', 'corrupt', 'missing_proof', 'too_long'])
def test_unsafe_state_or_lost_proof_never_fabricates_progress(tmp_path, fault):
    runner, path = fixture(tmp_path)
    updates = {}
    if fault == 'symlink':
        target = path.with_suffix('.source')
        path.rename(target)
        path.symlink_to(target)
    elif fault == 'oversized':
        with path.open('ab') as handle:
            handle.truncate(2 * 1024 * 1024)
    elif fault == 'corrupt':
        path.write_bytes(b'not a sqlite database')
    elif fault == 'missing_proof':
        result = run(runner)
        result.review.report_path.rename(result.review.report_path.with_suffix('.saved'))
    else:
        updates['now'] = clock_args()['now'] + timedelta(days=367)
    before = path.read_bytes()
    result = run(runner, **updates)
    assert result.disposition is ResearchDisposition.BLOCKED
    assert not result.advanced and path.read_bytes() == before


def test_replaced_database_during_worker_cannot_report_cursor_committed(tmp_path):
    runner, path = fixture(tmp_path)
    before = path.read_bytes()
    class Replaced(SubprocessResearchExecutor):
        def run(self, invocation, **kwargs):
            result = super().run(invocation, **kwargs)
            path.rename(path.with_suffix('.original'))
            path.write_bytes(before)
            return result
    result = run(ResearchReviewCursorRunner(replace(runner.runtime, executor=Replaced()), runner.registry))
    assert result.disposition is ResearchDisposition.BLOCKED
    assert result.advanced is False
    assert state(path)['generation'] == 0


@pytest.mark.parametrize('domain', list(Domain))
def test_same_cursor_api_supports_each_domain_without_promotion(tmp_path, domain):
    runner, path = fixture(tmp_path)
    clock = clock_args()
    if domain is not Domain.AU:
        path = runner.initialize(domain=domain, initial_window_start=clock['window_start'],
                                 ruler_digest=clock['ruler_digest'], ruler_released_at=clock['ruler_released_at'])
    result = run(runner, domain=domain)
    assert result.disposition is ResearchDisposition.SUCCEEDED, result
    assert state(path)['config']['domain'] == domain.value
    assert state(path)['model_promotion_allowed'] is False


def test_ruler_freeze_persists_after_cursor_advances(tmp_path):
    runtime, registry = setup(tmp_path)
    (runtime.state_root / 'research-review-cursors').mkdir(parents=True)
    runner = ResearchReviewCursorRunner(runtime, registry)
    clock = clock_args()
    release = clock['now'] - timedelta(days=91)
    runner.initialize(domain=Domain.AU, initial_window_start=clock['window_start'],
                      ruler_digest=clock['ruler_digest'], ruler_released_at=release)
    first = run(runner, ruler_released_at=release)
    second = run(runner, now=clock['now'] + timedelta(days=1), ruler_released_at=release)
    assert first.advanced and second.advanced
    assert json.loads(second.review.report_path.read_bytes())['freeze_research_required'] is True


@pytest.mark.parametrize('fault', ['duplicate_json_key', 'hash', 'promotion', 'generation'])
def test_invalid_cursor_payload_becomes_blocked_result(tmp_path, fault):
    runner, path = fixture(tmp_path)
    value = state(path)
    if fault == 'duplicate_json_key':
        encoded = json.dumps(value).replace('"generation": 0', '"generation": 0, "generation": 0')
    else:
        if fault == 'hash':
            value['content_hash'] = '0' * 64
        elif fault == 'promotion':
            value['model_promotion_allowed'] = True
        else:
            value['generation'] = True
        if fault != 'hash':
            value.pop('content_hash')
            value['content_hash'] = _hash(value)
        encoded = json.dumps(value)
    with sqlite3.connect(path) as db:
        db.execute('UPDATE cursor_state SET payload=? WHERE id=1', (encoded,))
    result = run(runner)
    assert result.disposition is ResearchDisposition.BLOCKED
    assert result.advanced is False


def test_commit_storage_failure_rolls_back_cursor(tmp_path, monkeypatch):
    import shared_wong_choi.research_review_cursor as module
    runner, path = fixture(tmp_path)
    before = state(path)
    original = sqlite3.connect
    class DiskFull(sqlite3.Connection):
        def execute(self, sql, parameters=()):
            if sql == 'COMMIT':
                raise sqlite3.OperationalError('disk full')
            return super().execute(sql, parameters)
    with monkeypatch.context() as patcher:
        patcher.setattr(module.sqlite3, 'connect', lambda *a, **k: original(*a, **k, factory=DiskFull))
        result = run(runner)
    assert result.disposition is ResearchDisposition.BLOCKED
    assert result.advanced is False and state(path) == before
    assert run(runner).advanced


@pytest.mark.parametrize('preempt', [False, True])
def test_supervisor_timeout_or_production_preemption_preserves_cursor(tmp_path, preempt):
    runner, path = fixture(tmp_path)
    before = state(path)
    fifo, ready = tmp_path / 'blocked-index', tmp_path / 'ready'
    os.mkfifo(fifo)
    handles = []
    class Blocked(SubprocessResearchExecutor):
        def run(self, invocation, *, timeout_seconds, production_active):
            program = (
                'from pathlib import Path; import sys; import shared_wong_choi.research_review_runtime as r; '
                'import shared_wong_choi.research_supervision as s; '
                f'r.build_research_index=lambda **k: (Path({str(ready)!r}).touch(),open({str(fifo)!r}).read())[1]; '
                's._worker(Path(sys.argv[1]))'
            )
            def check():
                if preempt and ready.exists() and not handles:
                    handle = runner.runtime.production_lock_paths[0].open('a')
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    handles.append(handle)
                return production_active()
            return super().run(replace(invocation, argv=(sys.executable, '-c', program, invocation.argv[-1])),
                               timeout_seconds=1, production_active=check)
    try:
        result = run(ResearchReviewCursorRunner(replace(runner.runtime, executor=Blocked()), runner.registry))
    finally:
        for handle in handles:
            handle.close()
    assert ready.exists()
    assert result.disposition is (ResearchDisposition.PREEMPTED if preempt else ResearchDisposition.TIMED_OUT)
    assert result.advanced is False and state(path) == before
