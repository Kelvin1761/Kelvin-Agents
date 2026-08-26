"""Engine-neutral contracts for the Wong Choi automation control plane."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from pathlib import PurePosixPath
from typing import Any, Mapping, Protocol, runtime_checkable
from urllib.parse import quote


class Domain(str, Enum):
    AU = "au"
    HKJC = "hkjc"
    TENNIS = "tennis"
    NBA = "nba"


class Operation(str, Enum):
    DISCOVER = "discover"
    PREDICT = "predict"
    VALIDATE = "validate"
    PUBLISH = "publish"
    SETTLE = "settle"
    HEALTH = "health"
    NOTIFY = "notify"
    CALENDAR_STATE = "calendar_state"
    RECOVER = "recover"


class CapabilityReadiness(str, Enum):
    IMPLEMENTED = "implemented"
    PARTIAL = "partial"
    DEFERRED_LIVE_GATE = "deferred_live_gate"


class RunState(str, Enum):
    DORMANT = "dormant"
    READY = "ready"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    BLOCKED = "blocked"


TERMINAL_STATES = frozenset(
    {
        RunState.DORMANT,
        RunState.SUCCEEDED,
        RunState.PARTIAL,
        RunState.FAILED,
        RunState.BLOCKED,
    }
)

_ALLOWED_TRANSITIONS = {
    RunState.READY: frozenset(
        {RunState.RUNNING, RunState.DORMANT, RunState.BLOCKED}
    ),
    RunState.RUNNING: frozenset(
        {
            RunState.DORMANT,
            RunState.SUCCEEDED,
            RunState.PARTIAL,
            RunState.FAILED,
            RunState.BLOCKED,
        }
    ),
}

_STATUS_ALIASES = {
    "already_archived": RunState.SUCCEEDED,
    "archive_skipped": RunState.PARTIAL,
    "archived": RunState.SUCCEEDED,
    "blocked": RunState.BLOCKED,
    "complete": RunState.SUCCEEDED,
    "degraded": RunState.PARTIAL,
    "dormant": RunState.DORMANT,
    "error": RunState.FAILED,
    "failed": RunState.FAILED,
    "interrupted": RunState.FAILED,
    "missing_prediction": RunState.FAILED,
    "ok": RunState.SUCCEEDED,
    "partial": RunState.PARTIAL,
    "ready": RunState.READY,
    "running": RunState.RUNNING,
    "shadow_complete": RunState.SUCCEEDED,
    "skipped_locked": RunState.BLOCKED,
    "succeeded": RunState.SUCCEEDED,
    "success": RunState.SUCCEEDED,
    "temporary_failure": RunState.PARTIAL,
    "warmup_complete": RunState.SUCCEEDED,
}


def can_transition(current: RunState, target: RunState) -> bool:
    """Return whether one run attempt may move between two canonical states."""
    return target in _ALLOWED_TRANSITIONS.get(current, frozenset())


def normalize_run_state(status: str) -> RunState:
    """Map an adapter's explicit status to the canonical lifecycle vocabulary.

    Unknown values fail closed.  Adapters must make a deliberate mapping rather
    than letting a new domain status silently look successful.
    """
    key = status.strip().lower().replace("-", "_").replace(" ", "_")
    try:
        return _STATUS_ALIASES[key]
    except KeyError as exc:
        raise ValueError(f"unknown Wong Choi run status: {status!r}") from exc


def _component(value: str, *, field_name: str) -> str:
    clean = value.strip().lower()
    if not clean:
        raise ValueError(f"{field_name} must not be empty")
    return quote(clean, safe="._-")


@dataclass(frozen=True)
class EventIdentity:
    domain: Domain
    event_date: date
    source: str
    source_event_id: str

    @property
    def canonical_id(self) -> str:
        return ":".join(
            (
                "wc",
                self.domain.value,
                "event",
                self.event_date.isoformat(),
                _component(self.source, field_name="source"),
                _component(self.source_event_id, field_name="source_event_id"),
            )
        )


@dataclass(frozen=True)
class RunIdentity:
    domain: Domain
    mode: str
    target_date: date
    scheduled_slot: str
    attempt: int = 1

    def __post_init__(self) -> None:
        if self.attempt < 1:
            raise ValueError("attempt must be at least 1")
        _component(self.mode, field_name="mode")
        _component(self.scheduled_slot, field_name="scheduled_slot")

    @property
    def idempotency_key(self) -> str:
        return ":".join(
            (
                "wc",
                self.domain.value,
                "run",
                self.target_date.isoformat(),
                _component(self.mode, field_name="mode"),
                _component(self.scheduled_slot, field_name="scheduled_slot"),
            )
        )

    @property
    def run_id(self) -> str:
        return f"{self.idempotency_key}:attempt-{self.attempt}"


@dataclass(frozen=True)
class OperationBinding:
    operation: Operation
    entrypoint: str
    modes: tuple[str, ...]
    readiness: CapabilityReadiness = CapabilityReadiness.IMPLEMENTED
    note: str = ""

    def __post_init__(self) -> None:
        path = PurePosixPath(self.entrypoint)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("adapter entrypoint must be a repo-relative path")
        if not self.modes:
            raise ValueError("operation binding must declare at least one mode")


@dataclass(frozen=True)
class AdapterSpec:
    domain: Domain
    display_name: str
    owner: str
    orchestrator: str
    bindings: tuple[OperationBinding, ...]

    def __post_init__(self) -> None:
        if not self.display_name.strip() or not self.owner.strip():
            raise ValueError("adapter display_name and owner are required")
        path = PurePosixPath(self.orchestrator)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("adapter orchestrator must be a repo-relative path")
        operations = [binding.operation for binding in self.bindings]
        if len(operations) != len(set(operations)):
            raise ValueError(f"duplicate operation binding for {self.domain.value}")

    @property
    def capabilities(self) -> frozenset[Operation]:
        return frozenset(binding.operation for binding in self.bindings)

    def binding(self, operation: Operation) -> OperationBinding:
        for binding in self.bindings:
            if binding.operation == operation:
                return binding
        raise KeyError(f"{self.domain.value} does not declare {operation.value}")


@dataclass(frozen=True)
class RunRequest:
    identity: RunIdentity
    operation: Operation
    dry_run: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OperationResult:
    state: RunState
    status: str
    artifacts: tuple[str, ...] = ()
    detail: Mapping[str, Any] = field(default_factory=dict)


@runtime_checkable
class DomainAdapter(Protocol):
    """Boundary implemented by each domain without exposing scoring internals."""

    @property
    def spec(self) -> AdapterSpec:
        ...

    def execute(self, request: RunRequest) -> OperationResult:
        ...
