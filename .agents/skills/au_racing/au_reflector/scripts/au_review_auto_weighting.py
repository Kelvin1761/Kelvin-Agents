#!/usr/bin/env python3
"""
AU auto weighting review baseline.
Scans AU archive meetings dynamically and evaluates current live deterministic outputs.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[5]
sys.path.append(str(PROJECT_ROOT / ".agents" / "scripts"))

from reflector_auto_stats import run_stats


HK_EXCLUDE_TOKENS = (
    "ShaTin",
    "Sha Tin",
    "HappyValley",
    "Happy Valley",
    "HKJC",
)


def find_au_meetings(base_dir: pathlib.Path) -> list[pathlib.Path]:
    meetings = []
    for path in sorted(base_dir.iterdir()):
        if not path.is_dir():
            continue
        if any(token in path.name for token in HK_EXCLUDE_TOKENS):
            continue
        has_logic = bool(list(path.glob("Race_*_Logic.json")))
        has_au_artifacts = bool(list(path.glob("*Racecard.md"))) or bool(list(path.glob("*Formguide.md"))) or bool(list(path.glob("*Facts.md")))
        has_results = bool(meeting_results_file(path))
        if has_logic and has_au_artifacts and has_results:
            meetings.append(path)
    return meetings


def meeting_results_file(meeting_dir: pathlib.Path) -> pathlib.Path | None:
    md_results = sorted(meeting_dir.glob("Race_Results_Reflector.md"))
    if md_results:
        return md_results[0]
    json_results = sorted(meeting_dir.glob("Race_Results_*.json"))
    return json_results[0] if json_results else None


def summarize_stats(stats: dict) -> dict:
    summary = stats.get("summary", {})
    races = stats.get("races", [])
    total = summary.get("total_races", 0)
    champ = summary.get("champion_hit_rates", {}).get("top1_champion", {}).get("count", 0)
    gold = summary.get("position_hit_rates", {}).get("gold_standard", {}).get("count", 0)
    good = summary.get("position_hit_rates", {}).get("good_result", {}).get("count", 0)
    minimum = summary.get("position_hit_rates", {}).get("min_threshold", {}).get("count", 0)
    order_issue = summary.get("ranking_order", {}).get("pick34_beat_12", {}).get("count", 0)
    avg_top4_hits = 0.0
    mrr = 0.0
    if races and total:
        hit_sum = 0.0
        rr_sum = 0.0
        for race in races:
            top_picks = race.get("top_picks", [])
            actual_top3 = race.get("actual_top3", [])
            actual_pos = {row[1]: row[0] for row in actual_top3}
            hit_sum += sum(1 for pick in top_picks[:4] if pick[1] in actual_pos)
            winner = actual_top3[0][1] if actual_top3 else None
            rr = 0.0
            for idx, pick in enumerate(top_picks[:4], start=1):
                if pick[1] == winner:
                    rr = 1.0 / idx
                    break
            rr_sum += rr
        avg_top4_hits = round(hit_sum / total, 3)
        mrr = round(rr_sum / total, 4)
    return {
        "meetings": None,
        "races": total,
        "Champion": champ,
        "Gold": gold,
        "Good": good,
        "Minimum": minimum,
        "MRR": mrr,
        "Order Issue": order_issue,
        "Avg Top4 Hits": avg_top4_hits,
    }


def run_review(base_dir: pathlib.Path) -> dict:
    meetings = find_au_meetings(base_dir)
    aggregate = {
        "meetings": len(meetings),
        "races": 0,
        "Champion": 0,
        "Gold": 0,
        "Good": 0,
        "Minimum": 0,
        "MRR": 0.0,
        "Order Issue": 0,
        "Avg Top4 Hits": 0.0,
    }
    mrr_weighted = 0.0
    top4_weighted = 0.0
    total_races = 0
    details = []
    for meeting in meetings:
        results_file = meeting_results_file(meeting)
        if not results_file:
            continue
        stats = run_stats(str(meeting), str(results_file))
        summary = summarize_stats(stats)
        races = summary["races"]
        if not races:
            continue
        total_races += races
        aggregate["Champion"] += summary["Champion"]
        aggregate["Gold"] += summary["Gold"]
        aggregate["Good"] += summary["Good"]
        aggregate["Minimum"] += summary["Minimum"]
        aggregate["Order Issue"] += summary["Order Issue"]
        mrr_weighted += summary["MRR"] * races
        top4_weighted += summary["Avg Top4 Hits"] * races
        details.append({"meeting": meeting.name, **summary})
    aggregate["races"] = total_races
    aggregate["MRR"] = round(mrr_weighted / total_races, 4) if total_races else 0.0
    aggregate["Avg Top4 Hits"] = round(top4_weighted / total_races, 3) if total_races else 0.0
    return {"current_live": aggregate, "details": details}


def main():
    parser = argparse.ArgumentParser(description="Review AU current live deterministic weighting baseline")
    parser.add_argument("--base-dir", default=str(PROJECT_ROOT / "Archive_Race_Analysis"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run_review(pathlib.Path(args.base_dir))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    current = report["current_live"]
    print("current_live")
    for key in ("meetings", "races", "Champion", "Gold", "Good", "Minimum", "MRR", "Order Issue", "Avg Top4 Hits"):
        print(f"{key} {current[key]}")


if __name__ == "__main__":
    main()
