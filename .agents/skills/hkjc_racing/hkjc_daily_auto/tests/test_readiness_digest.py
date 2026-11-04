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
    # 呢個 fixture 冇 `*_state`（即係舊格式 readiness 檔）—— 分唔到就保守
    # 當「冇有效檔」，唔可以靜靜當成保留檔而唔嗌。
    assert digest.splitlines() == [
        "排位表 10/10 · 賽績 8/10 · 晨操 10/10 · PDF ✅",
        "冇有效檔（要人睇）：R4賽績、R5賽績",
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


# ───────────── starter PDF：2026-11-03 起係軟閘 ─────────────
# PDF 唔再卡住場次（海外往績改用 fsc 來港前賽績），但 digest 一定要講出嚟，
# 而且要講明「唔阻塞」—— 唔可以靜靜 fallback，亦唔可以嚇人話卡死。

def test_soft_pdf_failure_is_a_warning_not_a_blocker(tmp_path):
    digest = readiness_digest(_write(
        tmp_path, formguides_ready=10, starter_pdf_ready=False,
        starter_pdf_gate="soft", starter_pdf_soft_fail=True,
        starter_pdf_state="missing", starter_pdf_error="HTTP 404",
        races=[{"race": n, "racecard_ok": True, "formguide_ok": True} for n in range(1, 11)]))
    lines = digest.splitlines()
    assert lines[0].endswith("PDF ⚠️")
    assert "唔阻塞" in lines[1] and "fsc" in lines[1] and "HTTP 404" in lines[1]
    assert "卡住" not in digest


def test_old_hard_gate_readiness_still_says_it_blocked(tmp_path):
    """舊 readiness 檔（冇 `starter_pdf_gate`）嗰陣 PDF 真係硬條件，照講卡住。"""
    digest = readiness_digest(_write(
        tmp_path, starter_pdf_ready=False, starter_pdf_state="missing"))
    assert digest.splitlines()[0].endswith("PDF ❌")
    assert "卡住成個場次" in digest
