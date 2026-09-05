"""賽日名單掃描嘅排程層行為。

`run_prerace` 排喺 21:30 / 23:30 / 00:30 / 08:00 / 11:00（悉尼），香港頭場約
15:00 悉尼 —— 開賽前 4 個鐘之後成個賽日冇覆蓋。`run_lineup` 補呢段窗。

三條唔可以破嘅規矩：
  1. 掃唔到 ≠ 名單變咗 —— 一次 timeout 唔可以觸發 7 分鐘全場重跑同假通知
  2. 同一批變動只處理一次 —— 賽日唔可以打圈重跑
  3. 重跑失敗要清走 signature —— 唔可以當處理咗然後永遠唔再試
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

import hkjc_daily_schedule as sched

# `run_lineup` 執行時先將呢個路徑插入 sys.path，所以測試要自己行先一步。
sys.path.insert(0, str(sched.EXTRACTOR_SCRIPTS))
import scan_lineup


@pytest.fixture
def meeting(tmp_path):
    tomorrow = (sched.now_local().date() + timedelta(days=1)).isoformat()
    return {"date": tomorrow, "venue": "ShaTin",
            "url": "https://racing.hkjc.com/zh-hk/local/information/racecard"
                   "?racedate=2026/09/06&Racecourse=ST&RaceNo=1"}


@pytest.fixture
def meeting_dir(tmp_path):
    for race in (1, 2):
        (tmp_path / f"Race_{race}_Logic.json").write_text(
            '{"horses": {"1": {"horse_name": "A"}}}', encoding="utf-8")
    return tmp_path


def _run(state_path, meeting, meeting_dir, scan_results, prerace_code=0,
         verify_reason=""):
    state = {"meetings": {}, "notifications": {}}
    calls = {"notify": [], "prerace": 0}

    def fake_scan(_card_url, logic_path, formguide_url=""):
        return scan_results[int(Path(logic_path).stem.split("_")[1])]

    def fake_prerace(*_a, **_k):
        calls["prerace"] += 1
        return prerace_code

    with (
        mock.patch.object(sched, "meeting_dir_for", return_value=meeting_dir),
        mock.patch.object(sched, "notify", side_effect=lambda m, **k: calls["notify"].append(m)),
        mock.patch.object(sched, "run_prerace", side_effect=fake_prerace),
        mock.patch.object(sched, "save_state"),
        mock.patch.object(sched, "set_control_outcome"),
        mock.patch.object(scan_lineup, "scan_race", side_effect=fake_scan),
        mock.patch.object(scan_lineup, "verify_applied", return_value=verify_reason),
    ):
        code = sched.run_lineup(state, state_path, meeting=meeting)
    return code, calls, state


CLEAN = {"changed": False, "error": "", "scratched": [], "added": [], "replaced": []}
SCRATCHED = {"changed": True, "error": "",
             "scratched": [{"no": 3, "horse": "錶之星河"}], "added": [], "replaced": []}
FETCH_FAILED = {"changed": False, "error": "TimeoutExpired: 60",
                "scratched": [], "added": [], "replaced": []}


def test_no_change_does_not_rerun_or_notify(tmp_path, meeting, meeting_dir):
    code, calls, _ = _run(tmp_path / "s.json", meeting, meeting_dir, {1: CLEAN, 2: CLEAN})
    assert code == sched.EXIT_OK
    assert calls["prerace"] == 0
    assert calls["notify"] == []


def test_a_fetch_failure_does_not_rerun_or_notify(tmp_path, meeting, meeting_dir):
    """呢個係最重要嗰條：HKJC 一 timeout 就重跑全場 = 賽日災難。"""
    code, calls, _ = _run(tmp_path / "s.json", meeting, meeting_dir,
                          {1: FETCH_FAILED, 2: FETCH_FAILED})
    assert code == sched.EXIT_OK
    assert calls["prerace"] == 0, "抓取失敗唔可以觸發重跑"
    assert calls["notify"] == [], "抓取失敗唔可以出假通知"


def test_a_scratching_triggers_one_rerun_and_notifies(tmp_path, meeting, meeting_dir):
    code, calls, state = _run(tmp_path / "s.json", meeting, meeting_dir,
                              {1: SCRATCHED, 2: CLEAN})
    assert code == sched.EXIT_OK
    assert calls["prerace"] == 1
    assert any("出賽名單有變" in m for m in calls["notify"])
    assert any("退出 3 錶之星河" in m for m in calls["notify"])
    key = f"{meeting['date']}|ShaTin"
    assert state["meetings"][key]["last_lineup_signature"]


def test_the_same_change_is_not_rerun_twice(tmp_path, meeting, meeting_dir):
    """賽日唔可以每 30 分鐘重跑同一批變動一次。"""
    state = {"meetings": {}, "notifications": {}}
    calls = {"prerace": 0}

    def fake_scan(_card_url, logic_path, formguide_url=""):
        return SCRATCHED if int(Path(logic_path).stem.split("_")[1]) == 1 else CLEAN

    with (
        mock.patch.object(sched, "meeting_dir_for", return_value=meeting_dir),
        mock.patch.object(sched, "notify"),
        mock.patch.object(sched, "run_prerace",
                          side_effect=lambda *a, **k: calls.__setitem__("prerace", calls["prerace"] + 1) or 0),
        mock.patch.object(sched, "save_state"),
        mock.patch.object(sched, "set_control_outcome"),
        mock.patch.object(scan_lineup, "scan_race", side_effect=fake_scan),
    ):
        sched.run_lineup(state, tmp_path / "s.json", meeting=meeting)
        sched.run_lineup(state, tmp_path / "s.json", meeting=meeting)
    assert calls["prerace"] == 1, "同一批變動只應該重跑一次"


def test_a_failed_rerun_clears_the_signature_so_it_retries(tmp_path, meeting, meeting_dir):
    """重跑失敗唔可以當處理咗 —— 否則個退出馬永遠唔會反映到板上。"""
    _code, _calls, state = _run(tmp_path / "s.json", meeting, meeting_dir,
                                {1: SCRATCHED, 2: CLEAN},
                                prerace_code=sched.EXIT_TEMPORARY)
    key = f"{meeting['date']}|ShaTin"
    assert "last_lineup_signature" not in state["meetings"][key]


def test_a_meeting_that_is_days_away_is_not_scanned(tmp_path, meeting_dir):
    """名單早幾日基本上唔會郁，掃只係嘥 HKJC 請求。"""
    far = {"date": (sched.now_local().date() + timedelta(days=5)).isoformat(),
           "venue": "ShaTin", "url": "https://x?racedate=2026/09/10&Racecourse=ST&RaceNo=1"}
    with (
        mock.patch.object(sched, "meeting_dir_for", return_value=meeting_dir),
        mock.patch.object(sched, "set_control_outcome"),
        mock.patch.object(scan_lineup, "scan_race") as scan_race,
    ):
        code = sched.run_lineup({"meetings": {}}, tmp_path / "s.json", meeting=far)
    assert code == sched.EXIT_OK
    scan_race.assert_not_called()


def test_a_rerun_that_did_not_apply_the_change_escalates(tmp_path, meeting, meeting_dir):
    """`run_prerace` 回 0 唔代表隻退出馬真係走咗。

    2026-09-05 呢個掃描器最初比對排位表，而重建鏈食嘅係賽績 —— 咁樣會次次
    回 0、次次冇改到嘢，而 signature 去重會令佢靜靜收檔，板上一直掛住隻已
    退出嘅馬。所以驗結果失敗一定要：唔標記已處理、大聲嗌、回 FAILED。
    """
    code, calls, state = _run(tmp_path / "s.json", meeting, meeting_dir,
                              {1: SCRATCHED, 2: CLEAN},
                              verify_reason="重跑後仍然喺 Logic 入面：3 錶之星河")
    assert code == sched.EXIT_FAILED
    assert any("冇反映到" in m for m in calls["notify"])
    assert any("3 錶之星河" in m for m in calls["notify"])
    key = f"{meeting['date']}|ShaTin"
    assert "last_lineup_signature" not in state["meetings"][key], \
        "冇反映到就唔可以當處理咗 —— 下次掃描要再試"
    assert state["meetings"][key]["lineup_unapplied_streak"] == 1


def test_the_rerun_uses_the_narrowed_field_change_gate(tmp_path, meeting, meeting_dir):
    """名單變動嘅重跑要用 `field_change` 閘（只鬆 PDF 一格）。

    用 strict 嘅話，一次 PDF 失敗就可以令一隻已退出嘅馬留喺板上 —— 而 PDF
    嘅截止時間必定早過賽事，佢對「今日邊隻馬跑」零資訊。
    """
    seen = {}

    def fake_prerace(*_a, **kw):
        seen.update(kw)
        return 0

    with (
        mock.patch.object(sched, "meeting_dir_for", return_value=meeting_dir),
        mock.patch.object(sched, "notify"),
        mock.patch.object(sched, "run_prerace", side_effect=fake_prerace),
        mock.patch.object(sched, "save_state"),
        mock.patch.object(sched, "set_control_outcome"),
        mock.patch.object(scan_lineup, "scan_race",
                          side_effect=lambda _c, lp, formguide_url="":
                              SCRATCHED if int(Path(lp).stem.split("_")[1]) == 1 else CLEAN),
        mock.patch.object(scan_lineup, "verify_applied", return_value=""),
    ):
        sched.run_lineup({"meetings": {}}, tmp_path / "s.json", meeting=meeting)
    assert seen.get("gate_mode") == "field_change"
    assert seen.get("force") is True


def test_source_disagreement_is_logged_but_does_not_trigger(tmp_path, meeting, meeting_dir):
    """排位表同賽績唔一致值得記低，但唔可以自己觸發重跑。"""
    disagree = dict(CLEAN, source_disagreement="排位表已經冇：3 錶之星河")
    code, calls, _ = _run(tmp_path / "s.json", meeting, meeting_dir,
                          {1: disagree, 2: CLEAN})
    assert code == sched.EXIT_OK
    assert calls["prerace"] == 0
    assert calls["notify"] == []


def test_a_meeting_never_analysed_is_skipped(tmp_path, meeting):
    """冇 Logic 就冇得比對 —— 唔可以當「成場馬退晒」。"""
    empty = tmp_path / "empty"
    empty.mkdir()
    with (
        mock.patch.object(sched, "meeting_dir_for", return_value=empty),
        mock.patch.object(sched, "notify") as notify,
        mock.patch.object(sched, "run_prerace") as prerace,
        mock.patch.object(sched, "set_control_outcome"),
    ):
        code = sched.run_lineup({"meetings": {}}, tmp_path / "s.json", meeting=meeting)
    assert code == sched.EXIT_OK
    prerace.assert_not_called()
    notify.assert_not_called()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
