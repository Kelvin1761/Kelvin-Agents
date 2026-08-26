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

AU_RACING and HK_RACING are additionally relocatable on their own. 2026-08-05:
the AU tree moved to local disk on the Mac
because a launchd-spawned process is a different TCC context from Terminal and
cannot read CloudStorage — `AU_RACING.iterdir()` raised `PermissionError:
Operation not permitted` and every scheduled run died in preflight. Tennis solved
the same problem on 2026-07-14 by running from local disk.

Measured 2026-08-05, three identical launchd probes on the Drive AU path — the
permissions are partial, not all-or-nothing:

    iterdir()      PermissionError (errno 1)
    read_bytes()   PermissionError (errno 1)
    stat()         OK
    write+unlink   OK

So `.is_dir()` / `.exists()` are USELESS as reachability probes from a scheduled
context: they are stat() calls and succeed on a path the same process cannot
list or read. Probe by attempting the real operation.

WONGCHOI_AU_MIRROR_ROOT is the other half of the split: the engine reads and
writes local disk, then copies reports back to the Drive folder so Kelvin keeps
reading analysis where he always has. That mirror only stats and writes, which is
exactly the half of the API launchd is allowed, so it works from the scheduler
too. It stays best-effort regardless — a mirror failure must never fail a run
whose analysis already succeeded.

HKJC gained its own unattended scheduler in 2026-08.  It therefore uses the
same local-primary / Drive-mirror pattern when `WONGCHOI_HK_DATA_ROOT` (or
`.wongchoi_hk_data_root`) is configured.  Existing historical placeholders do
not have to be downloaded before the next-season forward pipeline can run.

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
    """True only when a regular file has local, readable bytes.

    File Provider/TCC can expose a non-zero ``stat`` result (and even allocated
    blocks) while denying the actual read.  Scheduled pipelines care about the
    latter, so probe one byte instead of treating metadata as reachability.
    """
    target = Path(path)
    try:
        info = target.stat()
    except OSError:
        return False
    blocks = getattr(info, "st_blocks", None)
    has_local_bytes = (
        stat_module.S_ISREG(info.st_mode)
        and info.st_size > 0
        and not (blocks == 0 and info.st_size > 0)
    )
    if not has_local_bytes:
        return False
    try:
        with target.open("rb") as handle:
            return bool(handle.read(1))
    except OSError:
        return False


def _resolve_root(env_var: str, cfg_name: str, default: Path) -> Path:
    """env var, then a one-line <PROJECT_ROOT>/<cfg_name> file, then `default`.

    The file read is guarded: on a checkout whose PROJECT_ROOT is itself on
    cloud storage, `is_file()` can raise rather than return False.
    """
    env = os.environ.get(env_var)
    if env and env.strip():
        return Path(env.strip()).expanduser()
    cfg = PROJECT_ROOT / cfg_name
    try:
        if cfg.is_file():
            line = cfg.read_text(encoding="utf-8").strip()
            if line:
                return Path(line).expanduser()
    except OSError:
        pass
    return default


DATA_ROOT: Path = _resolve_root("WONGCHOI_DATA_ROOT", ".wongchoi_data_root", PROJECT_ROOT)

# --- Per-sport analysis homes (new naming) ----------------------------------
HORSE_RACE_ANALYSIS: Path = DATA_ROOT / "Wong Choi Horse Race Analysis"
NBA_ANALYSIS: Path = _resolve_root(
    "WONGCHOI_NBA_DATA_ROOT",
    ".wongchoi_nba_data_root",
    DATA_ROOT / "Wong Choi NBA Analysis",
)
TENNIS_ANALYSIS: Path = DATA_ROOT / "Wong Choi Tennis Analysis"

# Internal sub-structure preserved from the old Archive_Race_Analysis layout.
# AU is separately relocatable so the launchd-driven AU pipeline can run entirely
# off local disk while HK stays on Drive — see the module docstring.
AU_RACING: Path = _resolve_root(
    "WONGCHOI_AU_DATA_ROOT", ".wongchoi_au_data_root", HORSE_RACE_ANALYSIS / "AU_Racing"
)
HK_RACING: Path = _resolve_root(
    "WONGCHOI_HK_DATA_ROOT", ".wongchoi_hk_data_root", HORSE_RACE_ANALYSIS / "HK_Racing"
)

# Where to copy AU reports after a run so the Drive folder does not silently go
# stale once AU_RACING lives on local disk. None = no mirroring configured.
# Resolved like the roots above (env var, then dotfile) so a run started straight
# from `au_daily_schedule.py` mirrors too, not only one launched via
# run_au_daily_schedule.sh — otherwise manual runs would be the ones that skip it.
_AU_MIRROR_UNSET = Path("__wongchoi_au_mirror_unset__")
_au_mirror = _resolve_root(
    "WONGCHOI_AU_MIRROR_ROOT", ".wongchoi_au_mirror_root", _AU_MIRROR_UNSET
)
AU_RACING_MIRROR: Path | None = None if _au_mirror == _AU_MIRROR_UNSET else _au_mirror

_HK_MIRROR_UNSET = Path("__wongchoi_hk_mirror_unset__")
_hk_mirror = _resolve_root(
    "WONGCHOI_HK_MIRROR_ROOT", ".wongchoi_hk_mirror_root", _HK_MIRROR_UNSET
)
HK_RACING_MIRROR: Path | None = None if _hk_mirror == _HK_MIRROR_UNSET else _hk_mirror


def au_historical_results_csv(root: Path | None = None) -> Path:
    """Resolve the freshest canonical AU results corpus, including mirror fallback.

    Google Drive FileProvider can leave the canonical name as an undeletable,
    dataless placeholder.  The scheduler then writes the current bytes to the
    deterministic `.latest.csv` sibling.  Local-primary machines keep using the
    canonical name; Drive/Windows readers automatically choose the newer file.
    """
    base = Path(root or AU_RACING)
    canonical = base / "AU_Historical_Raw_Race_Results.csv"
    latest = base / "AU_Historical_Raw_Race_Results.latest.csv"
    candidates: list[tuple[float, int, Path]] = []
    for path in (canonical, latest):
        try:
            stat = path.stat()
            if path.is_file() and stat.st_size > 0:
                candidates.append((stat.st_mtime, stat.st_size, path))
        except OSError:
            continue
    if not candidates:
        return canonical
    return max(candidates, key=lambda item: (item[0], item[1]))[2]


def au_racing_is_relocated() -> bool:
    """True when AU_RACING has been moved out from under HORSE_RACE_ANALYSIS.

    Callers that walk HORSE_RACE_ANALYSIS (dashboard file watchers) need to know
    to watch the AU root as a second location.
    """
    return AU_RACING.parent != HORSE_RACE_ANALYSIS


def hkjc_racing_is_relocated() -> bool:
    """True when HKJC meetings use a local primary outside the shared Drive tree."""
    return HK_RACING.parent != HORSE_RACE_ANALYSIS


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
    "AU draw bias (historical)": au_historical_results_csv(),
    "AU draw bias (backfill)": AU_RACING / "AU_Backfill_Race_Results.csv",
}


def check_data_root() -> list[str]:
    """Return a list of human-readable problems with the resolved DATA_ROOT.

    Empty list means everything the engines need is reachable. Each check is
    wrapped because a cloud-storage root can raise (not just return False) —
    macOS revoking CloudStorage access raises PermissionError from .exists().

    An unreachable DATA_ROOT no longer short-circuits the per-file checks: AU may
    have been moved out from under it (WONGCHOI_AU_DATA_ROOT), so "Drive is not
    readable in this context" and "the AU engine cannot run" are now separate
    facts and both are worth reporting.
    """
    problems: list[str] = []

    try:
        reachable, err = DATA_ROOT.is_dir(), None
    except OSError as exc:
        reachable, err = False, exc
    if err is not None:
        problems.append(f"DATA_ROOT is not readable ({err.__class__.__name__}): {DATA_ROOT}")
    elif not reachable:
        problems.append(
            f"DATA_ROOT does not exist: {DATA_ROOT}\n"
            "     Fix: set it in .wongchoi_data_root (one line) or the "
            "WONGCHOI_DATA_ROOT env var.\n"
            "     On Windows this is usually your Google Drive path, e.g.\n"
            '       G:\\My Drive\\Antigravity Shared\\Antigravity'
        )

    for label, path in REQUIRED_DATA_FILES.items():
        try:
            if not path.is_file():
                problems.append(f"missing [{label}]: {path}")
        except OSError as exc:
            problems.append(f"unreadable [{label}] ({exc.__class__.__name__}): {path}")

    return problems


if __name__ == "__main__":
    print("PROJECT_ROOT        :", PROJECT_ROOT)
    try:
        _dr_state = "(exists)" if DATA_ROOT.is_dir() else "(MISSING)"
    except OSError as _exc:
        # A launchd/cron context has no CloudStorage access at all — .is_dir()
        # raises here rather than returning False. Report it, do not traceback.
        _dr_state = f"(UNREADABLE: {_exc.__class__.__name__})"
    print("DATA_ROOT           :", DATA_ROOT, _dr_state)
    for name in ("HORSE_RACE_ANALYSIS", "NBA_ANALYSIS", "TENNIS_ANALYSIS",
                 "AU_RACING", "HK_RACING", "NBA_ML_DATASET"):
        p = globals()[name]
        try:
            state = "(exists)" if p.is_dir() else "(missing)"
        except OSError as exc:
            state = f"(UNREADABLE: {exc.__class__.__name__})"
        note = ""
        if name == "AU_RACING" and au_racing_is_relocated():
            note = "  <- relocated off DATA_ROOT"
        if name == "HK_RACING" and hkjc_racing_is_relocated():
            note = "  <- relocated off DATA_ROOT"
        print(f"{name:20}:", p, state + note)

    print(f"{'AU_RACING_MIRROR':20}:",
          AU_RACING_MIRROR if AU_RACING_MIRROR is not None else "(not configured)")
    print(f"{'HK_RACING_MIRROR':20}:",
          HK_RACING_MIRROR if HK_RACING_MIRROR is not None else "(not configured)")

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
