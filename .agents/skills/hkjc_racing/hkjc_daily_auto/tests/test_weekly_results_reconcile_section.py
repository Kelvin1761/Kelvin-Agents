"""每週 review 尾段嘅官方騎練排名對數：有就加，壞咗就少一段，永遠唔可以拖冧 review。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import hkjc_daily_schedule as schedule  # noqa: E402

sys.path.insert(0, str(schedule.EXTRACTOR_SCRIPTS))
import crawl_hkjc_jockey_trainer as ranking  # noqa: E402


def test_section_reports_warning(monkeypatch):
    report = {
        "status": "warn", "season": "26/27", "official_last_meeting": "2026-10-14",
        "problems": ["官方最近賽日 2026-10-14，賽果庫最後係 2026-10-11"],
        "jockey": {"matched": 0, "compared": 1, "mismatches": []},
        "trainer": {"matched": 0, "compared": 1, "mismatches": []},
    }
    monkeypatch.setattr(ranking, "build_report", lambda *_a, **_k: report)
    text = schedule.results_db_reconcile_section()
    assert "⚠️" in text and "2026-10-14" in text


def test_section_failure_is_non_blocking(monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("anything")

    monkeypatch.setattr(ranking, "build_report", boom)
    assert schedule.results_db_reconcile_section() == ""
