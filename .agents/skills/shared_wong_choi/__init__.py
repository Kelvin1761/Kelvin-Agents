"""Shared lifecycle contracts for Wong Choi domain adapters.

This package owns orchestration vocabulary only.  Domain prediction and
scoring implementations remain in their existing AU, HKJC, Tennis and NBA
packages.
"""

from .contracts import (
    AdapterSpec,
    CapabilityReadiness,
    Domain,
    DomainAdapter,
    EventIdentity,
    Operation,
    OperationBinding,
    OperationResult,
    RunIdentity,
    RunRequest,
    RunState,
    can_transition,
    normalize_run_state,
)
from .control import (
    ManifestExistsError,
    RetryPolicy,
    RunManifest,
    manifest_path,
    single_run_lock,
)
from .registry import ADAPTER_SPECS, adapter_spec
from .au_adapter import AUAdapter
from .hkjc_adapter import HKJCAdapter
from .nba_adapter import NBAAdapter
from .tennis_adapter import TennisAdapter
from .adapters import ADAPTER_TYPES, create_adapter
from .schedule_policy import (
    CalendarMode,
    DOMAIN_SCHEDULES,
    FreshnessRole,
    JobPolicy,
    RefreshScope,
    ScheduledRun,
    SnapshotMode,
    due_runs,
    missed_runs,
    nba_pregame_role,
    refreshable_events,
)
from .operational import (
    OperationalEvent,
    Severity,
    operational_event,
    release_allowed,
    severity_for,
)

__all__ = [
    "ADAPTER_SPECS",
    "ADAPTER_TYPES",
    "AdapterSpec",
    "AUAdapter",
    "CapabilityReadiness",
    "CalendarMode",
    "Domain",
    "DomainAdapter",
    "EventIdentity",
    "FreshnessRole",
    "HKJCAdapter",
    "ManifestExistsError",
    "NBAAdapter",
    "Operation",
    "OperationBinding",
    "OperationResult",
    "OperationalEvent",
    "JobPolicy",
    "RefreshScope",
    "RetryPolicy",
    "RunIdentity",
    "RunManifest",
    "RunRequest",
    "RunState",
    "ScheduledRun",
    "Severity",
    "SnapshotMode",
    "TennisAdapter",
    "adapter_spec",
    "can_transition",
    "create_adapter",
    "due_runs",
    "manifest_path",
    "missed_runs",
    "nba_pregame_role",
    "normalize_run_state",
    "operational_event",
    "release_allowed",
    "severity_for",
    "single_run_lock",
    "refreshable_events",
    "DOMAIN_SCHEDULES",
]
