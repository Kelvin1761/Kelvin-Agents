#!/usr/bin/env python3
"""One definition of "where the scored races live".

WHY THIS EXISTS
---------------
The AU daily schedule moves finished meetings into `<root>/Archive/`.  Most
harnesses enumerate with `<root>/*/Race_*_Logic.json` or `root.iterdir()`, which
only sees one level — so 2026-08-21 measured **751 of 1,530 scored races (49.1%)
invisible to every evaluation tool**, with zero overlap between the two halves.

The damage is not merely "half the data":

    top level   89 meetings  779 races  64 dates   1 date  on/after 2026-08-05
    Archive/    96 meetings  751 races  21 dates  16 dates on/after 2026-08-05

Only races scored on/after 2026-08-05 are clean point-in-time (older ones were
re-scored after the fact).  So the ONLY trustworthy corpus was almost entirely
in the half nobody was reading.

`rglob` is the WRONG fix.  HKJC nests real backup directories
(`_pre_v52_backup`, `.backup_before_trackwork_fix`, and one self-nested meeting),
so recursing would silently promote backups to corpus and double-count a
meeting.  AU's depth distribution is clean — 779 at depth 2, 751 at depth 3,
every one of the latter under `Archive` — so scanning exactly the two known
roots is both complete and safe.

Matches the pattern already used by `au_results_ingest.py` and
`au_paired_significance.py`, and is a no-op for HKJC.
"""
from __future__ import annotations

import glob
import re
from pathlib import Path

# Directory names that hold finished meetings rather than a different corpus.
ARCHIVE_DIRNAMES = ("Archive",)

# A meeting folder always starts with its date. The data roots also contain
# reference folders (`Official_Free_Data`, `HKJC_Race_Results_Database`, ...)
# which are not meetings and must not be counted as corpus.
MEETING_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}")


def corpus_roots(root: Path | str) -> list[Path]:
    """The directories whose immediate children are meeting folders."""
    root = Path(root)
    roots = [root]
    for name in ARCHIVE_DIRNAMES:
        candidate = root / name
        try:
            if candidate.is_dir():
                roots.append(candidate)
        except OSError:
            continue
    return roots


def logic_files(root: Path | str, pattern: str = "Race_*_Logic.json") -> list[str]:
    """Every scored-race file under `root`, including archived meetings.

    Sorted newest-meeting-first so a caller taking the first N gets the most
    recent races — which, given the corpus history above, is also the only
    portion that is clean point-in-time.
    """
    seen: dict[str, None] = {}
    for base in corpus_roots(root):
        for path in glob.glob(str(base / "*" / pattern)):
            seen.setdefault(path, None)
    # Meeting folder name starts with the date, so sorting on it sorts by date.
    return sorted(seen, key=lambda p: (Path(p).parent.name, Path(p).name), reverse=True)


def meeting_dirs(root: Path | str) -> list[Path]:
    """Every meeting folder under `root`, including archived ones."""
    out: dict[str, Path] = {}
    for base in corpus_roots(root):
        try:
            entries = sorted(base.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_dir() and MEETING_NAME.match(entry.name):
                out.setdefault(entry.name, entry)
    return [out[k] for k in sorted(out, reverse=True)]
