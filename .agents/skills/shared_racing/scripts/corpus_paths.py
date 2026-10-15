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

EXCLUSIONS (2026-10-15)
-----------------------
AU meetings listed in `resources/au_corpus_exclusions.json` are skipped by
`meeting_dirs` and `logic_files` (EXP-20261015-04: extracted after the races,
so page cumulative stats leak the result).  Each call that drops something
prints one stderr line per process with the count and reasons; the last
report is in `last_exclusion_report`.  Pass `include_excluded=True` only for
maintenance/audit tools that must see every folder (e.g. the detector).
"""
from __future__ import annotations

import glob
import re
import sys
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


last_exclusion_report: dict = {}
_reported: set = set()


def _exclusions_for_root(root: Path | str) -> dict[str, dict]:
    if Path(root).name.lower() != "au_racing":
        return {}
    here = str(Path(__file__).resolve().parent)
    if here not in sys.path:
        sys.path.insert(0, here)
    from corpus_exclusions import load_exclusions

    return load_exclusions("au")


def _note_exclusions(root: Path | str, dropped: list[str], exclusions: dict) -> None:
    reasons: dict[str, int] = {}
    for name in dropped:
        reason = exclusions[name].get("reason", "?")
        reasons[reason] = reasons.get(reason, 0) + 1
    last_exclusion_report.clear()
    last_exclusion_report.update({"root": str(root), "excluded": sorted(dropped),
                                  "reasons": reasons})
    key = (str(root), tuple(sorted(dropped)))
    if dropped and key not in _reported:
        _reported.add(key)
        detail = "、".join(f"{r} ×{n}" for r, n in sorted(reasons.items()))
        print(f"corpus_paths：語料排除 {len(dropped)} 個場次（{detail}；"
              "見 shared_racing/resources/au_corpus_exclusions.json）", file=sys.stderr)


def logic_files(root: Path | str, pattern: str = "Race_*_Logic.json",
                include_excluded: bool = False) -> list[str]:
    """Every scored-race file under native roots plus verified catalog WARM.

    Sorted newest-meeting-first so a caller taking the first N gets the most
    recent races — which, given the corpus history above, is also the only
    portion that is clean point-in-time.
    """
    seen: dict[str, None] = {}
    for base in corpus_roots(root):
        for path in glob.glob(str(base / "*" / pattern)):
            seen.setdefault(path, None)
    # For registered meetings, only the content-verified resolved copy is valid.
    # Empty/corrupt native folders must not mask a valid WARM copy. Unregistered
    # native enumeration (including legacy non-date names) stays unchanged.
    for logical_name, meeting in _au_catalog_meetings(root):
        if MEETING_NAME.match(logical_name):
            seen = {path: value for path, value in seen.items()
                    if Path(path).parent.name != logical_name}
            for path in glob.glob(str(meeting / pattern)):
                seen.setdefault(path, None)
    if not include_excluded:
        exclusions = _exclusions_for_root(root)
        if exclusions:
            dropped = {Path(p).parent.name for p in seen if Path(p).parent.name in exclusions}
            seen = {p: v for p, v in seen.items() if Path(p).parent.name not in exclusions}
            _note_exclusions(root, sorted(dropped), exclusions)
    # Meeting folder name starts with the date, so sorting on it sorts by date.
    return sorted(seen, key=lambda p: (Path(p).parent.name, Path(p).name), reverse=True)


def _au_catalog_meetings(root: Path | str) -> list[tuple[str, Path]]:
    if Path(root).name.lower() != "au_racing":
        return []
    skills_root = Path(__file__).resolve().parents[2]
    if str(skills_root) not in sys.path:
        sys.path.insert(0, str(skills_root))
    from shared_wong_choi.corpus_catalog import catalog_meeting_locations

    return catalog_meeting_locations(domain="au")


def meeting_dirs(root: Path | str, include_excluded: bool = False) -> list[Path]:
    """Every meeting folder under HOT plus verified catalog-backed WARM.

    AU is inferred from its canonical root name.  Once any settled meeting is
    archived through Central, a missing/corrupt known copy raises instead of
    returning a smaller corpus.  Domains with different storage shapes opt in
    through their own reader rather than being guessed here.
    """
    out: dict[str, Path] = {}
    for base in corpus_roots(root):
        try:
            entries = sorted(base.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_dir() and MEETING_NAME.match(entry.name):
                out.setdefault(entry.name, entry)
    for logical_name, path in _au_catalog_meetings(root):
        if MEETING_NAME.match(logical_name):
            out[logical_name] = path
    if not include_excluded:
        exclusions = _exclusions_for_root(root)
        if exclusions:
            dropped = sorted(k for k in out if k in exclusions)
            for k in dropped:
                del out[k]
            _note_exclusions(root, dropped, exclusions)
    return [out[k] for k in sorted(out, reverse=True)]
