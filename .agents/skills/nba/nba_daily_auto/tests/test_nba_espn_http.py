"""ESPN request discipline (2026-11-01).

stats.nba.com most likely blocked us for our own volume; the ESPN path was
repeating it (~300 game-log calls per run, ~20 runs a day while a slate kept
failing). These tests pin the spacing, the circuit and the closed-answer cache.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import requests

NBA_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(NBA_ROOT))
import nba_espn_http as H  # noqa: E402
import nba_espn_snapshots as S  # noqa: E402
import nba_espn_stats as E  # noqa: E402

ET = ZoneInfo("America/New_York")


class Reply:
    def __init__(self, status=200, payload=None):
        self.status_code, self._payload = status, payload if payload is not None else {"ok": 1}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


@pytest.fixture
def net(tmp_path, monkeypatch):
    monkeypatch.setenv("WC_NBA_ESPN_HTTP_DIR", str(tmp_path / "http"))
    monkeypatch.setattr(H, "MIN_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(H.time, "sleep", lambda s: None)
    for key in H._state:
        H._state[key] = 0
    calls, replies = [], []

    def fake_get(url, timeout=None, headers=None):
        calls.append(url)
        return replies.pop(0) if replies else Reply()
    monkeypatch.setattr(requests, "get", fake_get)
    return calls, replies


def test_closed_answer_is_replayed_without_a_request(net):
    calls, _ = net
    closed = datetime.now(timezone.utc) - timedelta(hours=1)
    assert H.get_json("https://espn/x", fresh_after=closed) == {"ok": 1}
    assert H.get_json("https://espn/x", fresh_after=closed) == {"ok": 1}
    assert len(calls) == 1 and H._state["cache_hits"] == 1
    later = datetime.now(timezone.utc) + timedelta(hours=1)   # cached copy predates this
    H.get_json("https://espn/x", fresh_after=later)
    assert len(calls) == 2


def test_open_answers_are_never_cached(net):
    calls, _ = net
    H.get_json("https://espn/y")
    H.get_json("https://espn/y")
    assert len(calls) == 2


def test_three_refusals_open_the_circuit_and_stop_requests(net):
    calls, replies = net
    closed = datetime.now(timezone.utc) - timedelta(hours=1)
    H.get_json("https://espn/kept", fresh_after=closed)
    replies.extend([Reply(403), Reply(429), Reply(403)])
    for _ in range(3):
        with pytest.raises(requests.HTTPError):
            H.get_json("https://espn/z")
    assert H.blocked_until()
    before = len(calls)
    with pytest.raises(H.EspnBlocked):
        H.get_json("https://espn/z")
    assert len(calls) == before, "an open circuit must not touch the network"
    assert H.get_json("https://espn/kept", fresh_after=closed) == {"ok": 1}, "cache still served"


def test_server_errors_retry_then_succeed_and_close_the_circuit(net):
    calls, replies = net
    replies.extend([Reply(503), Reply(200, {"v": 2})])
    assert H.get_json("https://espn/r") == {"v": 2} and len(calls) == 2
    assert H._state["consecutive"] == 0


def test_requests_are_spaced_across_calls(net, monkeypatch):
    pauses = []
    monkeypatch.setattr(H, "MIN_INTERVAL_SECONDS", 5)
    monkeypatch.setattr(H.time, "sleep", pauses.append)
    H.get_json("https://espn/a")
    H.get_json("https://espn/b")
    assert pauses and pauses[-1] > 4, "second call waits for the interval"


def test_gamelog_window_closes_the_morning_after_and_at_season_end():
    now = datetime(2026, 11, 1, 12, tzinfo=ET)
    assert E.gamelog_fresh_after(2026, None, now=now) == datetime(2026, 7, 15, tzinfo=ET)
    assert E.gamelog_fresh_after(2027, date(2026, 10, 30), now=now) == datetime(2026, 10, 31, 6, tzinfo=ET)
    assert E.gamelog_fresh_after(2027, date(2026, 10, 31), now=now) == datetime(2026, 11, 1, 6, tzinfo=ET)
    assert E.gamelog_fresh_after(2027, date(2026, 11, 1), now=now) is None, "today is still open"
    assert E.gamelog_fresh_after(2027, None, now=now) is None


def test_daily_snapshot_is_taken_once_and_records_partial_failures(tmp_path, monkeypatch):
    monkeypatch.setenv("WC_NBA_ESPN_SNAPSHOT_DIR", str(tmp_path))
    teams = [{"team": {"id": str(i), "abbreviation": f"T{i}"}} for i in range(30)]

    def fake(url, timeout=None):
        if url.endswith("/teams"):
            return Reply(payload={"sports": [{"leagues": [{"teams": teams}]}]})
        if url.endswith("/teams/7/depthcharts"):
            return Reply(500)
        return Reply(payload={"url": url})
    now = datetime(2026, 11, 1, 1, tzinfo=timezone.utc)   # 12:00 Sydney
    first = S.take_daily(now=now, get=fake)
    assert first == {"status": "partial", "day": "2026-11-01", "files": 30, "failures": 1}
    manifest = json.loads((tmp_path / "2026-11-01" / "manifest.json").read_text())
    assert manifest["failures"][0]["source"] == "depthchart_T7"
    assert {f["name"] for f in manifest["files"]} >= {"injuries.json", "depthchart_T0.json"}
    assert S.take_daily(now=now, get=fake)["status"] == "already_taken"


def test_daily_snapshot_leaves_no_folder_when_nothing_was_captured(tmp_path, monkeypatch):
    monkeypatch.setenv("WC_NBA_ESPN_SNAPSHOT_DIR", str(tmp_path))
    result = S.take_daily(now=datetime(2026, 11, 1, 1, tzinfo=timezone.utc), get=lambda url, timeout=None: Reply(500))
    assert result["status"] == "failed" and not any(tmp_path.iterdir())
