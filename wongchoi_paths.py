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
import stat as stat_module
from pathlib import Path

PROJECT_ROOT: Path = Path(__file__).resolve().parent


def is_materialized_file(path: Path) -> bool:
    """True only when a regular file has local bytes, not a cloud placeholder."""
    try:
        info = Path(path).stat()
    except OSError:
        return False
    blocks = getattr(info, "st_blocks", None)
    return (
        stat_module.S_ISREG(info.st_mode)
        and info.st_size > 0
        and not (blocks == 0 and info.st_size > 0)
    )


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


# --- Files the engines hard-depend on (not in git — they live on DATA_ROOT) --
# Used by the bootstrap preflight so a new machine finds out NOW, rather than
# mid-scoring-run, that its Google Drive folder is not actually synced.
REQUIRED_DATA_FILES = {
    # AU: read by racing_engine/au_draw_bias_calculator.py
    "AU draw bias (historical)": AU_RACING / "AU_Historical_Raw_Race_Results.csv",
    "AU draw bias (backfill)": AU_RACING / "AU_Backfill_Race_Results.csv",
}


def check_data_root() -> list[str]:
    """Return a list of human-readable problems with the resolved DATA_ROOT.

    Empty list means everything the engines need is reachable. Each check is
    wrapped because a cloud-storage root can raise (not just return False) —
    macOS revoking CloudStorage access raises PermissionError from .exists().
    """
    problems: list[str] = []

    try:
        if not DATA_ROOT.is_dir():
            problems.append(
                f"DATA_ROOT does not exist: {DATA_ROOT}\n"
                "     Fix: set it in .wongchoi_data_root (one line) or the "
                "WONGCHOI_DATA_ROOT env var.\n"
                "     On Windows this is usually your Google Drive path, e.g.\n"
                '       G:\\My Drive\\Antigravity Shared\\Antigravity'
            )
            return problems
    except OSError as exc:
        problems.append(f"DATA_ROOT is not readable ({exc.__class__.__name__}): {DATA_ROOT}")
        return problems

    for label, path in REQUIRED_DATA_FILES.items():
        try:
            if not path.is_file():
                problems.append(f"missing [{label}]: {path}")
        except OSError as exc:
            problems.append(f"unreadable [{label}] ({exc.__class__.__name__}): {path}")

    return problems


if __name__ == "__main__":
    print("PROJECT_ROOT        :", PROJECT_ROOT)
    print("DATA_ROOT           :", DATA_ROOT, "(exists)" if DATA_ROOT.is_dir() else "(MISSING)")
    for name in ("HORSE_RACE_ANALYSIS", "NBA_ANALYSIS", "TENNIS_ANALYSIS",
                 "AU_RACING", "HK_RACING", "NBA_ML_DATASET"):
        p = globals()[name]
        print(f"{name:20}:", p, "(exists)" if p.is_dir() else "(missing)")

    print()
    issues = check_data_root()
    if not issues:
        print("Data preflight     : OK — all required engine data files reachable.")
    else:
        print(f"Data preflight     : {len(issues)} PROBLEM(S)")
        for item in issues:
            print("  -", item)
        print()
        print("  HKJC scoring can fall back to neutral/tier ratings when cloud priors")
        print("  are unavailable; materialize the HKJC statistics files for the")
        print("  calibrated continuous jockey/trainer and combination priors.")
        print("  AU scoring needs the files above — they are gitignored and live")
        print("  on Google Drive. Install Google Drive Desktop, sign in, and set")
        print("  the 'Antigravity Shared' folder to 'Available offline'.")
