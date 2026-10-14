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
        TERMINAL_STATES,
        Domain,
        Operation,
        OperationResult,
        RunIdentity,
        RunRequest,
        RunState,
    )
    from shared_wong_choi.control import RetryPolicy, RunManifest, manifest_path
    from shared_wong_choi.operational import operational_event
    from shared_wong_choi.scheduler_window import DeferredQueue, next_allowed, retry_request
    from shared_wong_choi.schedule_policy import NBA_ROLE_SLOTS
else:
    from .adapters import create_adapter
    from .contracts import (
        TERMINAL_STATES,
        Domain,
        Operation,
        OperationResult,
        RunIdentity,
        RunRequest,
        RunState,
    )
    from .control import RetryPolicy, RunManifest, manifest_path
    from .operational import operational_event
    from .scheduler_window import DeferredQueue, next_allowed, retry_request
    from .schedule_policy import NBA_ROLE_SLOTS


SYDNEY = ZoneInfo("Australia/Sydney")
DEFAULT_STATE_ROOT = Path.home() / "WongChoiData" / "WongChoiControl"

PRIMARY_OPERATIONS: dict[tuple[Domain, str], Operation] = {
    (Domain.AU, "evening"): Operation.PREDICT,
    (Domain.AU, "morning"): Operation.PREDICT,
    (Domain.AU, "healthcheck"): Operation.HEALTH,
    (Domain.HKJC, "watch"): Operation.DISCOVER,
    (Domain.HKJC, "prerace"): Operation.PREDICT,
    # `lineup` 係賽日出賽名單掃描器 —— 同 `watch` 一樣係平價偵測器，
    # 大部分時間乜都唔做；一旦見到退出／換馬先 in-process call `run_prerace`
    # 重跑。同 `recovery`（RECOVER 之後 call prerace）同一形狀。
    (Domain.HKJC, "lineup"): Operation.DISCOVER,
    (Domain.HKJC, "postrace"): Operation.SETTLE,
    (Domain.HKJC, "recovery"): Operation.RECOVER,
    (Domain.HKJC, "startup"): Operation.RECOVER,
    (Domain.HKJC, "weekly"): Operation.HEALTH,
    (Domain.HKJC, "intraday"): Operation.HEALTH,
    (Domain.TENNIS, "card"): Operation.PREDICT,
    (Domain.TENNIS, "daily"): Operation.SETTLE,
    (Domain.TENNIS, "recovery"): Operation.RECOVER,
    (Domain.NBA, "pregame"): Operation.PREDICT,
    (Domain.NBA, "postgame"): Operation.SETTLE,
    (Domain.NBA, "health"): Operation.HEALTH,
    (Domain.NBA, "startup"): Operation.RECOVER,
}

FIXED_MODE_SLOTS: dict[tuple[Domain, str], str] = {
    (Domain.AU, "evening"): "17:00",
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
    local = now.astimezone(SYDNEY)
    local_day = local.date()
    if domain is Domain.NBA and mode == "pregame" and slot in ("19:30", "20:30", "21:00"):
        return local_day if local.hour < 12 else local_day + timedelta(days=1)
    if domain is Domain.AU and mode == "evening" and local.hour < 12:
        return local_day - timedelta(days=1)
    if domain is Domain.TENNIS and mode == "daily" and local.hour < 9:
        return local_day - timedelta(days=1)
    return local_day


def _last_exit_code(manifest: RunManifest) -> int | None:
    operations = manifest.payload.get("operations") or []
    if not operations:
        return None
    value = operations[-1].get("detail", {}).get("exit_code")
    return value if isinstance(value, int) else None


#: `--force` 最多可以行到第幾個 attempt。純粹係防止一個爛狀態令我哋無限
#: 行落去；正常一日唔會用到幾個。
FORCE_ATTEMPT_CEILING = 20


def _next_request(
    request: RunRequest,
    state_root: Path,
    retry: RetryPolicy,
    *,
    force: bool = False,
) -> RunRequest:
    """Resume at the first unused retry attempt when earlier attempts were temporary.

    `force=True` 額外容許跳過一個**已經終局**嘅 manifest（`failed` 包括在內），
    行到第一個未用過嘅 attempt。

    ⚠️ 點解要有呢個：自動重試**只認 `PARTIAL`**（暫時性失敗），呢個係刻意嘅 ——
    唔好無限重試一個真 bug。但復原 job（例如 `tennis_card_recovery.py`）存在嘅
    唯一目的就係重試一個**失敗咗**嘅 run，而佢原本會攞返同一個 identity，
    `command_adapter` 見到 manifest 已經存在就即刻回 `duplicate_skipped`，一步
    都唔行。2026-09-09 實測：09:00 網球咭 `failed`，10:30 同 12:30 兩個復原時段
    都係 `duplicate_skipped`，兩個 attempt 燒晒喺空跑度，當日冇咭。

    NBA warmup 另容許暫時失敗後嘅後續調用讀取新市場；其他排程政策保持不變。明確人手／復原調用
    有辦法開一個新 attempt。`--max-attempts` 同 `FORCE_ATTEMPT_CEILING` 照封頂。
    """
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
        # A later NBA warmup must read newly opened markets after an earlier
        # bounded batch exhausted its retries. Preserve old manifests, success
        # idempotency, permanent failures and every other domain's policy.
        if (
            candidate.identity.domain is Domain.NBA
            and candidate.identity.mode == "pregame"
            and candidate.identity.scheduled_slot in ("19:30", "21:00")
            and existing.state is RunState.PARTIAL
            and exit_code is not None
            and retry.should_retry(exit_code=exit_code, attempt=1)
            and candidate.identity.attempt < FORCE_ATTEMPT_CEILING
        ):
            candidate = replace(
                candidate,
                identity=replace(candidate.identity, attempt=candidate.identity.attempt + 1),
            )
            continue
        if (
            force
            and existing.state in TERMINAL_STATES
            and candidate.identity.attempt < FORCE_ATTEMPT_CEILING
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
    # Source waiting and temporary failures are retried by the durable queue,
    # not by re-running the whole pipeline three times at the same instant.
    return adapter.execute(request)


def dispatch(request: RunRequest, root: Path, state_root: Path, retry: RetryPolicy,
             clock: datetime) -> OperationResult:
    queue = DeferredQueue(state_root, request.identity.domain)
    pending = queue.path(request)
    if not request.dry_run and pending.exists():
        saved = json.loads(pending.read_text(encoding="utf-8"))
        due = datetime.fromisoformat(saved["due_at"])
        if due > clock:
            return OperationResult(RunState.BLOCKED, "deferred_cooldown", artifacts=(str(pending),),
                                   detail={"next_retry_at": due.isoformat()})
    allowed = next_allowed(clock, request.identity.domain, request.identity.mode)
    if allowed > clock and not request.dry_run:
        path = queue.put(request, allowed, reason="gaming_window")
        return OperationResult(RunState.BLOCKED, "deferred_quiet_hours", artifacts=(str(path),),
                               detail={"next_retry_at": allowed.isoformat()})
    # A fresh launchd invocation may race the deferred consumer after cooldown.
    # Resume the saved identity and retry budget rather than replaying attempt 1.
    if not request.dry_run and pending.exists():
        request = queue.request(json.loads(pending.read_text(encoding="utf-8")))
    adapter = create_adapter(request.identity.domain, root, state_root)
    result = execute_with_retry(adapter, request, retry)
    exit_code = result.detail.get("exit_code")
    if not request.dry_run and result.state is RunState.PARTIAL and isinstance(exit_code, int):
        payload = result.detail.get("source_payload") or {}
        checkpoint = payload.get("reason") == "gaming_window_checkpoint"
        failures = int(request.metadata.get("temporary_failures", 0)) + (0 if checkpoint else 1)
        limit = int(request.metadata.get("max_attempts", retry.max_attempts))
        if (exit_code in retry.retryable_exit_codes
                and request.identity.attempt < FORCE_ATTEMPT_CEILING
                and (checkpoint or failures < limit)):
            next_request = replace(retry_request(request), metadata={
                **request.metadata, "temporary_failures": failures,
            })
            finished = max(clock, datetime.now(SYDNEY))
            due = next_allowed(finished + timedelta(minutes=30), request.identity.domain, request.identity.mode)
            queue.put(next_request, due, reason="checkpoint" if checkpoint else "temporary_failure",
                      replace_existing=True)
            result = replace(result, detail={**result.detail, "next_retry_at": due.isoformat()})
    elif not request.dry_run and result.state is RunState.BLOCKED:
        due = next_allowed(max(clock, datetime.now(SYDNEY)) + timedelta(minutes=30),
                           request.identity.domain, request.identity.mode)
        if result.detail.get("source_payload"):
            request = retry_request(request)
        if request.identity.attempt > FORCE_ATTEMPT_CEILING:
            return result
        queue.put(request, due, reason="scheduler_locked", replace_existing=True)
        result = replace(result, detail={**result.detail, "next_retry_at": due.isoformat()})
    return result


def drain_deferred(domain: Domain, root: Path, state_root: Path, clock: datetime) -> int:
    from shared_wong_choi.control import single_run_lock
    queue = DeferredQueue(state_root, domain)
    if next_allowed(clock, domain, "deferred") > clock:
        print(json.dumps({"status": "quiet_hours", "domain": domain.value}))
        return 0
    with single_run_lock(queue.root / "drain.lock") as acquired:
        if not acquired:
            return 0
        for path, request in queue.ready(clock):
            request = _next_request(request, state_root,
                                    RetryPolicy(max_attempts=int(request.metadata.get("max_attempts", 3))),
                                    force=bool(request.metadata.get("force")))
            result = dispatch(request, root, state_root,
                              RetryPolicy(max_attempts=int(request.metadata.get("max_attempts", 3))), clock)
            # Rescheduled requests retain the same filename with a new attempt.
            if "next_retry_at" not in result.detail:
                path.unlink(missing_ok=True)
            print(json.dumps({"domain": domain.value, "status": result.status,
                              "target_date": request.identity.target_date.isoformat(),
                              "scheduled_slot": request.identity.scheduled_slot,
                              "detail": dict(result.detail)}, ensure_ascii=False))
            return 0
    print(json.dumps({"status": "no_pending_requests", "domain": domain.value}))
    return 0


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
    parser.add_argument(
        "--force", action="store_true",
        help="明確人手／復原調用：容許跳過一個已經終局（包括 failed）嘅 "
             "manifest，開一個新 attempt。唔會改變排程嘅自動重試政策。")
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
    state_root = args.state_root.expanduser().resolve()
    root = repo_root or Path(__file__).resolve().parents[3]
    if mode == "deferred":
        if args.dry_run:
            print(json.dumps({"status": "dry_run", "domain": domain.value}))
            return 0
        return drain_deferred(domain, root, state_root, clock)
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
        "max_attempts": args.max_attempts,
    }
    request = RunRequest(identity, operation, dry_run=args.dry_run, metadata=metadata)
    state_root = args.state_root.expanduser().resolve()
    retry = RetryPolicy(max_attempts=args.max_attempts)
    if not args.dry_run:
        request = _next_request(request, state_root, retry, force=args.force)

    result = dispatch(request, root, state_root, retry, clock)
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
