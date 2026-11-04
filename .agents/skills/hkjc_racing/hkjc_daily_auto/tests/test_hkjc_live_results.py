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


def _run(root, now, fetch, deploy, provisional=lambda day, race, venue, meeting_dir: None):
    with mock.patch.object(live, "HK_RACING", root), mock.patch.object(live, "log"):
        return live.tick(now, fetch=fetch, deploy=deploy, provisional=provisional)


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


# HKJC 2026-11-04 R1 about ten minutes after the race: only the top four, four columns.
PROVISIONAL_HTML = """<table><tr><td>第 1 場 (158)</td></tr><tr><td>第五班 - 1000米 - (40-0)</td><td>場地狀況 :</td><td>好地</td></tr>
<tr><td>加寧讓賽</td><td>賽道 :</td><td>草地 - "A" 賽道</td></tr></table>
<table class="f_tac table_bd"><tr><td>名次</td><td>馬號</td><td>馬名</td><td>騎師</td></tr>
<tr><td>1</td><td>2</td><td>燊輝之星 (L067)</td><td>鍾易禮</td></tr><tr><td>2</td><td>7</td><td>喆喆友福 (J345)</td><td>周俊樂</td></tr>
<tr><td>3</td><td>10</td><td>飈誌 (J504)</td><td>奧爾民</td></tr><tr><td>4</td><td>1</td><td>天下寵兒 (J359)</td><td>袁幸堯</td></tr></table>"""
CARD = {"1": {"horse_name": "天下寵兒", "jockey": "袁幸堯", "trainer": "廖康銘", "barrier": 7},
        "2": {"horse_name": "燊輝之星", "jockey": "鍾易禮", "trainer": "告東尼", "barrier": 3},
        "5": {"horse_name": "第五", "jockey": "潘頓", "trainer": "呂健威", "barrier": 1}}


def test_provisional_top_four_takes_trainer_and_draw_from_the_card():
    rows = live.parse_provisional(PROVISIONAL_HTML, CARD)
    assert [(r["pos"], r["horse_no"], r["jockey"]) for r in rows[:4]] == [
        ("1", "2", "鍾易禮"), ("2", "7", "周俊樂"), ("3", "10", "奧爾民"), ("4", "1", "袁幸堯")]
    assert rows[0]["trainer"] == "告東尼" and rows[0]["draw"] == "3" and rows[1]["trainer"] == ""
    # The rest of the card ran unplaced; no running positions until the full result.
    assert rows[4] == {"pos": "", "horse_no": "5", "horse_name": "第五", "jockey": "潘頓", "trainer": "呂健威",
                       "draw": "1", "running_positions": ""}
    assert live.parse_provisional("<table><tr><td>派彩</td></tr></table>", CARD) is None


def test_provisional_is_shown_at_once_then_replaced_by_the_full_result(tmp_path):
    _meeting(tmp_path)
    deploys = []
    deploy = lambda: deploys.append(1) or 0
    early = {"racedate": "2026-11-04", "race_no": 1, "venue": "跑馬地", "provisional": True,
             "results": [{"pos": str(p), "jockey": f"J{p}", "running_positions": ""} for p in range(1, 5)]}
    first = _run(tmp_path, START + timedelta(minutes=5), lambda d, r, v: None, deploy, lambda d, r, v, m: early)
    assert first["captured"] == ["2026-11-04 R1"] and first["pending"] == ["2026-11-04 R1"] and deploys == [1]
    path = tmp_path / "HKJC_Race_Results_Database/_live/2026-11-04.json"
    assert json.loads(path.read_text())["1"]["provisional"]
    # Still due: keeps asking for the full table, and does not redeploy the same top four.
    again = _run(tmp_path, START + timedelta(minutes=6), lambda d, r, v: None, deploy,
                 lambda d, r, v, m: (_ for _ in ()).throw(AssertionError("refetched provisional")))
    assert again["pending"] == ["2026-11-04 R1"] and deploys == [1]
    # The intraday shadow never sees a provisional race.
    with mock.patch.object(schedule, "HK_RACING", tmp_path):
        assert schedule.live_results_prefix(START.date()) == {}
    full = _run(tmp_path, START + timedelta(minutes=7), lambda d, r, v: _official(r), deploy)
    assert full["captured"] == ["2026-11-04 R1"] and deploys == [1, 1]
    assert "provisional" not in json.loads(path.read_text())["1"]
    state = json.loads((tmp_path / "HKJC_Race_Results_Database/_live/2026-11-04.state.json").read_text())
    assert state["1"]["captured_at"] and state["1"]["provisional_at"]
