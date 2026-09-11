"""Fail-closed production-day coverage evidence for Stage 5 reviews.

Terminal failures still close an execution day; they do not make it healthy.
A day can close only when an approved producer attests the complete declarative
schedule and every expected run identity has a terminal immutable manifest.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Callable

from .contracts import Domain, RunIdentity, RunState, TERMINAL_STATES
from .control import SCHEMA_VERSION as RUN_SCHEMA, manifest_path
from .research_index import _Reader, _at, _encoded, _hash, _hashed, _safe
from .research_review_clock import ReviewEvent
from .schedule_policy import DOMAIN_SCHEDULES, SYDNEY, due_runs


ATTESTATION_SCHEMA = "wong-choi-production-day-attestation/v1"
REPORT_SCHEMA = "wong-choi-production-day-evidence/v1"
_ATTEMPT = re.compile(r"attempt-([1-9][0-9]{0,2})\.json")
_HEX40 = re.compile(r"[0-9a-f]{40}")
_HEX64 = re.compile(r"[0-9a-f]{64}")
_BLOCKER_ORDER = (
    "production_day_not_ended",
    "schedule_identity_collision",
    "schedule_attestation_missing",
    "schedule_trigger_coverage_incomplete",
    "expected_run_missing",
    "expected_run_nonterminal",
)


def production_day_report_reference(path: Path, report: dict) -> dict:
    """Return the bounded identity retained by review summaries/cursors."""
    verify_production_day_evidence(
        report,
        run_root=Path(report["run_root"]),
        attestation_path=(
            Path(report["attestation_path"])
            if report["attestation_path"] is not None else None
        ),
        domain=Domain(report["domain"]),
        production_day=date.fromisoformat(report["production_day"]),
        as_of=report["as_of"],
    )
    return {
        "path": str(path),
        "content_hash": report["content_hash"],
        "observed_at": _at(report["as_of"]).isoformat(),
        "production_day": report["production_day"],
        "production_day_closed": report["production_day_closed"],
        "operational_health": report["operational_health"],
        "counts": report["counts"],
        "closure_blockers": report["closure_blockers"],
    }


def _policy_payload(domain: Domain) -> dict:
    policy = DOMAIN_SCHEDULES[domain]
    return {
        "domain": domain.value,
        "timezone": policy.timezone,
        "jobs": [
            {
                "mode": job.mode,
                "operation": job.operation.value,
                "times": [value.isoformat() for value in job.times],
                "interval_minutes": job.interval_minutes,
                "target_day_offset": job.target_day_offset,
                "freshness_role": job.freshness_role.value,
                "refresh_scope": job.refresh_scope.value,
                "snapshot_mode": job.snapshot_mode.value,
                "publish_allowed": job.publish_allowed,
                "content_notify_allowed": job.content_notify_allowed,
            }
            for job in policy.jobs
        ],
    }


def production_day_schedule(domain: Domain, production_day: date) -> dict:
    """Expand one real Sydney day, preserving DST folds and collisions."""
    if not isinstance(domain, Domain) or type(production_day) is not date:
        raise ValueError("known domain and production date required")
    local_start = datetime.combine(production_day, time.min, tzinfo=SYDNEY)
    local_end = datetime.combine(
        production_day + timedelta(days=1), time.min, tzinfo=SYDNEY,
    )
    cursor = local_start.astimezone(timezone.utc)
    end = local_end.astimezone(timezone.utc)
    expected = []
    while cursor < end:
        for run in due_runs(cursor, domain):
            if run.scheduled_at.date() != production_day:
                continue
            identity = RunIdentity(
                domain, run.mode, run.target_date, run.scheduled_slot,
            )
            expected.append({
                "run_identity": identity.idempotency_key,
                "mode": run.mode,
                "operation": run.operation.value,
                "scheduled_at": run.scheduled_at.isoformat(),
                "target_date": run.target_date.isoformat(),
                "scheduled_slot": run.scheduled_slot,
                "freshness_role": run.freshness_role.value,
            })
        cursor += timedelta(minutes=1)
    expected.sort(key=lambda item: (_at(item["scheduled_at"]), item["mode"]))
    identities = defaultdict(list)
    for item in expected:
        identities[item["run_identity"]].append(item["scheduled_at"])
    collisions = [
        {"run_identity": identity, "scheduled_at": values}
        for identity, values in sorted(identities.items()) if len(values) > 1
    ]
    return {
        "domain": domain.value,
        "production_day": production_day.isoformat(),
        "timezone": "Australia/Sydney",
        "day_started_at": local_start.isoformat(),
        "day_ended_at": local_end.isoformat(),
        "policy_digest": _hash(_policy_payload(domain)),
        "expected_runs": expected,
        "identity_collisions": collisions,
    }


def _attestation(
    reader: _Reader,
    path: Path | None,
    *,
    schedule: dict,
    as_of: datetime,
) -> tuple[dict | None, str | None]:
    if path is None:
        return None, None
    value, digest = reader.read(_safe(path.expanduser().absolute()))
    _hashed(value, ATTESTATION_SCHEMA)
    expected_fields = {
        "schema_version", "append_only", "domain", "production_day",
        "generated_at", "policy_digest", "producer_commit",
        "installed_schedule_digest", "expected_runs",
        "trigger_coverage_complete", "model_promotion_allowed", "content_hash",
    }
    if (
        set(value) != expected_fields
        or value["append_only"] is not True
        or value["domain"] != schedule["domain"]
        or value["production_day"] != schedule["production_day"]
        or _at(value["generated_at"]) > as_of
        or value["policy_digest"] != schedule["policy_digest"]
        or value["expected_runs"] != schedule["expected_runs"]
        or _HEX40.fullmatch(value.get("producer_commit", "")) is None
        or _HEX64.fullmatch(value.get("installed_schedule_digest", "")) is None
        or type(value.get("trigger_coverage_complete")) is not bool
        or value["model_promotion_allowed"] is not False
    ):
        raise ValueError("production-day attestation does not match expected schedule")
    return value, digest


def _manifest(
    reader: _Reader,
    path: Path,
    *,
    identity: RunIdentity,
    attempt: int,
    as_of: datetime,
) -> tuple[dict, str]:
    value, digest = reader.read(path)
    fields = {
        "schema_version", "run_id", "idempotency_key", "domain", "mode",
        "target_date", "scheduled_slot", "attempt", "state", "started_at",
        "completed_at", "operations", "warnings", "errors",
    }
    if (
        set(value) != fields
        or value["schema_version"] != RUN_SCHEMA
        or value["run_id"] != RunIdentity(
            identity.domain, identity.mode, identity.target_date,
            identity.scheduled_slot, attempt,
        ).run_id
        or value["idempotency_key"] != identity.idempotency_key
        or value["domain"] != identity.domain.value
        or value["mode"] != identity.mode
        or value["target_date"] != identity.target_date.isoformat()
        or value["scheduled_slot"] != identity.scheduled_slot
        or value["attempt"] != attempt
        or not isinstance(value["operations"], list)
        or not isinstance(value["warnings"], list)
        or not isinstance(value["errors"], list)
    ):
        raise ValueError("production run manifest identity mismatch")
    try:
        state = RunState(value["state"])
        started = _at(value["started_at"])
        completed = _at(value["completed_at"]) if value["completed_at"] else None
    except (ValueError, RuntimeError, TypeError) as exc:
        raise ValueError("production run manifest chronology invalid") from exc
    if (
        started > as_of
        or (state in TERMINAL_STATES)
        != (completed is not None and started <= completed <= as_of)
    ):
        raise ValueError("production run manifest chronology invalid")
    return value, digest


def inspect_production_day(
    *,
    run_root: Path,
    attestation_path: Path | None,
    domain: Domain,
    production_day: date,
    as_of: datetime,
    checkpoint: Callable[[], None] = lambda: None,
) -> dict:
    """Build bounded coverage evidence; never mutate runs or emit approval."""
    schedule = production_day_schedule(domain, production_day)
    end = _at(as_of)
    root = _safe(run_root.expanduser().absolute())
    reader = _Reader(
        checkpoint, max_records=1024, max_record_bytes=1048576,
        max_total_bytes=33554432,
    )
    attestation, attestation_file_digest = _attestation(
        reader, attestation_path, schedule=schedule, as_of=end,
    )
    rows = []
    state_counts = Counter()
    missing = nonterminal = 0
    for expected in schedule["expected_runs"]:
        checkpoint()
        identity = RunIdentity(
            domain,
            expected["mode"],
            date.fromisoformat(expected["target_date"]),
            expected["scheduled_slot"],
        )
        folder = manifest_path(root, identity).parent
        entries = reader.listing(folder)
        attempts = []
        for path in entries:
            match = _ATTEMPT.fullmatch(path.name)
            if match is None:
                raise ValueError("unexpected production run evidence entry")
            attempt = int(match.group(1))
            value, digest = _manifest(
                reader, path, identity=identity, attempt=attempt, as_of=end,
            )
            attempts.append({
                "attempt": attempt,
                "state": value["state"],
                "started_at": _at(value["started_at"]).isoformat(),
                "completed_at": (
                    _at(value["completed_at"]).isoformat()
                    if value["completed_at"] else None
                ),
                "manifest_sha256": digest,
            })
        attempts.sort(key=lambda item: item["attempt"])
        if attempts and [item["attempt"] for item in attempts] != list(
            range(1, attempts[-1]["attempt"] + 1)
        ):
            raise ValueError("production run attempt sequence has a gap")
        if not attempts:
            missing += 1
            latest_state = "missing"
        else:
            latest_state = attempts[-1]["state"]
            if any(RunState(item["state"]) not in TERMINAL_STATES for item in attempts):
                nonterminal += 1
            else:
                state_counts[latest_state] += 1
        rows.append({
            **expected,
            "attempts": attempts,
            "latest_state": latest_state,
        })
    reader.recheck()
    blockers = []
    if end < _at(schedule["day_ended_at"]):
        blockers.append("production_day_not_ended")
    if schedule["identity_collisions"]:
        blockers.append("schedule_identity_collision")
    if attestation is None:
        blockers.append("schedule_attestation_missing")
    elif not attestation["trigger_coverage_complete"]:
        blockers.append("schedule_trigger_coverage_incomplete")
    if missing:
        blockers.append("expected_run_missing")
    if nonterminal:
        blockers.append("expected_run_nonterminal")
    blockers = [item for item in _BLOCKER_ORDER if item in blockers]
    terminal = sum(state_counts.values())
    closed_at_values = [
        _at(attempt["completed_at"])
        for row in rows for attempt in row["attempts"][-1:]
        if attempt["completed_at"] is not None
    ]
    closed = not blockers and terminal == len(rows)
    unhealthy = sum(
        state_counts[state.value]
        for state in (RunState.PARTIAL, RunState.FAILED, RunState.BLOCKED)
    )
    report = {
        "schema_version": REPORT_SCHEMA,
        "domain": domain.value,
        "production_day": production_day.isoformat(),
        "as_of": end.isoformat(),
        "run_root": str(root),
        "attestation_path": (
            str(_safe(attestation_path.expanduser().absolute()))
            if attestation_path is not None else None
        ),
        "attestation_file_sha256": attestation_file_digest,
        "policy_digest": schedule["policy_digest"],
        "schedule_attestation_verified": attestation is not None,
        "schedule_trigger_coverage_complete": (
            attestation["trigger_coverage_complete"]
            if attestation is not None else False
        ),
        "source_snapshot_verified": True,
        "production_day_closed": closed,
        "closed_at": max(closed_at_values).isoformat() if closed else None,
        "operational_health": (
            "attention" if closed and unhealthy else "healthy" if closed else "not_closed"
        ),
        "counts": {
            "expected": len(rows),
            "terminal": terminal,
            "missing": missing,
            "nonterminal": nonterminal,
            **{state.value: state_counts[state.value] for state in TERMINAL_STATES},
        },
        "identity_collisions": schedule["identity_collisions"],
        "closure_blockers": blockers,
        "runs": rows,
        "review_event_allowed": closed,
        "schedule_mutation_allowed": False,
        "rerun_allowed": False,
        "model_promotion_allowed": False,
    }
    report["content_hash"] = _hash(report)
    verify_production_day_evidence(
        report,
        run_root=root,
        attestation_path=attestation_path,
        domain=domain,
        production_day=production_day,
        as_of=end,
    )
    return report


def verify_production_day_evidence(
    report: dict,
    *,
    run_root: Path,
    attestation_path: Path | None,
    domain: Domain,
    production_day: date,
    as_of: datetime,
    reverify_source: bool = False,
    checkpoint: Callable[[], None] = lambda: None,
) -> None:
    _hashed(report, REPORT_SCHEMA)
    expected_fields = {
        "schema_version", "domain", "production_day", "as_of", "run_root",
        "attestation_path", "attestation_file_sha256", "policy_digest",
        "schedule_attestation_verified", "schedule_trigger_coverage_complete",
        "source_snapshot_verified",
        "production_day_closed", "closed_at", "operational_health", "counts",
        "identity_collisions", "closure_blockers", "runs", "review_event_allowed",
        "schedule_mutation_allowed", "rerun_allowed", "model_promotion_allowed",
        "content_hash",
    }
    root = _safe(run_root.expanduser().absolute())
    expected_attestation = (
        str(_safe(attestation_path.expanduser().absolute()))
        if attestation_path is not None else None
    )
    schedule = production_day_schedule(domain, production_day)
    if (
        set(report) != expected_fields
        or report["domain"] != domain.value
        or report["production_day"] != production_day.isoformat()
        or report["as_of"] != _at(as_of).isoformat()
        or report["run_root"] != str(root)
        or report["attestation_path"] != expected_attestation
        or report["policy_digest"] != schedule["policy_digest"]
        or report["source_snapshot_verified"] is not True
        or type(report["schedule_trigger_coverage_complete"]) is not bool
        or report["identity_collisions"] != schedule["identity_collisions"]
        or report["schedule_mutation_allowed"] is not False
        or report["rerun_allowed"] is not False
        or report["model_promotion_allowed"] is not False
        or report["review_event_allowed"] is not report["production_day_closed"]
        or len(_encoded(report)) > 1048576
    ):
        raise ValueError("production-day evidence scope or authority mismatch")
    attested = report["schedule_attestation_verified"]
    if (
        type(attested) is not bool
        or attested is not (expected_attestation is not None)
        or attested is not (report["attestation_file_sha256"] is not None)
        or (
            report["attestation_file_sha256"] is not None
            and _HEX64.fullmatch(report["attestation_file_sha256"]) is None
        )
        or (not attested and report["schedule_trigger_coverage_complete"])
    ):
        raise ValueError("production-day attestation evidence mismatch")

    counts = report["counts"]
    count_fields = {
        "expected", "terminal", "missing", "nonterminal",
        *(state.value for state in TERMINAL_STATES),
    }
    if (not isinstance(report["runs"], list)
            or len(report["runs"]) != len(schedule["expected_runs"])):
        raise ValueError("production-day evidence row count mismatch")
    state_counts = Counter()
    missing = nonterminal = 0
    latest_completions = []
    for row, expected in zip(report["runs"], schedule["expected_runs"]):
        if (
            not isinstance(row, dict)
            or set(row) != {*expected, "attempts", "latest_state"}
            or {key: row[key] for key in expected} != expected
            or not isinstance(row["attempts"], list)
            or len(row["attempts"]) > 100
        ):
            raise ValueError("production-day evidence row mismatch")
        attempts = row["attempts"]
        if not attempts:
            missing += 1
            if row["latest_state"] != "missing":
                raise ValueError("production-day evidence row mismatch")
            continue
        has_nonterminal = False
        for index, attempt in enumerate(attempts, 1):
            if (
                not isinstance(attempt, dict)
                or set(attempt) != {
                    "attempt", "state", "started_at", "completed_at",
                    "manifest_sha256",
                }
                or attempt["attempt"] != index
                or _HEX64.fullmatch(attempt.get("manifest_sha256", "")) is None
            ):
                raise ValueError("production-day evidence row attempt mismatch")
            try:
                state = RunState(attempt["state"])
                started = _at(attempt["started_at"])
                completed = (
                    _at(attempt["completed_at"])
                    if attempt["completed_at"] is not None else None
                )
            except (ValueError, RuntimeError, TypeError) as exc:
                raise ValueError(
                    "production-day evidence row chronology mismatch"
                ) from exc
            if (
                started > _at(as_of)
                or (state in TERMINAL_STATES)
                != (completed is not None and started <= completed <= _at(as_of))
            ):
                raise ValueError("production-day evidence row chronology mismatch")
            has_nonterminal |= state not in TERMINAL_STATES
        if row["latest_state"] != attempts[-1]["state"]:
            raise ValueError("production-day evidence row latest state mismatch")
        if has_nonterminal:
            nonterminal += 1
        else:
            state_counts[RunState(row["latest_state"]).value] += 1
        if attempts[-1]["completed_at"] is not None:
            latest_completions.append(_at(attempts[-1]["completed_at"]))

    expected_counts = {
        "expected": len(schedule["expected_runs"]),
        "terminal": sum(state_counts.values()),
        "missing": missing,
        "nonterminal": nonterminal,
        **{state.value: state_counts[state.value] for state in TERMINAL_STATES},
    }
    derived_blockers = []
    if _at(as_of) < _at(schedule["day_ended_at"]):
        derived_blockers.append("production_day_not_ended")
    if schedule["identity_collisions"]:
        derived_blockers.append("schedule_identity_collision")
    if not attested:
        derived_blockers.append("schedule_attestation_missing")
    elif not report["schedule_trigger_coverage_complete"]:
        derived_blockers.append("schedule_trigger_coverage_incomplete")
    if missing:
        derived_blockers.append("expected_run_missing")
    if nonterminal:
        derived_blockers.append("expected_run_nonterminal")
    derived_blockers = [item for item in _BLOCKER_ORDER if item in derived_blockers]
    closed = (
        not derived_blockers
        and expected_counts["terminal"] == expected_counts["expected"]
    )
    unhealthy = sum(
        state_counts[state.value]
        for state in (RunState.PARTIAL, RunState.FAILED, RunState.BLOCKED)
    )
    expected_health = (
        "attention" if closed and unhealthy
        else "healthy" if closed
        else "not_closed"
    )
    expected_closed_at = (
        max(latest_completions).isoformat() if closed else None
    )
    if report["operational_health"] != expected_health:
        raise ValueError("production-day evidence health mismatch")
    if (
        not isinstance(counts, dict)
        or set(counts) != count_fields
        or any(type(value) is not int or not 0 <= value <= 1000 for value in counts.values())
        or counts != expected_counts
        or report["closure_blockers"] != derived_blockers
        or report["production_day_closed"] is not closed
        or report["closed_at"] != expected_closed_at
    ):
        raise ValueError("production-day evidence aggregate mismatch")
    if reverify_source:
        rebuilt = inspect_production_day(
            run_root=root,
            attestation_path=attestation_path,
            domain=domain,
            production_day=production_day,
            as_of=_at(as_of),
            checkpoint=checkpoint,
        )
        if rebuilt != report:
            raise ValueError("production-day source changed during verification")


def production_day_review_event(report: dict) -> ReviewEvent:
    """Convert verified closure evidence into the existing review-clock event."""
    if (
        report.get("schema_version") != REPORT_SCHEMA
        or not report.get("production_day_closed")
        or not report.get("review_event_allowed")
    ):
        raise ValueError("production day is not closed")
    _hashed(report, REPORT_SCHEMA)
    return ReviewEvent(
        "production_day_closed",
        f"production-day:{report['domain']}:{report['production_day']}",
        _at(report["closed_at"]),
        report["content_hash"],
        production_day=date.fromisoformat(report["production_day"]),
    )
