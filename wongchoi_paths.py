"""Central, cross-platform path config for the Wong Choi engines.

Two roots, deliberately separated so code and data can live in different places
(e.g. code in a local git clone, data on Google Drive):

    PROJECT_ROOT  - where THIS repo is checked out (the code). Auto-detected as the
                    folder containing this file.
    DATA_ROOT     - where the large data / analysis folders live. Resolved from,
                    in order:
                      1. env var  WONGCHOI_DATA_ROOT
                      2. a one-line file  <PROJECT_ROOT>/.wongchoi_data_root
                      3. PROJECT_ROOT      (data co-located with code)

Each machine sets its own DATA_ROOT (macOS -> its Google Drive path, Windows ->
its Google Drive path), so the engines run unchanged on either OS.

Usage from any script:
    import sys; sys.path.insert(0, str(PROJECT_ROOT))   # PROJECT_ROOT already known
    from wongchoi_paths import DATA_ROOT, HORSE_RACE_ANALYSIS, new_analysis_dir
"""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT: Path = Path(__file__).resolve().parent


def _resolve_data_root() -> Path:
    env = os.environ.get("WONGCHOI_DATA_ROOT")
    if env and env.strip():
        return Path(env).expanduser()
    cfg = PROJECT_ROOT / ".wongchoi_data_root"
    if cfg.is_file():
        line = cfg.read_text(encoding="utf-8").strip()
        if line:
            return Path(line).expanduser()
    return PROJECT_ROOT


DATA_ROOT: Path = _resolve_data_root()

# --- Per-sport analysis homes (new naming) ----------------------------------
HORSE_RACE_ANALYSIS: Path = DATA_ROOT / "Wong Choi Horse Race Analysis"
NBA_ANALYSIS: Path = DATA_ROOT / "Wong Choi NBA Analysis"
TENNIS_ANALYSIS: Path = DATA_ROOT / "Wong Choi Tennis Analysis"

# Internal sub-structure preserved from the old Archive_Race_Analysis layout
AU_RACING: Path = HORSE_RACE_ANALYSIS / "AU_Racing"
HK_RACING: Path = HORSE_RACE_ANALYSIS / "HK_Racing"

# NBA raw ML dataset (name unchanged by the rename, just relocated under DATA_ROOT)
NBA_ML_DATASET: Path = DATA_ROOT / "NBA_ML_Dataset"

_SPORT_HOMES = {
    "horse": HORSE_RACE_ANALYSIS,
    "au": AU_RACING,
    "hk": HK_RACING,
    "hkjc": HK_RACING,
    "nba": NBA_ANALYSIS,
    "tennis": TENNIS_ANALYSIS,
}


def analysis_home(sport: str) -> Path:
    """Return the 'Wong Choi <Sport> Analysis' home dir for a sport key."""
    try:
        return _SPORT_HOMES[sport.lower()]
    except KeyError:
        raise ValueError(f"unknown sport key: {sport!r} (use one of {sorted(_SPORT_HOMES)})")


def new_analysis_dir(sport: str, label: str) -> Path:
    """Create and return a fresh analysis subfolder for one run, named by `label`
    (e.g. a meeting/date label), under the sport's Wong Choi Analysis home.

    Example: new_analysis_dir("hk", "2026-06-25 Sha Tin R1-9")
             -> <DATA_ROOT>/Wong Choi Horse Race Analysis/HK_Racing/2026-06-25 Sha Tin R1-9/
    """
    d = analysis_home(sport) / label
    d.mkdir(parents=True, exist_ok=True)
    return d


if __name__ == "__main__":
    print("PROJECT_ROOT        :", PROJECT_ROOT)
    print("DATA_ROOT           :", DATA_ROOT, "(exists)" if DATA_ROOT.is_dir() else "(MISSING)")
    for name in ("HORSE_RACE_ANALYSIS", "NBA_ANALYSIS", "TENNIS_ANALYSIS",
                 "AU_RACING", "HK_RACING", "NBA_ML_DATASET"):
        p = globals()[name]
        print(f"{name:20}:", p, "(exists)" if p.is_dir() else "(missing)")
