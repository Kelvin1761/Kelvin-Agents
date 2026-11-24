"""手機逐駒分段抓取健康（EXP-20261124-21／-32）：斷咗 11 日就永遠補唔返，所以要喺救得返嘅時候出聲。"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import au_healthcheck as H  # noqa: E402


def _setup(tmp_path, *, day="2026-11-22", races=4, captured=4, state="ok", finished="2026-11-24T04:39:10"):
    meet = tmp_path / f"{day} Kilmore Race 1-{races}"
    meet.mkdir()
    for n in range(1, races + 1):
        (meet / f"Race_{n}_Logic.json").write_text("{}")
    store = tmp_path / "AU_Mobile_Sectionals" / day
    store.mkdir(parents=True)
    for n in range(captured):
        (store / f"{n}.json.gz").write_bytes(b"x")
    status = tmp_path / "fetch.json"
    status.write_text(json.dumps({"state": state, "stop_reason": "AllRacing 2026-11-23: HTTP 403" if state != "ok" else "",
                                  "finished_at": finished}))
    return status


def test_healthy_capture_is_quiet(tmp_path):
    st = _setup(tmp_path)
    assert H.mobile_sectionals_advisories("2026-11-24", root=tmp_path, status_path=st,
                                          now=datetime(2026, 11, 24, 10)) == []


def test_stale_and_stopped_capture_speak_up(tmp_path):
    st = _setup(tmp_path, state="stopped", finished="2026-11-21T04:39:10")
    out = H.mobile_sectionals_advisories("2026-11-24", root=tmp_path, status_path=st, now=datetime(2026, 11, 24, 10))
    assert any("個鐘冇跑過" in x for x in out)
    assert any("停咗" in x and "403" in x for x in out)


def test_incomplete_day_says_how_long_it_can_still_be_recovered(tmp_path):
    st = _setup(tmp_path, captured=1)
    out = H.mobile_sectionals_advisories("2026-11-24", root=tmp_path, status_path=st, now=datetime(2026, 11, 24, 10))
    assert out == ["手機分段 2026-11-22 抓咗 1／4 場（分析場次），大約仲有 9 日可以補"]


def test_missing_status_file_speaks_up(tmp_path):
    _setup(tmp_path)
    out = H.mobile_sectionals_advisories("2026-11-24", root=tmp_path, status_path=tmp_path / "nope.json",
                                         now=datetime(2026, 11, 24, 10))
    assert any("冇狀態檔" in x for x in out)
