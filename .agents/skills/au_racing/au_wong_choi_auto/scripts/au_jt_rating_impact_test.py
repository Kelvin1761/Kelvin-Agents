#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.append(str(SCRIPT_DIR / "racing_engine"))
import engine_core  # noqa: E402
from engine_core import RacingEngine  # noqa: E402

sys.path.append(str(SCRIPT_DIR))
from au_target_gap_report import (  # noqa: E402
    ARCHIVE_ROOT,
    HISTORICAL_RESULTS_CSV,
    choose_track_rows,
    condition_bucket,
    detect_meeting_date,
    detect_meeting_track,
    field_size_bucket,
    load_historical_results,
    normalize_horse_name,
    parse_int,
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


def new_bucket():
    return {
        "races": 0,
        "gold": 0,
        "good": 0,
        "pass_": 0,
        "champion": 0,
        "winner_top3": 0,
        "places": 0,
        "slots": 0,
        "hits": {0: 0, 1: 0, 2: 0, 3: 0},
    }


def evaluate_archive(use_named_db: bool):
    original_loader = engine_core._load_named_rating_stats
    if not use_named_db:
        engine_core._load_named_rating_stats = lambda: ({}, {})
    historical_results = load_historical_results(HISTORICAL_RESULTS_CSV)
    overall = new_bucket()
    by_condition = defaultdict(new_bucket)
    by_field = defaultdict(new_bucket)
    total = 0
    try:
        for meeting_dir in sorted(p for p in ARCHIVE_ROOT.iterdir() if p.is_dir()):
            logic_files = sorted(
                meeting_dir.glob("Race_*_Logic.json"),
                key=lambda p: parse_int(p.stem.split("_")[1], 999),
            )
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
                race_context = dict(race_analysis)
                race_context["field_summary"] = build_field_summary(logic.get("horses", {}))
                scored = []
                for horse_num, horse in logic.get("horses", {}).items():
                    row = lookup.get(normalize_horse_name(horse.get("horse_name")))
                    if not row:
                        continue
                    engine = RacingEngine(
                        horse,
                        race_context,
                        facts_section=(horse.get("_data") or {}).get("facts_section", ""),
                    )
                    result = engine.analyze_horse()
                    scored.append(
                        {
                            "horse_number": parse_int(horse_num) or parse_int(horse.get("horse_number")) or parse_int(horse.get("number")) or 999,
                            "score": float(result.get("rank_score") or result.get("ability_score") or 0.0),
                            "actual": int(row["pos"]),
                        }
                    )
                if len(scored) < 4:
                    continue
                total += 1
                ranked = sorted(scored, key=lambda item: (-item["score"], item["horse_number"]))
                top3 = ranked[:3]
                top2 = ranked[:2]
                hits3 = sum(1 for item in top3 if item["actual"] <= 3)
                hits2 = sum(1 for item in top2 if item["actual"] <= 3)
                cond = condition_bucket(rows[0].get("condition", ""))
                field = field_size_bucket(len(rows))
                for bucket in (overall, by_condition[cond], by_field[field]):
                    bucket["races"] += 1
                    bucket["places"] += hits3
                    bucket["slots"] += 3
                    bucket["hits"][hits3] += 1
                    if hits3 == 3:
                        bucket["gold"] += 1
                    if hits2 == 2:
                        bucket["good"] += 1
                    if hits3 >= 2:
                        bucket["pass_"] += 1
                    if ranked[0]["actual"] == 1:
                        bucket["champion"] += 1
                    if any(item["actual"] == 1 for item in top3):
                        bucket["winner_top3"] += 1
    finally:
        engine_core._load_named_rating_stats = original_loader
    return total, overall, by_condition, by_field


def pct(part: int, whole: int) -> float:
    return (part / whole * 100.0) if whole else 0.0


def print_comparison(label: str, old: dict, new: dict, key: str, divisor: str = "races"):
    old_pct = pct(old[key], old[divisor])
    new_pct = pct(new[key], new[divisor])
    delta = new_pct - old_pct
    print(f"{label:<28} | Off {old_pct:>5.1f}% | On {new_pct:>5.1f}% | Δ {delta:+.1f}pp")


def main():
    total_off, off, off_cond, off_field = evaluate_archive(use_named_db=False)
    total_on, on, on_cond, on_field = evaluate_archive(use_named_db=True)
    total = min(total_off, total_on)

    print(f"\n{'=' * 72}")
    print(f"AU JT RATING DB IMPACT TEST — {total} races")
    print(f"{'=' * 72}")
    print("\n═══ OVERALL ═══")
    print_comparison("Gold (3/3)", off, on, "gold")
    print_comparison("Good (Top2 hit)", off, on, "good")
    print_comparison("Pass (>=2 in Top3)", off, on, "pass_")
    print_comparison("Champion", off, on, "champion")
    print_comparison("Winner in Top3", off, on, "winner_top3")
    print_comparison("Top3 Place Precision", off, on, "places", "slots")

    print("\nHit Distribution")
    for hits in (0, 1, 2, 3):
        off_hits = off["hits"][hits]
        on_hits = on["hits"][hits]
        print(f"  {hits}-hit: {off_hits:>3} -> {on_hits:>3} ({on_hits - off_hits:+d})")

    print("\n═══ BY CONDITION ═══")
    for cond in ("Good/Firm", "Soft", "Heavy"):
        if not off_cond.get(cond, {}).get("races"):
            continue
        print(f"\n[{cond}] {off_cond[cond]['races']} races")
        print_comparison("Pass", off_cond[cond], on_cond[cond], "pass_")
        print_comparison("Gold", off_cond[cond], on_cond[cond], "gold")

    print("\n═══ BY FIELD SIZE ═══")
    for field in ("Field <=8", "Field 9-12", "Field 13+"):
        if not off_field.get(field, {}).get("races"):
            continue
        print(f"\n[{field}] {off_field[field]['races']} races")
        print_comparison("Pass", off_field[field], on_field[field], "pass_")
        print_comparison("Gold", off_field[field], on_field[field], "gold")


if __name__ == "__main__":
    main()
