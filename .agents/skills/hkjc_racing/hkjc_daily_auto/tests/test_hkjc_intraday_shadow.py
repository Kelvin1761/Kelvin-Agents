from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path
from unittest import mock


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import hkjc_daily_schedule as schedule  # noqa: E402


def _meeting(root: Path, name: str = "2026-10-07_HappyValley") -> Path:
    meeting = root / name
    meeting.mkdir(parents=True)
    (meeting / "Race_1_Logic.json").write_text(
        '{"horses":{"1":{"python_auto":{"rank":1,"ability_score":70}}}}',
        encoding="utf-8",
    )
    return meeting


def test_intraday_scan_and_venue_windows(tmp_path: Path) -> None:
    hv = _meeting(tmp_path)
    st = _meeting(tmp_path, "2026-10-11_ShaTin")
    old = _meeting(tmp_path, "2026-10-04_ShaTin")
    with mock.patch.object(schedule, "HK_RACING", tmp_path):
        assert schedule.intraday_meeting_dirs(today=date(2026, 10, 7)) == [hv]
        assert set(schedule.intraday_meeting_dirs(today=date(2026, 10, 11))) == {st}
    assert schedule.intraday_window(hv, at=datetime(2026, 10, 7, 18, 14)) is False
    assert schedule.intraday_window(hv, at=datetime(2026, 10, 7, 18, 15)) is True
    assert schedule.intraday_window(hv, at=datetime(2026, 10, 8, 1, 30)) is True
    assert schedule.intraday_window(old, at=datetime(2026, 10, 7, 14, 0)) is False


def test_intraday_is_dormant_without_eligible_meeting(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state = schedule.load_state(state_path)
    with (
        mock.patch.object(schedule, "HK_RACING", tmp_path),
        mock.patch.object(schedule, "run_cmd") as run,
        mock.patch.object(schedule, "log"),
    ):
        assert schedule.run_intraday(
            state,
            state_path,
            at=datetime(2026, 10, 7, 20, 0),
        ) == schedule.EXIT_OK
    run.assert_not_called()
    assert schedule._CONTROL_OUTCOME["status"] == "dormant"


def test_intraday_freezes_shadow_and_notifies_only_new_reverse_risk(tmp_path: Path) -> None:
    meeting = _meeting(tmp_path)
    state_path = tmp_path / "state.json"
    state = schedule.load_state(state_path)

    def fake_run(command: list[str], **_kwargs):
        if Path(command[1]) == schedule.FAST_RESULTS:
            Path(command[3]).write_text(
                json.dumps({"1": {"results": [{"pos": str(i)} for i in range(1, 5)]}}),
                encoding="utf-8",
            )
            return 0, "extracted"
        return 0, json.dumps(
            {
                "status": "snapshot_created",
                "snapshot": str(meeting / "Prediction_Snapshots/Reverse_Bias/example.json"),
                "completed_prefix": [1, 2],
                "reverse_bias_targets": [3, 4],
                "candidate_applied_races": [3, 4],
                "live_score_changed": False,
            }
        )

    with (
        mock.patch.object(schedule, "HK_RACING", tmp_path),
        mock.patch.object(schedule, "run_cmd", side_effect=fake_run) as run,
        mock.patch.object(schedule, "notify") as notify,
        mock.patch.object(schedule, "log"),
    ):
        assert schedule.run_intraday(
            state,
            state_path,
            at=datetime(2026, 10, 7, 20, 0),
        ) == schedule.EXIT_OK

    assert run.call_count == 2
    notify.assert_called_once()
    record = state["meetings"][meeting.name]["reverse_bias_shadow"]
    assert record["candidate_applied_races"] == [3, 4]
    assert record["live_score_changed"] is False
    assert json.loads(state_path.read_text())["meetings"][meeting.name][
        "reverse_bias_shadow"
    ]["status"] == "snapshot_created"


def test_postrace_settles_reverse_bias_into_separate_ledger(tmp_path: Path) -> None:
    meeting = _meeting(tmp_path, "2026-10-04_ShaTin")
    (meeting / "HKJC_Reflection_Report.md").write_text("done", encoding="utf-8")
    state_path = tmp_path / "state.json"
    state = schedule.load_state(state_path)

    def fake_run(command: list[str], **_kwargs):
        if "--ledger" in command:
            ledger = Path(command[command.index("--ledger") + 1])
            ledger.write_text('{"summary":{"active_races":0}}', encoding="utf-8")
        return 0, "{}"

    with (
        mock.patch.object(schedule, "pending_postrace_meetings", return_value=[meeting]),
        mock.patch.object(schedule, "run_cmd", side_effect=fake_run) as run,
        mock.patch.object(schedule, "record_settlement_for_event", return_value={"ok": True}) as settle,
        mock.patch.object(schedule, "mirror_meeting", return_value={"status": "ok"}),
        mock.patch.object(schedule, "store_meeting_results", return_value={"stored": 1}),
        mock.patch.object(schedule, "refresh_dashboard_after_results", return_value=True),
        mock.patch.object(schedule, "notify"),
        mock.patch.object(schedule, "log"),
    ):
        assert schedule.run_postrace(state, state_path) == schedule.EXIT_OK

    reverse_calls = [
        call.args[0]
        for call in run.call_args_list
        if len(call.args[0]) > 1 and Path(call.args[0][1]) == schedule.REVERSE_BIAS_SHADOW
    ]
    assert len(reverse_calls) == 1
    rail_calls = [
        call.args[0]
        for call in run.call_args_list
        if len(call.args[0]) > 1 and Path(call.args[0][1]) == schedule.RAIL_DRAW_REFRESH
    ]
    assert len(rail_calls) == 1
    assert "--settle" in reverse_calls[0]
    reverse_ledger = state_path.parent / schedule.DEFAULT_REVERSE_BIAS_LEDGER_NAME
    assert reverse_ledger in settle.call_args.kwargs["artifacts"]
    assert state["meetings"][meeting.name]["reverse_bias_shadow"]["status"] == "settled"
    assert state["meetings"][meeting.name]["rail_draw_history"]["status"] == "refreshed"
