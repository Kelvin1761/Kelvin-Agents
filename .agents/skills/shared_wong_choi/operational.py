"""Shared operational vocabulary without owning domain message content."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum

from .contracts import OperationResult, RunRequest, RunState
from .schedule_policy import CalendarMode, ScheduledRun


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True)
class OperationalEvent:
    run_id: str
    domain: str
    mode: str
    state: RunState
    status: str
    severity: Severity
    dedup_key: str
    release_eligible: bool


def severity_for(state: RunState) -> Severity:
    if state in (RunState.FAILED, RunState.BLOCKED):
        return Severity.CRITICAL
    if state is RunState.PARTIAL:
        return Severity.WARNING
    return Severity.INFO


def release_allowed(
    run: ScheduledRun,
    result: OperationResult,
    *,
    calendar_mode: CalendarMode,
    source_fresh: bool,
) -> bool:
    """Fail closed unless policy, calendar, source and execution all agree."""
    return (
        calendar_mode is CalendarMode.PRODUCTION
        and run.publish_allowed
        and source_fresh
        and result.state is RunState.SUCCEEDED
    )


def operational_event(
    request: RunRequest,
    result: OperationResult,
    *,
    release_eligible: bool = False,
) -> OperationalEvent:
    raw = ":".join(
        (
            request.identity.idempotency_key,
            request.operation.value,
            result.state.value,
            result.status,
        )
    )
    dedup = "wc-op:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return OperationalEvent(
        run_id=request.identity.run_id,
        domain=request.identity.domain.value,
        mode=request.identity.mode,
        state=result.state,
        status=result.status,
        severity=severity_for(result.state),
        dedup_key=dedup,
        release_eligible=release_eligible,
    )
