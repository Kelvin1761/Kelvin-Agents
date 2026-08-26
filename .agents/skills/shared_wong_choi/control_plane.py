"""CLI entrypoint for manifest-backed Wong Choi scheduler dispatch.

The control plane owns run identity, idempotency and retry.  Domain adapters
continue to execute the existing schedulers; no prediction logic lives here.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Sequence
from zoneinfo import ZoneInfo


if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from shared_wong_choi.adapters import create_adapter
    from shared_wong_choi.contracts import (
        Domain,
        Operation,
        OperationResult,
        RunIdentity,
        RunRequest,
        RunState,
    )
    from shared_wong_choi.control import RetryPolicy, RunManifest, manifest_path
    from shared_wong_choi.operational import operational_event
else:
    from .adapters import create_adapter
    from .contracts import (
        Domain,
        Operation,
        OperationResult,
        RunIdentity,
        RunRequest,
        RunState,
    )
    from .control import RetryPolicy, RunManifest, manifest_path
    from .operational import operational_event


SYDNEY = ZoneInfo("Australia/Sydney")
DEFAULT_STATE_ROOT = Path.home() / "WongChoiData" / "WongChoiControl"

PRIMARY_OPERATIONS: dict[tuple[Domain, str], Operation] = {
    (Domain.AU, "evening"): Operation.PREDICT,
    (Domain.AU, "morning"): Operation.PREDICT,
    (Domain.AU, "healthcheck"): Operation.HEALTH,
    (Domain.HKJC, "watch"): Operation.DISCOVER,
    (Domain.HKJC, "prerace"): Operation.PREDICT,
    (Domain.HKJC, "postrace"): Operation.SETTLE,
    (Domain.HKJC, "recovery"): Operation.RECOVER,
    (Domain.HKJC, "startup"): Operation.RECOVER,
    (Domain.TENNIS, "card"): Operation.PREDICT,
    (Domain.TENNIS, "daily"): Operation.SETTLE,
    (Domain.TENNIS, "recovery"): Operation.RECOVER,
    (Domain.NBA, "pregame"): Operation.PREDICT,
    (Domain.NBA, "postgame"): Operation.SETTLE,
    (Domain.NBA, "health"): Operation.HEALTH,
    (Domain.NBA, "startup"): Operation.RECOVER,
}

NBA_ROLE_SLOTS = {
    "warmup": "21:00",
    "production": "00:30",
    "final_refresh": "06:30",
}

FIXED_MODE_SLOTS: dict[tuple[Domain, str], str] = {
    (Domain.AU, "evening"): "22:00",
    (Domain.AU, "morning"): "10:00",
    (Domain.TENNIS, "card"): "09:00",
    (Domain.TENNIS, "daily"): "18:00",
}


def primary_operation(domain: Domain, mode: str) -> Operation:
    try:
        return PRIMARY_OPERATIONS[(domain, mode)]
    except KeyError as exc:
        raise ValueError(
            f"no control-plane operation for {domain.value}/{mode}"
        ) from exc


def infer_slot(
    domain: Domain,
    mode: str,
    *,
    now: datetime,
    explicit: str | None = None,
    freshness_role: str | None = None,
) -> str:
    if explicit:
        return explicit
    if mode == "startup":
        return "startup"
    if domain is Domain.NBA and mode == "pregame" and freshness_role:
        try:
            return NBA_ROLE_SLOTS[freshness_role]
        except KeyError as exc:
            raise ValueError(f"unknown NBA freshness role: {freshness_role}") from exc
    return FIXED_MODE_SLOTS.get((domain, mode), now.astimezone(SYDNEY).strftime("%H:%M"))


def infer_target_date(
    domain: Domain,
    mode: str,
    slot: str,
    *,
    now: datetime,
    explicit: date | None = None,
) -> date:
    if explicit is not None:
        return explicit
    local_day = now.astimezone(SYDNEY).date()
    if domain is Domain.NBA and mode == "pregame" and slot == "21:00":
        return local_day + timedelta(days=1)
    return local_day


def _last_exit_code(manifest: RunManifest) -> int | None:
    operations = manifest.payload.get("operations") or []
    if not operations:
        return None
    value = operations[-1].get("detail", {}).get("exit_code")
    return value if isinstance(value, int) else None


def _next_request(
    request: RunRequest,
    state_root: Path,
    retry: RetryPolicy,
) -> RunRequest:
    """Resume at the first unused retry attempt when earlier attempts were temporary."""
    candidate = request
    while True:
        path = manifest_path(state_root / "runs", candidate.identity)
        if not path.exists():
            return candidate
        existing = RunManifest.load(path)
        exit_code = _last_exit_code(existing)
        if (
            existing.state is RunState.PARTIAL
            and exit_code is not None
            and retry.should_retry(
                exit_code=exit_code,
                attempt=candidate.identity.attempt,
            )
        ):
            candidate = replace(
                candidate,
                identity=replace(
                    candidate.identity,
                    attempt=candidate.identity.attempt + 1,
                ),
            )
            continue
        return candidate


def execute_with_retry(adapter, request: RunRequest, retry: RetryPolicy) -> OperationResult:
    current = request
    while True:
        result = adapter.execute(current)
        exit_code = result.detail.get("exit_code")
        if not (
            result.state is RunState.PARTIAL
            and isinstance(exit_code, int)
            and retry.should_retry(
                exit_code=exit_code,
                attempt=current.identity.attempt,
            )
        ):
            return result
        current = replace(
            current,
            identity=replace(
                current.identity,
                attempt=current.identity.attempt + 1,
            ),
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", required=True, choices=[item.value for item in Domain])
    parser.add_argument("--mode", required=True)
    parser.add_argument("--operation", choices=[item.value for item in Operation])
    parser.add_argument("--date", "--today", dest="target_date", type=date.fromisoformat)
    parser.add_argument("--scheduled-slot", "--slot", dest="scheduled_slot")
    parser.add_argument(
        "--freshness-role",
        choices=tuple(NBA_ROLE_SLOTS),
        help="NBA pregame role; also fixes the canonical scheduled slot.",
    )
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--meeting-url")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--state-root",
        type=Path,
        default=Path(os.environ.get("WONGCHOI_CONTROL_STATE_ROOT", DEFAULT_STATE_ROOT)),
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    now: datetime | None = None,
    repo_root: Path | None = None,
) -> int:
    parser = build_parser()
    args, scheduler_args = parser.parse_known_args(argv)
    clock = now or datetime.now(SYDNEY)
    if clock.tzinfo is None or clock.utcoffset() is None:
        parser.error("control-plane clock must be timezone-aware")

    domain = Domain(args.domain)
    mode = args.mode.strip().lower()
    try:
        operation = Operation(args.operation) if args.operation else primary_operation(domain, mode)
        slot = infer_slot(
            domain,
            mode,
            now=clock,
            explicit=args.scheduled_slot,
            freshness_role=args.freshness_role,
        )
        target = infer_target_date(
            domain,
            mode,
            slot,
            now=clock,
            explicit=args.target_date,
        )
    except ValueError as exc:
        parser.error(str(exc))

    identity = RunIdentity(domain, mode, target, slot, args.attempt)
    metadata = {
        "freshness_role": args.freshness_role,
        "meeting_url": args.meeting_url,
        "force": args.force,
        "scheduler_args": tuple(scheduler_args),
    }
    request = RunRequest(identity, operation, dry_run=args.dry_run, metadata=metadata)
    state_root = args.state_root.expanduser().resolve()
    retry = RetryPolicy(max_attempts=args.max_attempts)
    if not args.dry_run:
        request = _next_request(request, state_root, retry)

    root = repo_root or Path(__file__).resolve().parents[3]
    adapter = create_adapter(domain, root, state_root)
    result = execute_with_retry(adapter, request, retry)
    event = operational_event(request, result)
    output = {
        "schema_version": "wong-choi-control-result/v1",
        "domain": domain.value,
        "mode": mode,
        "operation": operation.value,
        "target_date": target.isoformat(),
        "scheduled_slot": slot,
        "state": result.state.value,
        "status": result.status,
        "severity": event.severity.value,
        "notification_dedup_key": event.dedup_key,
        "artifacts": list(result.artifacts),
        "detail": dict(result.detail),
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    if result.state is RunState.FAILED:
        return 1
    if result.state in (RunState.PARTIAL, RunState.BLOCKED):
        return 75
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
