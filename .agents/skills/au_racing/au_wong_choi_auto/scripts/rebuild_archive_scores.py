#!/usr/bin/env python3
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[4]
import sys as _sys; _sys.path.insert(0, str(PROJECT_ROOT))
from wongchoi_paths import AU_RACING
ARCHIVE_ROOT = AU_RACING

sys.path.append(str(SCRIPT_DIR))
from au_auto_orchestrator import process_meeting_dir


def _corpus_meeting_dirs(root):
    """Meeting folders under `root` AND under `root/Archive`, oldest first.

    `root.iterdir()` used to be enough. It is not: the daily schedule files
    finished meetings into `<root>/Archive/`, and on 2026-08-21 that hid 751 of
    1,530 scored AU races (49.1%) — including 16 of the 17 dates that are clean
    point-in-time. Any number this harness printed before this change was
    measured on the older, post-race-rescored half of the corpus.
    """
    import sys as _sys
    from pathlib import Path as _Path
    _shared = _Path(__file__).resolve()
    for _ in range(6):
        _shared = _shared.parent
        _cand = _shared / "shared_racing" / "scripts"
        if (_cand / "corpus_paths.py").exists():
            if str(_cand) not in _sys.path:
                _sys.path.insert(0, str(_cand))
            break
    from corpus_paths import meeting_dirs as _meeting_dirs
    return sorted(_meeting_dirs(root))


def rebuild_all():
    count = 0
    # Process historical archive
    for meeting_dir in _corpus_meeting_dirs(ARCHIVE_ROOT):
        if not meeting_dir.is_dir():
            continue
        logic_files = list(meeting_dir.glob("Race_*_Logic.json"))
        if not logic_files:
            continue
        print(f"Rebuilding meeting: {meeting_dir.name}")
        try:
            process_meeting_dir(meeting_dir)
            count += 1
        except Exception as e:
            print(f"Error rebuilding {meeting_dir.name}: {e}")
            
    # Process today's meetings in project root
    for today_dir in sorted(PROJECT_ROOT.iterdir()):
        if not today_dir.is_dir() or not ("2026-05-22" in today_dir.name):
            continue
        logic_files = list(today_dir.glob("Race_*_Logic.json"))
        if not logic_files:
            continue
        print(f"Rebuilding today's meeting: {today_dir.name}")
        try:
            process_meeting_dir(today_dir)
            count += 1
        except Exception as e:
            print(f"Error rebuilding today's {today_dir.name}: {e}")
            
    print(f"Rebuilt {count} meeting directories.")

if __name__ == "__main__":
    rebuild_all()
