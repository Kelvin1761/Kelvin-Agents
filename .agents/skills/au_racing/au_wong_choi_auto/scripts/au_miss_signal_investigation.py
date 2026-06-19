#!/usr/bin/env python3
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

from au_archive_calibrator import (
    ARCHIVE_ROOT,
    FEATURE_SCORE_KEYS,
    HISTORICAL_RESULTS_CSV,
    MATRIX_KEYS,
    MATRIX_LABELS,
    iter_logic_rows,
    load_historical_results,
)
from au_zero_hit_race_audit import field_size_bucket, race_class_bucket


OUTPUT_MD = ARCHIVE_ROOT / "AU_Miss_Signal_Investigation.md"

FEATURE_LABELS = {
    "form_score": "近績",
    "trial_score": "試閘",
    "sectional_score": "段速",
    "pace_map_score": "形勢",
    "jockey_score": "騎師",
    "trainer_score": "練馬師",
    "jockey_horse_fit_score": "人馬配搭",
    "class_score": "級數",
    "rating_score": "Rating",
    "weight_score": "負磅",
    "distance_score": "路程",
    "track_score": "場地",
    "formline_score": "賽績線",
    "consistency_score": "穩定",
    "health_score": "備戰",
    "confidence_score": "信心",
}


def avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def pct(n: int | float, d: int | float) -> str:
    return f"{(n / d * 100):.1f}%" if d else "0.0%"


def rank_bucket(rank: int) -> str:
    if rank <= 3:
        return "Top3"
    if rank <= 5:
        return "Rank 4-5"
    if rank <= 6:
        return "Rank 6"
    if rank <= 8:
        return "Rank 7-8"
    return "Rank 9+"


def signal_tags(row: dict, race: dict, top3_cutoff: float) -> list[str]:
    matrix = row["matrix_scores"]
    feat = row["feature_scores"]
    tags = []
    rank = row["model_rank"]
    gap = max(0.0, top3_cutoff - float(row["model_score"]))
    if rank <= 6:
        tags.append("rank4-6 視野內")
    if gap <= 2.0:
        tags.append("距離 Top3 分差<=2")
    if matrix["stability"] >= 68:
        tags.append("穩定性>=68")
    if matrix["form_line"] >= 66:
        tags.append("賽績線>=66")
    if matrix["jockey_trainer"] >= 66:
        tags.append("騎練>=66")
    if matrix["class_weight"] >= 62:
        tags.append("級磅>=62")
    if matrix["track"] >= 68:
        tags.append("場地>=68")
    if matrix["race_shape"] >= 62:
        tags.append("形勢>=62")
    if feat["trial_score"] >= 70:
        tags.append("試閘>=70")
    if feat["consistency_score"] >= 80:
        tags.append("穩定分>=80")
    if feat["confidence_score"] >= 85:
        tags.append("信心>=85")
    if feat["rating_score"] >= 65:
        tags.append("Rating>=65")
    if feat["distance_score"] >= 60:
        tags.append("路程>=60")
    if row.get("sp") and row["sp"] <= 15:
        tags.append("SP<=15")
    if race["condition_bucket"] in {"Soft", "Heavy"} and matrix["track"] >= 64:
        tags.append("濕地場地可用")
    if matrix["stability"] >= 68 and matrix["form_line"] >= 66 and (matrix["jockey_trainer"] >= 66 or feat["trial_score"] >= 70):
        tags.append("穩定+賽績線+騎練/試閘")
    if rank <= 6 and gap <= 2.5 and matrix["stability"] >= 66:
        tags.append("rank4-6近分+穩定")
    return tags


def summarize_row(row: dict) -> str:
    matrix = row["matrix_scores"]
    feat = row["feature_scores"]
    key_bits = [
        f"rank {row['model_rank']}",
        f"score {row['model_score']:.2f}",
        f"pos {row['actual_pos']}",
        f"穩 {matrix['stability']:.1f}",
        f"賽績 {matrix['form_line']:.1f}",
        f"騎練 {matrix['jockey_trainer']:.1f}",
        f"級磅 {matrix['class_weight']:.1f}",
        f"場地 {matrix['track']:.1f}",
        f"試閘 {feat['trial_score']:.1f}",
        f"信心 {feat['confidence_score']:.1f}",
    ]
    if row.get("sp"):
        key_bits.append(f"SP {row['sp']:.1f}")
    return f"#{row['horse_number']} {row['horse_name']} ({', '.join(key_bits)})"


def main() -> None:
    historical_results = load_historical_results(HISTORICAL_RESULTS_CSV)
    races = []
    missed_actual_rows = []
    failed_pick_rows = []
    race_counters = {
        "all": 0,
        "0hit": 0,
        "1hit": 0,
    }
    by_condition = Counter()
    by_class = Counter()
    by_field = Counter()
    rank_buckets = Counter()
    signal_counter = Counter()
    winner_rank_buckets = Counter()
    matrix_delta_sum = defaultdict(float)
    feature_delta_sum = defaultdict(float)
    delta_races = 0

    for race_rows in iter_logic_rows(ARCHIVE_ROOT, historical_results):
        ranked = sorted(race_rows, key=lambda row: (-row["model_score"], row["horse_number"]))
        for idx, row in enumerate(ranked, start=1):
            row["model_rank"] = idx
        top3 = ranked[:3]
        actual_top3 = sorted((row for row in ranked if row["actual_pos"] <= 3), key=lambda row: row["actual_pos"])
        if len(actual_top3) < 3:
            continue
        hits = sum(1 for row in top3 if row["actual_pos"] <= 3)
        race_counters["all"] += 1
        if hits > 1:
            continue
        label = "0hit" if hits == 0 else "1hit"
        race_counters[label] += 1
        race = {
            "meeting": ranked[0]["meeting"],
            "race": ranked[0]["race"],
            "condition_bucket": ranked[0]["condition_bucket"],
            "race_class_bucket": race_class_bucket(ranked[0].get("race_class")),
            "field_size_bucket": field_size_bucket(len(ranked)),
            "hits": hits,
            "ranked": ranked,
            "top3": top3,
            "actual_top3": actual_top3,
        }
        races.append(race)
        by_condition[race["condition_bucket"]] += 1
        by_class[race["race_class_bucket"]] += 1
        by_field[race["field_size_bucket"]] += 1

        top3_nums = {row["horse_number"] for row in top3}
        top3_cutoff = float(top3[-1]["model_score"])
        missed = [row for row in actual_top3 if row["horse_number"] not in top3_nums]
        for row in missed:
            missed_actual_rows.append(row)
            rank_buckets[rank_bucket(row["model_rank"])] += 1
            if row["actual_pos"] == 1:
                winner_rank_buckets[rank_bucket(row["model_rank"])] += 1
            for tag in signal_tags(row, race, top3_cutoff):
                signal_counter[tag] += 1

        for row in top3:
            if row["actual_pos"] > 3:
                failed_pick_rows.append(row)

        for key in MATRIX_KEYS:
            matrix_delta_sum[key] += avg([row["matrix_scores"][key] for row in missed]) - avg([row["matrix_scores"][key] for row in top3])
        for key in FEATURE_SCORE_KEYS:
            feature_delta_sum[key] += avg([row["feature_scores"][key] for row in missed]) - avg([row["feature_scores"][key] for row in top3])
        delta_races += 1

    missed_count = len(missed_actual_rows)
    failed_count = len(failed_pick_rows)
    matrix_delta = {key: matrix_delta_sum[key] / delta_races for key in MATRIX_KEYS}
    feature_delta = {key: feature_delta_sum[key] / delta_races for key in FEATURE_SCORE_KEYS}

    lines = [
        "# AU Miss Signal Investigation",
        "",
        "## Scope",
        "",
        f"- Historical races analysed: **{race_counters['all']}**",
        f"- 0-hit races: **{race_counters['0hit']}**",
        f"- 1-hit races: **{race_counters['1hit']}**",
        f"- Actual Top3 horses missed by model Top3 inside 0/1-hit races: **{missed_count}**",
        "",
        "## Where The Misses Sit",
        "",
    ]
    for label, count in rank_buckets.most_common():
        lines.append(f"- {label}: **{count}** ({pct(count, missed_count)})")
    lines.extend(["", "Winner rank buckets inside 0/1-hit races:", ""])
    for label, count in winner_rank_buckets.most_common():
        lines.append(f"- {label}: **{count}**")

    lines.extend(["", "## Race Context", ""])
    lines.append("Condition:")
    for key, count in by_condition.most_common():
        lines.append(f"- {key}: **{count}**")
    lines.append("")
    lines.append("Class:")
    for key, count in by_class.most_common():
        lines.append(f"- {key}: **{count}**")
    lines.append("")
    lines.append("Field size:")
    for key, count in by_field.most_common():
        lines.append(f"- {key}: **{count}**")

    lines.extend(["", "## Most Reusable Spotting Signals", ""])
    for tag, count in signal_counter.most_common(18):
        lines.append(f"- {tag}: **{count}** ({pct(count, missed_count)})")

    lines.extend(["", "## Missed Actual Top3 vs Failed Model Top3", ""])
    lines.append("Matrix delta, positive means actual Top3 missed horses were stronger than failed model picks:")
    for key in sorted(MATRIX_KEYS, key=lambda item: matrix_delta[item], reverse=True):
        lines.append(f"- {MATRIX_LABELS[key]}: **{matrix_delta[key]:+.2f}**")
    lines.append("")
    lines.append("Feature delta:")
    for key in sorted(FEATURE_SCORE_KEYS, key=lambda item: feature_delta[item], reverse=True)[:10]:
        lines.append(f"- {FEATURE_LABELS[key]}: **{feature_delta[key]:+.2f}**")
    lines.append("")
    lines.append("Failed model Top3 strongest average sections:")
    failed_matrix_avgs = {
        key: avg([row["matrix_scores"][key] for row in failed_pick_rows])
        for key in MATRIX_KEYS
    }
    for key in sorted(MATRIX_KEYS, key=lambda item: failed_matrix_avgs[item], reverse=True):
        lines.append(f"- {MATRIX_LABELS[key]}: **{failed_matrix_avgs[key]:.2f}**")

    lines.extend(["", "## Candidate Archetypes To Test", ""])
    archetypes = [
        ("A. Rank 4-6 + close score + stable", lambda row: row["model_rank"] <= 6 and row["matrix_scores"]["stability"] >= 66),
        ("B. Stable + formline + JT/trial", lambda row: row["matrix_scores"]["stability"] >= 68 and row["matrix_scores"]["form_line"] >= 66 and (row["matrix_scores"]["jockey_trainer"] >= 66 or row["feature_scores"]["trial_score"] >= 70)),
        ("C. Track fit on wet", lambda row: row["condition_bucket"] in {"Soft", "Heavy"} and row["matrix_scores"]["track"] >= 64),
        ("D. Rating/class near threshold", lambda row: row["feature_scores"]["rating_score"] >= 65 and row["matrix_scores"]["class_weight"] >= 62),
        ("E. SP live contender not in Top3", lambda row: row.get("sp") and row["sp"] <= 15),
    ]
    for name, predicate in archetypes:
        hits = [row for row in missed_actual_rows if predicate(row)]
        lines.append(f"- {name}: **{len(hits)}** ({pct(len(hits), missed_count)})")

    lines.extend(["", "## Examples", ""])
    for race in races[:25]:
        missed = [row for row in race["actual_top3"] if row["horse_number"] not in {p["horse_number"] for p in race["top3"]}]
        if not missed:
            continue
        lines.extend(
            [
                f"### {race['meeting']} R{race['race']} ({race['hits']}-hit)",
                f"- Context: {race['condition_bucket']} / {race['race_class_bucket']} / {race['field_size_bucket']}",
                "- Missed actual Top3:",
            ]
        )
        for row in missed:
            lines.append(f"  - {summarize_row(row)}")
        lines.append("- Failed model Top3:")
        for row in race["top3"]:
            if row["actual_pos"] > 3:
                lines.append(f"  - {summarize_row(row)}")
        lines.append("")

    OUTPUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Report written: {OUTPUT_MD}")
    print(f"0-hit races: {race_counters['0hit']}")
    print(f"1-hit races: {race_counters['1hit']}")
    print(f"Missed actual Top3 rows: {missed_count}")
    print("Top spotting signals:")
    for tag, count in signal_counter.most_common(10):
        print(f"- {tag}: {count} ({pct(count, missed_count)})")


if __name__ == "__main__":
    main()
