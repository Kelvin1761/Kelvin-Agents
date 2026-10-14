"""Sydney gaming window and durable deferred scheduler requests."""

from __future__ import annotations

import hashlib
import fcntl
import json
import os
from dataclasses import replace
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .contracts import Domain, Operation, RunIdentity, RunRequest

SYDNEY = ZoneInfo("Australia/Sydney")


def quiet_until(now: datetime, *, checkpoint: bool = False) -> datetime | None:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("scheduler clock must be timezone-aware")
    local = now.astimezone(SYDNEY)
    start = time(21, 45) if checkpoint else time(22)
    if local.time() >= start:
        return datetime.combine(local.date() + timedelta(days=1), time(1), SYDNEY)
    if local.time() < time(1):
        return datetime.combine(local.date(), time(1), SYDNEY)
    return None


def next_allowed(now: datetime, domain: Domain, mode: str) -> datetime:
    until = quiet_until(now)
    local = now.astimezone(SYDNEY)
    # HKJC full extraction waits for the late HK publication window. Same-day
    # lineup refreshes retain their normal daytime schedule.
    if domain is Domain.HKJC and mode in ("prerace", "recovery", "startup"):
        if local.time() >= time(20):
            until = datetime.combine(local.date() + timedelta(days=1), time(1, 15), SYDNEY)
        elif local.time() < time(1, 15):
            until = datetime.combine(local.date(), time(1, 15), SYDNEY)
    return until or local


class SchedulerDeferred(Exception):
    """A safe boundary was reached; finish the current child, then resume later."""


def checkpoint() -> None:
    # Only scheduler-managed processes enforce checkpoints. Research and unit
    # tests do not acquire an accidental dependence on the wall clock.
    if os.environ.get("WC_SCHEDULER_MANAGED") == "1":
        if quiet_until(datetime.now(SYDNEY), checkpoint=True):
            raise SchedulerDeferred("gaming_window_checkpoint")


class DeferredQueue:
    def __init__(self, root: Path, domain: Domain) -> None:
        self.root = root / "deferred" / domain.value

    def path(self, request: RunRequest) -> Path:
        key = request.identity.idempotency_key
        if request.identity.domain is Domain.HKJC and request.identity.mode == "recovery":
            # The half-hour poller should create one pending recovery per day,
            # not six full extractions to replay at the end of gaming hours.
            key = f"hkjc:recovery:{request.identity.target_date.isoformat()}"
        return self.root / (hashlib.sha256(key.encode()).hexdigest() + ".json")

    def put(self, request: RunRequest, due: datetime, *, reason: str, replace_existing: bool = False) -> Path:
        path = self.path(request)
        self.root.mkdir(parents=True, exist_ok=True)
        with (self.root / "queue.lock").open("a", encoding="utf-8") as lock:
            # Only the short JSON update holds this lock. Concurrent launchd
            # jobs wait for the write instead of losing one deferred request.
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            # A quiet-window duplicate must not erase a previous retry's
            # attempt or cooldown. Identity includes the original target day.
            if path.exists() and not replace_existing:
                return path
            payload = {
                "domain": request.identity.domain.value,
                "mode": request.identity.mode,
                "target_date": request.identity.target_date.isoformat(),
                "scheduled_slot": request.identity.scheduled_slot,
                "attempt": request.identity.attempt,
                "operation": request.operation.value,
                "metadata": dict(request.metadata),
                "due_at": due.isoformat(),
                "reason": reason,
            }
            temp = path.with_suffix(f".tmp.{os.getpid()}")
            temp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            temp.replace(path)
        return path

    @staticmethod
    def request(payload: dict) -> RunRequest:
        identity = RunIdentity(
            Domain(payload["domain"]), payload["mode"],
            date.fromisoformat(payload["target_date"]),
            payload["scheduled_slot"], payload["attempt"],
        )
        return RunRequest(identity, Operation(payload["operation"]), metadata=payload["metadata"])

    def ready(self, now: datetime):
        for path in sorted(self.root.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            if datetime.fromisoformat(payload["due_at"]) > now:
                continue
            request = self.request(payload)
            identity = request.identity
            if next_allowed(now, identity.domain, identity.mode) > now:
                continue
            yield path, request


def retry_request(request: RunRequest) -> RunRequest:
    return replace(request, identity=replace(request.identity, attempt=request.identity.attempt + 1))
