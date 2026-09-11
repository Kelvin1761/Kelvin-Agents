from __future__ import annotations

import json
import fcntl
import os
import sys
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared_wong_choi.research_index import record_review, _hash
from shared_wong_choi.research_review_clock import plan_reviews
from shared_wong_choi.research_notification_runtime import ResearchNotificationRunner
from shared_wong_choi.research_runner import ResearchDisposition, SubprocessResearchExecutor
from shared_wong_choi.contracts import Domain
from test_research_notification_runtime import setup, summary
from test_research_notifications import fixture as box_fixture, route
from test_research_index import clock_args


def catchup(runtime, registry, helper, **changes):
    return ResearchNotificationRunner(runtime, registry).catch_up(**{
        'domain': Domain.AU, 'route': route(), 'helper_path': helper,
        'estimated_bytes': 1048576, 'timeout_seconds': 15, 'scan_limit': 1, **changes,
    })


def add_week(runtime, registry, week=1):
    clock = clock_args()
    options = {**clock, 'window_start': clock['now'] + timedelta(days=7*(week-1)),
               'now': clock['now'] + timedelta(days=7*week)}
    paths = []
    for request in plan_reviews(**options)['requests']:
        result = record_review(root=runtime.warm_root / 'research-reviews', registry_root=registry.root,
                               clock_inputs=options, request_id=request['request_id'])
        paths.append(result['path'])
    return paths


def test_read_only_outbox_inspection_does_not_create_or_send(tmp_path):
    path, box, calls = box_fixture(tmp_path)
    before = list(box.root.iterdir())
    result = box.inspect(path)
    assert result['status'] == 'not_attempted'
    assert list(box.root.iterdir()) == before and calls == []
    box.dispatch(path)
    files = {str(p): p.read_bytes() for p in box.root.rglob('*.json')}
    assert box.inspect(path)['status'] == 'already_sent'
    assert len(calls) == 1
    assert files == {str(p): p.read_bytes() for p in box.root.rglob('*.json')}


def test_bounded_catchup_crosses_pages_and_fresh_runner_skips_prior_sends(tmp_path):
    runtime, registry, ids, helper, marker = setup(tmp_path)
    add_week(runtime, registry)
    first = summary(catchup(runtime, registry, helper))
    assert first['scanned_count'] == 1 and first['counts']['sent'] == 1
    assert first['cycle_complete'] is False
    second = summary(catchup(runtime, registry, helper))
    third = summary(catchup(runtime, registry, helper))
    assert third['cycle_complete'] is True
    assert len({s['observed'][0]['request_id'] for s in (first, second, third)}) == 3
    assert marker.read_text().splitlines() == ['sent'] * 3
    again = summary(catchup(runtime, registry, helper, scan_limit=10))
    assert again['counts']['skipped_sent'] == 3 and again['counts']['sent'] == 0
    assert again['delivery_confirmed'] is False
    assert marker.read_text().splitlines() == ['sent'] * 3


def test_ambiguous_prior_send_is_not_retried_and_does_not_starve_later_receipts(tmp_path):
    runtime, registry, ids, helper, marker = setup(tmp_path)
    helper.write_text("import json\nprint(json.dumps({'ok': True, 'status': 'dry_run'}))\n")
    first = summary(catchup(runtime, registry, helper))
    assert first['counts']['new_reconcile'] == 1
    add_week(runtime, registry)
    next_page = summary(catchup(runtime, registry, helper, scan_limit=10))
    assert next_page['counts']['preexisting_reconcile'] == 1
    assert next_page['counts']['new_reconcile'] == 2
    assert not marker.exists()
    assert len(list((runtime.state_root / 'research-notifications').rglob('intent.json'))) == 3


def test_disabled_catchup_never_allocates_worker_or_selection_state(tmp_path):
    runtime, registry, ids, helper, marker = setup(tmp_path)
    result = catchup(runtime, registry, helper, route=route(enabled=False))
    assert result.disposition is ResearchDisposition.DEFERRED
    assert result.attempt_path is None and not marker.exists()
    assert not list((runtime.state_root / 'research-notifications').rglob('selection.json'))


@pytest.mark.parametrize('limit', [0, 51, True, '1'])
def test_invalid_scan_bound_never_starts_worker(tmp_path, limit):
    runtime, registry, ids, helper, marker = setup(tmp_path)
    with pytest.raises(ValueError):
        catchup(runtime, registry, helper, scan_limit=limit)
    assert not marker.exists()


def test_missing_receipt_root_is_not_empty_healthy_catchup(tmp_path):
    runtime, registry, ids, helper, marker = setup(tmp_path)
    (runtime.warm_root / 'research-reviews').rename(runtime.warm_root / 'saved-reviews')
    result = catchup(runtime, registry, helper)
    assert result.disposition is ResearchDisposition.FAILED
    assert not marker.exists()


def test_whole_selected_page_validated_before_any_new_send(tmp_path):
    runtime, registry, ids, helper, marker = setup(tmp_path)
    paths = add_week(runtime, registry)
    paths[-1].write_text('{}')
    result = catchup(runtime, registry, helper, scan_limit=10)
    assert result.disposition is ResearchDisposition.FAILED
    assert not marker.exists()


def selection(runtime):
    return runtime.state_root / 'research-notifications/au/selection.json'


class InjectWorker(SubprocessResearchExecutor):
    def __init__(self, code):
        super().__init__(poll_seconds=0.02, terminate_grace=0.1)
        self.code = code

    def run(self, invocation, **kwargs):
        code = ('from pathlib import Path; import os,sys; '
                'import shared_wong_choi.research_notification_catchup as c; '
                'import shared_wong_choi.research_notifications as n; '
                'import shared_wong_choi.research_supervision as s; ' + self.code + '; '
                's._worker(Path(sys.argv[1]))')
        return super().run(replace(invocation, argv=(sys.executable, '-c', code, invocation.argv[-1])), **kwargs)


@pytest.mark.parametrize('point', ['send', 'before_state', 'after_state'])
def test_real_worker_crash_preserves_transport_evidence_and_replay(tmp_path, point):
    runtime, registry, ids, helper, marker = setup(tmp_path)
    add_week(runtime, registry)
    code = {
        'send': 'old=n.ResearchTelegramOutbox.dispatch; n.ResearchTelegramOutbox.dispatch=lambda *a,**k: (old(*a,**k),os._exit(77))',
        'before_state': 'c._advance_state=lambda *a,**k: os._exit(77)',
        'after_state': 'old=c._advance_state; c._advance_state=lambda *a,**k: (old(*a,**k),os._exit(77))',
    }[point]
    failed = catchup(replace(runtime, executor=InjectWorker(code)), registry, helper)
    assert failed.disposition is ResearchDisposition.FAILED
    assert marker.read_text() == 'sent\n'
    assert selection(runtime).exists() is (point == 'after_state')
    # A committed pagination advance is not a transport acknowledgement.
    # Either old or new cursor recovers safely; one full later cycle revisits all.
    for _ in range(4):
        summary(catchup(runtime, registry, helper, scan_limit=10))
    assert marker.read_text().splitlines() == ['sent'] * 3


def test_paginated_scan_rediscovers_late_insert_before_saved_cursor(tmp_path):
    runtime, registry, ids, helper, marker = setup(tmp_path)
    add_week(runtime, registry)
    summary(catchup(runtime, registry, helper, scan_limit=2))
    previous = json.loads(selection(runtime).read_text())['after_request_id']
    new = []
    for week in range(2, 7):
        new.extend(add_week(runtime, registry, week))
        if any(p.stem < previous for p in new):
            break
    assert any(p.stem < previous for p in new)
    seen = set()
    for _ in range(2):
        page = summary(catchup(runtime, registry, helper, scan_limit=50))
        seen.update(i['request_id'] for i in page['observed'])
    assert {p.stem for p in new} <= seen
    assert len(marker.read_text().splitlines()) == 3 + len(new)


@pytest.mark.parametrize('fault', ['corrupt', 'generation', 'context', 'route', 'helper', 'symlink'])
def test_pagination_conflict_does_not_reset_or_send(tmp_path, fault):
    runtime, registry, ids, helper, marker = setup(tmp_path)
    add_week(runtime, registry)
    summary(catchup(runtime, registry, helper))
    state = selection(runtime)
    kwargs = {}
    if fault == 'corrupt':
        state.write_text('{}')
    elif fault in {'generation', 'context'}:
        value = json.loads(state.read_text())
        if fault == 'generation':
            value['generation'] = True
        else:
            value['context']['registry_root'] = str(tmp_path / 'other')
        value.pop('content_hash')
        value['content_hash'] = _hash(value)
        state.write_text(json.dumps(value))
    elif fault == 'route':
        kwargs['route'] = route(primary_chat_id='123', authorized_chat_id='123')
    elif fault == 'helper':
        helper.write_text(helper.read_text() + '\n# changed helper\n')
    else:
        saved = state.with_suffix('.saved')
        state.rename(saved)
        state.symlink_to(saved)
    before = state.read_bytes()
    assert catchup(runtime, registry, helper, **kwargs).disposition is ResearchDisposition.FAILED
    assert marker.read_text() == 'sent\n' and state.read_bytes() == before


@pytest.mark.parametrize('fault', ['production', 'heavy', 'offline', 'capacity'])
def test_catchup_resources_defer_without_pagination_or_send(tmp_path, fault):
    runtime, registry, ids, helper, marker = setup(tmp_path)
    handle = None
    if fault in {'production', 'heavy'}:
        path = runtime.production_lock_paths[0] if fault == 'production' else runtime.state_root / 'locks/research-heavy-worker.lock'
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open('a')
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    elif fault == 'offline':
        runtime = replace(runtime, warm_root=tmp_path / 'offline')
    else:
        runtime = replace(runtime, free_space_probe=lambda _: 0)
    try:
        result = catchup(runtime, registry, helper)
    finally:
        if handle:
            handle.close()
    assert result.disposition is ResearchDisposition.DEFERRED
    assert not marker.exists() and not selection(runtime).exists()


@pytest.mark.parametrize('preempt', [False, True])
def test_hanging_helper_killed_and_unknown_send_not_retried(tmp_path, preempt):
    runtime, registry, ids, helper, marker = setup(tmp_path)
    lifecycle = tmp_path / 'helper.lock'
    helper.write_text('import fcntl,time\nfrom pathlib import Path\n'
                      f"held=open({str(lifecycle)!r},'a')\nfcntl.flock(held,fcntl.LOCK_EX)\n"
                      f"Path({str(marker)!r}).write_text('attempted')\ntime.sleep(60)\n")
    handles, errors = [], []
    class Interrupt(SubprocessResearchExecutor):
        def run(self, invocation, *, timeout_seconds, production_active):
            def check():
                if preempt and marker.exists() and not handles:
                    held = runtime.production_lock_paths[0].open('a')
                    fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    handles.append(held)
                return production_active()
            try:
                # Allow worker/import startup; the production test should be
                # interrupted by its ready marker, not an unrelated 1s deadline.
                return super().run(invocation, timeout_seconds=10 if preempt else 5, production_active=check)
            except Exception as error:
                errors.append((type(error).__name__, getattr(error, 'errno', None)))
                raise
    try:
        result = catchup(replace(runtime, executor=Interrupt(poll_seconds=0.02, terminate_grace=0.1)), registry, helper)
    finally:
        for held in handles:
            held.close()
    assert marker.exists(), (result, errors)
    if preempt:
        assert handles, (result, errors)
    assert result.disposition is (ResearchDisposition.PREEMPTED if preempt else ResearchDisposition.TIMED_OUT), errors
    with lifecycle.open('a') as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
    page = summary(catchup(runtime, registry, helper))
    assert page['counts']['preexisting_reconcile'] == 1 and page['counts']['sent'] == 0
    assert marker.read_text() == 'attempted'


@pytest.mark.parametrize('fault', ['oversized', 'budget', 'symlink', 'filename', 'foreign_registry'])
def test_unsafe_receipt_page_fails_before_any_new_intent(tmp_path, fault):
    from shared_wong_choi.research_registry import ExperimentRegistry
    runtime, registry, ids, helper, marker = setup(tmp_path)
    path = runtime.warm_root / 'research-reviews/au' / (ids[0] + '.json')
    if fault == 'oversized':
        with path.open('r+b') as handle:
            handle.truncate(16777217)
    elif fault == 'budget':
        code = ('old=c._Reader; c._Reader=lambda *a,**k: old(*a,**{**k,"max_total_bytes":1})')
        runtime = replace(runtime, executor=InjectWorker(code))
    elif fault == 'symlink':
        saved = tmp_path / 'saved.json'
        path.rename(saved)
        path.symlink_to(saved)
    elif fault == 'filename':
        (path.parent / 'unrecognized.json').write_text('{}')
    else:
        registry = ExperimentRegistry(tmp_path / 'foreign-registry')
    result = catchup(runtime, registry, helper)
    assert result.disposition is ResearchDisposition.FAILED
    assert not marker.exists() and not list((runtime.state_root / 'research-notifications').rglob('intent.json'))


@pytest.mark.parametrize('fault', ['count', 'cursor', 'complete', 'authority', 'review_set', 'summary_size'])
def test_parent_rejects_rehashed_false_page_summary(tmp_path, fault):
    runtime, registry, ids, helper, marker = setup(tmp_path)
    add_week(runtime, registry)
    class Forged(SubprocessResearchExecutor):
        def run(self, invocation, **kwargs):
            execution = super().run(invocation, **kwargs)
            completed = json.loads(invocation.metrics_path.read_text())
            path = Path(completed['report_path'])
            value = json.loads(path.read_text())
            if fault == 'count':
                value['counts']['sent'] += 1
            elif fault == 'cursor':
                value['selection_after']['after_request_id'] = 'f' * 64
                value['selection_after'].pop('content_hash')
                value['selection_after']['content_hash'] = _hash(value['selection_after'])
            elif fault == 'complete':
                value['cycle_complete'] = True
            elif fault == 'authority':
                value['delivery_confirmed'] = True
            elif fault == 'review_set':
                value['processed'][0]['request_id'] = 'f' * 64
            else:
                value['padding'] = 'x' * 65536
            value.pop('content_hash')
            value['content_hash'] = _hash(value)
            path.write_text(json.dumps(value))
            completed['content_hash'] = value['content_hash']
            invocation.metrics_path.write_text(json.dumps(completed))
            return execution
    result = catchup(replace(runtime, executor=Forged(poll_seconds=0.02, terminate_grace=0.1)), registry, helper)
    assert result.disposition is ResearchDisposition.FAILED and result.report_path is None


def test_empty_existing_collection_is_explicit_empty_page(tmp_path):
    runtime, registry, ids, helper, marker = setup(tmp_path)
    store = runtime.warm_root / 'research-reviews/au'
    store.rename(tmp_path / 'saved-reviews')
    store.mkdir()
    page = summary(catchup(runtime, registry, helper))
    assert page['scanned_count'] == 0 and page['cycle_complete'] is True
    assert not marker.exists() and page['delivery_confirmed'] is False


def test_blocking_receipt_io_is_contained_by_worker_timeout(tmp_path):
    runtime, registry, ids, helper, marker = setup(tmp_path)
    fifo, ready = tmp_path / 'fifo', tmp_path / 'ready'
    os.mkfifo(fifo)
    code = (f'c._load_review_receipt=lambda *a: (Path({str(ready)!r}).touch(),open({str(fifo)!r}).read())[1]')
    result = catchup(replace(runtime, executor=InjectWorker(code)), registry, helper, timeout_seconds=1)
    assert ready.exists() and result.disposition is ResearchDisposition.TIMED_OUT
    assert not marker.exists() and not selection(runtime).exists()


def test_catchup_state_and_summaries_do_not_persist_route_secrets(tmp_path):
    runtime, registry, ids, helper, marker = setup(tmp_path)
    summary(catchup(runtime, registry, helper))
    for root in (runtime.warm_root, runtime.state_root):
        for path in root.rglob('*.json'):
            assert b'dummy-secret' not in path.read_bytes()
            assert b'"98765"' not in path.read_bytes()


@pytest.mark.parametrize('after_replace', [False, True])
def test_lost_pagination_replace_ack_keeps_safe_old_or_new_generation(tmp_path, after_replace):
    runtime, registry, ids, helper, marker = setup(tmp_path)
    add_week(runtime, registry)
    summary(catchup(runtime, registry, helper))
    code = ('old=c.os.replace; c.os.replace=lambda *a,**k: '
            + ('(old(*a,**k),os._exit(77))' if after_replace else 'os._exit(77)'))
    result = catchup(replace(runtime, executor=InjectWorker(code)), registry, helper)
    assert result.disposition is ResearchDisposition.FAILED
    assert len(marker.read_text().splitlines()) == 2
    assert json.loads(selection(runtime).read_text())['generation'] == (2 if after_replace else 1)
    for _ in range(2):
        summary(catchup(runtime, registry, helper, scan_limit=10))
    assert marker.read_text().splitlines() == ['sent'] * 3


def test_warm_loss_does_not_recreate_volume_or_discard_hot_intent(tmp_path):
    runtime, registry, ids, helper, marker = setup(tmp_path)
    helper.write_text('import time\nfrom pathlib import Path\n'
                      f"Path({str(marker)!r}).write_text('attempted')\ntime.sleep(60)\n")
    moved = tmp_path / 'disconnected'
    errors = []
    class Disconnect(SubprocessResearchExecutor):
        def run(self, invocation, *, timeout_seconds, production_active):
            def check():
                if marker.exists() and runtime.warm_root.exists():
                    runtime.warm_root.rename(moved)
                return production_active()
            try:
                return super().run(invocation, timeout_seconds=10, production_active=check)
            except Exception as error:
                import traceback
                errors.append((type(error).__name__, getattr(error, 'errno', None),
                               [(f.name, f.lineno) for f in traceback.extract_tb(error.__traceback__)]))
                raise
    result = catchup(replace(runtime, executor=Disconnect(poll_seconds=0.02, terminate_grace=0.1)), registry, helper)
    assert result.disposition is ResearchDisposition.PREEMPTED, errors
    assert not runtime.warm_root.exists() and not selection(runtime).exists()
    assert len(list((runtime.state_root / 'research-notifications').rglob('intent.json'))) == 1
    moved.rename(runtime.warm_root)
    page = summary(catchup(runtime, registry, helper))
    assert page['counts']['preexisting_reconcile'] == 1 and marker.read_text() == 'attempted'


@pytest.mark.parametrize('domain', [Domain.HKJC, Domain.TENNIS, Domain.NBA])
def test_domain_pages_keep_distinct_store_and_no_promotion(tmp_path, domain):
    runtime, registry, ids, helper, marker = setup(tmp_path)
    options = {**clock_args(), 'domain': domain}
    for review in plan_reviews(**options)['requests']:
        record_review(root=runtime.warm_root / 'research-reviews', registry_root=registry.root,
                      clock_inputs=options, request_id=review['request_id'])
    page = summary(catchup(runtime, registry, helper, domain=domain))
    assert page['domain'] == domain.value and page['counts']['sent'] == 1
    assert page['model_promotion_allowed'] is False
    assert (runtime.state_root / 'research-notifications' / domain.value / 'selection.json').is_file()
    assert not selection(runtime).exists()


def test_parent_rejects_false_wrap_on_nonfinal_page(tmp_path):
    from shared_wong_choi.research_notification_catchup import verify_catchup_summary
    from shared_wong_choi.research_notification_runtime import _completion
    runtime, registry, ids, helper, marker = setup(tmp_path)
    add_week(runtime, registry)
    summary(catchup(runtime, registry, helper))
    result = catchup(runtime, registry, helper)
    value = summary(result)
    request = json.loads((result.attempt_path / 'request.json').read_text())
    assert value['selection_before']['after_request_id'] < value['observed'][0]['request_id']
    value.update(wrapped=True, start_index=0, remaining_in_cycle=value['listing_count'] - 1)
    value.pop('content_hash')
    value['content_hash'] = _hash(value)
    result.report_path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='transition'):
        verify_catchup_summary(request=request, runtime=runtime, report_path=result.report_path,
                               receipt=_completion(request, result.report_path, value))
