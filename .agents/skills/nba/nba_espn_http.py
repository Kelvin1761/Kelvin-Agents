"""One polite HTTP path to ESPN, shared across processes.

ESPN became the NBA pipeline's only source after stats.nba.com blocked this
machine (2026-10-29; EXP-20261101-60). The block most likely came from our own
volume -- ~13 pregame runs a day, each re-fetching every
player's game logs. Until 2026-11-01 the ESPN path repeated the pattern: seven
call sites each doing a bare ``requests.get``, ~300 game-log calls per run and
~20 runs a day while a slate kept failing.

Three rules, none of which changes data -- a call returns what ESPN returns:

* **Spacing.** At most one request per ``MIN_INTERVAL_SECONDS`` across every
  process (a file lock holds the last request time), so parallel game workers
  cannot burst.
* **Disk cache for closed answers.** A caller that knows an answer can no
  longer change (a finished day, a finished season) passes ``fresh_after``;
  a cached copy fetched at or after that instant is replayed, also while the
  circuit is open.
* **Circuit.** ``TRIP_AFTER`` consecutive blocking failures (403/429,
  timeouts, connection errors) open it for 30 min, doubling while the block
  continues (to 6 h). While open every call raises ``EspnBlocked`` at once.
  One success closes it.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

MIN_INTERVAL_SECONDS = 0.35
TRIP_AFTER = 3
COOLDOWN_SECONDS = 30 * 60
MAX_COOLDOWN_SECONDS = 6 * 60 * 60
ESCALATE_WITHIN_SECONDS = 3 * 60 * 60
BLOCKING_STATUS = {403, 429}
RETRY_STATUS = {500, 502, 503, 504}

_state = {"network_calls": 0, "cache_hits": 0, "failures": 0, "consecutive": 0}


class EspnBlocked(ConnectionError):
    """ESPN is refusing us; do not call it until the marker expires."""


def cache_root() -> Path:
    override = os.environ.get("WC_NBA_ESPN_HTTP_DIR")
    if override:
        return Path(override)
    return Path.home() / ".cache" / "wongchoi" / "espn_http"


def marker_path() -> Path:
    return cache_root() / "breaker.json"


def _read(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write(path: Path, payload) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".tmp{os.getpid()}")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass   # a cache must not break a run


def blocked_until(now: float | None = None) -> float | None:
    data = _read(marker_path()) or {}
    try:
        until = float(data.get("until") or 0)
    except (TypeError, ValueError):
        return None
    return until if until > (now if now is not None else time.time()) else None


def _trip(reason: str) -> None:
    now = time.time()
    previous = _read(marker_path()) or {}
    level = 0
    try:
        ended = float(previous.get("until") or 0)
        if ended and now - ended <= ESCALATE_WITHIN_SECONDS:
            level = int(previous.get("level") or 0) + 1
    except (TypeError, ValueError):
        level = 0
    cooldown = min(COOLDOWN_SECONDS * (2 ** level), MAX_COOLDOWN_SECONDS)
    _write(marker_path(), {"until": now + cooldown, "tripped_at": now, "level": level,
                           "cooldown_seconds": cooldown, "reason": reason[:300],
                           "blocked_since": previous.get("blocked_since") or now})


def _failure(reason: str) -> None:
    _state["failures"] += 1
    _state["consecutive"] += 1
    if _state["consecutive"] >= TRIP_AFTER:
        _trip(reason)


def _success() -> None:
    _state["consecutive"] = 0
    if marker_path().exists():
        try:
            marker_path().unlink()
        except OSError:
            pass


def _wait_turn() -> None:
    """Hold the cross-process lock until MIN_INTERVAL has passed since the last call."""
    path = cache_root() / "throttle.lock"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a+") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            handle.seek(0)
            try:
                last = float(handle.read().strip() or 0)
            except ValueError:
                last = 0.0
            pause = last + MIN_INTERVAL_SECONDS - time.time()
            if pause > 0:
                time.sleep(pause)
            handle.seek(0)
            handle.truncate()
            handle.write(str(time.time()))
            handle.flush()
    except OSError:
        time.sleep(MIN_INTERVAL_SECONDS)   # no lock file: still never burst


def responses_root() -> Path:
    """Where cached answers live. A historical backfill may point this at the
    external disk (``WC_NBA_ESPN_HTTP_RESPONSES_DIR``; one season of summaries is
    ~650 MB) while spacing and circuit stay shared with every other process."""
    override = os.environ.get("WC_NBA_ESPN_HTTP_RESPONSES_DIR")
    return Path(override) if override else cache_root() / "responses"


def _cache_path(url: str) -> Path:
    return responses_root() / f"{hashlib.sha256(url.encode()).hexdigest()}.json"


def cached(url: str, fresh_after: datetime | None):
    """The cached answer for ``url`` if it was fetched at or after ``fresh_after``."""
    if fresh_after is None:
        return None
    entry = _read(_cache_path(url))
    if not isinstance(entry, dict) or entry.get("url") != url:
        return None
    try:
        fetched = datetime.fromisoformat(entry["fetched_at"])
    except (KeyError, TypeError, ValueError):
        return None
    return entry.get("payload") if fetched >= fresh_after else None


def get_json(url: str, *, get=None, timeout: float = 15, fresh_after: datetime | None = None):
    """GET ``url`` as JSON with spacing, circuit and optional closed-answer cache.

    ``get`` is injected by tests; it bypasses spacing, cache and circuit.
    """
    if get is not None:
        response = get(url, timeout=timeout)
        response.raise_for_status()
        return response.json()
    hit = cached(url, fresh_after)
    if hit is not None:
        _state["cache_hits"] += 1
        return hit
    until = blocked_until()
    if until:
        _state["failures"] += 1
        raise EspnBlocked(f"ESPN blocked (circuit open until "
                          f"{datetime.fromtimestamp(until).strftime('%H:%M')}); skipped {url}")
    import requests
    for attempt in range(3):
        _wait_turn()
        _state["network_calls"] += 1
        try:
            response = requests.get(url, timeout=timeout,
                                    headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        except (requests.Timeout, requests.ConnectionError) as exc:
            _failure(f"{type(exc).__name__}: {url}")
            raise
        if response.status_code in BLOCKING_STATUS:
            _failure(f"HTTP {response.status_code}: {url}")
            response.raise_for_status()
        if response.status_code in RETRY_STATUS and attempt < 2:
            time.sleep(2 ** (attempt + 1))
            continue
        response.raise_for_status()
        payload = response.json()
        _success()
        if fresh_after is not None:
            _write(_cache_path(url), {"url": url, "payload": payload,
                                      "fetched_at": datetime.now(timezone.utc).isoformat()})
        return payload
    response.raise_for_status()   # pragma: no cover - loop always returns or raises


class _Response:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def response_get(url: str, timeout: float = 15):
    """``requests.get``-shaped wrapper for callers that read ``.status_code``/``.json()``."""
    return _Response(get_json(url, timeout=timeout))


def summary() -> str:
    return (f"📡 ESPN: {_state['network_calls']} 次網絡請求，{_state['cache_hits']} 次用 cache"
            + (f"，{_state['failures']} 次失敗" if _state["failures"] else ""))
