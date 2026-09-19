from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import au_daily_schedule as schedule  # noqa: E402


EVENT = "2026-09-19 Test Race 1-1"


def _runlog(tmp_path: Path) -> schedule.RunLog:
    return schedule.RunLog("test", date(2026, 9, 19), tmp_path / "run.json", notify=False)


def _prediction_meeting(tmp_path: Path, *, with_analysis_odds: bool = True) -> Path:
    folder = tmp_path / EVENT
    folder.mkdir()
    for kind in ("Racecard", "Formguide", "Facts"):
        (folder / f"09-19 Race 1 {kind}.md").write_text(
            f"# Race 1 {kind}\nHorse 7 Fast Horse\n", encoding="utf-8"
        )
    (folder / "Race_1_Logic.json").write_text(
        json.dumps({
            "race_analysis": {"race_number": 1},
            "horses": {"7": {"horse_name": "Fast Horse", "python_auto": {
                "score_provenance": {"form_score": "recent_form+class_weighted"},
            }}},
        }) + "\n",
        encoding="utf-8",
    )
    (folder / "Race_1_Auto_Analysis.md").write_text("# Analysis\n", encoding="utf-8")
    (folder / "Race_1_Auto_Scoring.csv").write_text(
        "race_number,rank,horse_number,horse_name,grade\n1,1,7,Fast Horse,B+\n",
        encoding="utf-8",
    )
    (folder / "Meeting_Auto_Scoring.csv").write_text(
        "race_number,rank,horse_number,horse_name,grade\n1,1,7,Fast Horse,B+\n",
        encoding="utf-8",
    )
    odds = {
        "1": {
            "2026-09-18T23:50:00+10:00|morning-refresh": {"7": ["3.0", "1.5"]},
        }
    }
    if with_analysis_odds:
        odds["1"]["2026-09-18T22:00:00+10:00|analysis"] = {"7": ["4.2", "1.9"]}
    (folder / "odds_history.json").write_text(json.dumps(odds) + "\n", encoding="utf-8")
    return folder


def test_prediction_adapter_hash_pins_inputs_projection_and_analysis_odds(
    tmp_path: Path, monkeypatch,
) -> None:
    folder = _prediction_meeting(tmp_path)
    monkeypatch.setenv("WC_AU_SCHED_LOG_DIR", str(tmp_path / "logs"))
    with (
        mock.patch.object(schedule, "scoring_recommendations", return_value=[]),
        mock.patch.object(
            schedule,
            "record_prediction_decision_if_configured",
            return_value={"status": "appended", "prediction_id": "prediction"},
        ),
    ):
        assert schedule.step_prediction_evidence(_runlog(tmp_path), [folder]) is True

    snapshots = list((folder / "_prediction_snapshots").glob("*/manifest.json"))
    assert len(snapshots) == 1
    manifest = json.loads(snapshots[0].read_text(encoding="utf-8"))
    names = {item["name"] for item in manifest["files"]}
    assert {
        "09-19 Race 1 Racecard.md",
        "09-19 Race 1 Formguide.md",
        "09-19 Race 1 Facts.md",
        "Race_1_Logic.json",
        "odds_history.json",
        "AU_Research_Feature_Provenance.json",
    }.issubset(names)
    projection = json.loads(
        (snapshots[0].parent / "AU_Research_Feature_Provenance.json").read_text(
            encoding="utf-8"
        )
    )
    assert projection["market"]["status"] == "complete"
    assert projection["market"]["earliest_analysis"]["1"]["prices"] == {
        "7": ["4.2", "1.9"]
    }
    assert datetime.fromisoformat(projection["captured_at"]).astimezone(timezone.utc) == (
        datetime.fromisoformat(manifest["created_at"]).astimezone(timezone.utc)
    )


def test_prediction_adapter_records_missing_analysis_without_substituting_morning_odds(
    tmp_path: Path, monkeypatch,
) -> None:
    folder = _prediction_meeting(tmp_path, with_analysis_odds=False)
    monkeypatch.setenv("WC_AU_SCHED_LOG_DIR", str(tmp_path / "logs"))
    with (
        mock.patch.object(schedule, "scoring_recommendations", return_value=[]),
        mock.patch.object(
            schedule,
            "record_prediction_decision_if_configured",
            return_value={"status": "appended", "prediction_id": "prediction"},
        ) as record,
    ):
        assert schedule.step_prediction_evidence(_runlog(tmp_path), [folder]) is True
    manifest_path = next((folder / "_prediction_snapshots").glob("*/manifest.json"))
    projection = json.loads(
        (manifest_path.parent / "AU_Research_Feature_Provenance.json").read_text(
            encoding="utf-8"
        )
    )
    assert projection["market"] == {
        "status": "missing_analysis",
        "artifact": "odds_history.json",
        "sha256": next(
            item["sha256"]
            for item in json.loads(manifest_path.read_text(encoding="utf-8"))["files"]
            if item["name"] == "odds_history.json"
        ),
        "earliest_analysis": {},
    }
    assert projection["model_promotion_allowed"] is False
    record.assert_called_once()


def test_settlement_adapter_pins_canonical_result_and_reflector(
    tmp_path: Path, monkeypatch,
) -> None:
    archive = tmp_path / "Archive"
    folder = archive / EVENT
    folder.mkdir(parents=True)
    result = folder / "Race_Results_Reflector.md"
    report = folder / f"{EVENT}_Reflector_Report.md"
    result.write_text("# canonical results\n", encoding="utf-8")
    report.write_text("# reflector\n", encoding="utf-8")
    monkeypatch.setattr(schedule, "ARCHIVE_ROOT", archive)
    monkeypatch.setenv("WC_AU_SCHED_LOG_DIR", str(tmp_path / "logs"))
    with mock.patch.object(
        schedule,
        "record_settlement_for_event",
        return_value={"status": "appended", "settlement_id": "settlement"},
    ) as record:
        assert schedule.step_settlement_evidence(_runlog(tmp_path), [EVENT]) is True
    assert record.call_args.kwargs["artifacts"] == [result, report]


def test_settlement_adapter_blocks_missing_canonical_result(
    tmp_path: Path, monkeypatch,
) -> None:
    archive = tmp_path / "Archive"
    folder = archive / EVENT
    folder.mkdir(parents=True)
    (folder / f"{EVENT}_Reflector_Report.md").write_text("# reflector\n", encoding="utf-8")
    monkeypatch.setattr(schedule, "ARCHIVE_ROOT", archive)
    monkeypatch.setenv("WC_AU_SCHED_LOG_DIR", str(tmp_path / "logs"))
    with mock.patch.object(schedule, "record_settlement_for_event") as record:
        assert schedule.step_settlement_evidence(_runlog(tmp_path), [EVENT]) is False
    record.assert_not_called()


def test_morning_review_records_settlement_and_propagates_evidence_failure(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setenv("WC_AU_SCHED_LOG_DIR", str(tmp_path / "logs"))
    args = SimpleNamespace(
        skip_review=False,
        skip_refresh=False,
        skip_analysis=True,
        max_meetings=0,
        rounds=1,
        round_gap=0,
        skip_deploy=True,
    )
    with (
        mock.patch.object(schedule, "step_review_archive", return_value=[EVENT]),
        mock.patch.object(schedule, "push_reflection"),
        mock.patch.object(schedule, "step_settlement_evidence", return_value=False) as settle,
        mock.patch.object(schedule, "step_refresh_active", return_value=[]),
        mock.patch.object(schedule, "step_prediction_evidence", return_value=True),
        mock.patch.object(schedule, "step_dashboard", return_value=True),
        mock.patch.object(schedule, "step_mirror_reports"),
        mock.patch.object(schedule, "push_run_summary"),
        mock.patch.object(schedule, "finish_run", return_value=schedule.EXIT_TEMPORARY) as finish,
    ):
        result = schedule.run_morning(_runlog(tmp_path), args, date(2026, 9, 19))
    assert result == schedule.EXIT_TEMPORARY
    settle.assert_called_once_with(mock.ANY, [EVENT])
    assert finish.call_args.args[2] is True
