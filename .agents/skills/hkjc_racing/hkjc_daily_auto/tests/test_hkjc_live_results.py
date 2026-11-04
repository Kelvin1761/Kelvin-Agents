"""即場賽果: fetch each race 5 minutes after its start, retry 1 then 2 minutes apart, give up at 90."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import hkjc_live_results as live  # noqa: E402
import hkjc_daily_schedule as schedule  # noqa: E402

HK = live.HK
START = datetime(2026, 11, 4, 18, 40, tzinfo=HK)


def _meeting(root: Path) -> Path:
    meeting = root / "2026-11-04_HappyValley"
    meeting.mkdir(parents=True)
    for race, clock in ((1, "18:40"), (2, "19:10")):
        (meeting / f"11-04 Race {race} 排位表.md").write_text(
            f"場次: 第{race}場\n日期: 2026-11-04\n時間: {clock}\n", encoding="utf-8")
    return meeting


def _official(race):
    return {"racedate": "2026-11-04", "race_no": race, "venue": "跑馬地", "results": [
        {"pos": str(p), "jockey": f"J{p}", "trainer": "T", "draw": str(p), "running_positions": f"{p} {p}"}
        for p in range(1, 6)]}


def _run(root, now, fetch, deploy):
    with mock.patch.object(live, "HK_RACING", root), mock.patch.object(live, "log"):
        return live.tick(now, fetch=fetch, deploy=deploy)


def test_waits_five_minutes_then_retries_one_then_two_minutes_apart(tmp_path):
    _meeting(tmp_path)
    calls, deploys = [], []
    fetch = lambda day, race, venue: calls.append((race, venue)) or None
    deploy = lambda: deploys.append(1) or 0
    _run(tmp_path, START + timedelta(minutes=4), fetch, deploy)
    assert calls == []                                         # not yet: start + 5
    for minute in range(5, 15):                                # every minute until start + 15
        _run(tmp_path, START + timedelta(minutes=minute), fetch, deploy)
    assert [c for c in calls if c[0] == 1] == [(1, "跑馬地")] * 10
    calls.clear()
    for minute in range(15, 22):                               # then every two minutes: 16, 18, 20
        _run(tmp_path, START + timedelta(minutes=minute), fetch, deploy)
    assert len([c for c in calls if c[0] == 1]) == 3
    assert deploys == []                                       # nothing captured, nothing deployed


def test_capture_writes_live_file_once_and_deploys(tmp_path):
    _meeting(tmp_path)
    deploys = []
    deploy = lambda: deploys.append(1) or 0
    summary = _run(tmp_path, START + timedelta(minutes=6), lambda d, r, v: _official(r), deploy)
    assert summary["captured"] == ["2026-11-04 R1"] and summary["deployed"] and deploys == [1]
    saved = json.loads((tmp_path / "HKJC_Race_Results_Database/_live/2026-11-04.json").read_text())
    assert list(saved) == ["1"] and saved["1"]["results"][0]["jockey"] == "J1"
    # Captured races are never fetched again.
    again = _run(tmp_path, START + timedelta(minutes=8), lambda d, r, v: (_ for _ in ()).throw(AssertionError(r)), deploy)
    assert again["captured"] == [] and deploys == [1]


def test_unofficial_page_is_not_a_result_and_late_races_are_handed_to_postrace(tmp_path):
    _meeting(tmp_path)
    provisional = {"results": [{"pos": "1", "running_positions": ""}]}
    summary = _run(tmp_path, START + timedelta(minutes=5), lambda d, r, v: provisional, lambda: 0)
    assert summary["captured"] == [] and summary["pending"] == ["2026-11-04 R1"]
    late = _run(tmp_path, START + timedelta(minutes=91), lambda d, r, v: None, lambda: 0)
    assert "2026-11-04 R1" in late["gave_up"]
    state = json.loads((tmp_path / "HKJC_Race_Results_Database/_live/2026-11-04.state.json").read_text())
    assert state["1"]["gave_up"]


def test_intraday_shadow_reads_live_capture_instead_of_refetching(tmp_path):
    live_dir = tmp_path / "HKJC_Race_Results_Database" / "_live"
    live_dir.mkdir(parents=True)
    (live_dir / "2026-11-04.json").write_text(json.dumps({"1": _official(1), "2": _official(2), "4": _official(4)}))
    with mock.patch.object(schedule, "HK_RACING", tmp_path):
        prefix = schedule.live_results_prefix(datetime(2026, 11, 4).date())
    assert list(prefix) == ["1", "2"]                          # contiguous from R1 only
