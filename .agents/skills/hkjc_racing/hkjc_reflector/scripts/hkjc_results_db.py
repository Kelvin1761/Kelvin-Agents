#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]

LEGACY_ANALYSIS_DB = ROOT / "Archive_Race_Analysis"
HK_RACING_ANALYSIS_DB = LEGACY_ANALYSIS_DB / "HK_Racing"
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


def get_season_results_roots() -> list[Path]:
    root = get_results_database_root()
    return [
        root / "hkjc results 2024 25",
        root / "hkjc results 2025 26",
    ]


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
