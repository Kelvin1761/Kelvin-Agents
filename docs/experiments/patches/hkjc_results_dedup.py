"""De-duplicated day loader for `HKJC_Race_Results_Database` scans.

From 2026-05 onward every race day in the database has two identical copies
(`<date>_<venue>_全日賽果.json` and `full_day_results.json`): 350 races, all
byte-for-byte the same runners.  `hkjc_situational_overlay_scan.load_days`
globs `*/*.json` and so counts each of those races twice.  Found in
EXP-20261110-07; this loader keeps one copy per (racedate, venue, race_no).
"""
from __future__ import annotations

import glob
import json
from collections import defaultdict
from pathlib import Path

from hkjc_situational_overlay_scan import DB, VENUE


def load_days():
    days, seen = defaultdict(list), set()
    for path in sorted(glob.glob(str(DB / "hkjc results */*/*.json"))):
        for race in json.loads(Path(path).read_text(encoding="utf-8")).values():
            if not isinstance(race, dict) or not race.get("racedate"):
                continue
            key = (race["racedate"], VENUE.get(race.get("venue"), race.get("venue")), str(race.get("race_no")))
            if key in seen:
                continue
            seen.add(key)
            days[race["racedate"]].append(race)
    return dict(sorted(days.items()))
