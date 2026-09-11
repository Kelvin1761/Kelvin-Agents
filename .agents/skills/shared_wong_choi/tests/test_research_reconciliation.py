from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared_wong_choi.artifact_archive import artifact_digest
from shared_wong_choi.control import single_run_lock
from shared_wong_choi.research_resources import ResearchPostflightRunner
from shared_wong_choi.research_runner import ResearchDisposition, SubprocessResearchExecutor
from shared_wong_choi.research_supervision import PostflightReconciliationRunner
from test_research_resources import fixture


def interrupted_fixture(tmp_path, point):
    spec, args, runtime, registry = fixture(tmp_path)

    class CrashingExecutor(SubprocessResearchExecutor):
        def run(self, invocation, **kwargs):
            code = "import os,sys\nfrom pathlib import Path\nimport shared_wong_choi.research_resources as r\n"
            if point == "after_decision":
                code += (
                    "publish = r.publish_evaluation_decision\n"
                    "def crash(*a, **k):\n    publish(*a, **k)\n    os._exit(73)\n"
                    "r.publish_evaluation_decision = crash\n"
                )
            elif point == "after_report":
                code += (
                    "append = r.ExperimentRegistry.append\n"
                    "def crash(self, record):\n"
                    "    if record.kind.value == 'experiment_decision': os._exit(74)\n"
                    "    return append(self, record)\n"
                    "r.ExperimentRegistry.append = crash\n"
                )
            else:
                code += "r.publish_evaluation_decision = lambda *a, **k: os._exit(75)\n"
            code += "r._worker(Path(sys.argv[1]))"
            return super().run(replace(invocation, argv=(sys.executable, "-c", code, invocation.argv[-1])), **kwargs)

    crashed = ResearchPostflightRunner(
        replace(runtime, executor=CrashingExecutor(poll_seconds=0.02, terminate_grace=0.1)), registry
    ).run(spec, **args, estimated_bytes=1024, timeout_seconds=30)
    assert crashed.disposition is ResearchDisposition.FAILED
    assert not (crashed.attempt_path / "completed.json").exists()
    outcome = json.loads((crashed.attempt_path / "outcome.json").read_text())
    assert outcome["publication"] == "unconfirmed_reconcile_before_retry"
    assert outcome["execution"]["returncode"] == {"after_decision": 73, "after_report": 74, "before_report": 75}[point]
    return spec, args, runtime, registry, crashed.attempt_path


def reconcile(spec, runtime, registry, attempt, **kwargs):
    return PostflightReconciliationRunner(runtime, registry).run(
        spec,
        attempt_path=attempt,
        request_sha256=hashlib.sha256((attempt / "request.json").read_bytes()).hexdigest(),
        estimated_bytes=1024,
        timeout_seconds=30,
        **kwargs,
    )


@pytest.mark.parametrize(
    "point,status",
    [
        ("after_decision", "verified_existing_decision"),
        ("after_report", "report_without_matching_decision"),
        ("before_report", "no_matching_publication_observed"),
    ],
)
def test_real_crash_boundary_is_reconciled_without_publishing_or_rescoring(tmp_path, point, status):
    spec, args, runtime, registry, attempt = interrupted_fixture(tmp_path, point)
    old_attempt, old_registry = artifact_digest(attempt), artifact_digest(registry.root)
    run_before = artifact_digest(args["run_artifact"])
    result = reconcile(spec, runtime, registry, attempt)
    assert result.disposition is ResearchDisposition.SUCCEEDED
    assert result.status == status
    payload = json.loads(result.report_path.read_text())
    assert payload["publication_status"] == status
    assert payload["run_id"] == args["run_id"]
    assert payload["rerun_scoring_allowed"] is False
    assert payload["retry_publication_allowed"] is False
    assert payload["model_promotion_allowed"] is False
    assert bool(result.decision_id) is (point == "after_decision")
    assert artifact_digest(registry.root) == old_registry
    assert artifact_digest(attempt) == old_attempt
    assert artifact_digest(args["run_artifact"]) == run_before
    again = reconcile(spec, runtime, registry, attempt)
    assert again.content_hash == result.content_hash


@pytest.mark.parametrize(
    "fault",
    ["request_hash", "report", "missing_report", "report_symlink", "decision", "run_artifact", "outside_attempt"],
)
def test_conflicting_or_redirected_evidence_cannot_be_reconciled_as_success(tmp_path, fault):
    spec, args, runtime, registry, attempt = interrupted_fixture(tmp_path, "after_decision")
    pinned = hashlib.sha256((attempt / "request.json").read_bytes()).hexdigest()
    if fault == "request_hash":
        pinned = "a" * 64
    elif fault in {"report", "missing_report", "report_symlink"}:
        report = next((runtime.warm_root / "research-evaluations").rglob("report.json"))
        if fault == "report":
            report.write_text('{"forged":true}')
        else:
            destination = tmp_path / "displaced-report.json"
            report.rename(destination)
            if fault == "report_symlink":
                report.symlink_to(destination)
    elif fault == "decision":
        decision = next((registry.root / "records/experiment_decision").glob("*.json"))
        decision.write_text('{"forged":true}')
    elif fault == "run_artifact":
        (args["run_artifact"] / "metrics.json").write_text('{"forged":true}')
    else:
        original = attempt
        attempt = tmp_path / "outside-attempt"
        attempt.mkdir()
        (attempt / "request.json").write_bytes((original / "request.json").read_bytes())
    result = PostflightReconciliationRunner(runtime, registry).run(
        spec, attempt_path=attempt, request_sha256=pinned, estimated_bytes=1024, timeout_seconds=30
    )
    assert result.disposition is not ResearchDisposition.SUCCEEDED
    assert result.decision_id is None and result.report_path is None


@pytest.mark.parametrize("lock_kind", ["heavy", "production"])
def test_reconciliation_yields_to_existing_heavy_or_production_work(tmp_path, lock_kind):
    spec, args, runtime, registry, attempt = interrupted_fixture(tmp_path, "before_report")
    lock = (
        runtime.production_lock_paths[0]
        if lock_kind == "production"
        else runtime.state_root / "locks/research-heavy-worker.lock"
    )
    with single_run_lock(lock) as acquired:
        assert acquired
        result = reconcile(spec, runtime, registry, attempt)
    assert result.disposition is ResearchDisposition.DEFERRED
    assert result.report_path is None


@pytest.mark.parametrize("preempt", [False, True])
def test_reconciliation_artifact_reads_are_externally_interruptible(tmp_path, preempt):
    spec, args, runtime, registry, attempt = interrupted_fixture(tmp_path, "after_decision")
    fifo, ready = tmp_path / "blocked-read", tmp_path / "read-ready"
    os.mkfifo(fifo)
    locks = []

    class BlockedReader(SubprocessResearchExecutor):
        def run(self, invocation, **kwargs):
            code = (
                "import sys\nfrom pathlib import Path\n"
                "import shared_wong_choi.research_reconciliation as r\n"
                "import shared_wong_choi.research_supervision as s\n"
                f"r.evaluate_run_artifact=lambda *a, **k: (Path({str(ready)!r}).touch(), open({str(fifo)!r}).read())[1]\n"
                "s._worker(Path(sys.argv[1]))"
            )
            probe = kwargs["production_active"]

            def production_active():
                if preempt and ready.exists() and not locks:
                    import fcntl

                    handle = runtime.production_lock_paths[0].open("a")
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    locks.append(handle)
                return probe()

            return super().run(
                replace(invocation, argv=(sys.executable, "-c", code, invocation.argv[-1])),
                **{**kwargs, "timeout_seconds": 1, "production_active": production_active},
            )

    try:
        result = reconcile(
            spec, replace(runtime, executor=BlockedReader(poll_seconds=0.02, terminate_grace=0.1)), registry, attempt
        )
    finally:
        for handle in locks:
            handle.close()
    assert ready.exists()
    assert result.disposition is (ResearchDisposition.PREEMPTED if preempt else ResearchDisposition.TIMED_OUT)
    assert result.report_path is None and result.decision_id is None


def test_reconciliation_offline_warm_defers_without_recreating_it(tmp_path):
    spec, args, runtime, registry, attempt = interrupted_fixture(tmp_path, "before_report")
    offline = tmp_path / "offline"
    result = reconcile(spec, replace(runtime, warm_root=offline), registry, attempt)
    assert result.disposition is ResearchDisposition.DEFERRED
    assert not offline.exists()


def test_parent_rejects_success_receipt_when_inspection_report_is_not_verified(tmp_path):
    from shared_wong_choi.research_runner import CommandExecution, CommandState

    spec, args, runtime, registry, attempt = interrupted_fixture(tmp_path, "before_report")

    class ForgedReceipt:
        def run(self, invocation, **kwargs):
            request = json.loads(Path(invocation.argv[-1]).read_text())
            report = invocation.output_dir / "forged-report.json"
            report.write_text('{"model_promotion_allowed":true}')
            invocation.metrics_path.write_text(
                json.dumps(
                    {
                        "disposition": "succeeded",
                        "status": "verified_existing_decision",
                        "report_path": str(report),
                        "content_hash": "a" * 64,
                        "request_sha256": request["payload"]["request_sha256"],
                        "rerun_scoring_allowed": False,
                        "retry_publication_allowed": False,
                        "model_promotion_allowed": False,
                        "decision_id": None,
                    }
                )
            )
            return CommandExecution(CommandState.SUCCEEDED, 0, "", "", 0.01, 0, 0, 0)

    result = reconcile(spec, replace(runtime, executor=ForgedReceipt()), registry, attempt)
    assert result.disposition is ResearchDisposition.FAILED
    assert result.report_path is None and result.decision_id is None
