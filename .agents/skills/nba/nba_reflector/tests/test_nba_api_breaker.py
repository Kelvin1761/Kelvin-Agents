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
