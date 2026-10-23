"""Failed analysis must remain retryable and stay out of dashboard recovery."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import au_daily_schedule as S  # noqa: E402


@pytest.fixture
def meeting(tmp_path):
    folder = tmp_path / "2026-10-24 Fixture Race 1-2"
    folder.mkdir()
    log = MagicMock()
    log.site_refusing = True
    log.data = {"races_added": []}
    plan = {"venue": "Fixture", "races": ["123", "124"],
            "meetingId": "456", "slug": "fixture", "going": "Good 4"}
    with patch.object(S, "find_meeting_dir", return_value=folder), \
         patch.object(S, "race_numbers", return_value=[1, 2]), \
         patch.object(S, "ensure_mapping"), \
         patch.object(S, "record_odds_snapshot", return_value=2) as snapshot:
        yield folder, log, plan, snapshot


@pytest.mark.parametrize("returncode", [1, 2, 124])
def test_failed_gate_with_all_reports_is_retried_before_completion(meeting, returncode):
    folder, log, plan, snapshot = meeting

    def analyse(*args, **kwargs):
        for race in (1, 2):
            (folder / f"Race_{race}_Auto_Analysis.md").write_text("report")
        return returncode, "Compliance gate failed"

    with patch.object(S, "run_cmd", side_effect=analyse):
        with pytest.raises(S.TemporaryFailure, match=f"rc={returncode}"):
            S.analyse_one_meeting(log, "2026-10-24", plan)
    assert not log.data["races_added"]
    snapshot.assert_not_called()
    assert (folder / S.ANALYSIS_PENDING).exists()

    # A later run sees all reports, but must retry the failed validation.
    with patch.object(S, "run_cmd", return_value=(0, "Validated")) as retry:
        result = S.analyse_one_meeting(log, "2026-10-24", plan)
    retry.assert_called_once()
    assert result == (folder, True, False)
    assert log.data["races_added"][0]["complete"] is True
    assert not (folder / S.ANALYSIS_PENDING).exists()
    snapshot.assert_called_once()


def test_interrupted_analysis_keeps_retry_marker(meeting):
    folder, log, plan, snapshot = meeting
    with patch.object(S, "run_cmd", side_effect=RuntimeError("interrupted")):
        with pytest.raises(RuntimeError, match="interrupted"):
            S.analyse_one_meeting(log, "2026-10-24", plan)
    assert (folder / S.ANALYSIS_PENDING).exists()
    snapshot.assert_not_called()


def test_success_code_without_all_extracted_races_does_not_clear_pending(meeting):
    folder, log, plan, snapshot = meeting
    with patch.object(S, "run_cmd", return_value=(0, "No outputs")):
        with pytest.raises(S.TemporaryFailure, match="分析輸出未齊"):
            S.analyse_one_meeting(log, "2026-10-24", plan)
    assert (folder / S.ANALYSIS_PENDING).exists()
    assert not log.data["races_added"]
    snapshot.assert_not_called()


def test_legacy_completed_meeting_still_skips_analysis(meeting):
    folder, log, plan, snapshot = meeting
    for race in (1, 2):
        (folder / f"Race_{race}_Auto_Analysis.md").write_text("validated report")
    with patch.object(S, "run_cmd") as run:
        assert S.analyse_one_meeting(log, "2026-10-24", plan) == (folder, True, False)
    run.assert_not_called()


def test_failed_analysis_is_excluded_from_unpublished_recovery(tmp_path):
    folder = tmp_path / "2026-10-24 Fixture Race 1-2"
    folder.mkdir()
    (folder / "Race_1_Auto_Analysis.md").write_text("unvalidated report")
    (folder / S.ANALYSIS_PENDING).touch()
    with patch.object(S, "live_meeting_dirs", return_value=[folder]):
        assert S.unpublished_local_meetings({}, [], S.date(2026, 10, 24)) == []


def test_explicit_snapshot_merge_rejects_pending_analysis(tmp_path):
    folder = tmp_path / "2026-10-24 Fixture Race 1-2"
    folder.mkdir()
    (folder / S.ANALYSIS_PENDING).touch()
    base = tmp_path / "base.json"
    base.write_text(json.dumps({"meetings": []}))
    with patch.object(S, "WORK_DIR", tmp_path / "work"), \
         patch.object(S, "download_live_snapshot", return_value=base), \
         patch.object(S, "unpublished_local_meetings", return_value=[]), \
         patch.object(S, "run_cmd") as run:
        with pytest.raises(S.TemporaryFailure, match="分析未通過"):
            S.build_snapshot(MagicMock(), [folder])
    run.assert_not_called()
