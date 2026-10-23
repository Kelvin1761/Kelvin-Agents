from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import au_diagnose as D  # noqa: E402


@pytest.mark.parametrize("message", [
    "開唔到真 Chrome（TimeoutError: BrowserType.launch_persistent_context: Timeout 180000ms exceeded）",
    "開唔到真 Chrome（Error: It looks like you are using Playwright Sync API inside the asyncio loop.）",
])
def test_partial_run_diagnoses_startup_failure_from_structured_gate_steps(message):
    run = {"mode": "morning", "review_day": "2026-10-23", "status": "partial",
           "started_at": "2026-10-23T10:50:22+11:00", "errors": [],
           "warnings": [{"message": "Page.goto: Timeout 90000ms exceeded"}],
           "meetings_processed": [{"meeting": "Mackay", "status": "refresh_deferred",
                                   "detail": "個站今次 run 已經拒絕"}],
           "steps": [{"step": "site-gate", "status": "tripped", "where": message},
                     {"step": "refresh-active", "status": "still-pending", "meetings": ["Mackay"]}]}
    with patch.object(D, "log_context", return_value=""):
        report = D.diagnose(run, [run])
    assert "Chrome／Playwright 啟動失敗" in report
    assert "個別頁面 hang 咗" not in report
    assert "sportsbetform 真係拒絕" not in report
    assert "Mackay" in report


def test_ordinary_page_timeout_keeps_its_existing_diagnosis():
    match = D.primary_known_match("Page.goto: Timeout 90000ms exceeded")
    assert "個別頁面 hang 咗" in match[0]
