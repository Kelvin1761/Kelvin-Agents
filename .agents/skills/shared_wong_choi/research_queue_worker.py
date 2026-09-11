"""One-job Stage 5 queue worker with fail-closed process-liveness evidence.

The worker process itself owns the immutable liveness lease.  A caller should
construct one instance, call ``run_one`` once, and then let that process exit.
The actual scoring remains in the existing independently supervised phase.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Callable, Protocol

from .research_liveness import (
    probe_process_start_token,
    record_research_liveness_lease,
)
from .research_registry import (
    ExperimentRegistry,
    ExperimentSpec,
    _record_from_payload,
)
from .research_runner import (
    QueueAppendResult,
    QueueClaim,
    ResearchDisposition,
    ResearchQueue,
    ResearchRunResult,
    ResearchRuntime,
    create_research_adapter,
)
from .research_supervision import ResearchScoringRunner


class _ScoringRunner(Protocol):
    def run(self, job, spec, adapter) -> ResearchRunResult: ...


@dataclass(frozen=True)
class QueueWorkerResult:
    status: str
    claim: QueueClaim | None = None
    lease_path: Path | None = None
    run_result: ResearchRunResult | None = None
    outcome: QueueAppendResult | None = None


class ResearchQueueWorker:
    """Claim and finish at most one job; never score without a live lease."""

    def __init__(
        self,
        runtime: ResearchRuntime,
        registry: ExperimentRegistry,
        *,
        queue_root: Path,
        lease_root: Path,
        worker_id: str,
        scoring_runner: _ScoringRunner | None = None,
        process_probe: Callable[[int], str | None] = probe_process_start_token,
        pid_probe: Callable[[], int] = os.getpid,
    ) -> None:
        if not isinstance(worker_id, str) or not worker_id.strip():
            raise ValueError("worker_id is required")
        self.runtime = runtime
        self.registry = registry
        self.queue = ResearchQueue(
            queue_root,
            clock=runtime.clock,
            runtime=runtime,
            registry=registry,
        )
        self.lease_root = lease_root
        self.worker_id = worker_id
        self.scoring_runner = scoring_runner or ResearchScoringRunner(runtime, registry)
        self.process_probe = process_probe
        self.pid_probe = pid_probe
        self._used = False

    @staticmethod
    def _failure(job_id: str, status: str, error: Exception | None = None):
        detail = {"error_type": type(error).__name__} if error is not None else None
        return ResearchRunResult(
            job_id,
            ResearchDisposition.FAILED
            if status == "worker_execution_failed"
            else ResearchDisposition.BLOCKED,
            status,
            detail=detail,
        )

    def _finish_failure(
        self,
        claim: QueueClaim,
        status: str,
        *,
        lease_path: Path | None = None,
        error: Exception | None = None,
    ) -> QueueWorkerResult:
        run_result = self._failure(claim.job.job_id, status, error)
        outcome = self.queue.finish(claim, run_result)
        return QueueWorkerResult(
            "finished", claim, lease_path, run_result, outcome,
        )

    def run_one(self) -> QueueWorkerResult:
        if self._used:
            raise RuntimeError("research queue worker is single-use")
        self._used = True
        claim = self.queue.claim_next(self.worker_id)
        if claim is None:
            return QueueWorkerResult("idle")

        try:
            pid = self.pid_probe()
            token = self.process_probe(pid)
        except Exception as exc:
            return self._finish_failure(
                claim, "worker_identity_unavailable", error=exc,
            )
        if type(pid) is not int or pid <= 0 or token is None:
            return self._finish_failure(claim, "worker_identity_unavailable")

        observed_at = self.runtime.clock()
        try:
            lease_path = record_research_liveness_lease(
                lease_root=self.lease_root,
                claim=claim,
                pid=pid,
                process_start_token=token,
                observed_at=observed_at,
                valid_until=observed_at
                + timedelta(seconds=claim.job.timeout_seconds),
            )
        except Exception as exc:
            return self._finish_failure(
                claim, "liveness_lease_failed", error=exc,
            )

        try:
            frozen = _record_from_payload(self.registry.load(claim.job.spec_id))
            if not isinstance(frozen, ExperimentSpec) or frozen.domain is not claim.job.domain:
                return self._finish_failure(
                    claim, "worker_spec_invalid", lease_path=lease_path,
                )
            run_result = self.scoring_runner.run(
                claim.job,
                frozen,
                create_research_adapter(claim.job.domain),
            )
        except Exception as exc:
            return self._finish_failure(
                claim,
                "worker_execution_failed",
                lease_path=lease_path,
                error=exc,
            )
        if type(run_result) is not ResearchRunResult or run_result.job_id != claim.job.job_id:
            return self._finish_failure(
                claim, "worker_result_invalid", lease_path=lease_path,
            )
        outcome = self.queue.finish(claim, run_result)
        return QueueWorkerResult(
            "finished", claim, lease_path, run_result, outcome,
        )
