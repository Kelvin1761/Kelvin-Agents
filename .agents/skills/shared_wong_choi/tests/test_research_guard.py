"""Execution must obey pinned review clocks, not caller-supplied 'not frozen'."""
from dataclasses import replace
from datetime import timedelta
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared_wong_choi.contracts import Domain
from shared_wong_choi.research_runner import ResearchDisposition, create_research_adapter
from shared_wong_choi.research_review_cursor import ResearchReviewCursorRunner
from test_research_review_cursor import fixture, run
from test_research_index import clock_args
from test_research_runner import runtime, registered_runner, spec, snapshot, job


def guard(runner, **changes):
    from shared_wong_choi.research_guard import research_gate_status
    return research_gate_status(replace(runner.runtime, clock=lambda: clock_args()['now']),
                                runner.registry, Domain.AU, '1' * 64, **changes)


def test_runner_without_review_configuration_never_executes(tmp_path):
    data = snapshot(tmp_path)
    runner = registered_runner(tmp_path, runtime(tmp_path))
    path = runner.runtime.state_root / 'research-review-cursors/au.sqlite3'
    path.rename(path.with_suffix('.saved'))
    result = runner.run(job(tmp_path, data.path), spec(), create_research_adapter('au'))
    assert result.status == 'research_review_unavailable'
    assert result.disposition is ResearchDisposition.BLOCKED
    assert result.artifact_path is None


def test_initial_pinned_ruler_is_not_an_expired_ruler_or_model_approval(tmp_path):
    runner, _ = fixture(tmp_path)
    assert guard(runner) is None


def test_age_freezes_even_if_review_has_never_run(tmp_path):
    runner, _ = fixture(tmp_path)
    from shared_wong_choi.research_guard import research_gate_status
    release = clock_args()['ruler_released_at']
    for delta, expected in [(timedelta(days=90, microseconds=-1), None),
                            (timedelta(days=90), 'research_frozen_ruler_90_day')]:
        configured = replace(runner.runtime, clock=lambda: release + delta)
        assert research_gate_status(configured, runner.registry, Domain.AU, '1' * 64) == expected


def test_once_observed_expired_clock_cannot_unfreeze_on_clock_rollback(tmp_path):
    runner, _ = fixture(tmp_path)
    from shared_wong_choi.research_guard import research_gate_status
    release = clock_args()['ruler_released_at']
    expired = replace(runner.runtime, clock=lambda: release + timedelta(days=90))
    assert research_gate_status(expired, runner.registry, Domain.AU, '1' * 64) == 'research_frozen_ruler_90_day'
    assert guard(runner) == 'research_frozen_ruler_90_day'


@pytest.mark.parametrize('fault', ['corrupt', 'oversized', 'symlink'])
def test_latch_damage_never_gets_replaced_or_cleared(tmp_path, fault):
    runner, path = fixture(tmp_path)
    target = path.with_suffix('.freeze.json')
    if fault == 'corrupt':
        target.write_bytes(b'partial')
    elif fault == 'oversized':
        target.write_bytes(b'x' * 65537)
    else:
        target.symlink_to(path)
    before = target.read_bytes()
    assert guard(runner) == 'research_review_unavailable'
    assert target.read_bytes() == before


def test_lost_directory_sync_keeps_freeze_and_never_permits_computation(tmp_path, monkeypatch):
    runner, path = fixture(tmp_path)
    import shared_wong_choi.research_review_cursor as module
    from shared_wong_choi.research_guard import research_gate_status
    def fail(_):
        raise OSError('injected directory fsync failure')
    monkeypatch.setattr(module, '_fsync_directory', fail)
    expired = replace(runner.runtime, clock=lambda: clock_args()['ruler_released_at'] + timedelta(days=90))
    assert research_gate_status(expired, runner.registry, Domain.AU, '1' * 64) == 'research_review_unavailable'
    assert path.with_suffix('.freeze.json').exists()
    assert guard(runner) == 'research_frozen_ruler_90_day'


def test_competing_latch_disappearance_is_not_permission(tmp_path, monkeypatch):
    runner, path = fixture(tmp_path)
    import shared_wong_choi.research_guard as module
    original = module.os.open
    def disappeared(target, flags, *args, **kwargs):
        if Path(target) == path.with_suffix('.freeze.json'):
            raise FileExistsError('competitor existed but vanished before read')
        return original(target, flags, *args, **kwargs)
    monkeypatch.setattr(module.os, 'open', disappeared)
    expired = replace(runner.runtime, clock=lambda: clock_args()['ruler_released_at'] + timedelta(days=90))
    assert module.research_gate_status(expired, runner.registry, Domain.AU, '1' * 64) == 'research_review_unavailable'


def test_review_receipt_and_cursor_advance_cannot_clear_expired_ruler(tmp_path):
    runner, _ = fixture(tmp_path)
    now = clock_args()['ruler_released_at'] + timedelta(days=91)
    assert run(runner, now=now).disposition is ResearchDisposition.SUCCEEDED
    from shared_wong_choi.research_guard import research_gate_status
    assert research_gate_status(replace(runner.runtime, clock=lambda: now), runner.registry,
                                Domain.AU, '1' * 64) == 'research_frozen_ruler_90_day'


@pytest.mark.parametrize('fault', ['missing', 'corrupt', 'symlink', 'oversized', 'locked'])
def test_guard_fails_closed_on_unreadable_hot_state(tmp_path, fault):
    runner, path = fixture(tmp_path)
    db = None
    if fault == 'missing':
        path.rename(path.with_suffix('.saved'))
    elif fault == 'corrupt':
        path.write_bytes(b'not sqlite')
    elif fault == 'symlink':
        saved = path.with_suffix('.saved')
        path.rename(saved)
        path.symlink_to(saved)
    elif fault == 'oversized':
        with path.open('ab') as handle:
            handle.write(b'x' * (1024 * 1024))
    else:
        db = sqlite3.connect(path)
        db.execute('BEGIN EXCLUSIVE')
    try:
        assert guard(runner) == 'research_review_unavailable'
    finally:
        if db:
            db.close()


def test_changed_ruler_is_not_permission_to_restart_90_day_clock(tmp_path):
    runner, _ = fixture(tmp_path)
    from shared_wong_choi.research_guard import research_gate_status
    assert research_gate_status(runner.runtime, runner.registry, Domain.AU, '2' * 64) == 'research_review_unavailable'


def test_missing_prior_review_proof_blocks_research(tmp_path):
    runner, _ = fixture(tmp_path)
    result = run(runner)
    assert result.disposition is ResearchDisposition.SUCCEEDED
    result.review.report_path.rename(result.review.report_path.with_suffix('.saved'))
    assert guard(runner) == 'research_review_unavailable'


def test_clock_before_verified_review_is_not_a_new_lease(tmp_path):
    runner, _ = fixture(tmp_path)
    assert run(runner, now=clock_args()['now'] + timedelta(days=1)).disposition is ResearchDisposition.SUCCEEDED
    assert guard(runner) == 'research_review_unavailable'


def test_unconfigured_queue_can_record_job_but_cannot_claim_it(tmp_path):
    from shared_wong_choi.research_runner import ResearchQueue, QueueConflictError
    queue = ResearchQueue(tmp_path / 'queue')
    queue.enqueue(job(tmp_path, snapshot(tmp_path).path))
    with pytest.raises(QueueConflictError, match='review runtime'):
        queue.claim_next('worker')
    assert not (queue.root / 'claims').exists()


def test_expired_queue_keeps_job_unclaimed_across_new_workers(tmp_path):
    from test_research_runner import configured_queue
    from shared_wong_choi.research_runner import ResearchQueue
    from datetime import datetime
    queue = configured_queue(tmp_path)
    current = job(tmp_path, snapshot(tmp_path).path)
    queue.enqueue(current)
    now = datetime.fromisoformat(spec().created_at) + timedelta(days=90)
    runtime = replace(queue.runtime, clock=lambda: now)
    for worker in ('first', 'second'):
        fresh = ResearchQueue(queue.root, runtime=runtime, registry=queue.registry)
        assert fresh.claim_next(worker) is None
        assert fresh.last_blocked == {current.job_id: 'research_frozen_ruler_90_day'}
    assert not (queue.root / 'claims').exists()


def test_only_frozen_domain_is_skipped_in_shared_queue(tmp_path):
    from test_research_runner import configured_queue
    from research_test_support import pin_review
    from datetime import datetime
    queue = configured_queue(tmp_path)
    data = snapshot(tmp_path)
    au_job = job(tmp_path, data.path)
    queue.enqueue(au_job)
    now = datetime.fromisoformat(spec().created_at) + timedelta(days=90)
    current_nba = replace(spec(Domain.NBA), created_at=now.isoformat())
    queue.registry.append(current_nba)
    pin_review(queue.runtime, queue.registry, current_nba, queue_root=queue.root)
    nba_job = replace(au_job, domain=Domain.NBA, spec_id=current_nba.record_id,
                      job_id='wc:nba:research-job:active')
    queue.enqueue(nba_job)
    queue.runtime = replace(queue.runtime, clock=lambda: now)
    assert queue.claim_next('worker').job == nba_job
    assert queue.last_blocked == {au_job.job_id: 'research_frozen_ruler_90_day'}


def test_runner_stops_when_ruler_expires_inside_command(tmp_path):
    from test_research_runner import DeterministicExecutor
    from datetime import datetime
    now = [datetime.fromisoformat(spec().created_at) + timedelta(days=89)]
    calls = []

    class ExpireDuringCommand(DeterministicExecutor):
        def run(self, invocation, *, timeout_seconds, production_active):
            calls.append(invocation.role)
            now[0] += timedelta(days=1)
            assert production_active() is True
            return super().run(invocation, timeout_seconds=timeout_seconds,
                               production_active=production_active)

    data = snapshot(tmp_path)
    current = replace(runtime(tmp_path, executor=ExpireDuringCommand()), clock=lambda: now[0])
    runner = registered_runner(tmp_path, current)
    result = runner.run(job(tmp_path, data.path), spec(), create_research_adapter('au'))
    assert result.status == 'research_frozen_ruler_90_day'
    assert result.disposition is ResearchDisposition.PREEMPTED
    assert calls == ['baseline']


@pytest.mark.parametrize('action', ['prepare', 'scoring', 'postflight'])
def test_managed_entries_block_missing_review_before_allocating_attempt(tmp_path, action):
    from test_research_resources import fixture as postflight_fixture
    from shared_wong_choi.research_supervision import _phase
    from shared_wong_choi.research_resources import ResearchPostflightRunner
    current_spec, args, current, registry = postflight_fixture(tmp_path)
    path = current.state_root / 'research-review-cursors/au.sqlite3'
    path.rename(path.with_suffix('.saved'))
    if action == 'postflight':
        result = ResearchPostflightRunner(current, registry).run(
            current_spec, **args, estimated_bytes=1024, timeout_seconds=10)
        outcome = (result.disposition, result.status, result.attempt_path)
    else:
        outcome = _phase(current, registry, current_spec, action=action, payload={},
                         estimated_bytes=1024, timeout_seconds=10)[:3]
    assert outcome == (ResearchDisposition.BLOCKED, 'research_review_unavailable', None)


@pytest.mark.parametrize('action', ['prepare', 'scoring', 'postflight'])
def test_worker_independently_rechecks_guard_after_parent_passes(tmp_path, action):
    from test_research_resources import fixture as postflight_fixture
    from shared_wong_choi.research_runner import SubprocessResearchExecutor
    from shared_wong_choi.research_supervision import _phase
    from shared_wong_choi.research_resources import ResearchPostflightRunner
    current_spec, args, current, registry = postflight_fixture(tmp_path)
    path = current.state_root / 'research-review-cursors/au.sqlite3'

    class MissedParentProbe:
        def run(self, invocation, *, timeout_seconds, production_active):
            path.rename(path.with_suffix('.saved'))
            # Deliberately disable the parent observation in this fault test;
            # the independent subprocess must still refuse work.
            return SubprocessResearchExecutor(poll_seconds=.02).run(
                invocation, timeout_seconds=timeout_seconds, production_active=lambda: False)

    current = replace(current, executor=MissedParentProbe())
    if action == 'postflight':
        result = ResearchPostflightRunner(current, registry).run(
            current_spec, **args, estimated_bytes=1024, timeout_seconds=10)
        outcome = (result.disposition, result.status)
    else:
        outcome = _phase(current, registry, current_spec, action=action, payload={},
                         estimated_bytes=1024, timeout_seconds=10)[:2]
    assert outcome == (ResearchDisposition.PREEMPTED, 'research_review_unavailable')


def test_live_scoring_process_stops_when_review_state_disappears(tmp_path):
    import time
    from concurrent.futures import ThreadPoolExecutor
    from test_research_supervision import fixture as scoring_fixture
    from shared_wong_choi.research_supervision import ResearchScoringRunner
    ready = tmp_path / 'command-ready'
    escaped = tmp_path / 'command-escaped'
    script = (f'import time; from pathlib import Path; Path({str(ready)!r}).touch(); '
              f'time.sleep(2); Path({str(escaped)!r}).touch(); time.sleep(20)')
    current_spec, current_job, current, registry = scoring_fixture(tmp_path, script)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(ResearchScoringRunner(current, registry).run, current_job,
                             current_spec, create_research_adapter('au'))
        deadline = time.monotonic() + 10
        while not ready.exists() and not future.done() and time.monotonic() < deadline:
            time.sleep(.02)
        assert ready.exists(), 'scoring command never started'
        path = current.state_root / 'research-review-cursors/au.sqlite3'
        path.rename(path.with_suffix('.saved'))
        result = future.result(timeout=10)
    assert result.disposition is ResearchDisposition.PREEMPTED, result
    assert result.status == 'research_review_unavailable', result
    time.sleep(2.1)
    assert not escaped.exists(), 'command survived the freeze interruption'
