#!/usr/bin/env python3
"""
Re-score all archived AU races using the CURRENT engine code.
Reads cached Logic.json, re-runs Python engine, compares old vs new performance.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.append(str(SCRIPT_DIR / "racing_engine"))

from engine_core import RacingEngine

# Reuse shared helpers
sys.path.append(str(SCRIPT_DIR))
from au_target_gap_report import (
    ARCHIVE_ROOT,
    HISTORICAL_RESULTS_CSV,
    choose_track_rows,
    condition_bucket,
    detect_meeting_date,
    detect_meeting_track,
    load_historical_results,
    normalize_horse_name,
    parse_int,
    race_class_bucket,
    field_size_bucket,
)


def build_field_summary(horses: dict) -> dict:
    weights = []
    for horse in horses.values():
        try:
            weights.append(float(horse.get("weight")))
        except (TypeError, ValueError):
            continue
    return {
        "count": len(horses),
        "min_weight": min(weights) if weights else 0,
        "max_weight": max(weights) if weights else 0,
        "avg_weight": sum(weights) / len(weights) if weights else 0,
    }


def main():
    historical_results = load_historical_results(HISTORICAL_RESULTS_CSV)

    overall_old = {"races": 0, "gold": 0, "good": 0, "pass_": 0, "champion": 0,
                   "winner_top3": 0, "places": 0, "slots": 0,
                   "hits": {0: 0, 1: 0, 2: 0, 3: 0}}
    overall_new = {"races": 0, "gold": 0, "good": 0, "pass_": 0, "champion": 0,
                   "winner_top3": 0, "places": 0, "slots": 0,
                   "hits": {0: 0, 1: 0, 2: 0, 3: 0}}

    # Track per-condition improvements
    cond_new = defaultdict(lambda: {"races": 0, "pass_": 0, "gold": 0, "hits": {0: 0, 1: 0, 2: 0, 3: 0}})
    cond_old = defaultdict(lambda: {"races": 0, "pass_": 0, "gold": 0, "hits": {0: 0, 1: 0, 2: 0, 3: 0}})

    field_new = defaultdict(lambda: {"races": 0, "pass_": 0, "gold": 0, "hits": {0: 0, 1: 0, 2: 0, 3: 0}})
    field_old = defaultdict(lambda: {"races": 0, "pass_": 0, "gold": 0, "hits": {0: 0, 1: 0, 2: 0, 3: 0}})

    total = 0
    for meeting_dir in sorted(p for p in ARCHIVE_ROOT.iterdir() if p.is_dir()):
        logic_files = sorted(meeting_dir.glob("Race_*_Logic.json"),
                             key=lambda p: parse_int(p.stem.split("_")[1], 999))
        if not logic_files:
            continue
        sample = json.loads(logic_files[0].read_text(encoding="utf-8"))
        meeting_date = detect_meeting_date(meeting_dir)
        meeting_track = detect_meeting_track(meeting_dir, sample)
        if not meeting_date or not meeting_track:
            continue

        for logic_path in logic_files:
            logic = json.loads(logic_path.read_text(encoding="utf-8"))
            race_analysis = logic.get("race_analysis", {})
            race_no = parse_int(race_analysis.get("race_number")) or parse_int(logic_path.stem.split("_")[1])
            rows = choose_track_rows(historical_results.get((meeting_date, race_no), []), meeting_track)
            if not rows:
                continue
            lookup = {normalize_horse_name(row["horse_slug"]): row for row in rows}

            cond_bucket = condition_bucket(rows[0].get("condition", ""))
            field_bucket = field_size_bucket(len(rows))

            old_horses = []
            new_horses = []
            for hnum, horse in logic.get("horses", {}).items():
                row = lookup.get(normalize_horse_name(horse.get("horse_name")))
                if not row:
                    continue
                pya = horse.get("python_auto") or {}
                old_rank = float(pya.get("rank_score") or pya.get("ability_score") or 0)
                actual_pos = int(row["pos"])

                # Re-run engine
                data = horse.get("_data", {}) if isinstance(horse.get("_data"), dict) else {}
                facts = data.get("facts_section", "")
                race_context = dict(race_analysis)
                race_context["field_summary"] = build_field_summary(logic.get("horses", {}))
                engine = RacingEngine(horse, race_context, facts_section=facts)
                result = engine.analyze_horse()
                new_rank = float(result.get("rank_score") or result.get("ability_score") or 0)

                old_horses.append({"score": old_rank, "actual": actual_pos})
                new_horses.append({"score": new_rank, "actual": actual_pos})

            if len(old_horses) < 4:
                continue
            total += 1

            # Evaluate old
            old_ranked = sorted(old_horses, key=lambda h: (-h["score"],))
            old_top3 = old_ranked[:3]
            old_top2 = old_ranked[:2]
            old_hits3 = sum(1 for h in old_top3 if h["actual"] <= 3)
            old_hits2 = sum(1 for h in old_top2 if h["actual"] <= 3)

            # Evaluate new
            new_ranked = sorted(new_horses, key=lambda h: (-h["score"],))
            new_top3 = new_ranked[:3]
            new_top2 = new_ranked[:2]
            new_hits3 = sum(1 for h in new_top3 if h["actual"] <= 3)
            new_hits2 = sum(1 for h in new_top2 if h["actual"] <= 3)

            for (ov, nv, ch, nh, b) in [
                (overall_old, overall_new, old_hits3, new_hits3, None),
            ]:
                ov["races"] += 1; nv["races"] += 1
                ov["places"] += ch; nv["places"] += nh
                ov["slots"] += 3; nv["slots"] += 3
                ov["hits"][ch] += 1; nv["hits"][nh] += 1
                if ch == 3: ov["gold"] += 1
                if nh == 3: nv["gold"] += 1
                if old_hits2 == 2: ov["good"] += 1
                if new_hits2 == 2: nv["good"] += 1
                if ch >= 2: ov["pass_"] += 1
                if nh >= 2: nv["pass_"] += 1
                if old_ranked[0]["actual"] == 1: ov["champion"] += 1
                if new_ranked[0]["actual"] == 1: nv["champion"] += 1
                if any(h["actual"] == 1 for h in old_top3): ov["winner_top3"] += 1
                if any(h["actual"] == 1 for h in new_top3): nv["winner_top3"] += 1

            # Per-condition
            for cb, ov_d, nv_d in [(cond_bucket, cond_old[cond_bucket], cond_new[cond_bucket]),
                                     (field_bucket, field_old[field_bucket], field_new[field_bucket])]:
                ov_d["races"] += 1; nv_d["races"] += 1
                ov_d["hits"][old_hits3] += 1; nv_d["hits"][new_hits3] += 1
                if old_hits3 == 3: ov_d["gold"] += 1
                if new_hits3 == 3: nv_d["gold"] += 1
                if old_hits3 >= 2: ov_d["pass_"] += 1
                if new_hits3 >= 2: nv_d["pass_"] += 1

    # ── Report ──
    def pct(part, whole):
        return f"{part / whole * 100:.1f}%" if whole else "N/A"

    print(f"\n{'='*70}")
    print(f"📊 AU ENGINE RE-SCORE — {total} races re-scored")
    print(f"{'='*70}")
    print()

    def print_row(label, old, new, key, divisor="races"):
        od = old[key] / old.get(divisor, old[key]) if isinstance(old[key], int) else 0
        nd = new[key] / new.get(divisor, new[key]) if isinstance(new[key], int) else 0
        if divisor == "races":
            oval = pct(old[key], old["races"])
            nval = pct(new[key], new["races"])
        else:
            oval = pct(old[key], old[divisor])
            nval = pct(new[key], new[divisor])
        delta = f"+{nd*100 - od*100:+.1f}pp" if od and nd else ""
        print(f"  {label:<30} | Old: {oval:>6} | New: {nval:>6} | Δ: {delta:>8}")

    print("═══ OVERALL ═══")
    print_row("Gold (3/3)", overall_old, overall_new, "gold")
    print_row("Good (Top1+2 in Top3)", overall_old, overall_new, "good")
    print_row("Pass (≥2 in Top3)", overall_old, overall_new, "pass_")
    print_row("Champion (Top1 wins)", overall_old, overall_new, "champion")
    print_row("Top3 Contains Winner", overall_old, overall_new, "winner_top3")
    print_row("Top3 Place Precision", overall_old, overall_new, "places", "slots")
    print()
    print(f"  Hit Distribution:")
    for h in (0, 1, 2, 3):
        o = overall_old["hits"][h]
        n = overall_new["hits"][h]
        diff = n - o
        sign = "+" if diff >= 0 else ""
        print(f"    {h}-hit: {o:>3} → {n:>3}  ({sign}{diff})")

    print()
    print("═══ BY CONDITION ═══")
    for cond in ("Good/Firm", "Soft", "Heavy"):
        o = cond_old.get(cond, {})
        n = cond_new.get(cond, {})
        if not o.get("races"):
            continue
        r = o["races"]
        print(f"  --- {cond} ({r} races) ---")
        print_row("  Gold", o, n, "gold")
        print_row("  Pass", o, n, "pass_")
        for h in (0, 1, 2, 3):
            od = o["hits"].get(h, 0)
            nd = n["hits"].get(h, 0)
            diff = nd - od
            sign = "+" if diff >= 0 else ""
            if diff != 0:
                print(f"    {h}-hit: {od:>3} → {nd:>3}  ({sign}{diff})")

    print()
    print("═══ BY FIELD SIZE ═══")
    for fs in ("Field <=8", "Field 9-12", "Field 13+"):
        o = field_old.get(fs, {})
        n = field_new.get(fs, {})
        if not o.get("races"):
            continue
        r = o["races"]
        print(f"  --- {fs} ({r} races) ---")
        print_row("  Gold", o, n, "gold")
        print_row("  Pass", o, n, "pass_")
        for h in (0, 1, 2, 3):
            od = o["hits"].get(h, 0)
            nd = n["hits"].get(h, 0)
            diff = nd - od
            sign = "+" if diff >= 0 else ""
            if diff != 0:
                print(f"    {h}-hit: {od:>3} → {nd:>3}  ({sign}{diff})")


if __name__ == "__main__":
    main()
