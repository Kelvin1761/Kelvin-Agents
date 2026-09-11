from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared_wong_choi.contracts import Domain
from shared_wong_choi.research_liveness import collect_research_liveness_evidence
from shared_wong_choi.research_registry import ExperimentRegistry
from shared_wong_choi.research_runner import (
    ResearchDisposition,
    ResearchJob,
    ResearchQueue,
    ResearchRunResult,
    ResearchRuntime,
    SubprocessResearchExecutor,
)
from shared_wong_choi.research_queue_worker import ResearchQueueWorker
from test_research_runner import configured_queue, runtime, spec


TOKEN = "worker-process-start:fixture"


def _fixture(tmp_path: Path, domain: Domain = Domain.AU):
    registry = ExperimentRegistry(tmp_path / "registry")
    frozen = spec(domain)
    queue = configured_queue(
        tmp_path, current_spec=frozen, registry=registry,
    )
    queued = ResearchJob(
        f"wc:{domain.value}:research-job:queue-worker-001",
        domain,
        frozen.record_id,
        tmp_path / "dataset",
        tmp_path / "baseline",
        tmp_path / "candidate",
        1024,
        30,
    )
    queue.enqueue(queued)
    leases = tmp_path / "leases"
    leases.mkdir()
    return registry, queue, queued, leases


class _Scoring:
    def __init__(self, result, on_run=None):
        self.result = result
        self.on_run = on_run
        self.calls = []

    def run(self, job, frozen, adapter):
        self.calls.append((job, frozen, adapter))
        if self.on_run:
            self.on_run()
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _outcome(queue, queued):
    path = queue.root / "outcomes" / queue._name(queued.job_id)
    return json.loads(path.read_text())


@pytest.mark.parametrize("domain", list(Domain))
def test_one_job_worker_records_exact_live_lease_before_scoring_and_finishes(
        tmp_path, domain):
    root = tmp_path / domain.value
    root.mkdir()
    registry, queue, queued, leases = _fixture(root, domain)
    run_runtime = runtime(root)
    # The real scorer registers a successful ExperimentRun before returning.
    # This seam result is deliberately non-success so the queue index remains
    # canonical without fabricating a registry record in a lifecycle unit test.
    expected = ResearchRunResult(
        queued.job_id, ResearchDisposition.DEFERRED, "production_active",
    )
    seen = []

    def inspect_while_scoring():
        report = collect_research_liveness_evidence(
            registry_root=registry.root,
            queue_root=queue.root,
            lease_root=leases,
            domain=domain,
            as_of=run_runtime.clock(),
            process_probe=lambda pid: TOKEN if pid == os.getpid() else None,
        )
        seen.append(report["queue"][0]["status"])

    scoring = _Scoring(expected, inspect_while_scoring)
    result = ResearchQueueWorker(
        run_runtime,
        registry,
        queue_root=queue.root,
        lease_root=leases,
        worker_id=f"{domain.value}-worker-1",
        scoring_runner=scoring,
        process_probe=lambda pid: TOKEN if pid == os.getpid() else None,
    ).run_one()

    assert seen == ["running_verified"]
    assert result.status == "finished"
    assert result.claim is not None and result.claim.job == queued
    assert result.lease_path is not None and result.lease_path.is_file()
    assert result.run_result == expected
    assert result.outcome is not None and result.outcome.status == "created"
    assert len(scoring.calls) == 1
    assert _outcome(queue, queued)["status"] == "production_active"

    terminal = collect_research_liveness_evidence(
        registry_root=registry.root,
        queue_root=queue.root,
        lease_root=leases,
        domain=domain,
        as_of=run_runtime.clock() + timedelta(seconds=1),
        process_probe=lambda pid: TOKEN,
    )
    assert terminal["queue"][0]["status"] == "terminal"


def test_lease_creation_failure_blocks_without_calling_scoring(tmp_path):
    registry, queue, queued, leases = _fixture(tmp_path)
    leases.rmdir()
    scoring = _Scoring(
        ResearchRunResult(queued.job_id, ResearchDisposition.SUCCEEDED, "succeeded")
    )

    result = ResearchQueueWorker(
        runtime(tmp_path),
        registry,
        queue_root=queue.root,
        lease_root=leases,
        worker_id="worker-1",
        scoring_runner=scoring,
        process_probe=lambda pid: TOKEN,
    ).run_one()

    assert scoring.calls == []
    assert result.lease_path is None
    assert result.run_result.disposition is ResearchDisposition.BLOCKED
    assert result.run_result.status == "liveness_lease_failed"
    assert _outcome(queue, queued)["status"] == "liveness_lease_failed"


def test_unavailable_process_identity_blocks_without_calling_scoring(tmp_path):
    registry, queue, queued, leases = _fixture(tmp_path)
    scoring = _Scoring(
        ResearchRunResult(queued.job_id, ResearchDisposition.SUCCEEDED, "succeeded")
    )

    result = ResearchQueueWorker(
        runtime(tmp_path),
        registry,
        queue_root=queue.root,
        lease_root=leases,
        worker_id="worker-1",
        scoring_runner=scoring,
        process_probe=lambda pid: None,
    ).run_one()

    assert scoring.calls == []
    assert not list(leases.iterdir())
    assert result.run_result.status == "worker_identity_unavailable"
    assert _outcome(queue, queued)["status"] == "worker_identity_unavailable"


def test_scoring_exception_becomes_terminal_failure_not_false_running(tmp_path):
    registry, queue, queued, leases = _fixture(tmp_path)
    scoring = _Scoring(RuntimeError("do not persist this detail"))

    result = ResearchQueueWorker(
        runtime(tmp_path),
        registry,
        queue_root=queue.root,
        lease_root=leases,
        worker_id="worker-1",
        scoring_runner=scoring,
        process_probe=lambda pid: TOKEN,
    ).run_one()

    assert result.run_result.disposition is ResearchDisposition.FAILED
    assert result.run_result.status == "worker_execution_failed"
    assert result.run_result.detail == {"error_type": "RuntimeError"}
    assert _outcome(queue, queued)["status"] == "worker_execution_failed"


def test_empty_queue_is_idle_and_does_not_create_lease(tmp_path):
    registry = ExperimentRegistry(tmp_path / "registry")
    frozen = spec()
    queue = configured_queue(tmp_path, current_spec=frozen, registry=registry)
    leases = tmp_path / "leases"
    leases.mkdir()
    scoring = _Scoring(None)

    result = ResearchQueueWorker(
        runtime(tmp_path),
        registry,
        queue_root=queue.root,
        lease_root=leases,
        worker_id="worker-1",
        scoring_runner=scoring,
        process_probe=lambda pid: TOKEN,
    ).run_one()

    assert result.status == "idle"
    assert result.claim is result.lease_path is result.run_result is result.outcome is None
    assert scoring.calls == [] and not list(leases.iterdir())


def test_worker_instance_cannot_be_reused_for_another_claim(tmp_path):
    registry, queue, _queued, leases = _fixture(tmp_path)
    worker = ResearchQueueWorker(
        runtime(tmp_path), registry, queue_root=queue.root, lease_root=leases,
        worker_id="worker-1", scoring_runner=_Scoring(None),
        process_probe=lambda pid: TOKEN,
    )
    worker.run_one()
    with pytest.raises(RuntimeError, match="single-use"):
        worker.run_one()


@pytest.mark.parametrize("bad_result", [None, object()])
def test_invalid_scoring_result_is_terminal_and_cannot_impersonate_success(
        tmp_path, bad_result):
    registry, queue, queued, leases = _fixture(tmp_path)
    result = ResearchQueueWorker(
        runtime(tmp_path), registry, queue_root=queue.root, lease_root=leases,
        worker_id="worker-1", scoring_runner=_Scoring(bad_result),
        process_probe=lambda pid: TOKEN,
    ).run_one()
    assert result.run_result.status == "worker_result_invalid"
    assert result.run_result.disposition is ResearchDisposition.BLOCKED
    assert _outcome(queue, queued)["status"] == "worker_result_invalid"


def test_real_supervised_scoring_runs_through_queue_worker_and_registers_run(tmp_path):
    from research_test_support import pin_review
    from test_research_runner import job, snapshot

    dataset = snapshot(tmp_path)
    queued = job(tmp_path, dataset.path)
    commits = []
    for folder in (queued.baseline_checkout, queued.candidate_checkout):
        (folder / "evaluate.py").write_text(
            "import json,os; from pathlib import Path; "
            "Path(os.environ['WC_RESEARCH_METRICS_PATH']).write_text("
            "json.dumps({'metric': .5}) + '\\n')\n"
        )
        for command in (
            ("init", "-q"),
            ("add", "evaluate.py"),
            ("-c", "user.name=Research Test", "-c",
             "user.email=research@example.invalid", "commit", "-qm", folder.name),
        ):
            subprocess.run(
                ["git", "-C", str(folder), *command], check=True,
                capture_output=True,
            )
        commits.append(subprocess.check_output(
            ["git", "-C", str(folder), "rev-parse", "HEAD"], text=True,
        ).strip())
    frozen = replace(
        spec(), baseline_commit=commits[0], candidate_commit=commits[1],
    )
    registry = ExperimentRegistry(tmp_path / "registry")
    registry.append(frozen)
    warm = tmp_path / "warm"
    warm.mkdir()
    run_runtime = ResearchRuntime(
        state_root=tmp_path / "state",
        warm_root=warm,
        production_lock_paths=(tmp_path / "production.lock",),
        executor=SubprocessResearchExecutor(
            poll_seconds=0.02, terminate_grace=0.1,
        ),
    )
    queue_root = tmp_path / "queue"
    pin_review(run_runtime, registry, frozen, queue_root=queue_root)
    queue = ResearchQueue(
        queue_root, runtime=run_runtime, registry=registry,
    )
    queued = replace(queued, spec_id=frozen.record_id)
    queue.enqueue(queued)
    leases = tmp_path / "leases"
    leases.mkdir()

    result = ResearchQueueWorker(
        run_runtime,
        registry,
        queue_root=queue_root,
        lease_root=leases,
        worker_id="real-worker-1",
    ).run_one()

    assert result.run_result.disposition is ResearchDisposition.SUCCEEDED
    assert result.run_result.status == "succeeded"
    registered = registry.load(result.run_result.experiment_run_id)
    assert registered["baseline_commit"] == frozen.baseline_commit
    assert registered["candidate_commit"] == frozen.candidate_commit
    assert _outcome(queue, queued)["experiment_run_id"] == registered["record_id"]
