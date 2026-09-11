from __future__ import annotations

import fcntl
import json
import os
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared_wong_choi.contracts import Domain
from shared_wong_choi.research_index import record_review
from shared_wong_choi.research_review_clock import plan_reviews
from shared_wong_choi.research_notification_runtime import ResearchNotificationRunner
from shared_wong_choi.research_runner import ResearchDisposition, SubprocessResearchExecutor
from shared_wong_choi.research_registry import ExperimentRegistry
from test_research_notifications import SENT, route
from test_research_index import fixture as registry_fixture, clock_args
from test_research_supervision import source_runtime


def setup(tmp_path):
    runtime, registry = source_runtime(tmp_path), registry_fixture(tmp_path)
    (runtime.state_root / "research-notifications").mkdir(parents=True)
    options = clock_args()
    ids = []
    for request in plan_reviews(**options)["requests"]:
        record_review(root=runtime.warm_root / "research-reviews", registry_root=registry.root,
                      clock_inputs=options, request_id=request["request_id"])
        ids.append(request["request_id"])
    helper = tmp_path / "fake-helper.py"
    marker = tmp_path / "fake-sent"
    helper.write_text("import json\nfrom pathlib import Path\n"
                      f"with Path({str(marker)!r}).open('a') as h: h.write('sent\\n')\n"
                      "print(json.dumps(" + repr(SENT) + "))\n")
    return runtime, registry, ids, helper, marker


def notify(runtime, registry, ids, helper, **kwargs):
    return ResearchNotificationRunner(runtime, registry).run(
        domain=Domain.AU, request_ids=ids, route=kwargs.pop("route", route()), helper_path=helper,
        estimated_bytes=1048576, timeout_seconds=kwargs.pop("timeout_seconds", 15), **kwargs)


def summary(result):
    assert result.disposition is ResearchDisposition.SUCCEEDED, result
    return json.loads(result.report_path.read_text())


def test_supervised_fake_send_then_dedup_preserves_receipts_and_secret_boundary(tmp_path):
    runtime, registry, ids, helper, marker = setup(tmp_path)
    original = {str(p): p.read_bytes() for p in (runtime.warm_root / "research-reviews").rglob("*.json")}
    first = summary(notify(runtime, registry, ids, helper))
    assert first["sent"] == 1 and first["reconcile_required"] == 0
    second = summary(notify(runtime, registry, ids, helper))
    assert second["sent"] == 0 and second["already_sent"] == 1
    assert marker.read_text() == "sent\n"
    assert second["delivery_confirmed"] is False and second["model_promotion_allowed"] is False
    for path, raw in original.items():
        assert Path(path).read_bytes() == raw
    for root in (runtime.warm_root, runtime.state_root):
        for path in root.rglob("*.json"):
            assert b"dummy-secret" not in path.read_bytes()
            assert b'"98765"' not in path.read_bytes()


def test_disabled_route_does_not_allocate_worker_or_create_outbox(tmp_path):
    runtime, registry, ids, helper, marker = setup(tmp_path)
    result = notify(runtime, registry, ids, helper, route=route(enabled=False))
    assert result.disposition is ResearchDisposition.DEFERRED and result.status == "disabled"
    assert result.attempt_path is None and not marker.exists()


def test_supervised_storage_summary_reaches_fake_helper_and_replay_is_deduped(tmp_path, monkeypatch):
    from test_research_presentation import storage_review
    runtime, registry, _, review, path = storage_review(tmp_path, monkeypatch)
    (runtime.state_root / "research-notifications").mkdir(parents=True)
    ids = [json.loads(path.read_text())["request_id"]]
    helper, marker = tmp_path / "fake-helper.py", tmp_path / "fake-message"
    helper.write_text("import json,sys\nfrom pathlib import Path\n"
                      f"Path({str(marker)!r}).write_text(sys.argv[sys.argv.index('--message')+1])\n"
                      "print(json.dumps(" + repr(SENT) + "))\n")
    kwargs = {"review_summary_path": review.report_path}
    first = summary(notify(runtime, registry, ids, helper, **kwargs))
    assert first["sent"] == 1 and first["delivery_confirmed"] is False
    assert "儲存健康：需留意（已核實時間點快照）" in marker.read_text()
    assert str(review.report_path) not in marker.read_text()
    assert summary(notify(runtime, registry, ids, helper, **kwargs))["already_sent"] == 1


def test_supervised_liveness_summary_reaches_fake_helper_and_replay_is_deduped(
        tmp_path):
    from test_research_presentation import liveness_review
    runtime, registry, _, review, path = liveness_review(tmp_path)
    (runtime.state_root / "research-notifications").mkdir(parents=True)
    ids = [json.loads(path.read_text())["request_id"]]
    helper, marker = tmp_path / "fake-helper.py", tmp_path / "fake-message"
    helper.write_text(
        "import json,sys\nfrom pathlib import Path\n"
        f"Path({str(marker)!r}).write_text(sys.argv[sys.argv.index('--message')+1])\n"
        "print(json.dumps(" + repr(SENT) + "))\n"
    )
    kwargs = {"review_summary_path": review.report_path}

    first = summary(notify(runtime, registry, ids, helper, **kwargs))

    assert first["sent"] == 1 and first["delivery_confirmed"] is False
    assert "運行存活：來源已核實（運行 1／未核實 0／非存活 0）" in marker.read_text()
    assert str(review.report_path) not in marker.read_text()
    assert summary(notify(runtime, registry, ids, helper, **kwargs))["already_sent"] == 1


def test_unowned_review_summary_never_creates_notification_intent(tmp_path):
    runtime, registry, ids, helper, marker = setup(tmp_path)
    result = notify(runtime, registry, ids, helper,
                    review_summary_path=tmp_path / "review-summary.json")
    assert result.disposition is ResearchDisposition.FAILED
    assert not marker.exists()
    assert not list((runtime.state_root / "research-notifications").rglob("intent.json"))


def test_storage_batch_is_fully_checked_before_first_send(tmp_path, monkeypatch):
    from test_research_presentation import storage_review
    runtime, registry, _, review, path = storage_review(tmp_path, monkeypatch)
    (runtime.state_root / "research-notifications").mkdir(parents=True)
    helper, marker = tmp_path / "fake-helper.py", tmp_path / "fake-sent"
    helper.write_text("from pathlib import Path\n" + f"Path({str(marker)!r}).touch()\n")
    ids = [json.loads(path.read_text())["request_id"], "f" * 64]
    result = notify(runtime, registry, ids, helper, review_summary_path=review.report_path)
    assert result.disposition is ResearchDisposition.FAILED
    assert not marker.exists()
    assert not list((runtime.state_root / "research-notifications").rglob("intent.json"))


@pytest.mark.parametrize("fault", ["production", "heavy", "offline", "capacity", "unconfigured"])
def test_resource_gates_prevent_notification_and_receipt_read(tmp_path, fault):
    runtime, registry, ids, helper, marker = setup(tmp_path)
    handle = None
    if fault in {"production", "heavy"}:
        path = runtime.production_lock_paths[0] if fault == "production" else runtime.state_root / "locks/research-heavy-worker.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("a")
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    elif fault == "offline":
        runtime = replace(runtime, warm_root=tmp_path / "missing-warm")
    elif fault == "capacity":
        runtime = replace(runtime, free_space_probe=lambda _: 0)
    else:
        runtime = replace(runtime, production_lock_paths=())
    try:
        result = notify(runtime, registry, ids, helper)
    finally:
        if handle:
            handle.close()
    assert result.disposition is ResearchDisposition.DEFERRED
    assert not marker.exists() and not list((runtime.state_root / "research-notifications").rglob("intent.json"))


@pytest.mark.parametrize("fault", ["registry", "missing", "duplicate", "path", "batch"])
def test_wrong_or_unbounded_receipt_requests_never_send(tmp_path, fault):
    runtime, registry, ids, helper, marker = setup(tmp_path)
    if fault == "registry":
        registry = ExperimentRegistry(tmp_path / "other-registry")
    elif fault == "missing":
        ids = ["a" * 64]
    elif fault == "duplicate":
        ids *= 2
    elif fault == "path":
        ids = ["../private"]
    else:
        ids = [f"{i:064x}" for i in range(51)]
    if fault in {"duplicate", "path", "batch"}:
        with pytest.raises(ValueError):
            notify(runtime, registry, ids, helper)
    else:
        assert notify(runtime, registry, ids, helper).disposition is ResearchDisposition.FAILED
    assert not marker.exists()


@pytest.mark.parametrize("preempt", [False, True])
def test_helper_hang_is_killed_with_worker_and_replay_is_not_a_resend(tmp_path, preempt):
    runtime, registry, ids, helper, marker = setup(tmp_path)
    lifecycle = tmp_path / "helper-lifecycle.lock"
    helper.write_text("import fcntl,time\nfrom pathlib import Path\n"
                      f"held=open({str(lifecycle)!r},'a')\nfcntl.flock(held,fcntl.LOCK_EX)\n"
                      f"Path({str(marker)!r}).write_text('attempted')\n"
                      "time.sleep(60)\n")
    handles, errors = [], []
    class Interrupt(SubprocessResearchExecutor):
        def run(self, invocation, *, timeout_seconds, production_active):
            def check():
                if preempt and marker.exists() and not handles:
                    handle = runtime.production_lock_paths[0].open("a")
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    handles.append(handle)
                return production_active()
            # Leave startup time before exercising the ready-marker interrupt.
            try:
                return super().run(invocation, timeout_seconds=10 if preempt else 5, production_active=check)
            except Exception as error:
                import traceback
                errors.append((type(error).__name__, getattr(error, 'errno', None),
                               [(f.name, f.lineno) for f in traceback.extract_tb(error.__traceback__)]))
                raise
    try:
        result = notify(replace(runtime, executor=Interrupt(poll_seconds=0.02, terminate_grace=0.1)), registry, ids, helper)
    finally:
        for handle in handles:
            handle.close()
    assert marker.exists()
    if preempt:
        assert handles, "production preemption must actually have been triggered"
    assert result.disposition is (ResearchDisposition.PREEMPTED if preempt else ResearchDisposition.TIMED_OUT), errors
    # Own-fixture lock stays held throughout its sleep, avoiding a sandbox-wide
    # process listing while proving the child released its kernel resource.
    with lifecycle.open("a") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
    # Keep the pinned helper unchanged: the durable intent alone suppresses replay.
    repeated = summary(notify(runtime, registry, ids, helper))
    assert repeated["reconcile_required"] == 1 and repeated["sent"] == 0
    assert marker.read_text() == "attempted"


def test_worker_crash_after_outcome_recovers_without_a_second_helper_call(tmp_path):
    runtime, registry, ids, helper, marker = setup(tmp_path)
    class Crash(SubprocessResearchExecutor):
        def run(self, invocation, **kwargs):
            code = ("from pathlib import Path; import os,sys; "
                    "import shared_wong_choi.research_notifications as n; "
                    "import shared_wong_choi.research_supervision as s; old=n.ResearchTelegramOutbox.dispatch; "
                    "n.ResearchTelegramOutbox.dispatch=lambda *a,**k: (old(*a,**k),os._exit(77)); "
                    "s._worker(Path(sys.argv[1]))")
            return super().run(replace(invocation, argv=(sys.executable, "-c", code, invocation.argv[-1])), **kwargs)
    result = notify(replace(runtime, executor=Crash(poll_seconds=0.02, terminate_grace=0.1)), registry, ids, helper)
    assert result.disposition is ResearchDisposition.FAILED
    repeated = summary(notify(runtime, registry, ids, helper))
    assert repeated["already_sent"] == 1 and marker.read_text() == "sent\n"


def test_worker_stdout_stderr_and_exception_text_cannot_persist_credentials(tmp_path):
    runtime, registry, ids, helper, marker = setup(tmp_path)
    class Leaky(SubprocessResearchExecutor):
        def run(self, invocation, **kwargs):
            code = ("import os,sys; secret=os.environ['WC_RESEARCH_NOTIFY_TOKEN']; "
                    "print(secret); print(secret,file=sys.stderr); raise RuntimeError(secret)")
            return super().run(replace(invocation, argv=(sys.executable, "-c", code)), **kwargs)
    result = notify(replace(runtime, executor=Leaky(poll_seconds=0.02, terminate_grace=0.1)), registry, ids, helper)
    assert result.disposition is ResearchDisposition.FAILED and not marker.exists()
    for path in result.attempt_path.rglob("*"):
        if path.is_file():
            assert b"dummy-secret" not in path.read_bytes()


@pytest.mark.parametrize("fault", ["count", "domain", "promotion"])
def test_parent_rejects_rehashed_false_notification_summary(tmp_path, fault):
    from shared_wong_choi.research_index import _hash
    runtime, registry, ids, helper, marker = setup(tmp_path)
    class Forged(SubprocessResearchExecutor):
        def run(self, invocation, **kwargs):
            execution = super().run(invocation, **kwargs)
            completed = json.loads(invocation.metrics_path.read_text())
            path = Path(completed["report_path"])
            payload = json.loads(path.read_text())
            if fault == "count":
                payload["sent"] += 1
            elif fault == "domain":
                payload["domain"] = "nba"
            else:
                payload["model_promotion_allowed"] = True
            payload.pop("content_hash")
            payload["content_hash"] = _hash(payload)
            path.write_text(json.dumps(payload))
            completed["content_hash"] = payload["content_hash"]
            invocation.metrics_path.write_text(json.dumps(completed))
            return execution
    result = notify(replace(runtime, executor=Forged(poll_seconds=0.02, terminate_grace=0.1)), registry, ids, helper)
    assert result.disposition is ResearchDisposition.FAILED and result.report_path is None


def test_changed_worker_route_cannot_send_to_another_recipient(tmp_path):
    runtime, registry, ids, helper, marker = setup(tmp_path)
    class WrongRoute(SubprocessResearchExecutor):
        def run(self, invocation, **kwargs):
            return super().run(replace(invocation, env={**invocation.env,
                               "WC_RESEARCH_NOTIFY_PRIMARY": "222", "WC_RESEARCH_NOTIFY_AUTHORIZED": "222"}), **kwargs)
    result = notify(replace(runtime, executor=WrongRoute(poll_seconds=0.02, terminate_grace=0.1)), registry, ids, helper)
    assert result.disposition is ResearchDisposition.FAILED and not marker.exists()


def test_parent_executor_exception_is_redacted(tmp_path):
    runtime, registry, ids, helper, marker = setup(tmp_path)
    class Broken(SubprocessResearchExecutor):
        def run(self, invocation, **kwargs):
            raise RuntimeError(invocation.env["WC_RESEARCH_NOTIFY_TOKEN"])
    result = notify(replace(runtime, executor=Broken()), registry, ids, helper)
    assert result.disposition is ResearchDisposition.FAILED and "dummy-secret" not in result.status
    assert b"dummy-secret" not in (result.attempt_path / "phase-outcome.json").read_bytes()


def test_blocked_receipt_io_remains_inside_killable_worker(tmp_path):
    runtime, registry, ids, helper, marker = setup(tmp_path)
    fifo, ready = tmp_path / "receipt-fifo", tmp_path / "receipt-read-started"
    os.mkfifo(fifo)
    class Blocked(SubprocessResearchExecutor):
        def run(self, invocation, **kwargs):
            code = ("from pathlib import Path; import sys; "
                    "import shared_wong_choi.research_notification_runtime as n; "
                    "import shared_wong_choi.research_supervision as s; "
                    f"n.load_review_receipt=lambda *a: (Path({str(ready)!r}).touch(),open({str(fifo)!r}).read())[1]; "
                    "s._worker(Path(sys.argv[1]))")
            return super().run(replace(invocation, argv=(sys.executable, "-c", code, invocation.argv[-1])),
                               timeout_seconds=1, production_active=kwargs["production_active"])
    result = notify(replace(runtime, executor=Blocked(poll_seconds=0.02, terminate_grace=0.1)), registry, ids, helper)
    assert ready.exists() and result.disposition is ResearchDisposition.TIMED_OUT
    assert not marker.exists() and not list((runtime.state_root / "research-notifications").rglob("intent.json"))


def test_warm_loss_keeps_hot_intent_and_does_not_recreate_lost_volume(tmp_path):
    runtime, registry, ids, helper, marker = setup(tmp_path)
    helper.write_text("import time\nfrom pathlib import Path\n"
                      f"Path({str(marker)!r}).write_text('attempted')\n"
                      "time.sleep(60)\n")
    moved = tmp_path / "disconnected-warm"
    class Disconnect(SubprocessResearchExecutor):
        def run(self, invocation, *, timeout_seconds, production_active):
            def check():
                if marker.exists() and runtime.warm_root.exists():
                    runtime.warm_root.rename(moved)
                return production_active()
            return super().run(invocation, timeout_seconds=2, production_active=check)
    result = notify(replace(runtime, executor=Disconnect(poll_seconds=0.02, terminate_grace=0.1)), registry, ids, helper)
    assert marker.exists() and result.disposition is ResearchDisposition.PREEMPTED
    assert not runtime.warm_root.exists()
    fallbacks = list((runtime.state_root / "research-interruptions").glob("*.json"))
    assert len(fallbacks) == 1 and b"dummy-secret" not in fallbacks[0].read_bytes()
    moved.rename(runtime.warm_root)
    assert summary(notify(runtime, registry, ids, helper))["reconcile_required"] == 1


def test_persisted_phase_payload_cannot_contain_notification_credentials(tmp_path):
    from shared_wong_choi.research_supervision import _phase
    runtime, registry, ids, helper, marker = setup(tmp_path)
    with pytest.raises(ValueError, match="fields"):
        _phase(runtime, registry, None, action="notify",
               payload={"domain": "au", "token": route().token}, notification_route=route(),
               estimated_bytes=100, timeout_seconds=5)
    assert not (runtime.warm_root / "research-phases").exists() and not marker.exists()


def test_notification_credentials_are_not_available_to_scoring_or_review_phases(tmp_path):
    from shared_wong_choi.research_supervision import _phase
    runtime, registry, ids, helper, marker = setup(tmp_path)
    with pytest.raises(ValueError, match="forbidden"):
        _phase(runtime, registry, None, action="review", payload={}, notification_route=route(),
               estimated_bytes=100, timeout_seconds=5)
    assert not (runtime.warm_root / "research-phases").exists() and not marker.exists()
