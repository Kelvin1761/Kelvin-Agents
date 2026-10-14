"""SpeedPro 收集駁咗入排程，而且**永遠唔會擋賽前流程**。

HKJC 只喺 `current/` 公布 SpeedPro、冇歷史檔，所以每個場次都要喺前一晚同
賽日早上至少抓一次。但佢只係資料收集：抓唔到、吊死、甚至 import 爆，
prerace 都要照行。呢度鎖住三樣嘢：
  1. prerace 同 lineup 都會叫（lineup 喺「未分析過」嘅 early return 之前）；
  2. 收集器任何失敗形狀都唔會 raise，pipeline 照樣行；
  3. 只有賽日連續失敗、一份都未存過，先會嗌一次（係警告唔係錯誤）。
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import hkjc_daily_schedule as sched  # noqa: E402

MEETING = {"date": "2026-10-14", "venue": "HappyValley", "course": "HV", "url": "fixture"}
RACE_DAY = datetime(2026, 10, 14, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def live(monkeypatch, tmp_path):
    monkeypatch.delenv("WC_HKJC_SPEEDPRO_DISABLE", raising=False)
    monkeypatch.setenv("WC_HKJC_SCHED_LOG_DIR", str(tmp_path))
    monkeypatch.setattr(sched, "SPEEDPRO_MIN_INTERVAL", 0)
    monkeypatch.setattr(sched, "now_local", lambda: RACE_DAY)
    return tmp_path


def _completed(code: int, out: str = "", err: str = ""):
    return subprocess.CompletedProcess(args=[], returncode=code, stdout=out, stderr=err)


def test_collector_script_path_exists() -> None:
    assert sched.SPEEDPRO_COLLECTOR.is_file()


def test_saved_snapshot_is_recorded(live) -> None:
    state = {"meetings": {}}
    out = json.dumps({"status": "saved", "snapshot": "/x/2026-10-14_HV/20261014T000000Z"})
    with mock.patch.object(sched.subprocess, "run", return_value=_completed(0, out)) as run:
        status = sched.collect_speedpro_best_effort(state, live / "s.json", MEETING)
    assert status == "saved"
    cmd = run.call_args.args[0]
    assert cmd[cmd.index("--date") + 1] == "2026-10-14"
    assert cmd[cmd.index("--course") + 1] == "HV"
    assert run.call_args.kwargs["timeout"] == sched.SPEEDPRO_TIMEOUT
    info = state["meetings"]["2026-10-14|HappyValley"]["speedpro"]
    assert info["last_status"] == "saved" and info["versions"] == 1


@pytest.mark.parametrize("effect", [
    _completed(3, err="SpeedPro NOT_CURRENT: current/ 而家係 2026-10-11"),
    _completed(1, err="Traceback ... ImportError: requests"),
    subprocess.TimeoutExpired(cmd="x", timeout=300),
    OSError("python vanished"),
])
def test_every_failure_shape_is_swallowed(live, effect) -> None:
    state = {"meetings": {}}
    kwargs = {"side_effect": effect} if isinstance(effect, BaseException) else {
        "return_value": effect}
    with mock.patch.object(sched.subprocess, "run", **kwargs):
        status = sched.collect_speedpro_best_effort(state, live / "s.json", MEETING)
    assert status in {"not_current", "failed"}


def test_prerace_still_runs_pipeline_when_speedpro_fails(live) -> None:
    calls = []

    def run_cmd(cmd, **_kw):
        calls.append(cmd)
        return 75, "formguide not ready"

    state_path = live / "state.json"
    state = sched.load_state(state_path)
    with (
        mock.patch.object(sched, "HK_RACING", live),
        mock.patch.object(sched.subprocess, "run", side_effect=OSError("boom")) as sp_run,
        mock.patch.object(sched, "run_cmd", side_effect=run_cmd),
        mock.patch.object(sched, "notify"),
    ):
        code = sched.run_prerace(state, state_path, meeting=MEETING)
    assert sp_run.called                       # 有試過抓 SpeedPro
    assert code == sched.EXIT_TEMPORARY        # 結果完全由 pipeline 決定
    assert any(str(sched.HKJC_ORCHESTRATOR) in map(str, c) for c in calls)


def test_prerace_can_skip_speedpro_for_lineup_reruns(live) -> None:
    state_path = live / "state.json"
    state = sched.load_state(state_path)
    with (
        mock.patch.object(sched, "HK_RACING", live),
        mock.patch.object(sched, "collect_speedpro_best_effort") as collect,
        mock.patch.object(sched, "run_cmd", return_value=(75, "x")),
        mock.patch.object(sched, "notify"),
    ):
        sched.run_prerace(state, state_path, meeting=MEETING, collect_speedpro=False)
    collect.assert_not_called()


def test_lineup_collects_even_before_the_meeting_is_analysed(live) -> None:
    meeting_dir = live / "2026-10-14_HappyValley"
    meeting_dir.mkdir()
    with (
        mock.patch.object(sched, "meeting_dir_for", return_value=meeting_dir),
        mock.patch.object(sched, "collect_speedpro_best_effort") as collect,
        mock.patch.object(sched, "set_control_outcome"),
    ):
        assert sched.run_lineup({"meetings": {}}, live / "s.json", meeting=MEETING) == 0
    collect.assert_called_once()


def test_throttle_limits_repeat_requests(live, monkeypatch) -> None:
    monkeypatch.setattr(sched, "SPEEDPRO_MIN_INTERVAL", 3000)
    state = {"meetings": {}}
    out = json.dumps({"status": "duplicate", "snapshot": "/x"})
    with mock.patch.object(sched.subprocess, "run", return_value=_completed(0, out)) as run:
        assert sched.collect_speedpro_best_effort(state, live / "s.json", MEETING) == "duplicate"
        assert sched.collect_speedpro_best_effort(state, live / "s.json", MEETING) == "throttled"
    assert run.call_count == 1


def test_warns_once_only_after_repeated_race_day_failures(live) -> None:
    state = {"meetings": {}}
    with (
        mock.patch.object(sched.subprocess, "run", return_value=_completed(1, err="HTTP 500")),
        mock.patch.object(sched, "notify") as notify,
    ):
        for _ in range(sched.SPEEDPRO_WARN_AFTER + 3):
            sched.collect_speedpro_best_effort(state, live / "s.json", MEETING)
    notify.assert_called_once()
    assert "SpeedPro" in notify.call_args.args[0]


def test_no_warning_once_a_snapshot_exists(live) -> None:
    state = {"meetings": {"2026-10-14|HappyValley": {"speedpro": {"last_success": "earlier"}}}}
    with (
        mock.patch.object(sched.subprocess, "run", return_value=_completed(1, err="HTTP 500")),
        mock.patch.object(sched, "notify") as notify,
    ):
        for _ in range(sched.SPEEDPRO_WARN_AFTER + 2):
            sched.collect_speedpro_best_effort(state, live / "s.json", MEETING)
    notify.assert_not_called()


def test_disabled_by_default_in_tests(monkeypatch, tmp_path) -> None:
    # conftest 嘅預設防線：冇明確 delenv 就唔會打 HKJC
    with mock.patch.object(sched.subprocess, "run") as run:
        assert sched.collect_speedpro_best_effort(
            {"meetings": {}}, tmp_path / "s.json", MEETING) == "disabled"
    run.assert_not_called()
