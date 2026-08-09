#!/usr/bin/env python3
"""Print compact Warwick Farm factor diagnostics from exact scoring/results."""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path


def number(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def main() -> int:
    meeting = Path(sys.argv[1])
    rows = list(csv.DictReader((meeting / "Meeting_Auto_Scoring.csv").open(encoding="utf-8-sig")))
    result_data = json.loads(
        (meeting / "Race_Results_Warwick_Farm_2026-07-15.json").read_text(encoding="utf-8")
    )["results"]
    features = [
        key
        for key in rows[0]
        if key.endswith("_score")
        and key
        not in {
            "pure_7d_score",
            "base_7d_score",
            "final_rank_score",
            "ability_score",
        }
    ]
    by_race: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        by_race[int(row["race_number"])].append(row)

    placer_values = defaultdict(list)
    nonplacer_values = defaultdict(list)
    winner_values = defaultdict(list)
    top1_values = defaultdict(list)
    print("R | Top1 finish | Winner model rank | SP | Score gap | T3 hits | T5 hits | Top1 -> Winner")
    print("--|-------------|-------------------|----|-----------|---------|---------|---------------")
    for race_num in sorted(by_race):
        scored = sorted(by_race[race_num], key=lambda row: int(float(row["rank"])))
        actual = sorted(
            [row for row in result_data[str(race_num)] if not row.get("is_scratched")],
            key=lambda row: int(row["finish_position"]),
        )
        actual_position = {
            int(row["competitor_number"]): int(row["finish_position"]) for row in actual
        }
        actual_top3 = {int(row["competitor_number"]) for row in actual[:3]}
        winner_no = int(actual[0]["competitor_number"])
        winner_row = next(row for row in scored if int(row["horse_number"]) == winner_no)
        top1 = scored[0]
        winner_rank = int(float(winner_row["rank"]))
        top1_finish = actual_position.get(int(top1["horse_number"]))
        gap = number(top1["ability_score"]) - number(winner_row["ability_score"])
        top3_hits = sum(int(row["horse_number"]) in actual_top3 for row in scored[:3])
        top5_hits = sum(int(row["horse_number"]) in actual_top3 for row in scored[:5])
        print(
            f"{race_num} | {top1_finish} | {winner_rank} | {actual[0].get('starting_price')} | "
            f"{gap:+.3f} | {top3_hits} | {top5_hits} | {top1['horse_name']} -> {winner_row['horse_name']}"
        )
        pair_deltas = []
        for feature in features:
            top1_value = number(top1.get(feature))
            winner_value = number(winner_row.get(feature))
            if top1_value is not None and winner_value is not None:
                pair_deltas.append((top1_value - winner_value, feature, top1_value, winner_value))
        print(
            "  top1 biggest edges:",
            ", ".join(
                f"{feature} {top1_value:g}>{winner_value:g}({delta:+.1f})"
                for delta, feature, top1_value, winner_value in sorted(pair_deltas, reverse=True)[:4]
            ),
        )
        print(
            "  winner biggest edges:",
            ", ".join(
                f"{feature} {winner_value:g}>{top1_value:g}({-delta:+.1f})"
                for delta, feature, top1_value, winner_value in sorted(pair_deltas)[:4]
            ),
        )
        for row in scored:
            horse_no = int(row["horse_number"])
            for feature in features:
                value = number(row.get(feature))
                if value is None:
                    continue
                (placer_values if horse_no in actual_top3 else nonplacer_values)[feature].append(value)
        for feature in features:
            winner_value = number(winner_row.get(feature))
            top1_value = number(top1.get(feature))
            if winner_value is not None:
                winner_values[feature].append(winner_value)
            if top1_value is not None:
                top1_values[feature].append(top1_value)

        ranked_features = []
        for feature in features:
            value = number(winner_row.get(feature))
            field_values = [number(row.get(feature)) for row in scored]
            field_values = [item for item in field_values if item is not None]
            if value is None or not field_values:
                continue
            rank = 1 + sum(item > value for item in field_values)
            ranked_features.append((rank, feature, value))
        strengths = sorted(ranked_features)[:4]
        weaknesses = sorted(ranked_features, reverse=True)[:4]
        print("  winner strengths:", ", ".join(f"{key}={value:g}(#{rank})" for rank, key, value in strengths))
        print("  winner low ranks:", ", ".join(f"{key}={value:g}(#{rank})" for rank, key, value in weaknesses))

    print("\nFeature | Actual Top3 mean | Others mean | Delta | Winners mean | Model Top1 mean")
    print("--------|------------------|-------------|-------|--------------|----------------")
    feature_rows = []
    for feature in features:
        placer_mean = mean(placer_values[feature])
        other_mean = mean(nonplacer_values[feature])
        feature_rows.append(
            (
                placer_mean - other_mean,
                feature,
                placer_mean,
                other_mean,
                mean(winner_values[feature]),
                mean(top1_values[feature]),
            )
        )
    for delta, feature, placer_mean, other_mean, winner_mean, top1_mean in sorted(
        feature_rows, reverse=True
    ):
        print(
            f"{feature} | {placer_mean:.2f} | {other_mean:.2f} | {delta:+.2f} | "
            f"{winner_mean:.2f} | {top1_mean:.2f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
