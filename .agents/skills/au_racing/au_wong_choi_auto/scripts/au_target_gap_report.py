#!/usr/bin/env python3
from __future__ import annotations

import math
from collections import defaultdict

from au_archive_calibrator import (
    ARCHIVE_ROOT,
    HISTORICAL_RESULTS_CSV,
    iter_logic_rows,
    load_historical_results,
    parse_int,
)

OUTPUT_MD = ARCHIVE_ROOT / "AU_Auto_Target_Gap_Report.md"

TARGETS = {
    "gold_rate": 0.30,
    "good_rate": 0.40,
    "minimum_rate": 0.60,
    "top3_place_precision": 0.80,
}


def race_class_bucket(text: str) -> str:
    value = str(text or "").lower()
    if "group 1" in value:
        return "Group 1"
    if "group 2" in value or "group 3" in value:
        return "Group 2/3"
    if "listed" in value:
        return "Listed"
    if "maiden" in value:
        return "Maiden"
    if "bm" in value:
        rating = parse_int(value, 0) or 0
        if rating >= 88:
            return "BM88+"
        if rating >= 72:
            return "BM72-84"
        return "BM58-70"
    return "Other"


def field_size_bucket(size: int) -> str:
    if size <= 8:
        return "Field <=8"
    if size <= 12:
        return "Field 9-12"
    return "Field 13+"


def condition_bucket(text: str) -> str:
    value = str(text or "").strip().lower()
    if value.startswith(("good", "firm")):
        return "Good/Firm"
    if value.startswith("soft"):
        return "Soft"
    if value.startswith("heavy"):
        return "Heavy"
    return "Other"


def new_bucket():
    return {
        "races": 0,
        "champion": 0,
        "gold": 0,
        "good": 0,
        "minimum": 0,
        "winner_in_top3": 0,
        "top3_places": 0,
        "top3_slots": 0,
        "hit_distribution": {0: 0, 1: 0, 2: 0, 3: 0},
    }


def rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def gap_count(target_rate: float, actual_count: int, total: int) -> int:
    return max(0, math.ceil(target_rate * total) - actual_count)


def iter_ability_races():
    historical_results = load_historical_results(HISTORICAL_RESULTS_CSV)
    for race_rows in iter_logic_rows(ARCHIVE_ROOT, historical_results):
        yield {
            "meeting": race_rows[0]["meeting"],
            "race": race_rows[0]["race"],
            "race_class_bucket": race_class_bucket(race_rows[0].get("race_class")),
            "field_size_bucket": field_size_bucket(len(race_rows)),
            "condition_bucket": condition_bucket(race_rows[0].get("condition")),
            "horses": [
                {
                    "horse_number": row["horse_number"],
                    "score": float(row["model_score"]),
                    "actual_pos": int(row["actual_pos"]),
                    "condition_bucket": condition_bucket(row.get("condition")),
                }
                for row in race_rows
            ],
        }


def collect_metrics():
    overall = new_bucket()
    by_condition = defaultdict(new_bucket)
    by_race_class = defaultdict(new_bucket)
    by_field_size = defaultdict(new_bucket)

    for race in iter_ability_races():
        ranked = sorted(race["horses"], key=lambda row: (-row["score"], row["horse_number"]))
        top3 = ranked[:3]
        top2 = ranked[:2]
        hits_top3 = sum(1 for row in top3 if row["actual_pos"] <= 3)
        hits_top2 = sum(1 for row in top2 if row["actual_pos"] <= 3)

        groups = (
            overall,
            by_condition[race["condition_bucket"]],
            by_race_class[race["race_class_bucket"]],
            by_field_size[race["field_size_bucket"]],
        )
        for bucket in groups:
            bucket["races"] += 1
            bucket["top3_places"] += hits_top3
            bucket["top3_slots"] += 3
            bucket["hit_distribution"][hits_top3] += 1
            if ranked[0]["actual_pos"] == 1:
                bucket["champion"] += 1
            if any(row["actual_pos"] == 1 for row in top3):
                bucket["winner_in_top3"] += 1
            if hits_top3 == 3:
                bucket["gold"] += 1
            if hits_top2 == 2:
                bucket["good"] += 1
            if hits_top3 >= 2:
                bucket["minimum"] += 1

    return overall, by_condition, by_race_class, by_field_size


def summarize_bucket(name: str, bucket: dict) -> dict:
    races = bucket["races"]
    top3_slots = bucket["top3_slots"]
    return {
        "name": name,
        "races": races,
        "champion_rate": rate(bucket["champion"], races),
        "winner_in_top3_rate": rate(bucket["winner_in_top3"], races),
        "gold_rate": rate(bucket["gold"], races),
        "good_rate": rate(bucket["good"], races),
        "minimum_rate": rate(bucket["minimum"], races),
        "top3_place_precision": rate(bucket["top3_places"], top3_slots),
        "gold_gap": gap_count(TARGETS["gold_rate"], bucket["gold"], races),
        "good_gap": gap_count(TARGETS["good_rate"], bucket["good"], races),
        "minimum_gap": gap_count(TARGETS["minimum_rate"], bucket["minimum"], races),
        "top3_slot_gap": gap_count(TARGETS["top3_place_precision"], bucket["top3_places"], top3_slots),
        "zero_hit_races": bucket["hit_distribution"][0],
        "one_hit_races": bucket["hit_distribution"][1],
        "two_hit_races": bucket["hit_distribution"][2],
        "perfect_races": bucket["hit_distribution"][3],
    }


def render_table(rows: list[dict]) -> list[str]:
    lines = [
        "| Group | Races | Gold | Gap | Good | Gap | Pass | Gap | Top3 Place | Slot Gap | Top1 | Top3冠軍 | 0-hit | 1-hit | 2-hit | 3-hit |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {name} | {races} | {gold} | {gold_gap} | {good} | {good_gap} | {minimum} | {minimum_gap} | {top3} | {slot_gap} | {top1} | {winner_top3} | {zero} | {one} | {two} | {three} |".format(
                name=row["name"],
                races=row["races"],
                gold=pct(row["gold_rate"]),
                gold_gap=row["gold_gap"],
                good=pct(row["good_rate"]),
                good_gap=row["good_gap"],
                minimum=pct(row["minimum_rate"]),
                minimum_gap=row["minimum_gap"],
                top3=pct(row["top3_place_precision"]),
                slot_gap=row["top3_slot_gap"],
                top1=pct(row["champion_rate"]),
                winner_top3=pct(row["winner_in_top3_rate"]),
                zero=row["zero_hit_races"],
                one=row["one_hit_races"],
                two=row["two_hit_races"],
                three=row["perfect_races"],
            )
        )
    return lines


def build_report(overall: dict, by_condition: dict, by_race_class: dict, by_field_size: dict) -> str:
    overall_row = summarize_bucket("Overall", overall)
    condition_rows = [summarize_bucket(name, bucket) for name, bucket in sorted(by_condition.items())]
    class_rows = [summarize_bucket(name, bucket) for name, bucket in sorted(by_race_class.items())]
    field_rows = [summarize_bucket(name, bucket) for name, bucket in sorted(by_field_size.items())]

    biggest_condition_gap = max(condition_rows, key=lambda row: row["minimum_gap"]) if condition_rows else None
    biggest_class_gap = max(class_rows, key=lambda row: row["minimum_gap"]) if class_rows else None
    biggest_field_gap = max(field_rows, key=lambda row: row["minimum_gap"]) if field_rows else None

    lines = [
        "# AU Auto Target Gap Report",
        "",
        "## Target Standard",
        "",
        "- Gold: Top 3 picks 全部跑入實際前三，目標 >= 30%",
        "- Good: Top 1 + Top 2 picks 同時跑入實際前三，目標 >= 40%",
        "- Pass: Top 3 picks 至少 2 匹跑入實際前三，目標 >= 60%",
        "- Top 3 Place Precision: Top 3 picks 單入位率，目標 >= 80%",
        "",
        "## Current Overall",
        "",
        f"- Races: **{overall_row['races']}**",
        f"- Gold: **{pct(overall_row['gold_rate'])}**  | gap to target: **+{overall_row['gold_gap']} races**",
        f"- Good: **{pct(overall_row['good_rate'])}**  | gap to target: **+{overall_row['good_gap']} races**",
        f"- Pass: **{pct(overall_row['minimum_rate'])}**  | gap to target: **+{overall_row['minimum_gap']} races**",
        f"- Top 3 Place Precision: **{pct(overall_row['top3_place_precision'])}**  | gap to target: **+{overall_row['top3_slot_gap']} placing hits**",
        f"- Top 1 Hit Rate: **{pct(overall_row['champion_rate'])}**",
        f"- Top 3 Contains Winner: **{pct(overall_row['winner_in_top3_rate'])}**",
        "",
        "## Miss Profile",
        "",
        f"- 0-hit races: **{overall_row['zero_hit_races']}**",
        f"- 1-hit races: **{overall_row['one_hit_races']}**",
        f"- 2-hit races: **{overall_row['two_hit_races']}**",
        f"- 3-hit races: **{overall_row['perfect_races']}**",
        "",
        "Interpretation: 要追近 Pass 60%，最實際係先將大量 `1-hit` race 推上 `2-hit`。要追 Gold，就要大幅提升 `3-hit` race 數量。",
        "",
        "## By Condition",
        "",
        *render_table(condition_rows),
        "",
        "## By Race Class",
        "",
        *render_table(class_rows),
        "",
        "## By Field Size",
        "",
        *render_table(field_rows),
        "",
        "## What The Archive Is Saying",
        "",
        f"- 最大 condition gap 來自 **{biggest_condition_gap['name']}**：Pass 尚差 **{biggest_condition_gap['minimum_gap']} races**。" if biggest_condition_gap else "- N/A",
        f"- 最大 class gap 來自 **{biggest_class_gap['name']}**：Pass 尚差 **{biggest_class_gap['minimum_gap']} races**。" if biggest_class_gap else "- N/A",
        f"- 最大 field-size gap 來自 **{biggest_field_gap['name']}**：Pass 尚差 **{biggest_field_gap['minimum_gap']} races**。" if biggest_field_gap else "- N/A",
        "- 目前最重要唔係再追 Top 1，而係先將 `0-hit / 1-hit` race 壓低。",
        "- 如果要上 Gold/Good/Pass 標準，模型核心任務應明確定義為：`提升 place-hit density`，而唔係單純拉高冠軍命中率。",
    ]
    return "\n".join(lines) + "\n"


def main():
    overall, by_condition, by_race_class, by_field_size = collect_metrics()
    report = build_report(overall, by_condition, by_race_class, by_field_size)
    OUTPUT_MD.write_text(report, encoding="utf-8")
    print(f"Report written: {OUTPUT_MD}")


if __name__ == "__main__":
    main()
