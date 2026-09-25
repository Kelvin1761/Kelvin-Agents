from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import pytest


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import hkjc_daily_schedule as schedule  # noqa: E402


EVENT = "2026-09-19|ShaTin"


def _prediction_meeting(tmp_path: Path) -> Path:
    folder = tmp_path / "2026-09-19_ShaTin"
    folder.mkdir()
    (folder / "09-19 Race 1 Facts.md").write_text(
        "# Facts\nHorse 7 Fast Horse\nlast_6_finishes: 1,2,3\n", encoding="utf-8"
    )
    (folder / "09-19 Race 1 排位表.md").write_text(
        "# Racecard\nHorse 7 barrier 3\n", encoding="utf-8"
    )
    (folder / "2026-09-19 Race 1 晨操.json").write_text(
        json.dumps({"7": {"digest": "positive"}}) + "\n", encoding="utf-8"
    )
    (folder / "Race_1_Logic.json").write_text(
        json.dumps({
            "race_analysis": {"race_number": 1},
            "horses": {"7": {"horse_name": "Fast Horse", "python_auto": {
                "score_provenance": {
                    "form_score": "last_6_finishes",
                    "draw_score": "barrier",
                    "trackwork_trend_score": "trackwork_digest",
                },
            }}},
        }) + "\n",
        encoding="utf-8",
    )
    (folder / "Race_1_Auto_Analysis.md").write_text("# Analysis\n", encoding="utf-8")
    (folder / "Race_1_Auto_Scoring.csv").write_text(
        "race_number,rank,horse_number,horse_name,grade\n1,1,7,Fast Horse,B+\n",
        encoding="utf-8",
    )
    (folder / "HKJC_Auto_Scoring.csv").write_text(
        "race_number,rank,horse_number,horse_name,grade\n1,1,7,Fast Horse,B+\n",
        encoding="utf-8",
    )
    return folder


def test_prediction_adapter_hash_pins_inputs_projection_and_cutoff(tmp_path: Path) -> None:
    folder = _prediction_meeting(tmp_path)
    cutoff = datetime(2026, 9, 18, 13, 30, tzinfo=timezone.utc)

    snapshot, recommendations = schedule.create_stage5_prediction_snapshot(
        folder, event_id=EVENT, at=cutoff,
    )

    assert snapshot.parent.name == "_prediction_snapshots"
    manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    names = {item["name"] for item in manifest["files"]}
    assert {
        "09-19 Race 1 Facts.md",
        "09-19 Race 1 排位表.md",
        "2026-09-19 Race 1 晨操.json",
        "Race_1_Logic.json",
        "Race_1_Auto_Scoring.csv",
        "HKJC_Auto_Scoring.csv",
        "HKJC_Research_Feature_Provenance.json",
    }.issubset(names)
    projection = json.loads(
        (snapshot / "HKJC_Research_Feature_Provenance.json").read_text(encoding="utf-8")
    )
    assert projection["model_promotion_allowed"] is False
    assert datetime.fromisoformat(projection["captured_at"]) == cutoff
    assert datetime.fromisoformat(manifest["created_at"]) == cutoff
    assert recommendations == manifest["recommendations"]
    assert any(item["selection_id"] == "7" for item in recommendations)


def test_prediction_adapter_fails_closed_when_feature_input_is_missing(tmp_path: Path) -> None:
    folder = _prediction_meeting(tmp_path)
    (folder / "2026-09-19 Race 1 晨操.json").unlink()

    with pytest.raises(ValueError, match="Trackwork"):
        schedule.create_stage5_prediction_snapshot(
            folder,
            event_id=EVENT,
            at=datetime(2026, 9, 18, 13, 30, tzinfo=timezone.utc),
        )
    assert not (folder / "_prediction_snapshots").exists()


def test_prediction_adapter_reports_all_missing_trackwork_races_numerically(
    tmp_path: Path,
) -> None:
    folder = _prediction_meeting(tmp_path)
    for race in range(2, 12):
        (folder / f"09-19 Race {race} Facts.md").write_text("# Facts\n", encoding="utf-8")
        (folder / f"09-19 Race {race} 排位表.md").write_text("# Racecard\n", encoding="utf-8")
        (folder / f"Race_{race}_Logic.json").write_text(
            json.dumps({
                "race_analysis": {"race_number": race},
                "horses": {"7": {"horse_name": "Fast Horse", "python_auto": {
                    "score_provenance": {
                        "form_score": "last_6_finishes",
                        "draw_score": "barrier",
                        "trackwork_trend_score": "trackwork_digest",
                    },
                }}},
            }) + "\n",
            encoding="utf-8",
        )
    for race in (1, 2):
        path = folder / f"2026-09-19 Race {race} 晨操.json"
        path.write_text('{}\n', encoding="utf-8")

    with pytest.raises(ValueError) as raised:
        schedule.create_stage5_prediction_snapshot(
            folder,
            event_id=EVENT,
            at=datetime(2026, 9, 18, 13, 30, tzinfo=timezone.utc),
        )
    message = str(raised.value)
    assert "Trackwork R3-R11" in message
    assert "Race 10" not in message


def test_prediction_adapter_requires_canonical_meeting_scoring(tmp_path: Path) -> None:
    folder = _prediction_meeting(tmp_path)
    (folder / "HKJC_Auto_Scoring.csv").unlink()

    with pytest.raises(ValueError, match="canonical HKJC scoring"):
        schedule.create_stage5_prediction_snapshot(
            folder,
            event_id=EVENT,
            at=datetime(2026, 9, 18, 13, 30, tzinfo=timezone.utc),
        )
    assert not (folder / "_prediction_snapshots").exists()


def test_prerace_blocks_dashboard_when_stage5_snapshot_fails(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state = schedule.load_state(state_path)
    meeting_day = schedule.now_local().date().isoformat()
    meeting = {
        "date": meeting_day,
        "venue": "ShaTin",
        "course": "ST",
        "url": "fixture",
    }
    meeting_dir = tmp_path / f"{meeting_day}_ShaTin"
    meeting_dir.mkdir()
    commands: list[list[str]] = []

    def run(command, **_kwargs):
        commands.append(command)
        return 0, "scored"

    with (
        mock.patch.dict(os.environ, {"WC_HKJC_SCHED_LOG_DIR": str(tmp_path / "logs")}),
        mock.patch.object(schedule, "meeting_dir_for", return_value=meeting_dir),
        mock.patch.object(
            schedule,
            "create_stage5_prediction_snapshot",
            side_effect=ValueError("missing HKJC Trackwork input for Race 1"),
        ),
        mock.patch.object(schedule, "run_cmd", side_effect=run),
        mock.patch.object(schedule, "record_prediction_decision_if_configured") as record,
        mock.patch.object(schedule, "notify"),
    ):
        assert schedule.run_prerace(
            state, state_path, meeting=meeting, force=True,
        ) == schedule.EXIT_FAILED
    record.assert_not_called()
    assert [str(schedule.DASHBOARD_DEPLOY)] not in commands


def _settled_meeting(tmp_path: Path, *, include_result: bool = True) -> tuple[Path, Path | None, Path]:
    folder = tmp_path / "2026-09-18_ShaTin"
    folder.mkdir()
    result = folder / "2026-09-18_ShaTin_全日賽果.json"
    if include_result:
        result.write_text('{"1":{"results":[]}}\n', encoding="utf-8")
    report = folder / "HKJC_Reflection_Report.md"
    report.write_text("# Reflection\n", encoding="utf-8")
    return folder, result if include_result else None, report


def test_settlement_adapter_pins_full_results_and_reflector(tmp_path: Path) -> None:
    folder, result, report = _settled_meeting(tmp_path)
    state_path = tmp_path / "state.json"
    state = schedule.load_state(state_path)
    with (
        mock.patch.dict(os.environ, {"WC_HKJC_SCHED_LOG_DIR": str(tmp_path / "logs")}),
        mock.patch.object(schedule, "pending_postrace_meetings", return_value=[folder]),
        mock.patch.object(schedule, "run_cmd", return_value=(0, "reflected")),
        mock.patch.object(
            schedule,
            "record_settlement_for_event",
            return_value={"status": "appended", "settlement_id": "settlement"},
        ) as record,
        mock.patch.object(schedule, "mirror_meeting", return_value={"status": "ok"}),
        mock.patch.object(schedule, "store_meeting_results", return_value={"stored": 1}),
        mock.patch.object(schedule, "refresh_dashboard_after_results", return_value=True),
        mock.patch.object(schedule, "notify"),
    ):
        assert schedule.run_postrace(state, state_path) == schedule.EXIT_OK
    assert record.call_args.kwargs["artifacts"] == [result, report]


def test_settlement_adapter_blocks_missing_full_results(tmp_path: Path) -> None:
    folder, _result, _report = _settled_meeting(tmp_path, include_result=False)
    state_path = tmp_path / "state.json"
    state = schedule.load_state(state_path)
    with (
        mock.patch.dict(os.environ, {"WC_HKJC_SCHED_LOG_DIR": str(tmp_path / "logs")}),
        mock.patch.object(schedule, "pending_postrace_meetings", return_value=[folder]),
        mock.patch.object(schedule, "run_cmd", return_value=(0, "reflected")),
        mock.patch.object(
            schedule,
            "record_settlement_for_event",
            return_value={"status": "appended", "settlement_id": "settlement"},
        ) as record,
        mock.patch.object(schedule, "mirror_meeting", return_value={"status": "ok"}),
        mock.patch.object(schedule, "store_meeting_results", return_value={"stored": 1}),
        mock.patch.object(schedule, "refresh_dashboard_after_results") as refresh,
    ):
        assert schedule.run_postrace(state, state_path) == schedule.EXIT_TEMPORARY
    record.assert_not_called()
    refresh.assert_not_called()
