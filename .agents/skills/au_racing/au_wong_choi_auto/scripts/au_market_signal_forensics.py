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
)
from au_target_gap_report import condition_bucket, field_size_bucket, race_class_bucket

OUTPUT_MD = ARCHIVE_ROOT / "AU_Auto_Market_Signal_Forensics.md"
OUTPUT_CSV = ARCHIVE_ROOT / "AU_Auto_Market_Signal_Forensics.csv"

SHORT_SP_THRESHOLD = 4.0
PROMINENT_MARKET_RANK = 3


def average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def parse_sp(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        text = str(value).replace("$", "").strip()
        try:
            return float(text)
        except ValueError:
            return None


def section_delta_map(winner: dict, picks: list[dict]) -> dict[str, float]:
    pick_avg = {
        key: average([row["matrix_scores"][key] for row in picks])
        for key in MATRIX_KEYS
    }
    return {
        key: winner["matrix_scores"][key] - pick_avg[key]
        for key in MATRIX_KEYS
    }


def bucket_market_signal(market_rank: int | None, sp: float | None) -> str:
    if market_rank == 1:
        return "Favourite"
    if sp is not None and sp <= SHORT_SP_THRESHOLD:
        return "Short SP<=4"
    if market_rank is not None and market_rank <= PROMINENT_MARKET_RANK:
        return "Market Top3"
    return "Longer Odds"


def is_market_signal_winner(market_rank: int | None, sp: float | None) -> bool:
    if market_rank is not None and market_rank <= PROMINENT_MARKET_RANK:
        return True
    return sp is not None and sp <= SHORT_SP_THRESHOLD


def top_sections(delta_map: dict[str, float], positive: bool = True, limit: int = 3) -> list[tuple[str, float]]:
    ordered = sorted(delta_map.items(), key=lambda item: item[1], reverse=positive)
    if not positive:
        ordered = [item for item in ordered if item[1] < 0]
    else:
        ordered = [item for item in ordered if item[1] > 0]
    return ordered[:limit]


def failure_tags(delta_map: dict[str, float], winner_rank: int, market_rank: int | None) -> list[str]:
    tags: list[str] = []
    for key in MATRIX_KEYS:
        if delta_map[key] >= 2.0:
            tags.append(f"{MATRIX_LABELS[key]}低估")
    for key in ("sectional", "race_shape", "jockey_trainer"):
        if delta_map[key] <= -2.0:
            tags.append(f"{MATRIX_LABELS[key]}可能過信")
    if winner_rank <= 6:
        tags.append("頭馬仍在前六")
    else:
        tags.append("頭馬跌出前六")
    if market_rank == 1:
        tags.append("市場頭號熱門失手")
    elif market_rank is not None and market_rank <= 3:
        tags.append("市場前列馬失手")
    return tags


def summarize_pick(row: dict) -> str:
    sp = parse_sp(row.get("sp"))
    sp_text = f"${sp:.2f}" if sp is not None else "n/a"
    return f"[{row['horse_number']}] {row['horse_name']} (名次 {row['actual_pos']}, SP {sp_text})"


def collect_rows() -> list[dict]:
    historical_results = load_historical_results(HISTORICAL_RESULTS_CSV)
    rows: list[dict] = []

    for race_rows in iter_logic_rows(ARCHIVE_ROOT, historical_results):
        ranked = sorted(race_rows, key=lambda row: (-row["model_score"], row["horse_number"]))
        for idx, row in enumerate(ranked, start=1):
            row["model_rank"] = idx

        by_pos = {row["actual_pos"]: row for row in ranked}
        winner = by_pos.get(1)
        if not winner:
            continue

        top3 = ranked[:3]
        top2 = ranked[:2]
        hits_top3 = sum(1 for row in top3 if row["actual_pos"] <= 3)
        if hits_top3 > 1:
            continue

        actual_rows = sorted((row for row in ranked if row["actual_pos"] <= 3), key=lambda row: row["actual_pos"])
        if len(actual_rows) < 3:
            continue

        market_ranked = sorted(
            ranked,
            key=lambda row: (
                parse_sp(row.get("sp")) if parse_sp(row.get("sp")) is not None else 9999.0,
                row["horse_number"],
            ),
        )
        for idx, row in enumerate(market_ranked, start=1):
            row["market_rank"] = idx

        winner_sp = parse_sp(winner.get("sp"))
        winner_market_rank = winner.get("market_rank")
        delta_map = section_delta_map(winner, top3)
        positives = top_sections(delta_map, positive=True)
        negatives = top_sections(delta_map, positive=False)
        tags = failure_tags(delta_map, winner["model_rank"], winner_market_rank)

        rows.append(
            {
                "meeting": winner["meeting"],
                "race_no": winner["race"],
                "condition": winner["condition"],
                "condition_bucket": condition_bucket(winner["condition"]),
                "race_class_bucket": race_class_bucket(winner.get("race_class") or winner["horse"].get("race_class") or winner["data"].get("race_class") or ""),
                "field_size_bucket": field_size_bucket(len(ranked)),
                "field_size": len(ranked),
                "miss_type": "0-hit" if hits_top3 == 0 else "1-hit",
                "hits_top3": hits_top3,
                "winner_name": winner["horse_name"],
                "winner_model_rank": winner["model_rank"],
                "winner_market_rank": winner_market_rank,
                "winner_sp": winner_sp,
                "market_signal_bucket": bucket_market_signal(winner_market_rank, winner_sp),
                "is_market_signal": is_market_signal_winner(winner_market_rank, winner_sp),
                "winner_score": winner["model_score"],
                "top3_picks": [summarize_pick(row) for row in top3],
                "actual_top3": [summarize_pick(row) for row in actual_rows],
                "top_delta_1": positives[0][0] if positives else "",
                "top_delta_1_value": positives[0][1] if positives else 0.0,
                "top_delta_2": positives[1][0] if len(positives) > 1 else "",
                "top_delta_2_value": positives[1][1] if len(positives) > 1 else 0.0,
                "top_over_1": negatives[0][0] if negatives else "",
                "top_over_1_value": negatives[0][1] if negatives else 0.0,
                "top_over_2": negatives[1][0] if len(negatives) > 1 else "",
                "top_over_2_value": negatives[1][1] if len(negatives) > 1 else 0.0,
                "winner_delta_map": delta_map,
                "tags": tags,
                "winner_in_top6": winner["model_rank"] <= 6,
                "top2_hits": sum(1 for row in top2 if row["actual_pos"] <= 3),
            }
        )

    return rows


def write_csv(rows: list[dict]) -> None:
    fieldnames = [
        "meeting",
        "race_no",
        "miss_type",
        "condition",
        "condition_bucket",
        "race_class_bucket",
        "field_size",
        "field_size_bucket",
        "winner_name",
        "winner_model_rank",
        "winner_market_rank",
        "winner_sp",
        "market_signal_bucket",
        "is_market_signal",
        "top_delta_1",
        "top_delta_1_value",
        "top_delta_2",
        "top_delta_2_value",
        "top_over_1",
        "top_over_1_value",
        "top_over_2",
        "top_over_2_value",
        "winner_in_top6",
        "top2_hits",
        "top3_picks",
        "actual_top3",
        "tags",
    ]
    with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    **{key: row[key] for key in fieldnames if key not in {"top3_picks", "actual_top3", "tags"}},
                    "top3_picks": " | ".join(row["top3_picks"]),
                    "actual_top3": " | ".join(row["actual_top3"]),
                    "tags": " | ".join(row["tags"]),
                }
            )


def build_report(rows: list[dict]) -> str:
    total = len(rows)
    market_rows = [row for row in rows if row["is_market_signal"]]
    zero_hit_rows = [row for row in rows if row["miss_type"] == "0-hit"]
    one_hit_rows = [row for row in rows if row["miss_type"] == "1-hit"]
    market_zero = [row for row in market_rows if row["miss_type"] == "0-hit"]
    market_one = [row for row in market_rows if row["miss_type"] == "1-hit"]

    tag_counts: Counter[str] = Counter()
    positive_counts: Counter[str] = Counter()
    negative_counts: Counter[str] = Counter()
    condition_counts: Counter[str] = Counter()
    class_counts: Counter[str] = Counter()
    field_counts: Counter[str] = Counter()
    bucket_counts: Counter[str] = Counter()

    for row in market_rows:
        bucket_counts[row["market_signal_bucket"]] += 1
        condition_counts[row["condition_bucket"]] += 1
        class_counts[row["race_class_bucket"]] += 1
        field_counts[row["field_size_bucket"]] += 1
        for tag in row["tags"]:
            tag_counts[tag] += 1
        for key, value in row["winner_delta_map"].items():
            if value >= 2.0:
                positive_counts[MATRIX_LABELS[key]] += 1
            if value <= -2.0:
                negative_counts[MATRIX_LABELS[key]] += 1

    promotable = [row for row in market_rows if 4 <= row["winner_model_rank"] <= 6]
    deep_miss = [row for row in market_rows if row["winner_model_rank"] >= 7]
    short_list = sorted(
        market_rows,
        key=lambda row: (
            row["winner_market_rank"] if row["winner_market_rank"] is not None else 99,
            row["winner_sp"] if row["winner_sp"] is not None else 99.0,
            -row["winner_model_rank"],
        ),
    )[:15]

    lines = [
        "# AU Auto Market Signal Forensics",
        "",
        "## Why This Report Exists",
        "",
        "- 目標唔係再由大盤盲修，而係專睇 `0-hit / 1-hit` 入面市場本身已經有明顯競爭訊號嘅頭馬。",
        "- 呢批馬理論上最值得模型睇得更清楚，因為如果連熱門或市場前列馬都經常完全睇唔到，代表訊號消化仍有實質缺口。",
        "",
        "## Overall Low-Hit Sample",
        "",
        f"- `0-hit + 1-hit` races: **{total}**",
        f"- `0-hit` races: **{len(zero_hit_rows)}**",
        f"- `1-hit` races: **{len(one_hit_rows)}**",
        "",
        "## Market-Signal Winner Subset",
        "",
        f"- 市場訊號頭馬樣本: **{len(market_rows)} / {total} = {pct(len(market_rows) / total if total else 0.0)}**",
        f"- 其中 `0-hit`: **{len(market_zero)}**",
        f"- 其中 `1-hit`: **{len(market_one)}**",
        f"- 頭馬仍排 model `4-6`: **{len(promotable)}**",
        f"- 頭馬跌出 model `7+`: **{len(deep_miss)}**",
        "",
        "Interpretation: `4-6` 比較似 rerank / tightening 問題；`7+` 更似上游 feature depth 未夠。",
        "",
        "## By Market Bucket",
        "",
        "| Bucket | Races | Share |",
        "|---|---:|---:|",
    ]
    for bucket in ("Favourite", "Short SP<=4", "Market Top3"):
        count = bucket_counts[bucket]
        lines.append(f"| {bucket} | {count} | {pct(count / len(market_rows) if market_rows else 0.0)} |")

    lines.extend(
        [
            "",
            "## Most Common Missing Signals In Market-Signal Winners",
            "",
            "| Section | Count |",
            "|---|---:|",
        ]
    )
    for label, count in positive_counts.most_common():
        lines.append(f"| {label}低估 | {count} |")

    lines.extend(
        [
            "",
            "## Most Common Overtrusted Signals In Failed Top Picks",
            "",
            "| Section | Count |",
            "|---|---:|",
        ]
    )
    for label, count in negative_counts.most_common():
        lines.append(f"| {label}可能過信 | {count} |")

    lines.extend(
        [
            "",
            "## Common Race Buckets For Market-Signal Misses",
            "",
            f"- Condition: {', '.join(f'{name} {count}' for name, count in condition_counts.most_common())}",
            f"- Race class: {', '.join(f'{name} {count}' for name, count in class_counts.most_common())}",
            f"- Field size: {', '.join(f'{name} {count}' for name, count in field_counts.most_common())}",
            "",
            "## High-Value Cases To Review First",
            "",
            "| Race | Miss | Market | Winner Rank | Winner | Main Missing Signals | Main Overtrust Signals |",
            "|---|---|---|---:|---|---|---|",
        ]
    )
    for row in short_list:
        missing = ", ".join(
            f"{MATRIX_LABELS[key]} {value:+.1f}"
            for key, value in top_sections(row["winner_delta_map"], positive=True, limit=2)
        ) or "-"
        overtrust = ", ".join(
            f"{MATRIX_LABELS[key]} {value:+.1f}"
            for key, value in top_sections(row["winner_delta_map"], positive=False, limit=2)
        ) or "-"
        market_text = row["market_signal_bucket"]
        if row["winner_sp"] is not None:
            market_text += f" / ${row['winner_sp']:.2f}"
        lines.append(
            f"| {row['meeting']} R{row['race_no']} | {row['miss_type']} | {market_text} | {row['winner_model_rank']} | {row['winner_name']} | {missing} | {overtrust} |"
        )

    lines.extend(
        [
            "",
            "## Working Read",
            "",
            "- 如果市場前列頭馬多數都只係排 `4-6`，下一刀應該偏向 `rerank / place-tightening`。",
            "- 如果市場前列頭馬經常跌出 `7+`，就唔係小修 ranking 可以解決，而係 `class / track / jockey_trainer / stability` 上游 digest 仲有漏位。",
            "- 呢份報告應該配合 `AU_Auto_Zero_Hit_Race_Audit.md` 一齊睇：前者聚焦市場可見訊號，後者聚焦全體失手模式。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    rows = collect_rows()
    write_csv(rows)
    OUTPUT_MD.write_text(build_report(rows), encoding="utf-8")
    print(f"Wrote {OUTPUT_MD}")
    print(f"Wrote {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
