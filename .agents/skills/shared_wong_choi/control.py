"""Durable run-control primitives shared by Wong Choi domain adapters."""

from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping
from uuid import uuid4

from .contracts import Operation, RunIdentity, RunState, TERMINAL_STATES, can_transition


SCHEMA_VERSION = "wong-choi-run-manifest/v1"


class ManifestExistsError(RuntimeError):
    """Raised when code tries to overwrite a run attempt's durable record."""


def _timestamp(value: datetime | None = None) -> str:
    stamp = value or datetime.now(timezone.utc)
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("run manifest timestamps must be timezone-aware")
    return stamp.isoformat()


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def manifest_path(root: Path, identity: RunIdentity) -> Path:
    """Return a stable, attempt-specific manifest path without touching disk."""
    slot = identity.idempotency_key.rsplit(":", 1)[-1]
    return (
        root
        / identity.domain.value
        / identity.target_date.isoformat()
        / identity.mode.strip().lower()
        / slot
        / f"attempt-{identity.attempt}.json"
    )


@dataclass
class RunManifest:
    """Atomic run record that becomes immutable once the attempt is terminal."""

    path: Path
    payload: dict[str, Any]

    @classmethod
    def create(
        cls,
        path: Path,
        identity: RunIdentity,
        *,
        at: datetime | None = None,
    ) -> "RunManifest":
        if path.exists():
            raise ManifestExistsError(f"run manifest already exists: {path}")
        started_at = _timestamp(at)
        payload: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "run_id": identity.run_id,
            "idempotency_key": identity.idempotency_key,
            "domain": identity.domain.value,
            "mode": identity.mode,
            "target_date": identity.target_date.isoformat(),
            "scheduled_slot": identity.scheduled_slot,
            "attempt": identity.attempt,
            "state": RunState.READY.value,
            "started_at": started_at,
            "completed_at": None,
            "operations": [],
            "warnings": [],
            "errors": [],
        }
        _atomic_json(path, payload)
        return cls(path=path, payload=payload)

    @classmethod
    def load(cls, path: Path) -> "RunManifest":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(f"unsupported run manifest schema: {payload.get('schema_version')!r}")
        RunState(payload["state"])
        return cls(path=path, payload=payload)

    @property
    def state(self) -> RunState:
        return RunState(self.payload["state"])

    def transition(
        self,
        target: RunState,
        *,
        at: datetime | None = None,
        warning: str | None = None,
        error: str | None = None,
    ) -> None:
        current = self.state
        if not can_transition(current, target):
            raise ValueError(f"invalid run transition: {current.value} -> {target.value}")
        self.payload["state"] = target.value
        if warning:
            self.payload["warnings"].append(warning)
        if error:
            self.payload["errors"].append(error)
        if target in TERMINAL_STATES:
            self.payload["completed_at"] = _timestamp(at)
        _atomic_json(self.path, self.payload)

    def record_operation(
        self,
        operation: Operation,
        status: str,
        *,
        at: datetime | None = None,
        artifacts: tuple[str, ...] = (),
        detail: Mapping[str, Any] | None = None,
    ) -> None:
        if self.state is not RunState.RUNNING:
            raise ValueError("operations may only be recorded while a run is running")
        self.payload["operations"].append(
            {
                "operation": operation.value,
                "status": status,
                "at": _timestamp(at),
                "artifacts": list(artifacts),
                "detail": dict(detail or {}),
            }
        )
        _atomic_json(self.path, self.payload)


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    retryable_exit_codes: tuple[int, ...] = (75, 124)

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")

    def should_retry(self, *, exit_code: int, attempt: int) -> bool:
        if attempt < 1:
            raise ValueError("attempt must be at least 1")
        return attempt < self.max_attempts and exit_code in self.retryable_exit_codes


@contextmanager
def single_run_lock(path: Path) -> Iterator[bool]:
    """Acquire one non-blocking process lock and report whether it succeeded."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        acquired = False
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except BlockingIOError:
            pass
        try:
            yield acquired
        finally:
            if acquired:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

