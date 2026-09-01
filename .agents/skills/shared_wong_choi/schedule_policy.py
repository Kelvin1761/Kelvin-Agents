"""Declarative scheduler and freshness policy for all Wong Choi domains."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import Enum
from typing import Iterable
from zoneinfo import ZoneInfo

from .contracts import Domain, Operation


SYDNEY = ZoneInfo("Australia/Sydney")


class CalendarMode(str, Enum):
    DORMANT = "dormant"
    SHADOW = "shadow"
    PRODUCTION = "production"


class FreshnessRole(str, Enum):
    STANDARD = "standard"
    WATCH = "watch"
    WARMUP = "warmup"
    PRODUCTION = "production"
    FINAL_REFRESH = "final_refresh"
    POST_EVENT = "post_event"
    HEALTH = "health"
    RECOVERY = "recovery"


class RefreshScope(str, Enum):
    NONE = "none"
    ALL = "all"
    UNSTARTED_ONLY = "unstarted_only"


class SnapshotMode(str, Enum):
    NONE = "none"
    APPEND_ONLY = "append_only"


@dataclass(frozen=True)
class JobPolicy:
    mode: str
    operation: Operation
    times: tuple[time, ...] = ()
    interval_minutes: int | None = None
    target_day_offset: int = 0
    freshness_role: FreshnessRole = FreshnessRole.STANDARD
    refresh_scope: RefreshScope = RefreshScope.NONE
    snapshot_mode: SnapshotMode = SnapshotMode.NONE
    publish_allowed: bool = False
    content_notify_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.times and self.interval_minutes is None:
            raise ValueError("job policy needs fixed times or an interval")
        if self.interval_minutes is not None and self.interval_minutes < 1:
            raise ValueError("interval_minutes must be positive")


@dataclass(frozen=True)
class DomainSchedulePolicy:
    domain: Domain
    timezone: str
    jobs: tuple[JobPolicy, ...]


@dataclass(frozen=True)
class ScheduledRun:
    domain: Domain
    mode: str
    operation: Operation
    scheduled_at: datetime
    target_date: date
    scheduled_slot: str
    freshness_role: FreshnessRole
    refresh_scope: RefreshScope
    snapshot_mode: SnapshotMode
    publish_allowed: bool
    content_notify_allowed: bool


def _t(hour: int, minute: int) -> time:
    return time(hour, minute)


DOMAIN_SCHEDULES: dict[Domain, DomainSchedulePolicy] = {
    Domain.AU: DomainSchedulePolicy(
        Domain.AU,
        "Australia/Sydney",
        (
            JobPolicy(
                "evening",
                Operation.PREDICT,
                times=(_t(22, 0),),
                freshness_role=FreshnessRole.PRODUCTION,
                refresh_scope=RefreshScope.ALL,
                snapshot_mode=SnapshotMode.APPEND_ONLY,
                publish_allowed=True,
                content_notify_allowed=True,
            ),
            JobPolicy(
                "morning",
                Operation.PREDICT,
                times=(_t(10, 0),),
                freshness_role=FreshnessRole.FINAL_REFRESH,
                refresh_scope=RefreshScope.UNSTARTED_ONLY,
                snapshot_mode=SnapshotMode.APPEND_ONLY,
                publish_allowed=True,
                content_notify_allowed=True,
            ),
            JobPolicy(
                "healthcheck",
                Operation.HEALTH,
                times=(_t(2, 30), _t(9, 15), _t(11, 0)),
                freshness_role=FreshnessRole.HEALTH,
            ),
        ),
    ),
    Domain.HKJC: DomainSchedulePolicy(
        Domain.HKJC,
        "Australia/Sydney",
        (
            JobPolicy(
                "watch",
                Operation.DISCOVER,
                times=(_t(0, 15), _t(9, 15), _t(21, 15), _t(23, 15)),
                freshness_role=FreshnessRole.WATCH,
            ),
            JobPolicy(
                "prerace",
                Operation.PREDICT,
                times=(_t(0, 30), _t(8, 0), _t(11, 0), _t(21, 30), _t(23, 30)),
                freshness_role=FreshnessRole.PRODUCTION,
                refresh_scope=RefreshScope.UNSTARTED_ONLY,
                snapshot_mode=SnapshotMode.APPEND_ONLY,
                publish_allowed=True,
                content_notify_allowed=True,
            ),
            JobPolicy(
                "postrace",
                Operation.SETTLE,
                times=(_t(8, 30),),
                freshness_role=FreshnessRole.POST_EVENT,
                publish_allowed=True,
            ),
            JobPolicy(
                "recovery",
                Operation.RECOVER,
                interval_minutes=30,
                freshness_role=FreshnessRole.RECOVERY,
            ),
        ),
    ),
    Domain.TENNIS: DomainSchedulePolicy(
        Domain.TENNIS,
        "Australia/Sydney",
        (
            JobPolicy(
                "card",
                Operation.PREDICT,
                times=(_t(9, 0),),
                freshness_role=FreshnessRole.PRODUCTION,
                refresh_scope=RefreshScope.UNSTARTED_ONLY,
                snapshot_mode=SnapshotMode.APPEND_ONLY,
                publish_allowed=True,
                content_notify_allowed=True,
            ),
            JobPolicy(
                "daily",
                Operation.SETTLE,
                times=(_t(18, 0),),
                freshness_role=FreshnessRole.POST_EVENT,
                publish_allowed=True,
            ),
            JobPolicy(
                "recovery",
                Operation.RECOVER,
                times=(_t(10, 30), _t(12, 30)),
                freshness_role=FreshnessRole.RECOVERY,
            ),
        ),
    ),
    Domain.NBA: DomainSchedulePolicy(
        Domain.NBA,
        "Australia/Sydney",
        (
            JobPolicy(
                "pregame",
                Operation.PREDICT,
                times=(_t(21, 0),),
                target_day_offset=1,
                freshness_role=FreshnessRole.WARMUP,
                refresh_scope=RefreshScope.ALL,
                snapshot_mode=SnapshotMode.APPEND_ONLY,
                publish_allowed=False,
                content_notify_allowed=False,
            ),
            JobPolicy(
                "pregame",
                Operation.PREDICT,
                times=(_t(0, 30),),
                freshness_role=FreshnessRole.PRODUCTION,
                refresh_scope=RefreshScope.UNSTARTED_ONLY,
                snapshot_mode=SnapshotMode.APPEND_ONLY,
                publish_allowed=True,
                content_notify_allowed=True,
            ),
            JobPolicy(
                "pregame",
                Operation.PREDICT,
                times=(_t(6, 30),),
                freshness_role=FreshnessRole.FINAL_REFRESH,
                refresh_scope=RefreshScope.UNSTARTED_ONLY,
                snapshot_mode=SnapshotMode.APPEND_ONLY,
                publish_allowed=True,
                content_notify_allowed=True,
            ),
            JobPolicy(
                "health",
                Operation.HEALTH,
                times=(_t(10, 30),),
                freshness_role=FreshnessRole.HEALTH,
            ),
            JobPolicy(
                "postgame",
                Operation.SETTLE,
                times=(_t(18, 30), _t(21, 30)),
                freshness_role=FreshnessRole.POST_EVENT,
                publish_allowed=True,
            ),
        ),
    ),
}


def _is_due(job: JobPolicy, local: datetime) -> bool:
    minute = local.hour * 60 + local.minute
    fixed = any((local.hour, local.minute) == (value.hour, value.minute) for value in job.times)
    interval = job.interval_minutes is not None and minute % job.interval_minutes == 0
    return fixed or interval


def due_runs(
    now: datetime,
    domain: Domain | str,
    *,
    calendar_mode: CalendarMode = CalendarMode.PRODUCTION,
) -> tuple[ScheduledRun, ...]:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("scheduler clock must be timezone-aware")
    policy = DOMAIN_SCHEDULES[Domain(domain)]
    local = now.astimezone(ZoneInfo(policy.timezone)).replace(second=0, microsecond=0)
    runs = []
    for job in policy.jobs:
        if not _is_due(job, local):
            continue
        publish_allowed = job.publish_allowed and calendar_mode is CalendarMode.PRODUCTION
        content_allowed = (
            job.content_notify_allowed and calendar_mode is CalendarMode.PRODUCTION
        )
        runs.append(
            ScheduledRun(
                domain=policy.domain,
                mode=job.mode,
                operation=job.operation,
                scheduled_at=local,
                target_date=local.date() + timedelta(days=job.target_day_offset),
                scheduled_slot=f"{local:%H:%M}",
                freshness_role=job.freshness_role,
                refresh_scope=job.refresh_scope,
                snapshot_mode=job.snapshot_mode,
                publish_allowed=publish_allowed,
                content_notify_allowed=content_allowed,
            )
        )
    return tuple(runs)


def missed_runs(
    after: datetime,
    through: datetime,
    domain: Domain | str,
    *,
    calendar_mode: CalendarMode = CalendarMode.PRODUCTION,
    max_lookback: timedelta = timedelta(days=2),
) -> tuple[ScheduledRun, ...]:
    """Return scheduled slots in ``(after, through]`` for deterministic catch-up."""
    if after.tzinfo is None or through.tzinfo is None:
        raise ValueError("missed-run clocks must be timezone-aware")
    if through < after:
        raise ValueError("through must not be earlier than after")
    start = max(after, through - max_lookback).replace(second=0, microsecond=0)
    cursor = start + timedelta(minutes=1)
    found: list[ScheduledRun] = []
    seen: set[tuple[str, str]] = set()
    while cursor <= through:
        for run in due_runs(cursor, domain, calendar_mode=calendar_mode):
            key = (run.mode, run.scheduled_at.isoformat())
            if key not in seen:
                found.append(run)
                seen.add(key)
        cursor += timedelta(minutes=1)
    return tuple(found)


def refreshable_events(
    run: ScheduledRun,
    event_starts: dict[str, datetime],
    *,
    now: datetime,
) -> frozenset[str]:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("refresh clock must be timezone-aware")
    if run.refresh_scope is RefreshScope.NONE:
        return frozenset()
    if run.refresh_scope is RefreshScope.ALL:
        return frozenset(event_starts)
    return frozenset(
        event_id
        for event_id, starts_at in event_starts.items()
        if starts_at.tzinfo is not None and starts_at > now
    )


def nba_pregame_role(now: datetime) -> FreshnessRole:
    local = now.astimezone(SYDNEY)
    if local.time() >= _t(12, 0):
        return FreshnessRole.WARMUP
    if local.time() < _t(3, 0):
        return FreshnessRole.PRODUCTION
    return FreshnessRole.FINAL_REFRESH


def jobs_for(domain: Domain | str) -> Iterable[JobPolicy]:
    return DOMAIN_SCHEDULES[Domain(domain)].jobs
