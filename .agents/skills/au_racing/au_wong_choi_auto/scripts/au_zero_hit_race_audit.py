#!/usr/bin/env python3
from __future__ import annotations

import csv
from collections import Counter, defaultdict

from au_archive_calibrator import (
    ARCHIVE_ROOT,
    HISTORICAL_RESULTS_CSV,
    MATRIX_KEYS,
    MATRIX_LABELS,
    iter_logic_rows,
    load_historical_results,
    normalize_condition_bucket,
    parse_int,
)

OUTPUT_MD = ARCHIVE_ROOT / "AU_Auto_Zero_Hit_Race_Audit.md"
OUTPUT_CSV = ARCHIVE_ROOT / "AU_Auto_Zero_Hit_Races.csv"


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


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def format_section_scores(scores: dict[str, float], keys: list[str] | None = None) -> str:
    ordered = keys or sorted(scores, key=lambda key: scores[key], reverse=True)
    return " / ".join(f"{MATRIX_LABELS[key]} {scores[key]:.1f}" for key in ordered)


def summarize_horse(row: dict) -> dict:
    scores = row["matrix_scores"]
    strongest = max(MATRIX_KEYS, key=lambda key: scores[key])
    weakest = min(MATRIX_KEYS, key=lambda key: scores[key])
    return {
        "horse_number": row["horse_number"],
        "horse_name": row["horse_name"],
        "ability_score": row["ability_score"],
        "model_score": row["model_score"],
        "actual_pos": row["actual_pos"],
        "model_rank": row["model_rank"],
        "strongest_key": strongest,
        "strongest_label": MATRIX_LABELS[strongest],
        "strongest_score": scores[strongest],
        "weakest_key": weakest,
        "weakest_label": MATRIX_LABELS[weakest],
        "weakest_score": scores[weakest],
        "matrix_scores": scores,
        "risk_flags": row["risk_flags"],
    }


def rank_gap_label(rank: int | None) -> str:
    if rank is None:
        return "winner rank unknown"
    if rank <= 3:
        return "頭馬其實已在 model top3"
    if rank <= 6:
        return "頭馬其實只係排第4-6"
    return "頭馬完全跌出前6"


def collect_failure_tags(deltas: dict[str, float], winner_rank: int | None, race: dict) -> list[str]:
    tags: list[str] = []
    if deltas.get("form_line", 0.0) >= 2.0:
        tags.append("賽績線低估")
    if deltas.get("track", 0.0) >= 2.0:
        tags.append("場地適性低估")
    if deltas.get("class_weight", 0.0) >= 2.0:
        tags.append("級數與負重低估")
    if deltas.get("jockey_trainer", 0.0) >= 2.0:
        tags.append("騎練訊號低估")
    if deltas.get("sectional", 0.0) >= 2.0:
        tags.append("段速與引擎低估")
    if deltas.get("stability", 0.0) >= 2.0:
        tags.append("狀態與穩定性低估")
    if deltas.get("race_shape", 0.0) >= 2.0:
        tags.append("檔位形勢低估")

    if deltas.get("race_shape", 0.0) <= -2.0:
        tags.append("檔位形勢可能過信")
    if deltas.get("sectional", 0.0) <= -2.0:
        tags.append("段速與引擎可能過信")
    if deltas.get("jockey_trainer", 0.0) <= -2.0:
        tags.append("騎練訊號可能過信")

    if winner_rank is not None:
        if winner_rank <= 6:
            tags.append("頭馬其實仍在視野內")
        else:
            tags.append("頭馬完全跌出視野")

    if race["condition_bucket"] == "Heavy":
        tags.append("Heavy 場失手")
    if race["condition_bucket"] == "Soft":
        tags.append("Soft 場失手")
    if race["race_class_bucket"] == "BM58-70":
        tags.append("BM58-70 失手")
    if race["field_size_bucket"] == "Field 9-12":
        tags.append("中型場失手")
    if race["field_size_bucket"] == "Field 13+":
        tags.append("大場面失手")

    return tags


def iter_races():
    historical_results = load_historical_results(HISTORICAL_RESULTS_CSV)
    for race_rows in iter_logic_rows(ARCHIVE_ROOT, historical_results):
        ranked = sorted(race_rows, key=lambda row: (-row["model_score"], row["horse_number"]))
        for idx, row in enumerate(ranked, start=1):
            row["model_rank"] = idx
        yield {
            "meeting": ranked[0]["meeting"],
            "meeting_date": ranked[0]["date"],
            "track": ranked[0]["track"],
            "race_no": ranked[0]["race"],
            "race_class": str(ranked[0].get("race_class") or "").strip(),
            "race_class_bucket": race_class_bucket(ranked[0].get("race_class")),
            "field_size": len(ranked),
            "field_size_bucket": field_size_bucket(len(ranked)),
            "condition_bucket": normalize_condition_bucket(ranked[0].get("condition") or ""),
            "condition": str(ranked[0].get("condition") or "").strip(),
            "horses": ranked,
        }


def collect_zero_hit_races():
    zero_hit_races = []
    pattern_counts: Counter[str] = Counter()
    delta_counts: Counter[str] = Counter()
    by_condition: Counter[str] = Counter()
    by_class: Counter[str] = Counter()
    by_field: Counter[str] = Counter()

    for race in iter_races():
        ranked = race["horses"]
        top3 = ranked[:3]
        actual_top3 = sorted((row for row in ranked if row["actual_pos"] <= 3), key=lambda row: row["actual_pos"])
        hits = sum(1 for row in top3 if row["actual_pos"] <= 3)
        if hits != 0:
            continue

        pick_avg = {
            key: average([row["matrix_scores"][key] for row in top3])
            for key in MATRIX_KEYS
        }
        actual_avg = {
            key: average([row["matrix_scores"][key] for row in actual_top3])
            for key in MATRIX_KEYS
        }
        deltas = {key: actual_avg[key] - pick_avg[key] for key in MATRIX_KEYS}
        sorted_positive = sorted(MATRIX_KEYS, key=lambda key: deltas[key], reverse=True)
        sorted_negative = sorted(MATRIX_KEYS, key=lambda key: deltas[key])
        winner = next((row for row in ranked if row["actual_pos"] == 1), None)
        winner_rank = winner["model_rank"] if winner else None
        tags = collect_failure_tags(deltas, winner_rank, race)
        if winner is None or len(actual_top3) < 3:
            tags.append("歷史賽果資料缺口")

        for tag in tags:
            pattern_counts[tag] += 1
        for key in sorted_positive[:2]:
            if deltas[key] >= 1.5:
                delta_counts[f"{MATRIX_LABELS[key]}低估"] += 1

        by_condition[race["condition_bucket"]] += 1
        by_class[race["race_class_bucket"]] += 1
        by_field[race["field_size_bucket"]] += 1

        zero_hit_races.append(
            {
                **race,
                "top3": [summarize_horse(row) for row in top3],
                "actual_top3": [summarize_horse(row) for row in actual_top3],
                "winner_rank": winner_rank,
                "winner_name": winner["horse_name"] if winner else "",
                "deltas": deltas,
                "sorted_positive": sorted_positive,
                "sorted_negative": sorted_negative,
                "tags": tags,
            }
        )

    zero_hit_races.sort(
        key=lambda race: (
            race["condition_bucket"] != "Good/Firm",
            race["race_class_bucket"] != "BM58-70",
            race["field_size_bucket"] != "Field 9-12",
            race["meeting_date"],
            race["race_no"],
        )
    )
    return zero_hit_races, pattern_counts, delta_counts, by_condition, by_class, by_field


def write_csv(rows: list[dict]) -> None:
    with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "meeting",
                "race_no",
                "condition",
                "race_class",
                "field_size",
                "winner_name",
                "winner_rank",
                "top_delta_1",
                "top_delta_1_value",
                "top_delta_2",
                "top_delta_2_value",
                "top_pick_1",
                "top_pick_1_pos",
                "top_pick_2",
                "top_pick_2_pos",
                "top_pick_3",
                "top_pick_3_pos",
                "tags",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "meeting": row["meeting"],
                    "race_no": row["race_no"],
                    "condition": row["condition"],
                    "race_class": row["race_class"],
                    "field_size": row["field_size"],
                    "winner_name": row["winner_name"],
                    "winner_rank": row["winner_rank"] or "",
                    "top_delta_1": MATRIX_LABELS[row["sorted_positive"][0]],
                    "top_delta_1_value": f"{row['deltas'][row['sorted_positive'][0]]:.2f}",
                    "top_delta_2": MATRIX_LABELS[row["sorted_positive"][1]],
                    "top_delta_2_value": f"{row['deltas'][row['sorted_positive'][1]]:.2f}",
                    "top_pick_1": row["top3"][0]["horse_name"],
                    "top_pick_1_pos": row["top3"][0]["actual_pos"],
                    "top_pick_2": row["top3"][1]["horse_name"],
                    "top_pick_2_pos": row["top3"][1]["actual_pos"],
                    "top_pick_3": row["top3"][2]["horse_name"],
                    "top_pick_3_pos": row["top3"][2]["actual_pos"],
                    "tags": " | ".join(row["tags"]),
                }
            )


def build_report(
    rows: list[dict],
    pattern_counts: Counter[str],
    delta_counts: Counter[str],
    by_condition: Counter[str],
    by_class: Counter[str],
    by_field: Counter[str],
) -> str:
    lines = [
        "# AU Auto Zero-Hit Race Audit",
        "",
        "## Summary",
        "",
        f"- 0-hit races: **{len(rows)}**",
        f"- Good/Firm: **{by_condition.get('Good/Firm', 0)}**",
        f"- Soft: **{by_condition.get('Soft', 0)}**",
        f"- Heavy: **{by_condition.get('Heavy', 0)}**",
        f"- BM58-70: **{by_class.get('BM58-70', 0)}**",
        f"- Field 9-12: **{by_field.get('Field 9-12', 0)}**",
        f"- Field 13+: **{by_field.get('Field 13+', 0)}**",
        f"- 歷史賽果資料缺口: **{pattern_counts.get('歷史賽果資料缺口', 0)}**",
        "",
        "## Most Common Failure Tags",
        "",
    ]

    for tag, count in pattern_counts.most_common(12):
        lines.append(f"- {tag}: **{count}**")

    lines.extend(
        [
            "",
            "## Most Common Underestimated Sections",
            "",
        ]
    )
    for tag, count in delta_counts.most_common(10):
        lines.append(f"- {tag}: **{count}**")

    lines.extend(
        [
            "",
            "## Race-By-Race Audit",
            "",
        ]
    )

    for row in rows:
        top_up = row["sorted_positive"][:3]
        top_down = row["sorted_negative"][:2]
        lines.extend(
            [
                f"### {row['meeting']} Race {row['race_no']}",
                "",
                f"- 條件: **{row['condition_bucket']}** (`{row['condition']}`) | 班次: **{row['race_class_bucket']}** (`{row['race_class'] or 'N/A'}`) | 場數: **{row['field_size']}** (`{row['field_size_bucket']}`)",
                f"- 頭馬: **{row['winner_name']}** | model 排名: **{row['winner_rank'] or 'N/A'}** | {rank_gap_label(row['winner_rank'])}",
                f"- 初步失誤標籤: **{' / '.join(row['tags'])}**",
                f"- 實際前三平均比 model top3 高分最多嘅 sections: **{format_section_scores(row['deltas'], top_up)}**",
                f"- model top3 反而高估最多嘅 sections: **{format_section_scores(row['deltas'], top_down)}**",
                "",
                "Model Top 3:",
            ]
        )
        for horse in row["top3"]:
            risk_suffix = f" | risk: {', '.join(horse['risk_flags'])}" if horse["risk_flags"] else ""
            lines.append(
                "- [{num}] {name} | model#{rank} | rank {model_score:.2f} | ability {ability:.2f} | 實際第 {pos} | 強項 {strong_label} {strong_score:.1f} | 弱項 {weak_label} {weak_score:.1f}{risk}".format(
                    num=horse["horse_number"],
                    name=horse["horse_name"],
                    rank=horse["model_rank"],
                    model_score=horse["model_score"],
                    ability=horse["ability_score"],
                    pos=horse["actual_pos"],
                    strong_label=horse["strongest_label"],
                    strong_score=horse["strongest_score"],
                    weak_label=horse["weakest_label"],
                    weak_score=horse["weakest_score"],
                    risk=risk_suffix,
                )
            )
        lines.extend(["", "Actual Top 3:"])
        for horse in row["actual_top3"]:
            lines.append(
                "- [{num}] {name} | 實際第 {pos} | model#{rank} | rank {model_score:.2f} | ability {ability:.2f} | 強項 {strong_label} {strong_score:.1f} | 弱項 {weak_label} {weak_score:.1f}".format(
                    num=horse["horse_number"],
                    name=horse["horse_name"],
                    pos=horse["actual_pos"],
                    rank=horse["model_rank"],
                    model_score=horse["model_score"],
                    ability=horse["ability_score"],
                    strong_label=horse["strongest_label"],
                    strong_score=horse["strongest_score"],
                    weak_label=horse["weakest_label"],
                    weak_score=horse["weakest_score"],
                )
            )
        lines.append("")

    return "\n".join(lines) + "\n"


def main():
    rows, pattern_counts, delta_counts, by_condition, by_class, by_field = collect_zero_hit_races()
    write_csv(rows)
    report = build_report(rows, pattern_counts, delta_counts, by_condition, by_class, by_field)
    OUTPUT_MD.write_text(report, encoding="utf-8")
    print(f"Markdown report written: {OUTPUT_MD}")
    print(f"CSV report written: {OUTPUT_CSV}")
    print(f"Zero-hit races: {len(rows)}")


if __name__ == "__main__":
    main()
