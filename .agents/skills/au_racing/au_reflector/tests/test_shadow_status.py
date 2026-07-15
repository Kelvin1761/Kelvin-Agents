import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/au_reflector_orchestrator.py"
SPEC = importlib.util.spec_from_file_location("au_reflector_orchestrator", SCRIPT)
reflector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reflector)


def test_shadow_report_block_is_idempotent(tmp_path):
    meeting = tmp_path / "2026-07-12 Test Track Race 1-1"
    meeting.mkdir()
    report = meeting / "Reflector_Report.md"
    report.write_text("# Reflector\n", encoding="utf-8")
    tracker = {
        "forward_races": 8,
        "tracks": ["Test Track"],
        "promotion_gate": {"minimum_forward_races": 150},
        "distance_family_counts": {"Sprint <=1400m": 8, "Middle 1401-1800m": 0, "Staying 1801m+": 0},
        "candidates": {
            "place_rating": {
                "deltas": {"top1_win": 0.01, "top2_place_strike": 0.02, "top4_place_coverage": 0, "top4_trifecta": 0},
                "promotion_eligible": False,
            }
        },
    }
    (tmp_path / "AU_Dual_Objective_Shadow_Tracker.json").write_text(json.dumps(tracker), encoding="utf-8")
    status = {
        "structural_shadow": {"status": "updated"},
        "dual_objective_shadow": {"status": "updated"},
        "promotion_ready": None,
    }
    reflector._append_shadow_status_to_report(report, meeting, status)
    reflector._append_shadow_status_to_report(report, meeting, status)
    text = report.read_text(encoding="utf-8")
    assert text.count("AU_SHADOW_STATUS_START") == 1
    assert "8/150 races" in text
    assert "place_rating" in text


def test_skipped_run_does_not_reuse_stale_promotion_alert(tmp_path):
    meeting = tmp_path / "meeting"
    meeting.mkdir()
    (meeting / "Dual_Objective_Shadow_Update_Status.json").write_text(
        json.dumps({"promotion_ready": "/stale/promotion.md"}), encoding="utf-8"
    )
    status = reflector._write_shadow_update_status(
        meeting, None, structural_review=None, dual_review=None, skipped=True
    )
    assert status["promotion_ready"] is None
    assert status["structural_shadow"]["status"] == "skipped_by_flag"
    assert status["dual_objective_shadow"]["status"] == "skipped_by_flag"
