"""每週 review 尾段嘅欄位健康摘要：有就加，壞咗就少一段，永遠唔可以拖冧 review。"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import hkjc_daily_schedule as schedule  # noqa: E402


def test_section_written_from_temp_root(tmp_path, monkeypatch):
    monkeypatch.setattr(schedule, "HK_RACING", tmp_path)
    text = schedule.field_health_section(date(2026, 10, 13))
    assert "HKJC 欄位健康週報" in text
    assert (tmp_path / "HKJC_Field_Health.jsonl").exists()


def test_section_failure_is_non_blocking(monkeypatch):
    monkeypatch.setattr(schedule, "HK_RACING", Path("/nonexistent/唔存在"))
    import field_health

    def boom(*_a, **_k):
        raise OSError("disk gone")

    monkeypatch.setattr(field_health, "record", boom)
    assert schedule.field_health_section(date(2026, 10, 13)) == ""
