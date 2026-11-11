"""`sync_hkjc_results_database` writes each day once, under the canonical name.

It used to copy `<date>_<venue>_全日賽果.json` under its own name *and* as
`full_day_results.json`; every `*/*.json` reader then counted each race twice
(EXP-20261110-07: 350 races from 2026-05).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import sync_hkjc_results_database as sync  # noqa: E402


def test_json_and_md_land_once_under_the_canonical_name(tmp_path, monkeypatch):
    db_root = tmp_path / "db"
    monkeypatch.setattr(sync, "ensure_results_database_dirs", lambda: {"root": db_root})
    meeting = tmp_path / "2026-11-08_ShaTin"
    meeting.mkdir()
    (meeting / "2026-11-08_ShaTin_全日賽果.json").write_text(json.dumps({"1": {"results": []}}), encoding="utf-8")
    (meeting / "2026-11-08_ShaTin_全日賽果.md").write_text("# results", encoding="utf-8")

    copies = sync.sync_meeting_results(meeting)

    target = db_root / sync.infer_season_bucket("2026-11-08") / "2026-11-08"
    assert sorted(p.name for p in target.iterdir()) == ["full_day_results.json", "full_day_results.md"]
    assert len(copies) == 2
