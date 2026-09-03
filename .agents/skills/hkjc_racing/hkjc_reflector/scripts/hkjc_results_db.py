#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import re
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
import sys as _sys; _sys.path.insert(0, str(ROOT))
from wongchoi_paths import HK_RACING, HORSE_RACE_ANALYSIS

LEGACY_ANALYSIS_DB = HORSE_RACE_ANALYSIS
HK_RACING_ANALYSIS_DB = HK_RACING
CANONICAL_RESULTS_DB = HK_RACING_ANALYSIS_DB / "HKJC_Race_Results_Database"
LEGACY_RESULTS_DB = LEGACY_ANALYSIS_DB / "HKJC_Race_Results_Database"


def _first_existing_path(candidates: list[Path], default: Path) -> Path:
    for path in candidates:
        if path.exists():
            return path
    return default


def get_results_database_root() -> Path:
    return _first_existing_path(
        [CANONICAL_RESULTS_DB, LEGACY_RESULTS_DB],
        CANONICAL_RESULTS_DB,
    )


def get_analysis_archive_root() -> Path:
    return _first_existing_path(
        [HK_RACING_ANALYSIS_DB, LEGACY_ANALYSIS_DB],
        HK_RACING_ANALYSIS_DB,
    )


SEASON_DIR_RE = re.compile(r"^hkjc results (\d{4}) (\d{2})$")
# HK racing runs September -> mid-July; nothing is scheduled in August, so any
# month from August onward belongs to the season that is about to start.
SEASON_START_MONTH = 8


def season_folder_name(value) -> str:
    """`date(2026, 9, 6)` -> `hkjc results 2026 27`.

    The season roots used to be a hardcoded pair (`2024 25`, `2025 26`), so the
    2026/27 season opening on 2026-09-06 would have been invisible to every
    consumer of this module -- results written, never found, and silently
    excluded from the comprehensive stats the live priors read.
    """
    if isinstance(value, str):
        value = date.fromisoformat(value[:10])
    start = value.year if value.month >= SEASON_START_MONTH else value.year - 1
    return f"hkjc results {start} {(start + 1) % 100:02d}"


def get_season_results_roots() -> list[Path]:
    """Every season folder that exists, oldest first."""
    root = get_results_database_root()
    if not root.exists():
        return []
    return sorted(
        (path for path in root.iterdir()
         if path.is_dir() and SEASON_DIR_RE.match(path.name)),
        key=lambda path: path.name,
    )


def get_comprehensive_stats_root() -> Path:
    root = get_results_database_root()
    candidates = [
        root / "comprehensive_stats",
        root / "comprehensive_stats" / "Full",
    ]
    for path in candidates:
        if path.exists():
            return path if path.name == "comprehensive_stats" else path.parent
    return root / "comprehensive_stats"


def get_season_csvs() -> list[Path]:
    root = get_results_database_root()
    return [
        root / "comprehensive_stats" / "24_25" / "race_results_24_25.csv",
        root / "comprehensive_stats" / "25_26" / "race_results_25_26.csv",
    ]


def get_full_results_csv() -> Path:
    root = get_results_database_root()
    return root / "comprehensive_stats" / "Full" / "race_results_Full.csv"


def get_combo_priors_csv() -> Path:
    root = get_results_database_root()
    return root / "comprehensive_stats" / "Full" / "general_pre_race_priors" / "jockey_trainer_combo_priors.csv"


def build_results_index(results_roots: list[Path] | None = None) -> dict[str, Path]:
    roots = results_roots or get_season_results_roots()
    index: dict[str, Path] = {}
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("full_day_results.json"):
            date_dir = path.parent.name
            index.setdefault(date_dir, path)
    return index


def find_meeting_results_file(meeting_dir: Path, results_roots: list[Path] | None = None) -> Path | None:
    local_candidates = sorted(meeting_dir.glob("*全日賽果.json"))
    if local_candidates:
        return local_candidates[0]

    date = meeting_dir.name[:10]
    return build_results_index(results_roots).get(date)


def ensure_results_database_dirs() -> dict[str, Path]:
    root = get_results_database_root()
    season_24 = root / "hkjc results 2024 25"
    season_25 = root / "hkjc results 2025 26"
    stats = root / "comprehensive_stats"
    for path in (root, season_24, season_25, stats):
        path.mkdir(parents=True, exist_ok=True)
    return {
        "root": root,
        "season_24_25": season_24,
        "season_25_26": season_25,
        "stats": stats,
    }


def load_full_day_results(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


MEETING_RESULTS_GLOB = "*全日賽果.json"
CANONICAL_RESULTS_NAME = "full_day_results.json"


def sync_meeting_results(meeting_dir: Path, *, overwrite: bool = False) -> dict:
    """Copy one meeting's extracted results into the canonical results database.

    The reflector already writes `<date>_<venue>_全日賽果.json` into the meeting
    folder for every meeting that runs, but nothing in the daily automation ever
    copied it into `HKJC_Race_Results_Database`: the only writer in the repo was
    a one-off migration script. Measured 2026-09-04: five meetings had results on
    disk and no database entry, including the most recent one (2026-07-12), and
    `comprehensive_stats` -- which `live_priors` reads for HKJC scoring -- had not
    been rebuilt since 2026-07-14.
    """
    meeting_dir = Path(meeting_dir)
    sources = sorted(meeting_dir.glob(MEETING_RESULTS_GLOB))
    if not sources:
        return {"status": "no_results", "meeting": meeting_dir.name, "copied": 0}
    source = sources[0]
    meeting_date = source.name[:10]
    try:
        date.fromisoformat(meeting_date)
    except ValueError:
        return {"status": "unparsable_date", "meeting": meeting_dir.name, "copied": 0}
    target_dir = get_results_database_root() / season_folder_name(meeting_date) / meeting_date
    target_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for name in (source.name, CANONICAL_RESULTS_NAME):
        target = target_dir / name
        if target.exists() and not overwrite:
            continue
        shutil.copy2(source, target)
        copied += 1
    return {"status": "ok" if copied else "already_present",
            "meeting": meeting_dir.name, "date": meeting_date,
            "season": season_folder_name(meeting_date),
            "target": str(target_dir), "copied": copied}
