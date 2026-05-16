#!/usr/bin/env python3
from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path

from au_target_gap_report import (
    ARCHIVE_ROOT,
    HISTORICAL_RESULTS_CSV,
    choose_track_rows,
    detect_meeting_date,
    detect_meeting_track,
    load_historical_results,
    normalize_horse_name,
    parse_int,
)

OUTPUT_MD = ARCHIVE_ROOT / "AU_Overrated_Horse_Audit.md"


def class_bucket(text: str) -> str:
    value = str(text or "").lower()
    if "maiden" in value:
        return "Maiden"
    if "bm" in value:
        rating = parse_int(value, 0) or 0
        return "BM72+" if rating >= 72 else "BM58-70"
    if "group" in value or "listed" in value:
        return "Group/Listed"
    return "Other"


def condition_bucket(text: str) -> str:
    value = str(text or "").lower()
    if "heavy" in value:
        return "Heavy"
    if "soft" in value:
        return "Soft"
    return "Good/Firm"


def pct(part: int, whole: int) -> str:
    return f"{(part / whole) * 100:.1f}%" if whole else "0.0%"


def main():
    historical_results = load_historical_results(HISTORICAL_RESULTS_CSV)
    cases = []
    top_sections = Counter()
    weak_sections = Counter()
    miss_types = Counter()
    pred_ranks = Counter()
    going_buckets = Counter()
    class_buckets = Counter()

    for meeting_dir in sorted(path for path in ARCHIVE_ROOT.iterdir() if path.is_dir()):
        logic_files = sorted(meeting_dir.glob("Race_*_Logic.json"), key=lambda p: parse_int(p.stem.split("_")[1], 999))
        if not logic_files:
            continue
        sample_logic = json.loads(logic_files[0].read_text(encoding="utf-8"))
        meeting_date = detect_meeting_date(meeting_dir)
        meeting_track = detect_meeting_track(meeting_dir, sample_logic)
        if not meeting_date or not meeting_track:
            continue

        for logic_path in logic_files:
            logic = json.loads(logic_path.read_text(encoding="utf-8"))
            race_analysis = logic.get("race_analysis", {})
            race_no = parse_int(race_analysis.get("race_number")) or parse_int(logic_path.stem.split("_")[1])
            rows_for_race = choose_track_rows(historical_results.get((meeting_date, race_no), []), meeting_track)
            if not rows_for_race:
                continue

            race_lookup = {row["horse_slug"]: row for row in rows_for_race}
            horses = []
            field_size = len(rows_for_race)
            last_batch_cut = max(4, math.ceil(field_size * 2 / 3))

            for horse_num, horse in logic.get("horses", {}).items():
                result_row = race_lookup.get(normalize_horse_name(horse.get("horse_name")))
                if not result_row:
                    continue
                python_auto = horse.get("python_auto") or {}
                horses.append(
                    {
                        "horse_number": parse_int(horse_num) or 999,
                        "horse_name": str(horse.get("horse_name") or "").strip(),
                        "rank_score": float(python_auto.get("rank_score") or python_auto.get("ability_score") or 0.0),
                        "matrix_scores": python_auto.get("matrix_scores") or {},
                        "actual_pos": int(result_row["pos"]),
                        "result_condition": str(result_row.get("condition") or ""),
                    }
                )

            if len(horses) < 4:
                continue

            ranked = sorted(horses, key=lambda horse: (-horse["rank_score"], horse["horse_number"]))
            top3 = ranked[:3]
            hits_top3 = sum(1 for horse in top3 if horse["actual_pos"] <= 3)
            miss_type = "0-hit" if hits_top3 == 0 else "1-hit" if hits_top3 == 1 else ""
            if not miss_type:
                continue

            for pred_rank, horse in enumerate(ranked[:2], start=1):
                if horse["actual_pos"] < last_batch_cut:
                    continue
                matrix_scores = horse["matrix_scores"]
                top_two = sorted(matrix_scores.items(), key=lambda item: item[1], reverse=True)[:2]
                weak_two = sorted(matrix_scores.items(), key=lambda item: item[1])[:2]
                cases.append(
                    {
                        "meeting": meeting_dir.name,
                        "race_no": race_no,
                        "miss_type": miss_type,
                        "pred_rank": pred_rank,
                        "horse_name": horse["horse_name"],
                        "actual_pos": horse["actual_pos"],
                        "field_size": field_size,
                        "last_batch_cut": last_batch_cut,
                        "race_class": class_bucket(race_analysis.get("race_class")),
                        "going": condition_bucket(horse.get("result_condition") or race_analysis.get("going")),
                        "top_two": top_two,
                        "weak_two": weak_two,
                    }
                )
                miss_types[miss_type] += 1
                pred_ranks[pred_rank] += 1
                going_buckets[condition_bucket(horse.get("result_condition") or race_analysis.get("going"))] += 1
                class_buckets[class_bucket(race_analysis.get("race_class"))] += 1
                for key, _ in top_two:
                    top_sections[key] += 1
                for key, _ in weak_two:
                    weak_sections[key] += 1

    lines = [
        "# AU Overrated Horse Audit",
        "",
        "- Definition: model 預測第 1 / 2，但實際跑入全場後段 batch。",
        "- 後段 batch 定義: `max(4, ceil(field_size * 2 / 3))` 或更後名次。",
        "",
        f"- Cases: **{len(cases)}**",
        f"- `0-hit`: **{miss_types['0-hit']}**",
        f"- `1-hit`: **{miss_types['1-hit']}**",
        f"- Pred rank 1: **{pred_ranks[1]}** | Pred rank 2: **{pred_ranks[2]}**",
        "",
        "## Buckets",
        "",
        f"- Good/Firm: **{going_buckets['Good/Firm']} = {pct(going_buckets['Good/Firm'], len(cases))}**",
        f"- Soft: **{going_buckets['Soft']} = {pct(going_buckets['Soft'], len(cases))}**",
        f"- Heavy: **{going_buckets['Heavy']} = {pct(going_buckets['Heavy'], len(cases))}**",
        f"- BM58-70: **{class_buckets['BM58-70']} = {pct(class_buckets['BM58-70'], len(cases))}**",
        f"- BM72+: **{class_buckets['BM72+']} = {pct(class_buckets['BM72+'], len(cases))}**",
        f"- Group/Listed: **{class_buckets['Group/Listed']} = {pct(class_buckets['Group/Listed'], len(cases))}**",
        f"- Maiden: **{class_buckets['Maiden']} = {pct(class_buckets['Maiden'], len(cases))}**",
        f"- Other: **{class_buckets['Other']} = {pct(class_buckets['Other'], len(cases))}**",
        "",
        "## Most Common Overtrusted Sections",
        "",
        "| Section | Count | Share |",
        "|---|---:|---:|",
    ]
    for key, count in top_sections.most_common():
        lines.append(f"| {key} | {count} | {pct(count, len(cases) * 2)} |")

    lines.extend(
        [
            "",
            "## Most Common Weak Sections In These Horses",
            "",
            "| Section | Count | Share |",
            "|---|---:|---:|",
        ]
    )
    for key, count in weak_sections.most_common():
        lines.append(f"| {key} | {count} | {pct(count, len(cases) * 2)} |")

    lines.extend(
        [
            "",
            "## Example Cases",
            "",
            "| Race | Miss | Pred | Horse | Actual | Top Signals | Weak Signals |",
            "|---|---|---:|---|---:|---|---|",
        ]
    )
    for case in cases[:40]:
        top_text = " / ".join(f"{key} {score:.1f}" for key, score in case["top_two"])
        weak_text = " / ".join(f"{key} {score:.1f}" for key, score in case["weak_two"])
        lines.append(
            f"| {case['meeting']} R{case['race_no']} | {case['miss_type']} | {case['pred_rank']} | {case['horse_name']} | {case['actual_pos']}/{case['field_size']} | {top_text} | {weak_text} |"
        )

    OUTPUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved: {OUTPUT_MD}")


if __name__ == "__main__":
    main()
