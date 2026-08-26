from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT.parent))

from shared_wong_choi.contracts import (  # noqa: E402
    Domain,
    Operation,
    OperationResult,
    RunIdentity,
    RunRequest,
    RunState,
)
from shared_wong_choi.operational import (  # noqa: E402
    Severity,
    operational_event,
    release_allowed,
)
from shared_wong_choi.schedule_policy import CalendarMode, due_runs  # noqa: E402


SYDNEY = ZoneInfo("Australia/Sydney")


def _request(domain: Domain, mode: str, slot: str) -> RunRequest:
    return RunRequest(
        RunIdentity(domain, mode, date(2026, 10, 21), slot),
        Operation.PREDICT,
    )


def test_operational_event_has_stable_dedup_and_common_severity() -> None:
    request = _request(Domain.NBA, "pregame", "00:30")
    result = OperationResult(RunState.PARTIAL, "temporary_failure")
    first = operational_event(request, result)
    second = operational_event(request, result)
    assert first.dedup_key == second.dedup_key
    assert first.severity is Severity.WARNING


@pytest.mark.parametrize(
    ("domain", "clock"),
    (
        (Domain.AU, datetime(2026, 10, 21, 22, 0, tzinfo=SYDNEY)),
        (Domain.HKJC, datetime(2026, 10, 21, 21, 30, tzinfo=SYDNEY)),
        (Domain.TENNIS, datetime(2026, 10, 21, 9, 0, tzinfo=SYDNEY)),
        (Domain.NBA, datetime(2026, 10, 21, 0, 30, tzinfo=SYDNEY)),
    ),
    ids=lambda value: value.value if isinstance(value, Domain) else None,
)
def test_four_domain_release_gate_fails_closed_for_partial_stale_and_shadow(
    domain: Domain, clock: datetime
) -> None:
    production = next(run for run in due_runs(clock, domain) if run.publish_allowed)
    success = OperationResult(RunState.SUCCEEDED, "complete")
    partial = OperationResult(RunState.PARTIAL, "partial")

    assert release_allowed(
        production, success, calendar_mode=CalendarMode.PRODUCTION, source_fresh=True
    )
    assert not release_allowed(
        production, partial, calendar_mode=CalendarMode.PRODUCTION, source_fresh=True
    )
    assert not release_allowed(
        production, success, calendar_mode=CalendarMode.PRODUCTION, source_fresh=False
    )
    assert not release_allowed(
        production, success, calendar_mode=CalendarMode.SHADOW, source_fresh=True
    )


def test_nba_warmup_cannot_release_even_when_analysis_succeeds() -> None:
    warmup = due_runs(datetime(2026, 10, 20, 21, 0, tzinfo=SYDNEY), Domain.NBA)[0]
    success = OperationResult(RunState.SUCCEEDED, "complete")
    assert not release_allowed(
        warmup, success, calendar_mode=CalendarMode.PRODUCTION, source_fresh=True
    )


def test_hard_failure_is_critical_and_never_release_eligible() -> None:
    request = _request(Domain.AU, "evening", "22:00")
    event = operational_event(request, OperationResult(RunState.FAILED, "failed"))
    assert event.severity is Severity.CRITICAL
    assert event.release_eligible is False
