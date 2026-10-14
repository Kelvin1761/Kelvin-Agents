"""賠率快照接入排程：失敗要睇得見，但**唔可以**拖冧預測 pipeline。"""
from __future__ import annotations

import fnmatch
import os
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

import hkjc_daily_schedule as sched  # noqa: E402

MEETING = {"date": "2026-10-14", "venue": "HappyValley", "course": "HV",
           "url": "https://racing.hkjc.com/x?racedate=2026/10/14&Racecourse=HV&RaceNo=1"}
KEY = "2026-10-14|HappyValley"


def _run(state, tmp_path, capture, label="prerace"):
    with (
        mock.patch.dict(os.environ, {"WC_HKJC_SCHED_LOG_DIR": str(tmp_path)}),
        mock.patch.object(sched, "notify") as notify,
    ):
        result = sched.capture_prerace_odds(state, tmp_path / "s.json", MEETING,
                                            tmp_path, label, capture=capture)
    return result, notify


def _ok(*_a, **_k):
    return {"status": "ok", "races": 9, "runners": 101, "pre_race_races": 9}


def _boom(*_a, **_k):
    raise RuntimeError("WHITELIST_ERROR")


def test_failure_is_swallowed_recorded_and_alerted(tmp_path):
    state = {"meetings": {}}
    result, notify = _run(state, tmp_path, _boom)
    assert result["status"] == "error" and "WHITELIST_ERROR" in result["error"]
    odds = state["meetings"][KEY]["odds_capture"]
    assert odds["failure_streak"] == 1 and "WHITELIST_ERROR" in odds["last_error"]
    notify.assert_called_once()
    assert "賠率" in notify.call_args.args[0]


def test_repeated_failures_alert_on_first_and_every_sixth_only(tmp_path):
    state = {"meetings": {}}
    alerts = 0
    for _ in range(7):
        _, notify = _run(state, tmp_path, _boom)
        alerts += notify.call_count
    assert state["meetings"][KEY]["odds_capture"]["failure_streak"] == 7
    assert alerts == 2   # 第 1 次 + 第 6 次


def test_recovery_resets_the_streak_and_says_so(tmp_path):
    state = {"meetings": {}}
    _run(state, tmp_path, _boom)
    _, notify = _run(state, tmp_path, _ok)
    odds = state["meetings"][KEY]["odds_capture"]
    assert odds["failure_streak"] == 0 and odds["snapshots"] == 1
    assert "恢復" in notify.call_args.args[0]


def test_success_is_quiet(tmp_path):
    state = {"meetings": {}}
    _, notify = _run(state, tmp_path, _ok)
    notify.assert_not_called()
    assert state["meetings"][KEY]["odds_capture"]["last_status"] == "ok"


def test_pools_not_open_is_not_a_failure(tmp_path):
    state = {"meetings": {}}
    _, notify = _run(state, tmp_path, lambda *a, **k: {"status": "not_open"})
    notify.assert_not_called()
    assert state["meetings"][KEY]["odds_capture"]["failure_streak"] == 0


def test_kill_switch_makes_no_call(tmp_path):
    with mock.patch.dict(os.environ, {"WC_HKJC_ODDS_CAPTURE": "0",
                                      "WC_HKJC_SCHED_LOG_DIR": str(tmp_path)}):
        got = sched.capture_prerace_odds({"meetings": {}}, tmp_path / "s.json",
                                         MEETING, tmp_path, "prerace")
    assert got == {"status": "disabled"}


def test_a_broken_capture_does_not_change_the_prerace_exit_code(tmp_path):
    """真 wrapper + 一個會炸嘅抓取模組：run_prerace 照樣回 pipeline 自己個 code。"""
    fake = types.ModuleType("hkjc_odds_capture")
    fake.capture_meeting = _boom
    state_path = tmp_path / "state.json"
    state = sched.load_state(state_path)
    order: list[str] = []

    def run(cmd, **_k):
        order.append("pipeline")
        return 75, "formguide not ready"

    with (
        mock.patch.dict(sys.modules, {"hkjc_odds_capture": fake}),
        mock.patch.dict(os.environ, {"WC_HKJC_ODDS_CAPTURE": "1",
                                     "WC_HKJC_SCHED_LOG_DIR": str(tmp_path)}),
        mock.patch.object(sched, "HK_RACING", tmp_path),
        mock.patch.object(sched, "now_local",
                          return_value=datetime(2026, 10, 14, 1, 0, tzinfo=timezone.utc)),
        mock.patch.object(sched, "run_cmd", side_effect=run),
        mock.patch.object(sched, "notify") as notify,
    ):
        code = sched.run_prerace(state, state_path, meeting=MEETING)
    assert code == 75, "賠率失敗唔可以改變 pipeline 個 exit code"
    assert order == ["pipeline"], "pipeline 一定照行"
    assert state["meetings"][KEY]["odds_capture"]["failure_streak"] == 1
    assert state["meetings"][KEY]["failure_streak"] == 1
    assert notify.call_count == 2   # pipeline 未齊 + 賠率失敗，各一


def test_prerace_captures_before_the_pipeline(tmp_path):
    order: list[str] = []
    with (
        mock.patch.dict(os.environ, {"WC_HKJC_SCHED_LOG_DIR": str(tmp_path)}),
        mock.patch.object(sched, "HK_RACING", tmp_path),
        mock.patch.object(sched, "now_local",
                          return_value=datetime(2026, 10, 14, 1, 0, tzinfo=timezone.utc)),
        mock.patch.object(sched, "capture_prerace_odds",
                          side_effect=lambda *a, **k: order.append(f"odds:{a[4]}")),
        mock.patch.object(sched, "run_cmd",
                          side_effect=lambda *a, **k: (order.append("pipeline"), (1, "x"))[1]),
        mock.patch.object(sched, "notify"),
    ):
        sched.run_prerace({"meetings": {}}, tmp_path / "s.json", meeting=MEETING)
    assert order == ["odds:prerace", "pipeline"]


def test_lineup_captures_even_before_any_logic_exists(tmp_path):
    meeting_dir = tmp_path / "2026-10-14_HappyValley"
    meeting_dir.mkdir()
    labels: list[str] = []
    with (
        mock.patch.dict(os.environ, {"WC_HKJC_SCHED_LOG_DIR": str(tmp_path)}),
        mock.patch.object(sched, "meeting_dir_for", return_value=meeting_dir),
        mock.patch.object(sched, "now_local",
                          return_value=datetime(2026, 10, 14, 1, 0, tzinfo=timezone.utc)),
        mock.patch.object(sched, "capture_prerace_odds",
                          side_effect=lambda *a, **k: labels.append(a[4])),
        mock.patch.object(sched, "set_control_outcome"),
    ):
        code = sched.run_lineup({"meetings": {}}, tmp_path / "s.json", meeting=MEETING)
    assert code == 0
    assert labels == ["lineup"]


def test_odds_history_is_not_part_of_the_prediction_snapshot():
    """入咗 SNAPSHOT_PATTERNS 會令每次影賠率都變一個新 prediction snapshot
    （signature 變）同一個新 Telegram —— 仲會將賠率帶入預測證據。"""
    name = "HKJC_Odds_History.json"
    assert not any(fnmatch.fnmatch(name, pat) for pat in sched.SNAPSHOT_PATTERNS)
