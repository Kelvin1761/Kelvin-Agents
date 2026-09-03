"""The prerace failure notice must say what is missing in a few lines.

It used to append `output[-1200:]` -- raw extractor stdout. Telegram clipped it
and the surviving text started mid-checklist with the header gone, so the reader
could not see which races were short or whether a retry would fix it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL))

from hkjc_daily_schedule import readiness_digest  # noqa: E402


def _write(tmp_path, **overrides):
    payload = {
        "expected_races": 10,
        "starter_pdf_ready": True,
        "racecards_ready": 10,
        "formguides_ready": 8,
        "trackwork_ready": 10,
        "races": [{"race": n, "racecard_ok": True, "formguide_ok": n not in (4, 5)}
                  for n in range(1, 11)],
    }
    payload.update(overrides)
    (tmp_path / "Extraction_Readiness.json").write_text(
        json.dumps(payload), encoding="utf-8")
    return tmp_path


def test_digest_names_the_short_races_in_two_lines(tmp_path):
    digest = readiness_digest(_write(tmp_path))
    assert digest.splitlines() == [
        "排位表 10/10 · 賽績 8/10 · 晨操 10/10 · PDF ✅",
        "未齊：R4賽績、R5賽績",
    ]
    # The whole point: it has to stay short enough to survive intact.
    assert len(digest) < 200


def test_a_complete_meeting_reports_no_missing_line(tmp_path):
    digest = readiness_digest(_write(
        tmp_path, formguides_ready=10,
        races=[{"race": n, "racecard_ok": True, "formguide_ok": True}
               for n in range(1, 11)]))
    assert digest.splitlines() == ["排位表 10/10 · 賽績 10/10 · 晨操 10/10 · PDF ✅"]


def test_a_long_missing_list_is_capped(tmp_path):
    digest = readiness_digest(_write(
        tmp_path, racecards_ready=0, formguides_ready=0,
        races=[{"race": n, "racecard_ok": False, "formguide_ok": False}
               for n in range(1, 11)]))
    assert "等 20 項" in digest
    assert len(digest) < 200


def test_missing_or_unreadable_file_never_blocks_the_notice(tmp_path):
    assert readiness_digest(tmp_path) == ""
    (tmp_path / "Extraction_Readiness.json").write_text("not json", encoding="utf-8")
    assert readiness_digest(tmp_path) == ""
