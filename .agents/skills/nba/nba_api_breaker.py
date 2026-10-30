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

2026-10-31, request volume. The block came back and stayed (10-29 21:00 to at
least 10-31) and our own volume is the likeliest trigger: 13 pregame slots a
day, each re-fetching every player's game logs (~9 calls per player, two of
them the same request twice -- L10 and H2H read one PlayerGameLog), with the
history window ending yesterday so every repeat got the same answer. Two
changes, neither alters data:

* A request carrying a ``DateTo`` asks about a closed window, so a 200 for it
  is cached (in-process and on disk) for ``CACHE_TTL_SECONDS`` and replayed
  byte-for-byte. A cached answer is served even while the circuit is open.
* Each trip that follows soon after the previous cooldown ended doubles the
  cooldown (30 min .. ``MAX_COOLDOWN_SECONDS``), so a lasting block is probed
  a few times a day instead of every half hour.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

TRIP_AFTER = 3
COOLDOWN_SECONDS = 30 * 60
MAX_COOLDOWN_SECONDS = 6 * 60 * 60
# A trip within this long after the previous cooldown ended counts as the same
# block continuing, and escalates.
ESCALATE_WITHIN_SECONDS = 3 * 60 * 60
CACHE_TTL_SECONDS = 20 * 60 * 60
BLOCKING_STATUS = {403, 429}

_state = {"consecutive": 0, "installed": False, "failures": 0, "network_calls": 0,
          "cache_hits": 0}
_memo: dict[str, tuple[str, int, str]] = {}


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


def _read_marker() -> dict:
    try:
        data = json.loads(marker_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _trip(reason: str) -> None:
    path = marker_path()
    now = time.time()
    previous = _read_marker()
    level = 0
    try:
        ended = float(previous.get("until") or 0)
        if ended and now - ended <= ESCALATE_WITHIN_SECONDS:
            level = int(previous.get("level") or 0) + 1
    except (TypeError, ValueError):
        level = 0
    cooldown = min(COOLDOWN_SECONDS * (2 ** level), MAX_COOLDOWN_SECONDS)
    payload = {"until": now + cooldown, "tripped_at": now, "level": level,
               "cooldown_seconds": cooldown, "reason": reason[:300]}
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


def failure_count() -> int:
    """Network failures plus short-circuited calls in this process, ever.
    A caller compares it before/after a fetch to tell an outage from a
    genuinely empty answer."""
    return _state["failures"]


def record_failure(reason: str) -> None:
    _state["failures"] += 1
    _state["consecutive"] += 1
    if _state["consecutive"] >= TRIP_AFTER:
        _trip(reason)


def record_success() -> None:
    # An expired marker is kept as the escalation history; a success ends it.
    if _state["consecutive"] or marker_path().exists():
        _clear()


def _is_network_failure(exc: BaseException) -> bool:
    try:
        import requests
        return isinstance(exc, (requests.exceptions.Timeout,
                                requests.exceptions.ConnectionError))
    except ImportError:
        return isinstance(exc, (TimeoutError, ConnectionError))


def cache_root() -> Path:
    override = os.environ.get("WC_NBA_HTTP_CACHE_DIR")
    if override:
        return Path(override)
    return Path.home() / ".cache" / "wongchoi" / "nba_http"


def _window_closed(date_to: str, now: float | None = None) -> bool:
    """True once every game of ``date_to`` (US date) is final and posted.

    West-coast games end around 01:30 ET the next day; by 06:00 ET the box
    scores are on stats.nba.com. Before that a window ending today or tonight
    is still filling in, and caching it would pin the gap for a day.
    """
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    try:
        day = datetime.strptime(str(date_to), "%m/%d/%Y")
    except ValueError:
        return False
    eastern = ZoneInfo("America/New_York")
    closes = (day + timedelta(days=1, hours=6)).replace(tzinfo=eastern)
    current = datetime.fromtimestamp(now if now is not None else time.time(), eastern)
    return current >= closes


def _cache_key(endpoint, parameters) -> str | None:
    """Key for a closed-window request, or None when it must go to the network."""
    if not isinstance(parameters, dict) or not parameters.get("DateTo"):
        return None
    if not _window_closed(parameters["DateTo"]):
        return None
    items = sorted((str(k), "" if v is None else str(v)) for k, v in parameters.items())
    raw = json.dumps([str(endpoint).lower(), items])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cache_get(key: str):
    if key in _memo:
        return _memo[key]
    path = cache_root() / key[:2] / f"{key}.json"
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - float(body["saved_at"]) > CACHE_TTL_SECONDS:
            return None
        hit = (body["contents"], int(body["status"]), body.get("url"))
    except (OSError, ValueError, KeyError, TypeError):
        return None
    _memo[key] = hit
    return hit


def _cache_put(key: str, response) -> None:
    """Keep a 200 whose body is JSON. Never raises: a cache must not break a run."""
    contents = getattr(response, "_response", None)
    if getattr(response, "_status_code", None) != 200 or not isinstance(contents, str):
        return
    try:
        json.loads(contents)
    except ValueError:
        return
    hit = (contents, 200, getattr(response, "_url", None))
    _memo[key] = hit
    path = cache_root() / key[:2] / f"{key}.json"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".tmp{os.getpid()}")
        tmp.write_text(json.dumps({"saved_at": time.time(), "status": 200,
                                   "url": hit[2], "contents": contents}), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass


def _replay(self, hit):
    contents, status, url = hit
    factory = getattr(self, "nba_response", None)
    if factory is None:
        from nba_api.library.http import NBAResponse as factory
    return factory(response=contents, status_code=status, url=url)


def guard(send):
    """Wrap an nba_api ``send_api_request``."""
    def guarded(self, endpoint, *args, **kwargs):
        parameters = args[0] if args else kwargs.get("parameters")
        key = _cache_key(endpoint, parameters)
        hit = _cache_get(key) if key else None
        if hit is not None:
            _state["cache_hits"] += 1
            return _replay(self, hit)
        until = blocked_until()
        if until is not None or _state["consecutive"] >= TRIP_AFTER:
            when = time.strftime("%H:%M", time.localtime(until)) if until else "this run"
            _state["failures"] += 1
            raise StatsNbaBlocked(
                f"stats.nba.com blocked (circuit open until {when}); skipped {endpoint}")
        _state["network_calls"] += 1
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
            if key:
                _cache_put(key, response)
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
