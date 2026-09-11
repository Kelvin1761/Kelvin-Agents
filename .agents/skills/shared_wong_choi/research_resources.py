"""Bounded Stage 5 postflight execution; no model or deployment authority.

The operational entry owns the SAME heavy-worker lock as scoring. All expensive
verification, safety, bootstrap and publication re-verification runs in a
terminable process group. A failed/killed attempt is retained on WARM, never
silently retried or represented as a completed decision.

Low-level evaluation functions remain available for offline tests. Operational
callers must use this runner, not call those functions in a scheduler process.
This is resource supervision of trusted code, not an OS security sandbox.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from .research_supervision import PreparationResult

from .control import single_run_lock
from .research_evaluation import (
    EvaluationVerification,
    _strict_json,
    _write_report,
    evaluate_run_artifact,
    publish_evaluation_decision,
)
from .research_postflight import SafetyEvidence
from .research_registry import ExperimentRegistry, ExperimentSpec, _record_from_payload
from .research_runner import (
    CommandInvocation,
    CommandState,
    ResearchDomainAdapter,
    ResearchDisposition,
    ResearchJob,
    ResearchRunResult,
    ResearchRunner,
    ResearchRuntime,
)


class ResourceInterrupted(RuntimeError):
    """Resources stopped being safe; no subsequent publication is authorized."""


DEADLINE_CLOCK = "posix-clock-monotonic/v1"


def _deadline_now() -> float:
    """System-wide clock; time.monotonic is process-relative on macOS Python 3.9."""
    try:
        value = time.clock_gettime(time.CLOCK_MONOTONIC)
        if not math.isfinite(value) or value < 0:
            raise ValueError("invalid monotonic clock")
        return value
    except (AttributeError, OSError, ValueError) as exc:
        raise ResourceInterrupted("deadline_clock_unavailable") from exc


def _validate_deadline(request: dict) -> None:
    deadline = request.get("deadline")
    if (
        request.get("deadline_clock") != DEADLINE_CLOCK
        or type(deadline) not in (int, float)
        or not math.isfinite(deadline)
        or deadline <= 0
    ):
        raise ValueError("invalid or unbound cross-process deadline")


def _interruption_receipt(reason: str) -> dict:
    if not isinstance(reason, str) or not reason:
        raise ValueError("interruption reason required")
    return {
        "interrupted": True,
        "disposition": "timed_out" if reason in {"timeout", "phase_timeout", "workflow_timeout"} else "preempted",
        "status": reason,
        "publication": "unconfirmed_reconcile_before_retry",
    }


def _read_interruption(payload: dict) -> ResearchDisposition:
    if payload != _interruption_receipt(payload.get("status")):
        raise ValueError("invalid interruption receipt")
    return ResearchDisposition(payload["disposition"])


@dataclass(frozen=True)
class PostflightResult:
    disposition: ResearchDisposition
    status: str
    attempt_path: Path | None = None
    decision_id: str | None = None
    report_path: Path | None = None


def _resource_status(runtime: ResearchRuntime, registry: ExperimentRegistry, estimated_bytes: int) -> str | None:
    if not runtime.production_lock_paths:
        return "production_locks_unconfigured"
    if ResearchRunner(runtime, registry)._production_active():
        return "production_active"
    warm = runtime.warm_root.expanduser().absolute()
    if any(path.is_symlink() for path in (warm, *warm.parents)) or not warm.is_dir():
        return "warm_offline"
    try:
        free = runtime.free_space_probe(warm)
    except (OSError, ValueError):
        return "capacity_unavailable"
    if type(free) is not int or free < 0:
        return "capacity_unavailable"
    if free < estimated_bytes + runtime.reserve_bytes:
        return "insufficient_capacity"
    return None


def _record_attempt_outcome(runtime: ResearchRuntime, attempt: Path, filename: str, payload: dict) -> Path:
    """Never recreate a lost WARM hierarchy merely to record an interruption.

    The HOT fallback contains bounded metadata and a digest, not potentially
    large command output or model artifacts. Existing WARM evidence is retained.
    """
    target = attempt / filename
    try:
        if any(path.is_symlink() for path in (target, *target.parents)):
            raise OSError("unsafe outcome path")
        _write_report(target, payload, create_parents=False)
        return target
    except OSError:
        state = runtime.state_root.expanduser().absolute()
        if state.is_relative_to(runtime.warm_root.expanduser().absolute()):
            raise ResourceInterrupted("HOT interruption state must be outside WARM")
        identity = hashlib.sha256(str(target).encode()).hexdigest()
        target = state / "research-interruptions" / f"{identity}.json"
        fallback = {
            "schema_version": "wong-choi-research-interruption/v1",
            "outcome_storage": "hot_fallback",
            "attempt_path": str(attempt),
            "outcome_filename": filename,
            "disposition": payload.get("disposition"),
            "status": str(payload.get("status", ""))[:500],
            "publication": payload.get("publication"),
            "outcome_digest": hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
        }
        _write_report(target, fallback)
        return target


class ResearchPostflightRunner:
    def __init__(self, runtime: ResearchRuntime, registry: ExperimentRegistry):
        self.runtime = replace(
            runtime,
            state_root=runtime.state_root.expanduser().absolute(),
            warm_root=runtime.warm_root.expanduser().absolute(),
            production_lock_paths=tuple(path.expanduser().absolute() for path in runtime.production_lock_paths),
        )
        self.registry = registry

    def run(
        self,
        spec: ExperimentSpec,
        *,
        dataset_snapshot: Path,
        run_artifact: Path,
        run_id: str,
        evidence: SafetyEvidence,
        estimated_bytes: int,
        timeout_seconds: float,
    ) -> PostflightResult:
        if type(estimated_bytes) is not int or estimated_bytes <= 0:
            raise ValueError("estimated_bytes must be positive")
        if type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be finite and positive")
        deadline = _deadline_now() + timeout_seconds
        spec.validate()
        # Small metadata check here. Corpus reads and all hashing belong to worker.
        if self.registry.load(spec.record_id) != spec.to_payload():
            return PostflightResult(ResearchDisposition.BLOCKED, "spec_registry_mismatch")
        from .research_guard import research_gate_status

        def status_probe():
            return _resource_status(self.runtime, self.registry, estimated_bytes) or research_gate_status(
                self.runtime, self.registry, spec.domain, spec.evaluation_ruler_digest)

        status = status_probe()
        if status:
            return PostflightResult(ResearchDisposition.BLOCKED if status.startswith("research_") else ResearchDisposition.DEFERRED, status)
        state = self.runtime.state_root.expanduser().absolute()
        lock = state / "locks" / "research-heavy-worker.lock"
        if any(path.is_symlink() for path in (lock, *lock.parents)):
            return PostflightResult(ResearchDisposition.BLOCKED, "unsafe_lock_path")
        with single_run_lock(lock) as acquired:
            if not acquired:
                return PostflightResult(ResearchDisposition.DEFERRED, "heavy_worker_busy")
            status = status_probe()
            if status:
                return PostflightResult(ResearchDisposition.DEFERRED, status)
            root = self.runtime.warm_root / "research-postflight" / spec.domain.value
            reports = self.runtime.warm_root / "research-evaluations"
            if any(path.is_symlink() for base in (root, reports) for path in (base, *base.parents)):
                return PostflightResult(ResearchDisposition.BLOCKED, "unsafe_output_path")
            root.mkdir(parents=True, exist_ok=True)
            attempt = Path(tempfile.mkdtemp(prefix="attempt-", dir=root))
            request = {
                "schema_version": "wong-choi-research-postflight-request/v1",
                "spec_id": spec.record_id,
                "registry": str(self.registry.root),
                "dataset_snapshot": str(dataset_snapshot.absolute()),
                "run_artifact": str(run_artifact.absolute()),
                "run_id": run_id,
                "evidence": {
                    "input_protocol": str(evidence.input_protocol.absolute()),
                    "postflight_protocol": str(evidence.postflight_protocol.absolute()),
                    "source_paths": {name: str(path.absolute()) for name, path in evidence.source_paths.items()},
                },
                "state_root": str(state),
                "warm_root": str(self.runtime.warm_root),
                "production_locks": [str(path.absolute()) for path in self.runtime.production_lock_paths],
                "reserve_bytes": self.runtime.reserve_bytes,
                "estimated_bytes": estimated_bytes,
                "deadline": deadline,
                "deadline_clock": DEADLINE_CLOCK,
                "parent_pid": os.getpid(),
            }
            request_path = attempt / "request.json"
            _write_report(request_path, request)
            invocation = CommandInvocation(
                "postflight",
                0,
                (sys.executable, "-m", "shared_wong_choi.research_resources", str(request_path)),
                attempt,
                {
                    "PYTHONPATH": str(Path(__file__).resolve().parent.parent),
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONHASHSEED": str(spec.seed),
                    "TZ": "UTC",
                    "LC_ALL": "C",
                    "LANG": "C",
                    "OMP_NUM_THREADS": "1",
                    "OPENBLAS_NUM_THREADS": "1",
                    "MKL_NUM_THREADS": "1",
                },
                attempt,
                attempt / "completed.json",
            )
            interruption = None

            def interrupted():
                nonlocal interruption
                interruption = status_probe()
                return interruption is not None

            execution = None
            outcome = {"schema_version": "wong-choi-research-postflight-outcome/v1", "run_id": run_id}
            try:
                remaining = deadline - _deadline_now()
                if remaining <= 0:
                    raise ResourceInterrupted("timeout")
                execution = self.runtime.executor.run(
                    invocation, timeout_seconds=remaining, production_active=interrupted
                )
                outcome["execution"] = asdict(execution)
                if execution.state is not CommandState.SUCCEEDED or execution.returncode != 0:
                    disposition = {
                        CommandState.TIMED_OUT: ResearchDisposition.TIMED_OUT,
                        CommandState.PREEMPTED: ResearchDisposition.PREEMPTED,
                    }.get(execution.state, ResearchDisposition.FAILED)
                    result = PostflightResult(disposition, interruption or execution.state.value, attempt)
                    # A kill can happen after an atomic decision append but before
                    # the response. Never claim 'nothing published' or delete it.
                    outcome["publication"] = "unconfirmed_reconcile_before_retry"
                else:
                    payload = _strict_json(invocation.metrics_path.read_text())
                    if payload.get("interrupted") is True:
                        result = PostflightResult(_read_interruption(payload), payload["status"], attempt)
                        outcome["publication"] = "unconfirmed_reconcile_before_retry"
                    else:
                        decision = self.registry.load(payload["decision_id"])
                        report_path = Path(payload["report_path"])
                        if (
                            decision["links"]["run_id"] != run_id
                            or not report_path.is_relative_to(reports)
                            or any(path.is_symlink() for path in (report_path, *report_path.parents))
                            or hashlib.sha256(report_path.read_bytes()).hexdigest() != decision["artifact_digest"]
                        ):
                            raise ValueError("worker publication receipt does not match registry")
                        result = PostflightResult(
                            ResearchDisposition.SUCCEEDED,
                            payload["status"],
                            attempt,
                            payload["decision_id"],
                            report_path,
                        )
                        outcome["publication"] = "verified"
            except Exception as exc:
                result = PostflightResult(
                    ResearchDisposition.TIMED_OUT
                    if isinstance(exc, ResourceInterrupted)
                    else ResearchDisposition.FAILED,
                    f"{type(exc).__name__}: {exc}",
                    attempt,
                )
                outcome["publication"] = "unconfirmed_reconcile_before_retry"
            outcome.update(
                {"disposition": result.disposition.value, "status": result.status, "decision_id": result.decision_id}
            )
            _record_attempt_outcome(self.runtime, attempt, "outcome.json", outcome)
            return result


@dataclass(frozen=True)
class WorkflowResult:
    scoring: ResearchRunResult
    postflight: PostflightResult | None = None


@dataclass(frozen=True)
class PreparedWorkflowResult:
    preparation: PreparationResult
    workflow: WorkflowResult | None = None


class ResearchWorkflow:
    """Scoring then registered postflight, sharing a single elapsed-time budget.

    The heavy lock is released/reacquired at the phase boundary. Production or
    another worker may win it; in that case postflight defers without rerunning
    scoring. Resume via ResearchPostflightRunner with the registered run ID.
    Use prepare_and_run to include supervised dataset preparation in the budget.
    """

    def __init__(
        self, runtime: ResearchRuntime, registry: ExperimentRegistry, *, monotonic: Callable[[], float] = time.monotonic
    ):
        self.runtime, self.registry, self.monotonic = runtime, registry, monotonic

    def run(
        self, job: ResearchJob, spec: ExperimentSpec, adapter: ResearchDomainAdapter, *, evidence: SafetyEvidence
    ) -> WorkflowResult:
        started = self.monotonic()
        job.validate()
        status = _resource_status(self.runtime, self.registry, job.estimated_bytes)
        if status:
            return WorkflowResult(ResearchRunResult(job.job_id, ResearchDisposition.DEFERRED, status))
        from .research_supervision import ResearchScoringRunner

        scoring = ResearchScoringRunner(self.runtime, self.registry).run(job, spec, adapter)
        if scoring.disposition is not ResearchDisposition.SUCCEEDED:
            return WorkflowResult(scoring)
        remaining = job.timeout_seconds - (self.monotonic() - started)
        if remaining <= 0:
            return WorkflowResult(scoring, PostflightResult(ResearchDisposition.TIMED_OUT, "workflow_timeout"))
        if scoring.artifact_path is None or scoring.experiment_run_id is None:
            return WorkflowResult(scoring, PostflightResult(ResearchDisposition.BLOCKED, "scoring_receipt_missing"))
        postflight = ResearchPostflightRunner(self.runtime, self.registry).run(
            spec,
            dataset_snapshot=job.dataset_snapshot,
            run_artifact=scoring.artifact_path,
            run_id=scoring.experiment_run_id,
            evidence=evidence,
            estimated_bytes=job.estimated_bytes,
            timeout_seconds=remaining,
        )
        return WorkflowResult(scoring, postflight)

    def prepare_and_run(
        self, job, spec, adapter, *, sources, split_policy, evidence, previous_snapshot=None
    ) -> PreparedWorkflowResult:
        from .research_supervision import ResearchPreparationRunner

        job.validate()
        started = self.monotonic()
        preparation = ResearchPreparationRunner(self.runtime, self.registry).run(
            spec,
            sources=sources,
            split_policy=split_policy,
            estimated_bytes=job.estimated_bytes,
            timeout_seconds=job.timeout_seconds,
            previous_snapshot=previous_snapshot,
        )
        if preparation.disposition is not ResearchDisposition.SUCCEEDED:
            return PreparedWorkflowResult(preparation)
        remaining = job.timeout_seconds - (self.monotonic() - started)
        if remaining <= 0:
            scoring = ResearchRunResult(job.job_id, ResearchDisposition.TIMED_OUT, "workflow_timeout")
            return PreparedWorkflowResult(preparation, WorkflowResult(scoring))
        prepared_job = replace(job, dataset_snapshot=preparation.snapshot_path, timeout_seconds=remaining)
        return PreparedWorkflowResult(preparation, self.run(prepared_job, spec, adapter, evidence=evidence))


def _worker_body(request_path: Path) -> None:
    request = _strict_json(request_path.read_text())
    if request["schema_version"] != "wong-choi-research-postflight-request/v1":
        raise ValueError("unsupported postflight request")
    _validate_deadline(request)
    registry = ExperimentRegistry(Path(request["registry"]))
    runtime = ResearchRuntime(
        state_root=Path(request["state_root"]),
        warm_root=Path(request["warm_root"]),
        production_lock_paths=tuple(Path(path) for path in request["production_locks"]),
        reserve_bytes=request["reserve_bytes"],
    )
    spec = None

    def checkpoint():
        if os.getppid() != request["parent_pid"]:
            raise ResourceInterrupted("supervisor_unavailable")
        if _deadline_now() >= request["deadline"]:
            raise ResourceInterrupted("timeout")
        status = _resource_status(runtime, registry, request["estimated_bytes"])
        if not status and spec is not None:
            from .research_guard import research_gate_status
            status = research_gate_status(runtime, registry, spec.domain, spec.evaluation_ruler_digest)
        if status:
            raise ResourceInterrupted(status)

    checkpoint()
    spec = _record_from_payload(registry.load(request["spec_id"]))
    if not isinstance(spec, ExperimentSpec):
        raise ValueError("postflight needs a registered experiment spec")
    checkpoint()
    raw = request["evidence"]
    evidence = SafetyEvidence(
        Path(raw["input_protocol"]),
        Path(raw["postflight_protocol"]),
        {name: Path(path) for name, path in raw["source_paths"].items()},
    )
    snapshot, artifact = Path(request["dataset_snapshot"]), Path(request["run_artifact"])
    report = evaluate_run_artifact(
        spec,
        dataset_snapshot=snapshot,
        run_artifact=artifact,
        run_id=request["run_id"],
        registry=registry,
        evidence=evidence,
    )
    checkpoint()
    published = publish_evaluation_decision(
        report,
        registry=registry,
        run_id=request["run_id"],
        report_root=runtime.warm_root / "research-evaluations",
        decided_at=datetime.now(timezone.utc).isoformat(),
        verification=EvaluationVerification(spec, snapshot, artifact, evidence),
        resource_checkpoint=checkpoint,
    )
    _write_report(
        request_path.parent / "completed.json",
        {
            "status": published.status,
            "decision_id": published.decision_id,
            "report_path": str(published.report_path),
        },
    )


def _worker(request_path: Path) -> None:
    try:
        _worker_body(request_path)
    except ResourceInterrupted as exc:
        _write_report(request_path.parent / "completed.json", _interruption_receipt(str(exc)), create_parents=False)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m shared_wong_choi.research_resources REQUEST.json")
    _worker(Path(sys.argv[1]))
