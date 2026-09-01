"""Production-safe local queue and deterministic Stage 5 research runner."""

from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import resource
import shlex
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import quote
from uuid import uuid4

from .artifact_archive import artifact_digest
from .contracts import Domain
from .control import single_run_lock
from .research_dataset import DatasetSnapshotError, load_dataset_snapshot
from .research_registry import (
    ExperimentRegistry,
    ExperimentRun,
    ExperimentRunState,
    ExperimentSpec,
    ResearchConflictError,
)


QUEUE_SCHEMA_VERSION = "wong-choi-research-job/v1"
QUEUE_CLAIM_SCHEMA_VERSION = "wong-choi-research-claim/v1"
QUEUE_OUTCOME_SCHEMA_VERSION = "wong-choi-research-outcome/v1"
RUN_ARTIFACT_SCHEMA_VERSION = "wong-choi-research-artifact/v1"


class QueueConflictError(RuntimeError):
    """Raised when an immutable queue identity is reused with new content."""


class ResearchRunnerError(RuntimeError):
    """Raised for malformed runner input or an unsafe runtime boundary."""


class CommandState(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    PREEMPTED = "preempted"


class ResearchDisposition(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"
    DEFERRED = "deferred"
    TIMED_OUT = "timed_out"
    PREEMPTED = "preempted"


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _timestamp(clock: Callable[[], datetime]) -> str:
    value = clock()
    if value.tzinfo is None or value.utcoffset() is None:
        raise ResearchRunnerError("research clock must be timezone-aware")
    return value.isoformat()


def _write_exclusive_json(path: Path, payload: Mapping[str, Any]) -> str:
    body = dict(payload)
    body["content_hash"] = _digest(body)
    encoded = (
        json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing != body:
            raise QueueConflictError(f"immutable queue conflict: {path.name}")
        return "duplicate"
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    return "created"


def _load_hashed_json(path: Path, *, schema_version: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise QueueConflictError(f"invalid immutable queue record: {path}: {exc}") from exc
    content_hash = payload.pop("content_hash", None)
    if content_hash != _digest(payload):
        raise QueueConflictError(f"immutable queue hash mismatch: {path.name}")
    if payload.get("schema_version") != schema_version:
        raise QueueConflictError(f"unsupported queue schema: {path.name}")
    payload["content_hash"] = content_hash
    return payload


@dataclass(frozen=True)
class ResearchJob:
    job_id: str
    domain: Domain
    spec_id: str
    dataset_snapshot: Path
    baseline_checkout: Path
    candidate_checkout: Path
    estimated_bytes: int
    timeout_seconds: float

    def validate(self) -> None:
        prefix = f"wc:{self.domain.value}:research-job:"
        if not self.job_id.startswith(prefix) or not self.job_id[len(prefix) :].strip():
            raise ValueError(f"job_id must use canonical prefix {prefix!r}")
        if not self.spec_id.startswith(f"wc:{self.domain.value}:experiment-spec:"):
            raise ValueError("research job spec_id does not match domain")
        if isinstance(self.estimated_bytes, bool) or not isinstance(
            self.estimated_bytes, int
        ) or self.estimated_bytes < 1:
            raise ValueError("estimated_bytes must be positive")
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or not math.isfinite(float(self.timeout_seconds))
            or self.timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds must be positive")

    def to_payload(self) -> dict[str, Any]:
        self.validate()
        payload = {
            "schema_version": QUEUE_SCHEMA_VERSION,
            "append_only": True,
            "job_id": self.job_id,
            "domain": self.domain.value,
            "spec_id": self.spec_id,
            "dataset_snapshot": str(self.dataset_snapshot.expanduser().resolve()),
            "baseline_checkout": str(self.baseline_checkout.expanduser().resolve()),
            "candidate_checkout": str(self.candidate_checkout.expanduser().resolve()),
            "estimated_bytes": self.estimated_bytes,
            "timeout_seconds": float(self.timeout_seconds),
        }
        payload["content_hash"] = _digest(payload)
        return payload

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "ResearchJob":
        expected = {
            "schema_version",
            "append_only",
            "job_id",
            "domain",
            "spec_id",
            "dataset_snapshot",
            "baseline_checkout",
            "candidate_checkout",
            "estimated_bytes",
            "timeout_seconds",
            "content_hash",
        }
        if set(payload) != expected or payload.get("append_only") is not True:
            raise QueueConflictError("research job schema mismatch")
        if payload.get("content_hash") != _digest(
            {key: value for key, value in payload.items() if key != "content_hash"}
        ):
            raise QueueConflictError("research job content hash mismatch")
        try:
            job = cls(
                job_id=str(payload["job_id"]),
                domain=Domain(str(payload["domain"])),
                spec_id=str(payload["spec_id"]),
                dataset_snapshot=Path(str(payload["dataset_snapshot"])),
                baseline_checkout=Path(str(payload["baseline_checkout"])),
                candidate_checkout=Path(str(payload["candidate_checkout"])),
                estimated_bytes=int(payload["estimated_bytes"]),
                timeout_seconds=float(payload["timeout_seconds"]),
            )
            job.validate()
        except (TypeError, ValueError) as exc:
            raise QueueConflictError(f"invalid research job: {exc}") from exc
        if job.to_payload() != dict(payload):
            raise QueueConflictError("research job is not canonical")
        return job


@dataclass(frozen=True)
class QueueAppendResult:
    status: str
    path: Path


@dataclass(frozen=True)
class QueueClaim:
    job: ResearchJob
    worker_id: str
    path: Path


class ResearchQueue:
    """Create-only local job queue; claims and outcomes are separate records."""

    def __init__(
        self, root: Path, *, clock: Callable[[], datetime] | None = None
    ) -> None:
        self.root = root.expanduser().resolve()
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _name(self, job_id: str) -> str:
        return quote(job_id, safe="._-") + ".json"

    def enqueue(self, job: ResearchJob) -> QueueAppendResult:
        path = self.root / "jobs" / self._name(job.job_id)
        payload = job.to_payload()
        status = _write_exclusive_json(
            path, {key: value for key, value in payload.items() if key != "content_hash"}
        )
        return QueueAppendResult(status, path)

    def claim_next(self, worker_id: str) -> QueueClaim | None:
        if not worker_id.strip():
            raise ValueError("worker_id is required")
        jobs_root = self.root / "jobs"
        for path in sorted(jobs_root.glob("*.json")) if jobs_root.exists() else ():
            raw = _load_hashed_json(path, schema_version=QUEUE_SCHEMA_VERSION)
            job = ResearchJob.from_payload(raw)
            claim_path = self.root / "claims" / path.name
            outcome_path = self.root / "outcomes" / path.name
            if claim_path.exists() or outcome_path.exists():
                continue
            payload = {
                "schema_version": QUEUE_CLAIM_SCHEMA_VERSION,
                "append_only": True,
                "job_id": job.job_id,
                "worker_id": worker_id,
                "claimed_at": _timestamp(self.clock),
                "job_content_hash": raw["content_hash"],
            }
            try:
                status = _write_exclusive_json(claim_path, payload)
            except QueueConflictError:
                continue
            if status != "created":
                continue
            return QueueClaim(job, worker_id, claim_path)
        return None

    def finish(self, claim: QueueClaim, result: "ResearchRunResult") -> QueueAppendResult:
        if claim.job.job_id != result.job_id:
            raise ValueError("queue outcome does not match claim")
        expected_claim_path = self.root / "claims" / self._name(claim.job.job_id)
        if claim.path.expanduser().resolve() != expected_claim_path:
            raise QueueConflictError("queue claim verification failed")
        try:
            claim_payload = _load_hashed_json(
                expected_claim_path, schema_version=QUEUE_CLAIM_SCHEMA_VERSION
            )
            job_payload = _load_hashed_json(
                self.root / "jobs" / self._name(claim.job.job_id),
                schema_version=QUEUE_SCHEMA_VERSION,
            )
        except (OSError, QueueConflictError) as exc:
            raise QueueConflictError(f"queue claim verification failed: {exc}") from exc
        expected_claim_fields = {
            "schema_version",
            "append_only",
            "job_id",
            "worker_id",
            "claimed_at",
            "job_content_hash",
            "content_hash",
        }
        if (
            set(claim_payload) != expected_claim_fields
            or claim_payload.get("append_only") is not True
            or claim_payload.get("job_id") != claim.job.job_id
            or claim_payload.get("worker_id") != claim.worker_id
            or claim_payload.get("job_content_hash") != job_payload.get("content_hash")
            or ResearchJob.from_payload(job_payload) != claim.job
        ):
            raise QueueConflictError("queue claim verification failed")
        path = self.root / "outcomes" / self._name(claim.job.job_id)
        stable_payload = {
            "schema_version": QUEUE_OUTCOME_SCHEMA_VERSION,
            "append_only": True,
            "job_id": claim.job.job_id,
            "worker_id": claim.worker_id,
            "disposition": result.disposition.value,
            "status": result.status,
            "experiment_run_id": result.experiment_run_id,
            "artifact_path": str(result.artifact_path) if result.artifact_path else None,
            "reproducibility_digest": result.reproducibility_digest,
        }
        if path.exists():
            existing = _load_hashed_json(
                path, schema_version=QUEUE_OUTCOME_SCHEMA_VERSION
            )
            comparable = {
                key: value
                for key, value in existing.items()
                if key not in {"completed_at", "content_hash"}
            }
            if comparable != stable_payload:
                raise QueueConflictError(f"immutable queue conflict: {path.name}")
            return QueueAppendResult("duplicate", path)
        payload = {**stable_payload, "completed_at": _timestamp(self.clock)}
        try:
            status = _write_exclusive_json(path, payload)
        except QueueConflictError:
            existing = _load_hashed_json(
                path, schema_version=QUEUE_OUTCOME_SCHEMA_VERSION
            )
            comparable = {
                key: value
                for key, value in existing.items()
                if key not in {"completed_at", "content_hash"}
            }
            if comparable != stable_payload:
                raise
            status = "duplicate"
        return QueueAppendResult(status, path)


@dataclass(frozen=True)
class CommandInvocation:
    role: str
    index: int
    argv: tuple[str, ...]
    cwd: Path
    env: Mapping[str, str]
    output_dir: Path
    metrics_path: Path


class ResearchDomainAdapter:
    """Pure command adapter; deliberately imports no domain scoring code."""

    def __init__(self, domain: Domain) -> None:
        self.domain = domain

    def invocations(
        self,
        spec: ExperimentSpec,
        *,
        role: str,
        checkout: Path,
        dataset_path: Path,
        output_dir: Path,
    ) -> tuple[CommandInvocation, ...]:
        if spec.domain is not self.domain:
            raise ValueError("research adapter domain does not match spec")
        if role not in {"baseline", "candidate"}:
            raise ValueError("research role must be baseline or candidate")
        invocations: list[CommandInvocation] = []
        for index, command in enumerate(spec.commands):
            argv = tuple(shlex.split(command))
            if not argv:
                raise ValueError("frozen research command cannot be empty")
            command_output = output_dir / f"command-{index:02d}"
            metrics_path = command_output / "metrics.json"
            env = {
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONHASHSEED": str(spec.seed),
                "TZ": "UTC",
                "LC_ALL": "C",
                "LANG": "C",
                "WC_RESEARCH_DOMAIN": self.domain.value,
                "WC_RESEARCH_ROLE": role,
                "WC_RESEARCH_DATASET": str(dataset_path.resolve()),
                "WC_RESEARCH_OUTPUT_DIR": str(command_output.resolve()),
                "WC_RESEARCH_METRICS_PATH": str(metrics_path.resolve()),
                "WC_RESEARCH_SEED": str(spec.seed),
                "WC_RESEARCH_SPEC_ID": spec.record_id,
            }
            invocations.append(
                CommandInvocation(
                    role=role,
                    index=index,
                    argv=argv,
                    cwd=checkout.resolve(),
                    env=env,
                    output_dir=command_output,
                    metrics_path=metrics_path,
                )
            )
        return tuple(invocations)


def create_research_adapter(domain: Domain | str) -> ResearchDomainAdapter:
    return ResearchDomainAdapter(Domain(domain))


@dataclass(frozen=True)
class CommandExecution:
    state: CommandState
    returncode: int | None
    stdout: str
    stderr: str
    wall_seconds: float
    user_seconds: float
    system_seconds: float
    max_rss_kb: int


class ResearchExecutor(Protocol):
    def run(
        self,
        invocation: CommandInvocation,
        *,
        timeout_seconds: float,
        production_active: Callable[[], bool],
    ) -> CommandExecution: ...


class SubprocessResearchExecutor:
    """Run one command in its own process group with timeout/preemption polling."""

    def __init__(self, *, poll_seconds: float = 1.0, terminate_grace: float = 5.0):
        if poll_seconds <= 0 or terminate_grace <= 0:
            raise ValueError("executor polling and grace periods must be positive")
        self.poll_seconds = poll_seconds
        self.terminate_grace = terminate_grace

    def _terminate(self, process: subprocess.Popen[str]) -> tuple[str, str]:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        try:
            return process.communicate(timeout=self.terminate_grace)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            return process.communicate()

    def run(
        self,
        invocation: CommandInvocation,
        *,
        timeout_seconds: float,
        production_active: Callable[[], bool],
    ) -> CommandExecution:
        before = resource.getrusage(resource.RUSAGE_CHILDREN)
        started = time.monotonic()
        process = subprocess.Popen(
            list(invocation.argv),
            cwd=invocation.cwd,
            env={**os.environ, **dict(invocation.env)},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        state = CommandState.SUCCEEDED
        while True:
            elapsed = time.monotonic() - started
            try:
                should_preempt = production_active()
            except Exception:
                should_preempt = True
            if should_preempt:
                state = CommandState.PREEMPTED
                stdout, stderr = self._terminate(process)
                break
            if elapsed >= timeout_seconds:
                state = CommandState.TIMED_OUT
                stdout, stderr = self._terminate(process)
                break
            try:
                stdout, stderr = process.communicate(
                    timeout=min(self.poll_seconds, timeout_seconds - elapsed)
                )
                if process.returncode != 0:
                    state = CommandState.FAILED
                break
            except subprocess.TimeoutExpired:
                continue
        after = resource.getrusage(resource.RUSAGE_CHILDREN)
        return CommandExecution(
            state=state,
            returncode=process.returncode,
            stdout=stdout,
            stderr=stderr,
            wall_seconds=time.monotonic() - started,
            user_seconds=max(0.0, after.ru_utime - before.ru_utime),
            system_seconds=max(0.0, after.ru_stime - before.ru_stime),
            max_rss_kb=max(0, int(after.ru_maxrss)),
        )


def _git_checkout_probe(path: Path) -> str:
    if not path.is_dir():
        raise ResearchRunnerError(f"checkout unavailable: {path}")
    commit = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    dirty = subprocess.run(
        ["git", "-C", str(path), "status", "--porcelain"],
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    if commit.returncode != 0 or dirty.returncode != 0:
        raise ResearchRunnerError(f"checkout cannot be verified: {path}")
    if dirty.stdout.strip():
        raise ResearchRunnerError(f"checkout is dirty: {path}")
    return commit.stdout.strip()


def _free_space(path: Path) -> int:
    return int(shutil.disk_usage(path).free)


@dataclass(frozen=True)
class ResearchRuntime:
    state_root: Path
    warm_root: Path
    production_lock_paths: tuple[Path, ...] = ()
    reserve_bytes: int = 0
    checkout_probe: Callable[[Path], str] = _git_checkout_probe
    free_space_probe: Callable[[Path], int] = _free_space
    executor: ResearchExecutor = SubprocessResearchExecutor()
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)

    def __post_init__(self) -> None:
        if self.reserve_bytes < 0:
            raise ValueError("reserve_bytes cannot be negative")


@dataclass(frozen=True)
class ResearchRunResult:
    job_id: str
    disposition: ResearchDisposition
    status: str
    artifact_path: Path | None = None
    experiment_run_id: str | None = None
    reproducibility_digest: str | None = None
    detail: Mapping[str, Any] | None = None


class ResearchRunner:
    def __init__(self, runtime: ResearchRuntime, registry: ExperimentRegistry) -> None:
        self.runtime = runtime
        self.registry = registry

    def _result(
        self,
        job: ResearchJob,
        disposition: ResearchDisposition,
        status: str,
        **kwargs: Any,
    ) -> ResearchRunResult:
        return ResearchRunResult(job.job_id, disposition, status, **kwargs)

    def _production_active(self) -> bool:
        for path in self.runtime.production_lock_paths:
            if not path.exists():
                continue
            try:
                with path.open("a", encoding="utf-8") as handle:
                    try:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        return True
                    finally:
                        try:
                            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                        except OSError:
                            pass
            except OSError:
                return True
        return False

    def _preflight(
        self,
        job: ResearchJob,
        spec: ExperimentSpec,
        adapter: ResearchDomainAdapter,
    ) -> ResearchRunResult | None:
        try:
            job.validate()
            spec.validate()
        except ValueError as exc:
            return self._result(
                job, ResearchDisposition.BLOCKED, "invalid_contract", detail={"error": str(exc)}
            )
        if job.domain is not spec.domain or adapter.domain is not spec.domain:
            return self._result(job, ResearchDisposition.BLOCKED, "domain_mismatch")
        if job.spec_id != spec.record_id:
            return self._result(job, ResearchDisposition.BLOCKED, "spec_mismatch")
        try:
            registered_spec = self.registry.load(spec.record_id)
        except (FileNotFoundError, ResearchConflictError) as exc:
            return self._result(
                job,
                ResearchDisposition.BLOCKED,
                "spec_not_registered",
                detail={"error": str(exc)},
            )
        if registered_spec != spec.to_payload():
            return self._result(job, ResearchDisposition.BLOCKED, "spec_registry_mismatch")
        if self._production_active():
            return self._result(job, ResearchDisposition.DEFERRED, "production_active")
        warm_root = self.runtime.warm_root.expanduser()
        if warm_root.is_symlink() or not warm_root.is_dir():
            return self._result(job, ResearchDisposition.DEFERRED, "warm_offline")
        try:
            free_bytes = int(self.runtime.free_space_probe(warm_root.resolve()))
        except (OSError, ValueError) as exc:
            return self._result(
                job,
                ResearchDisposition.DEFERRED,
                "capacity_unavailable",
                detail={"error": str(exc)},
            )
        required = job.estimated_bytes + self.runtime.reserve_bytes
        if free_bytes < required:
            return self._result(
                job,
                ResearchDisposition.DEFERRED,
                "insufficient_capacity",
                detail={"free_bytes": free_bytes, "required_bytes": required},
            )
        try:
            baseline = self.runtime.checkout_probe(job.baseline_checkout.resolve())
            candidate = self.runtime.checkout_probe(job.candidate_checkout.resolve())
        except (OSError, ResearchRunnerError, subprocess.SubprocessError) as exc:
            return self._result(
                job,
                ResearchDisposition.BLOCKED,
                "checkout_unverified",
                detail={"error": str(exc)},
            )
        if baseline != spec.baseline_commit or candidate != spec.candidate_commit:
            return self._result(
                job,
                ResearchDisposition.BLOCKED,
                "checkout_commit_mismatch",
                detail={
                    "baseline_expected": spec.baseline_commit,
                    "baseline_actual": baseline,
                    "candidate_expected": spec.candidate_commit,
                    "candidate_actual": candidate,
                },
            )
        return None

    def _publish_failure(
        self,
        final: Path,
        *,
        job: ResearchJob,
        status: str,
        execution_log: list[dict[str, Any]],
    ) -> Path:
        temporary = final.with_name(f".{final.name}.failure-{uuid4().hex}")
        temporary.mkdir(parents=True)
        payload = {
            "schema_version": RUN_ARTIFACT_SCHEMA_VERSION,
            "append_only": True,
            "job_id": job.job_id,
            "status": status,
            "removed_partial": True,
            "executions": execution_log,
        }
        (temporary / "cleanup.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if final.exists():
            raise ResearchRunnerError(f"research artifact already exists: {final}")
        temporary.rename(final)
        return final

    def _register_run(
        self,
        *,
        job: ResearchJob,
        spec: ExperimentSpec,
        dataset_manifest_id: str,
        started_at: str,
        completed_at: str,
        state: ExperimentRunState,
        metrics_digest: str,
        artifact_path: Path,
        stdout_digest: str,
    ) -> str:
        identity = _digest(
            {
                "job_id": job.job_id,
                "started_at": started_at,
                "artifact_digest": artifact_digest(artifact_path)["sha256"],
            }
        )[:24]
        record = ExperimentRun(
            record_id=f"wc:{job.domain.value}:experiment-run:{identity}",
            domain=job.domain,
            created_at=completed_at,
            spec_id=spec.record_id,
            dataset_manifest_id=dataset_manifest_id,
            started_at=started_at,
            completed_at=completed_at,
            state=state,
            evaluation_ruler_id=spec.evaluation_ruler_id,
            evaluation_ruler_digest=spec.evaluation_ruler_digest,
            baseline_commit=spec.baseline_commit,
            candidate_commit=spec.candidate_commit,
            seed=spec.seed,
            commands=spec.commands,
            metrics_digest=metrics_digest,
            artifact_digest=artifact_digest(artifact_path)["sha256"],
            stdout_digest=stdout_digest,
        )
        self.registry.append(record)
        return record.record_id

    def run(
        self,
        job: ResearchJob,
        spec: ExperimentSpec,
        adapter: ResearchDomainAdapter,
    ) -> ResearchRunResult:
        preflight = self._preflight(job, spec, adapter)
        if preflight is not None:
            return preflight
        heavy_lock = (
            self.runtime.state_root.expanduser().resolve()
            / "locks"
            / "research-heavy-worker.lock"
        )
        with single_run_lock(heavy_lock) as acquired:
            if not acquired:
                return self._result(
                    job, ResearchDisposition.DEFERRED, "heavy_worker_busy"
                )
            if self._production_active():
                return self._result(
                    job, ResearchDisposition.DEFERRED, "production_active"
                )
            warm_root = self.runtime.warm_root.expanduser()
            if warm_root.is_symlink() or not warm_root.is_dir():
                return self._result(
                    job, ResearchDisposition.DEFERRED, "warm_offline"
                )
            try:
                free_bytes = int(self.runtime.free_space_probe(warm_root.resolve()))
            except (OSError, ValueError) as exc:
                return self._result(
                    job,
                    ResearchDisposition.DEFERRED,
                    "capacity_unavailable",
                    detail={"error": str(exc)},
                )
            required = job.estimated_bytes + self.runtime.reserve_bytes
            if free_bytes < required:
                return self._result(
                    job,
                    ResearchDisposition.DEFERRED,
                    "insufficient_capacity",
                    detail={"free_bytes": free_bytes, "required_bytes": required},
                )
            try:
                baseline_now = self.runtime.checkout_probe(
                    job.baseline_checkout.resolve()
                )
                candidate_now = self.runtime.checkout_probe(
                    job.candidate_checkout.resolve()
                )
            except (OSError, ResearchRunnerError, subprocess.SubprocessError) as exc:
                return self._result(
                    job,
                    ResearchDisposition.BLOCKED,
                    "checkout_unverified",
                    detail={"error": str(exc)},
                )
            if (
                baseline_now != spec.baseline_commit
                or candidate_now != spec.candidate_commit
            ):
                return self._result(
                    job,
                    ResearchDisposition.BLOCKED,
                    "checkout_changed_during_run",
                )
            try:
                dataset = load_dataset_snapshot(job.dataset_snapshot)
                if (
                    dataset.manifest.domain is not spec.domain
                    or dataset.manifest.spec_id != spec.record_id
                ):
                    return self._result(
                        job, ResearchDisposition.BLOCKED, "dataset_lineage_mismatch"
                    )
                self.registry.append(dataset.manifest)
            except (
                DatasetSnapshotError,
                FileNotFoundError,
                ResearchConflictError,
                ValueError,
            ) as exc:
                return self._result(
                    job,
                    ResearchDisposition.BLOCKED,
                    "dataset_unverified",
                    detail={"error": str(exc)},
                )

            started_at = _timestamp(self.runtime.clock)
            token = quote(job.job_id, safe="._-")
            root = (
                self.runtime.warm_root.expanduser().resolve()
                / "research-runs"
                / job.domain.value
            )
            final = root / token
            if final.exists():
                return self._result(
                    job, ResearchDisposition.BLOCKED, "artifact_conflict"
                )
            root.mkdir(parents=True, exist_ok=True)
            partial = root / f".{token}.partial-{uuid4().hex}"
            partial.mkdir()
            metrics: dict[str, list[dict[str, Any]]] = {
                "baseline": [],
                "candidate": [],
            }
            execution_log: list[dict[str, Any]] = []
            failure_status: str | None = None
            failure_disposition = ResearchDisposition.FAILED
            deadline = time.monotonic() + job.timeout_seconds
            try:
                for role, checkout in (
                    ("baseline", job.baseline_checkout),
                    ("candidate", job.candidate_checkout),
                ):
                    role_output = partial / role
                    invocations = adapter.invocations(
                        spec,
                        role=role,
                        checkout=checkout,
                        dataset_path=dataset.path / "rows.jsonl",
                        output_dir=role_output,
                    )
                    for invocation in invocations:
                        invocation.output_dir.mkdir(parents=True)
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            failure_status = "command_timeout"
                            failure_disposition = ResearchDisposition.TIMED_OUT
                            break
                        try:
                            execution = self.runtime.executor.run(
                                invocation,
                                timeout_seconds=remaining,
                                production_active=self._production_active,
                            )
                        except Exception as exc:
                            execution_log.append(
                                {
                                    "role": role,
                                    "index": invocation.index,
                                    "argv": list(invocation.argv),
                                    "returncode": None,
                                    "state": CommandState.FAILED.value,
                                    "stdout": "",
                                    "stderr": f"{type(exc).__name__}: {exc}",
                                    "resources": {
                                        "wall_seconds": 0.0,
                                        "user_seconds": 0.0,
                                        "system_seconds": 0.0,
                                        "max_rss_kb": 0,
                                    },
                                }
                            )
                            failure_status = "executor_exception"
                            break
                        item = {
                            "role": role,
                            "index": invocation.index,
                            "argv": list(invocation.argv),
                            "returncode": execution.returncode,
                            "state": execution.state.value,
                            "stdout": execution.stdout,
                            "stderr": execution.stderr,
                            "resources": {
                                "wall_seconds": execution.wall_seconds,
                                "user_seconds": execution.user_seconds,
                                "system_seconds": execution.system_seconds,
                                "max_rss_kb": execution.max_rss_kb,
                            },
                        }
                        execution_log.append(item)
                        if execution.state is CommandState.TIMED_OUT:
                            failure_status = "command_timeout"
                            failure_disposition = ResearchDisposition.TIMED_OUT
                            break
                        if execution.state is CommandState.PREEMPTED:
                            failure_status = "production_preempted"
                            failure_disposition = ResearchDisposition.PREEMPTED
                            break
                        if (
                            execution.state is not CommandState.SUCCEEDED
                            or execution.returncode != 0
                        ):
                            failure_status = "command_failed"
                            break
                        if self._production_active():
                            failure_status = "production_preempted"
                            failure_disposition = ResearchDisposition.PREEMPTED
                            break
                        if invocation.metrics_path.is_symlink() or any(
                            path.is_symlink()
                            for path in invocation.output_dir.rglob("*")
                        ):
                            failure_status = "unsafe_output_symlink"
                            failure_disposition = ResearchDisposition.BLOCKED
                            break
                        try:
                            current_dataset = load_dataset_snapshot(
                                job.dataset_snapshot
                            )
                        except (DatasetSnapshotError, OSError, ValueError):
                            current_dataset = None
                        if (
                            current_dataset is None
                            or current_dataset.manifest.to_payload()
                            != dataset.manifest.to_payload()
                        ):
                            failure_status = "dataset_changed_during_run"
                            failure_disposition = ResearchDisposition.BLOCKED
                            break
                        try:
                            metric = json.loads(
                                invocation.metrics_path.read_text(encoding="utf-8")
                            )
                        except (OSError, ValueError) as exc:
                            execution_log[-1]["metrics_error"] = str(exc)
                            failure_status = "metrics_missing_or_invalid"
                            break
                        if not isinstance(metric, dict):
                            failure_status = "metrics_missing_or_invalid"
                            break
                        metrics[role].append(metric)
                    if failure_status:
                        break

                if not failure_status:
                    try:
                        baseline_after = self.runtime.checkout_probe(
                            job.baseline_checkout.resolve()
                        )
                        candidate_after = self.runtime.checkout_probe(
                            job.candidate_checkout.resolve()
                        )
                    except (OSError, ResearchRunnerError, subprocess.SubprocessError):
                        baseline_after = None
                        candidate_after = None
                    if (
                        baseline_after != spec.baseline_commit
                        or candidate_after != spec.candidate_commit
                    ):
                        failure_status = "checkout_changed_during_run"
                        failure_disposition = ResearchDisposition.BLOCKED

                stdout_digest = _digest(
                    [
                        {"stdout": item["stdout"], "stderr": item["stderr"]}
                        for item in execution_log
                    ]
                )
                if failure_status:
                    shutil.rmtree(partial, ignore_errors=True)
                    artifact_path = self._publish_failure(
                        final,
                        job=job,
                        status=failure_status,
                        execution_log=execution_log,
                    )
                    metrics_digest = _digest(
                        {"state": failure_status, "metrics": metrics}
                    )
                    completed_at = _timestamp(self.runtime.clock)
                    run_state = (
                        ExperimentRunState.BLOCKED
                        if failure_disposition
                        in {
                            ResearchDisposition.PREEMPTED,
                            ResearchDisposition.BLOCKED,
                        }
                        else ExperimentRunState.FAILED
                    )
                    run_id = self._register_run(
                        job=job,
                        spec=spec,
                        dataset_manifest_id=dataset.manifest.record_id,
                        started_at=started_at,
                        completed_at=completed_at,
                        state=run_state,
                        metrics_digest=metrics_digest,
                        artifact_path=artifact_path,
                        stdout_digest=stdout_digest,
                    )
                    return self._result(
                        job,
                        failure_disposition,
                        failure_status,
                        artifact_path=artifact_path,
                        experiment_run_id=run_id,
                        reproducibility_digest=metrics_digest,
                    )

                reproducibility_digest = _digest(metrics)
                result_payload = {
                    "schema_version": RUN_ARTIFACT_SCHEMA_VERSION,
                    "append_only": True,
                    "job_id": job.job_id,
                    "domain": job.domain.value,
                    "spec_id": spec.record_id,
                    "dataset_manifest_id": dataset.manifest.record_id,
                    "baseline_commit": spec.baseline_commit,
                    "candidate_commit": spec.candidate_commit,
                    "commands": list(spec.commands),
                    "seed": spec.seed,
                    "reproducibility_digest": reproducibility_digest,
                }
                (partial / "metrics.json").write_text(
                    json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True)
                    + "\n",
                    encoding="utf-8",
                )
                (partial / "runtime.json").write_text(
                    json.dumps(
                        execution_log,
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                (partial / "result.json").write_text(
                    json.dumps(
                        result_payload,
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                partial.rename(final)
                completed_at = _timestamp(self.runtime.clock)
                run_id = self._register_run(
                    job=job,
                    spec=spec,
                    dataset_manifest_id=dataset.manifest.record_id,
                    started_at=started_at,
                    completed_at=completed_at,
                    state=ExperimentRunState.SUCCEEDED,
                    metrics_digest=reproducibility_digest,
                    artifact_path=final,
                    stdout_digest=stdout_digest,
                )
                return self._result(
                    job,
                    ResearchDisposition.SUCCEEDED,
                    "succeeded",
                    artifact_path=final,
                    experiment_run_id=run_id,
                    reproducibility_digest=reproducibility_digest,
                )
            except Exception:
                shutil.rmtree(partial, ignore_errors=True)
                raise
