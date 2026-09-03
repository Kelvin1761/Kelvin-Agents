"""Race results have to reach the database the priors are built from.

The reflector wrote `<date>_<venue>_全日賽果.json` into every meeting folder,
but the only writer into `HKJC_Race_Results_Database` was a one-off migration
script. Measured 2026-09-04: five meetings had results on disk and no database
entry -- including the most recent one -- and the season roots were a hardcoded
pair that did not include the season starting 2026-09-06.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

# Load by explicit file path under a private name. `hkjc_results_db` is a
# top-level module name shared by every checkout on this machine, so whichever
# test imports it first wins for the whole pytest session -- run beside the
# other reflector tests, this file was asserting against a copy from somewhere
# else and failed with "no attribute season_folder_name" while passing alone.
_spec = importlib.util.spec_from_file_location(
    "_hkjc_results_db_under_test", SCRIPTS / "hkjc_results_db.py")
db = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(db)
assert Path(db.__file__).resolve() == (SCRIPTS / "hkjc_results_db.py").resolve()


@pytest.mark.parametrize("day,expected", [
    ("2026-09-06", "hkjc results 2026 27"),   # season opener
    ("2026-07-12", "hkjc results 2025 26"),   # last meeting of the old season
    ("2026-08-15", "hkjc results 2026 27"),   # no racing in August; new season
    ("2026-01-01", "hkjc results 2025 26"),   # mid-season
    ("2025-09-07", "hkjc results 2025 26"),
])
def test_season_folder_follows_the_hk_calendar(day, expected):
    assert db.season_folder_name(day) == expected
    assert db.season_folder_name(date.fromisoformat(day)) == expected


def test_season_roots_are_discovered_not_hardcoded(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "get_results_database_root", lambda: tmp_path)
    for name in ("hkjc results 2024 25", "hkjc results 2025 26",
                 "hkjc results 2026 27", "comprehensive_stats", "notes"):
        (tmp_path / name).mkdir()
    assert [p.name for p in db.get_season_results_roots()] == [
        "hkjc results 2024 25", "hkjc results 2025 26", "hkjc results 2026 27"]


def _meeting(tmp_path, name, payload=None):
    folder = tmp_path / "meetings" / name.rsplit("_", 1)[0]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}_全日賽果.json").write_text(
        json.dumps(payload or {"1": {"results": []}}), encoding="utf-8")
    return folder


def test_results_land_in_the_season_folder_under_both_names(tmp_path, monkeypatch):
    db_root = tmp_path / "db"
    monkeypatch.setattr(db, "get_results_database_root", lambda: db_root)
    folder = _meeting(tmp_path, "2026-09-06_ShaTin")
    out = db.sync_meeting_results(folder)
    assert out["status"] == "ok" and out["copied"] == 2
    target = db_root / "hkjc results 2026 27" / "2026-09-06"
    assert (target / "2026-09-06_ShaTin_全日賽果.json").is_file()
    assert (target / "full_day_results.json").is_file()


def test_running_twice_does_not_duplicate_or_overwrite(tmp_path, monkeypatch):
    db_root = tmp_path / "db"
    monkeypatch.setattr(db, "get_results_database_root", lambda: db_root)
    folder = _meeting(tmp_path, "2026-09-06_ShaTin")
    db.sync_meeting_results(folder)
    again = db.sync_meeting_results(folder)
    assert again["status"] == "already_present" and again["copied"] == 0


def test_overwrite_refreshes_a_corrected_result(tmp_path, monkeypatch):
    db_root = tmp_path / "db"
    monkeypatch.setattr(db, "get_results_database_root", lambda: db_root)
    folder = _meeting(tmp_path, "2026-09-06_ShaTin")
    db.sync_meeting_results(folder)
    (folder / "2026-09-06_ShaTin_全日賽果.json").write_text(
        json.dumps({"1": {"results": [{"pos": 1}]}}), encoding="utf-8")
    out = db.sync_meeting_results(folder, overwrite=True)
    assert out["copied"] == 2
    stored = json.loads(
        (db_root / "hkjc results 2026 27" / "2026-09-06" / "full_day_results.json")
        .read_text(encoding="utf-8"))
    assert stored["1"]["results"] == [{"pos": 1}]


def test_a_meeting_with_no_results_is_reported_not_crashed(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "get_results_database_root", lambda: tmp_path / "db")
    folder = tmp_path / "meetings" / "2026-09-06_ShaTin"
    folder.mkdir(parents=True)
    assert db.sync_meeting_results(folder)["status"] == "no_results"
