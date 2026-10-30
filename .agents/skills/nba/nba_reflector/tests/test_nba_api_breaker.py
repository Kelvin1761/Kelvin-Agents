"""stats.nba.com circuit breaker (2026-10-29).

A blocked IP used to cost 30s per call x ~200 calls per game x 3 workers x 3
retries per slot. After TRIP_AFTER consecutive network failures every caller,
in every process, now fails at once until the marker expires or a call works.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest
import requests

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
import nba_api_breaker as B  # noqa: E402


class _Resp:
    def __init__(self, status):
        self._status_code = status


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("WC_NBA_API_BREAKER_FILE", str(tmp_path / "breaker.json"))
    monkeypatch.setitem(B._state, "consecutive", 0)
    yield


def _timeout(self, endpoint, *a, **k):
    raise requests.exceptions.ReadTimeout("read timeout=30")


def test_trips_after_consecutive_timeouts_and_then_never_calls_out():
    calls = []

    def send(self, endpoint, *a, **k):
        calls.append(endpoint)
        return _timeout(self, endpoint)

    guarded = B.guard(send)
    for _ in range(B.TRIP_AFTER):
        with pytest.raises(requests.exceptions.ReadTimeout):
            guarded(None, "playergamelog", {})
    assert B.blocked_until() is not None
    with pytest.raises(B.StatsNbaBlocked):
        guarded(None, "playergamelog", {})
    assert len(calls) == B.TRIP_AFTER, "an open circuit must not touch the network"


def test_marker_is_shared_with_a_fresh_process():
    guarded = B.guard(_timeout)
    for _ in range(B.TRIP_AFTER):
        with pytest.raises(requests.exceptions.ReadTimeout):
            guarded(None, "x", {})
    B._state["consecutive"] = 0          # a new process starts at zero
    with pytest.raises(B.StatsNbaBlocked):
        B.guard(lambda *a, **k: _Resp(200))(None, "x", {})


def test_403_counts_and_a_success_resets():
    status = {"code": 403}
    guarded = B.guard(lambda self, endpoint, *a, **k: _Resp(status["code"]))
    for _ in range(B.TRIP_AFTER - 1):
        guarded(None, "x", {})
    status["code"] = 200
    guarded(None, "x", {})
    assert B._state["consecutive"] == 0 and B.blocked_until() is None


def test_non_network_errors_do_not_trip():
    def bad(self, endpoint, *a, **k):
        raise ValueError("bad json")
    guarded = B.guard(bad)
    for _ in range(B.TRIP_AFTER + 2):
        with pytest.raises(ValueError):
            guarded(None, "x", {})
    assert B.blocked_until() is None


def test_marker_expires_by_itself(monkeypatch):
    B._trip("test")
    assert B.blocked_until() is not None
    assert B.blocked_until(now=time.time() + B.COOLDOWN_SECONDS + 1) is None


# ── 2026-10-31: request cache and escalating cooldown ──────────────────────

class _Body:
    def __init__(self, text, status=200, url="u"):
        self._response, self._status_code, self._url = text, status, url


CLOSED = {"DateTo": "10/20/2026", "PlayerID": 1}


def _counting(text='{"resultSets": []}', status=200):
    calls = []

    def send(self, endpoint, parameters, *a, **k):
        calls.append((endpoint, dict(parameters)))
        return _Body(text, status)
    return calls, send


def test_closed_window_is_fetched_once_across_processes(tmp_path, monkeypatch):
    monkeypatch.setenv("WC_NBA_HTTP_CACHE_DIR", str(tmp_path / "http"))
    B._memo.clear()
    calls, send = _counting()
    guarded = B.guard(send)
    first = guarded(None, "playergamelog", dict(CLOSED))
    again = guarded(None, endpoint="playergamelog", parameters=dict(CLOSED))
    assert len(calls) == 1 and again._response == first._response
    B._memo.clear()                      # a fresh process reads the disk copy
    guarded(None, "playergamelog", dict(CLOSED))
    assert len(calls) == 1
    guarded(None, "playergamelog", {**CLOSED, "PlayerID": 2})
    assert len(calls) == 2, "different parameters are a different request"


def test_open_or_undated_windows_always_go_to_the_network(tmp_path, monkeypatch):
    monkeypatch.setenv("WC_NBA_HTTP_CACHE_DIR", str(tmp_path / "http"))
    B._memo.clear()
    calls, send = _counting()
    guarded = B.guard(send)
    today = time.strftime("%m/%d/%Y")
    for params in ({"TeamID": 1}, {"DateTo": today}, {"DateTo": ""}):
        guarded(None, "x", dict(params))
        guarded(None, "x", dict(params))
    assert len(calls) == 6


def test_window_closes_at_six_am_eastern_the_next_day():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    before = datetime(2026, 10, 30, 5, 59, tzinfo=et).timestamp()
    after = datetime(2026, 10, 30, 6, 0, tzinfo=et).timestamp()
    assert not B._window_closed("10/29/2026", before)
    assert B._window_closed("10/29/2026", after)


def test_errors_and_non_json_are_never_cached(tmp_path, monkeypatch):
    monkeypatch.setenv("WC_NBA_HTTP_CACHE_DIR", str(tmp_path / "http"))
    for text, status in (('{"a": 1}', 500), ("<html>blocked</html>", 200)):
        B._memo.clear()
        calls, send = _counting(text, status)
        guarded = B.guard(send)
        guarded(None, "x", dict(CLOSED))
        guarded(None, "x", dict(CLOSED))
        assert len(calls) == 2


def test_cached_answer_is_served_while_the_circuit_is_open(tmp_path, monkeypatch):
    monkeypatch.setenv("WC_NBA_HTTP_CACHE_DIR", str(tmp_path / "http"))
    B._memo.clear()
    calls, send = _counting()
    B.guard(send)(None, "x", dict(CLOSED))
    B._trip("test")
    assert B.guard(send)(None, "x", dict(CLOSED))._status_code == 200
    with pytest.raises(B.StatsNbaBlocked):
        B.guard(send)(None, "x", {"TeamID": 1})
    assert len(calls) == 1


def test_cooldown_doubles_while_the_block_persists_and_resets_on_success(monkeypatch):
    clock = {"now": 1_000_000.0}
    monkeypatch.setattr(B.time, "time", lambda: clock["now"])
    cooldowns = []
    for _ in range(6):
        B._trip("blocked")
        marker = B._read_marker()
        cooldowns.append(marker["cooldown_seconds"])
        clock["now"] = marker["until"] + 60      # probe just after it expires
    assert cooldowns == [1800, 3600, 7200, 14400, 21600, 21600]
    B.record_success()
    B._trip("blocked again")
    assert B._read_marker()["cooldown_seconds"] == 1800
