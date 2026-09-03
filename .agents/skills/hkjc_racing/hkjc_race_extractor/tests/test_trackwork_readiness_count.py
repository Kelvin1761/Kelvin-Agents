"""晨操 readiness counted 0 on every run while every file was on disk.

`batch_extract` builds `date_prefix` as MM-DD (`09-06`) and
`extract_trackwork.py` writes YYYY-MM-DD (`2026-09-06`), so the existence check
looked for a filename that is never produced. Nothing gated on it, so the only
symptom was a permanent "⚠️ 晨操 Trackwork: 0/N (fallback)" line in the Telegram
notice and a `trackwork_ready: 0` field that was simply untrue.
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from batch_extract import _trackwork_file_ok  # noqa: E402


def _write(folder: Path, name: str, size: int) -> None:
    (folder / name).write_text("x" * size, encoding="utf-8")


def test_the_writer_s_own_full_date_prefix_is_found(tmp_path):
    _write(tmp_path, "2026-09-06 Race 1 晨操.json", 500)
    _write(tmp_path, "2026-09-06 Race 1 晨操.md", 300)
    assert _trackwork_file_ok(tmp_path, 1, "json", 100)
    assert _trackwork_file_ok(tmp_path, 1, "md", 50)


def test_the_short_prefix_still_works(tmp_path):
    """Either convention has to pass; the check must not pin one of them."""
    _write(tmp_path, "09-06 Race 2 晨操.json", 500)
    assert _trackwork_file_ok(tmp_path, 2, "json", 100)


def test_a_missing_race_is_still_reported_missing(tmp_path):
    _write(tmp_path, "2026-09-06 Race 1 晨操.json", 500)
    assert not _trackwork_file_ok(tmp_path, 2, "json", 100)


def test_a_truncated_file_does_not_count(tmp_path):
    _write(tmp_path, "2026-09-06 Race 3 晨操.json", 10)
    assert not _trackwork_file_ok(tmp_path, 3, "json", 100)


def test_one_good_file_beside_a_stale_empty_one_passes(tmp_path):
    _write(tmp_path, "09-06 Race 4 晨操.json", 5)
    _write(tmp_path, "2026-09-06 Race 4 晨操.json", 500)
    assert _trackwork_file_ok(tmp_path, 4, "json", 100)


def test_race_numbers_do_not_match_by_prefix(tmp_path):
    """`Race 1` must not be satisfied by `Race 10`'s file."""
    _write(tmp_path, "2026-09-06 Race 10 晨操.json", 500)
    assert not _trackwork_file_ok(tmp_path, 1, "json", 100)
