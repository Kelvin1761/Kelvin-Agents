#!/usr/bin/env python3
"""Quantify the Benbulben failure mode across the AU archive.

Question: when the model's top pick rests on STALE evidence (last official run a
long time ago) or on a THIN evidence window (very few official runs / very few PI
runs), does it under-perform its own baseline?

Read-only.  Writes a JSON summary to scratch/.
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


def parse_iso(text):
    match = ISO.search(str(text or ""))
    if not match:
        return None
    try:
        return date(*(int(part) for part in match.groups()))
    except ValueError:
        return None


def spell_days(row):
    """Days between the horse's last official run and this meeting."""
    data = row["data"]
    latest = parse_iso(data.get("latest_official_date"))
    meeting = parse_iso(row["date"])
    if not latest or not meeting:
        return None
    return max(0, (meeting - latest).days)


def pi_run_count(row):
    """How many official runs actually carried a PI value (drives sectional_score)."""
    trend = str(row["data"].get("sectional_trend_line") or "")
    head = trend.split("L400")[0]
    return len(re.findall(r"[+-]\d+", head))


def formal_count(row):
    value = row["data"].get("formal_count")
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def bucket_spell(days):
    if days is None:
        return "unknown"
    if days <= 45:
        return "a_0-45d"
    if days <= 90:
        return "b_46-90d"
    if days <= 180:
        return "c_91-180d"
    if days <= 365:
        return "d_181-365d"
    return "e_365d+"


def main():
    results = load_historical_results(HISTORICAL_RESULTS_CSV)
    # cohort -> counters, measured on the model's TOP PICK of each race
    top = defaultdict(lambda: {"n": 0, "win": 0, "top3": 0, "last_third": 0,
                               "pos_sum": 0, "field_sum": 0, "sp_sum": 0.0, "sp_n": 0})
    # and on every runner, for a rank-vs-result sanity view
    allr = defaultdict(lambda: {"n": 0, "top3": 0})
    races = 0

    for race_rows in iter_logic_rows(ARCHIVE_ROOT, results):
        races += 1
        field = len(race_rows)
        ranked = sorted(race_rows, key=lambda r: (-r["model_score"], r["horse_number"]))
        pick = ranked[0]

        for row in race_rows:
            b = bucket_spell(spell_days(row))
            allr[b]["n"] += 1
            allr[b]["top3"] += 1 if row["actual_pos"] <= 3 else 0

        for label, cohort in (
            (bucket_spell(spell_days(pick)), "spell"),
            (f"pi_runs_{min(pi_run_count(pick), 4)}", "pi"),
            (f"formal_{min(formal_count(pick), 5)}" if formal_count(pick) is not None else "formal_unknown", "formal"),
            ("ALL", "all"),
        ):
            key = f"{cohort}:{label}"
            entry = top[key]
            entry["n"] += 1
            entry["win"] += 1 if pick["actual_pos"] == 1 else 0
            entry["top3"] += 1 if pick["actual_pos"] <= 3 else 0
            entry["last_third"] += 1 if pick["actual_pos"] > field * 2 / 3 else 0
            entry["pos_sum"] += pick["actual_pos"]
            entry["field_sum"] += field
            if pick["sp"]:
                entry["sp_sum"] += float(pick["sp"])
                entry["sp_n"] += 1

    out = {"races": races, "top_pick": {}, "all_runners": {}}
    for key, e in sorted(top.items()):
        if not e["n"]:
            continue
        out["top_pick"][key] = {
            "n": e["n"],
            "win_pct": round(100 * e["win"] / e["n"], 1),
            "top3_pct": round(100 * e["top3"] / e["n"], 1),
            "bottom_third_pct": round(100 * e["last_third"] / e["n"], 1),
            "avg_pos": round(e["pos_sum"] / e["n"], 2),
            "avg_field": round(e["field_sum"] / e["n"], 1),
            "avg_sp": round(e["sp_sum"] / e["sp_n"], 1) if e["sp_n"] else None,
        }
    for key, e in sorted(allr.items()):
        if not e["n"]:
            continue
        out["all_runners"][key] = {"n": e["n"], "top3_pct": round(100 * e["top3"] / e["n"], 1)}

    dest = Path(__file__).with_suffix(".json")
    dest.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
