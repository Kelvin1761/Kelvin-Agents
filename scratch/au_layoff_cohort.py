#!/usr/bin/env python3
"""Layoff (spell) cohort audit for AU top picks — reads the date out of the
persisted Facts record table when `latest_official_date` is blank.

Read-only.  Writes scratch/au_layoff_cohort.json.
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR / "racing_engine"))

from au_archive_calibrator import (  # noqa: E402
    ARCHIVE_ROOT,
    HISTORICAL_RESULTS_CSV,
    iter_logic_rows,
    load_historical_results,
)

ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
# A formal (non-trial) row of the persisted Facts record table.
FORMAL_ROW = re.compile(r"^\|\s*\d+\s*\|\s*([^|]*?)\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|(.*)$")


def parse_iso(text):
    m = ISO.search(str(text or ""))
    if not m:
        return None
    try:
        return date(*(int(p) for p in m.groups()))
    except ValueError:
        return None


def last_official_date(row):
    """Most recent NON-trial run date: explicit field first, Facts table fallback."""
    data = row["data"]
    explicit = parse_iso(data.get("latest_official_date"))
    if explicit:
        return explicit, "field"
    best = None
    for line in str(data.get("facts_section") or "").splitlines():
        m = FORMAL_ROW.match(line.strip())
        if not m:
            continue
        kind, iso, rest = m.group(1), m.group(2), m.group(3)
        if "試閘" in kind or "TRIAL" in rest.upper():
            continue
        parsed = parse_iso(iso)
        if parsed and (best is None or parsed > best):
            best = parsed
    return (best, "facts") if best else (None, "none")


def bucket(days):
    if days is None:
        return "z_unknown"
    for limit, label in ((45, "a_0-45d"), (90, "b_46-90d"), (180, "c_91-180d"),
                         (365, "d_181-365d")):
        if days <= limit:
            return label
    return "e_365d+"


def main():
    results = load_historical_results(HISTORICAL_RESULTS_CSV)
    top = defaultdict(lambda: {"n": 0, "win": 0, "top3": 0, "bot": 0,
                               "pos": 0, "sp": 0.0, "spn": 0})
    allr = defaultdict(lambda: {"n": 0, "top3": 0})
    src = defaultdict(int)
    races = 0
    worst = []

    for race_rows in iter_logic_rows(ARCHIVE_ROOT, results):
        races += 1
        field = len(race_rows)
        pick = sorted(race_rows, key=lambda r: (-r["model_score"], r["horse_number"]))[0]

        for row in race_rows:
            d, how = last_official_date(row)
            src[how] += 1
            days = (parse_iso(row["date"]) - d).days if d and parse_iso(row["date"]) else None
            b = bucket(days)
            allr[b]["n"] += 1
            allr[b]["top3"] += 1 if row["actual_pos"] <= 3 else 0

        d, _ = last_official_date(pick)
        mdate = parse_iso(pick["date"])
        days = (mdate - d).days if d and mdate else None
        for key in (bucket(days), "ALL"):
            e = top[key]
            e["n"] += 1
            e["win"] += 1 if pick["actual_pos"] == 1 else 0
            e["top3"] += 1 if pick["actual_pos"] <= 3 else 0
            e["bot"] += 1 if pick["actual_pos"] > field * 2 / 3 else 0
            e["pos"] += pick["actual_pos"]
            if pick["sp"]:
                e["sp"] += float(pick["sp"])
                e["spn"] += 1
        if days is not None and days > 180:
            worst.append({"meeting": pick["meeting"], "race": pick["race"],
                          "horse": pick["horse_name"], "spell_days": days,
                          "pos": pick["actual_pos"], "field": field, "sp": pick["sp"]})

    out = {"races": races, "date_source": dict(src), "top_pick": {}, "all_runners": {},
           "long_layoff_top_picks": sorted(worst, key=lambda r: -r["spell_days"])}
    for k, e in sorted(top.items()):
        out["top_pick"][k] = {
            "n": e["n"],
            "win_pct": round(100 * e["win"] / e["n"], 1),
            "top3_pct": round(100 * e["top3"] / e["n"], 1),
            "bottom_third_pct": round(100 * e["bot"] / e["n"], 1),
            "avg_pos": round(e["pos"] / e["n"], 2),
            "avg_sp": round(e["sp"] / e["spn"], 1) if e["spn"] else None,
        }
    for k, e in sorted(allr.items()):
        out["all_runners"][k] = {"n": e["n"], "top3_pct": round(100 * e["top3"] / e["n"], 1)}

    Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "long_layoff_top_picks"}, indent=2))
    print("\nlong-layoff top picks (>180d):")
    for r in out["long_layoff_top_picks"][:25]:
        print(f"  {r['spell_days']:>5}d  {r['meeting'][:34]:34} R{r['race']:<2} "
              f"{r['horse'][:20]:20} pos {r['pos']}/{r['field']} SP {r['sp']}")


if __name__ == "__main__":
    main()
