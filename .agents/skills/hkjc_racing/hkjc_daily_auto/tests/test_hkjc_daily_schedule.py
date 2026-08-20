from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from unittest import mock


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import hkjc_daily_schedule as schedule  # noqa: E402


def test_discovery_deduplicates_and_ignores_past_meetings() -> None:
    page = """
    <a href="?racedate=2026/08/19&amp;Racecourse=HV&amp;RaceNo=1">past</a>
    <a href="?racedate=2026/09/06&amp;Racecourse=ST&amp;RaceNo=1">next</a>
    <a href="?racedate=2026/09/06&Racecourse=ST&RaceNo=2">duplicate</a>
    <a href="?racedate=2026/09/09&Racecourse=HV&RaceNo=1">later</a>
    """
    meetings = schedule.discover_meetings(page, today=date(2026, 8, 20))
    assert [(row["date"], row["venue"]) for row in meetings] == [
        ("2026-09-06", "ShaTin"),
        ("2026-09-09", "HappyValley"),
    ]


def test_watch_notifies_once(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state = schedule.load_state(state_path)
    meeting = {
        "date": "2026-09-06",
        "venue": "ShaTin",
        "course": "ST",
        "url": "fixture",
    }
    with mock.patch.object(schedule, "notify") as notify:
        assert schedule.run_watch(state, state_path, meeting=meeting) == 0
        assert schedule.run_watch(state, state_path, meeting=meeting) == 0
    notify.assert_called_once()


def test_prediction_snapshot_is_immutable_and_deduplicated(tmp_path: Path) -> None:
    meeting = tmp_path / "2026-09-06_ShaTin"
    meeting.mkdir()
    logic = meeting / "Race_1_Logic.json"
    logic.write_text('{"horses": {}}', encoding="utf-8")
    at = datetime(2026, 9, 5, 8, 0, tzinfo=timezone.utc)
    first = schedule.create_prediction_snapshot(meeting, at=at)
    second = schedule.create_prediction_snapshot(
        meeting, at=datetime(2026, 9, 5, 9, 0, tzinfo=timezone.utc)
    )
    assert second == first
    assert json.loads((first / "manifest.json").read_text())["immutable_prediction_snapshot"] is True

    logic.write_text('{"horses": {"1": {}}}', encoding="utf-8")
    third = schedule.create_prediction_snapshot(
        meeting, at=datetime(2026, 9, 5, 10, 0, tzinfo=timezone.utc)
    )
    assert third != first
    assert (first / "Race_1_Logic.json").read_text() == '{"horses": {}}'


def test_candidate_gate_creates_pr_without_merge(tmp_path: Path) -> None:
    body = tmp_path / "body.md"
    body.write_text("candidate", encoding="utf-8")
    gate = tmp_path / "gate.json"
    gate.write_text(
        json.dumps(
            {
                "status": "passed",
                "branch": "codex/hkjc-candidate",
                "title": "HKJC candidate",
                "body_file": str(body),
                "performance_summary": "paired improvement",
            }
        ),
        encoding="utf-8",
    )
    with mock.patch.object(
        schedule,
        "run_cmd",
        return_value=(0, "https://github.com/example/repo/pull/123"),
    ) as run:
        status, url = schedule.process_candidate_gate(gate)
    assert status == "created"
    assert url and url.endswith("/123")
    command = run.call_args.args[0]
    assert command[:3] == ["gh", "pr", "create"]
    assert "merge" not in command
    persisted = json.loads(gate.read_text())
    assert persisted["merge_requires_user_approval"] is True


def test_candidate_gate_does_nothing_without_explicit_pass(tmp_path: Path) -> None:
    gate = tmp_path / "gate.json"
    gate.write_text('{"status":"continue_observing"}', encoding="utf-8")
    with mock.patch.object(schedule, "run_cmd") as run:
        status, url = schedule.process_candidate_gate(gate)
    assert (status, url) == ("continue_observing", None)
    run.assert_not_called()


def test_pending_postrace_excludes_current_day_and_completed(tmp_path: Path) -> None:
    pending = tmp_path / "2026-09-06_ShaTin"
    pending.mkdir()
    (pending / "Race_1_Logic.json").write_text("{}", encoding="utf-8")
    complete = tmp_path / "2026-09-09_HappyValley"
    complete.mkdir()
    (complete / "Race_1_Logic.json").write_text("{}", encoding="utf-8")
    (complete / "HKJC_Reflection_Report.md").write_text("done", encoding="utf-8")
    current = tmp_path / "2026-09-13_ShaTin"
    current.mkdir()
    (current / "Race_1_Logic.json").write_text("{}", encoding="utf-8")
    with mock.patch.object(schedule, "HK_RACING", tmp_path):
        assert schedule.pending_postrace_meetings(today=date(2026, 9, 13)) == [pending]


def test_local_primary_meeting_is_mirrored_best_effort(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    mirror = tmp_path / "mirror"
    meeting = primary / "2026-09-06_ShaTin"
    meeting.mkdir(parents=True)
    (meeting / "Data_Health.json").write_text('{"status":"ok"}', encoding="utf-8")
    with (
        mock.patch.object(schedule, "HK_RACING", primary),
        mock.patch.object(schedule, "HK_RACING_MIRROR", mirror),
    ):
        result = schedule.mirror_meeting(meeting)
    assert result == {"status": "ok", "copied": 1, "failed": 0}
    assert (mirror / meeting.name / "Data_Health.json").read_text() == '{"status":"ok"}'


def test_log_is_redirectable_for_tests(tmp_path: Path) -> None:
    with mock.patch.dict(os.environ, {"WC_HKJC_SCHED_LOG_DIR": str(tmp_path)}):
        schedule.log("fixture")
    assert "fixture" in (tmp_path / "hkjc_daily_schedule.log").read_text()
