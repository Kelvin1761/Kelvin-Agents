from __future__ import annotations

import importlib.util
from pathlib import Path


SCHEDULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "tennis_daily_schedule.py"
SPEC = importlib.util.spec_from_file_location("tennis_daily_schedule", SCHEDULE_PATH)
schedule = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(schedule)


def _payload(*, evidence: bool, pending: int = 0) -> dict:
    settlement = {
        "pending_without_result": pending,
        "tracker_settlement": {"pending_without_result": 0},
        "combo_settlement": {"pending_without_result": 0},
        "auto_refresh": {"results": {"error": None, "winners_seen": 1 if evidence else 0}},
    }
    return {
        "review_report_path": "/tmp/review.txt",
        "settlement_qa_report_path": "/tmp/qa.txt",
        "settlement": settlement,
    }


def test_archive_requires_result_evidence_even_when_no_items_are_pending():
    decision = schedule.archive_decision(_payload(evidence=False))
    assert not decision["allowed"]
    assert "official_results_unconfirmed" in decision["reasons"]


def test_archive_allows_confirmed_results_with_no_pending_items():
    decision = schedule.archive_decision(_payload(evidence=True))
    assert decision["allowed"]
    assert decision["pending"] == 0


def test_archive_rejects_pending_settlements_after_results_arrive():
    decision = schedule.archive_decision(_payload(evidence=True, pending=1))
    assert not decision["allowed"]
    assert "pending_settlements" in decision["reasons"]
