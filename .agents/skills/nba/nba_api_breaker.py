"""Circuit breaker for stats.nba.com, shared across processes.

2026-10-28/29: Akamai stopped answering this machine on every nba.com host
(hang, then 403) for hours. Nothing stopped us calling it: the extractor makes
~200 calls per game, three games in parallel, each paying the 30s timeout, and
the scheduler retried every slot three times. A pregame run then took 6+
minutes to learn what the first three calls already said, and the volume
itself plausibly kept the block alive.

``install()`` wraps nba_api's single HTTP entry point. After ``TRIP_AFTER``
consecutive network failures (timeout, connection error, HTTP 403/429) it
writes a marker file; while the marker is fresh every call in every process
raises ``StatsNbaBlocked`` at once, without touching the network. One success
clears it. The marker expires on its own, so a lifted block is picked up by
the next run with no manual step.

This changes no data: a call either returns what nba.com returns, or fails --
it just fails in milliseconds instead of 30 seconds.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

TRIP_AFTER = 3
COOLDOWN_SECONDS = 30 * 60
BLOCKING_STATUS = {403, 429}

_state = {"consecutive": 0, "installed": False}


class StatsNbaBlocked(ConnectionError):
    """stats.nba.com is refusing us; do not call it until the marker expires."""


def marker_path() -> Path:
    override = os.environ.get("WC_NBA_API_BREAKER_FILE")
    if override:
        return Path(override)
    return Path.home() / ".cache" / "wongchoi" / "stats_nba_breaker.json"


def blocked_until(now: float | None = None) -> float | None:
    """Epoch until which stats.nba.com is considered blocked, or None."""
    try:
        data = json.loads(marker_path().read_text(encoding="utf-8"))
        until = float(data.get("until") or 0)
    except (OSError, ValueError, TypeError):
        return None
    return until if until > (now if now is not None else time.time()) else None


def _trip(reason: str) -> None:
    path = marker_path()
    now = time.time()
    payload = {"until": now + COOLDOWN_SECONDS, "tripped_at": now, "reason": reason[:300]}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass  # the in-process counter still trips


def _clear() -> None:
    _state["consecutive"] = 0
    try:
        marker_path().unlink()
    except OSError:
        pass


def record_failure(reason: str) -> None:
    _state["consecutive"] += 1
    if _state["consecutive"] >= TRIP_AFTER:
        _trip(reason)


def record_success() -> None:
    if _state["consecutive"] or blocked_until() is not None:
        _clear()


def _is_network_failure(exc: BaseException) -> bool:
    try:
        import requests
        return isinstance(exc, (requests.exceptions.Timeout,
                                requests.exceptions.ConnectionError))
    except ImportError:
        return isinstance(exc, (TimeoutError, ConnectionError))


def guard(send):
    """Wrap an nba_api ``send_api_request``."""
    def guarded(self, endpoint, *args, **kwargs):
        until = blocked_until()
        if until is not None or _state["consecutive"] >= TRIP_AFTER:
            when = time.strftime("%H:%M", time.localtime(until)) if until else "this run"
            raise StatsNbaBlocked(
                f"stats.nba.com blocked (circuit open until {when}); skipped {endpoint}")
        try:
            response = send(self, endpoint, *args, **kwargs)
        except Exception as exc:
            if _is_network_failure(exc):
                record_failure(f"{endpoint}: {type(exc).__name__}: {exc}")
            raise
        status = getattr(response, "_status_code", None)
        if status in BLOCKING_STATUS:
            record_failure(f"{endpoint}: HTTP {status}")
        else:
            record_success()
        return response
    guarded.__wrapped__ = send
    return guarded


def install() -> bool:
    """Patch nba_api once per process. False when nba_api is missing."""
    if _state["installed"]:
        return True
    try:
        from nba_api.stats.library.http import NBAStatsHTTP
    except ImportError:
        return False
    NBAStatsHTTP.send_api_request = guard(NBAStatsHTTP.send_api_request)
    _state["installed"] = True
    return True
