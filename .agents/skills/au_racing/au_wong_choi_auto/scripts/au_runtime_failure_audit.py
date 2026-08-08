#!/usr/bin/env python3
"""Explain AU ranking failures from raw pre-race Logic on a fixed result set.

The current RacingEngine scores every horse before actual position and SP are
used.  Results are joined only for retrospective evaluation and cohort labels.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, pstdev

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR / "racing_engine"))

from au_archive_calibrator import (
    detect_meeting_date,
    detect_meeting_track,
    load_historical_results,
    parse_int,
)
from au_data_explorer import (
    HIGH_POTENTIAL_UNUSED,
    LOADED_DATA_FIELDS,
    UNUSED_IN_SCORING,
    USED_IN_SCORING,
)
from au_runtime_micro_ablation import (
    aligned_race,
    discover_logic_files,
    iter_aligned_races,
    prepare_logic_for_scoring,
    score_variant,
)
from io_utils import write_json_atomic, write_text_atomic
from scoring import MATRIX_WEIGHTS


PRIMARY_MATRIX_KEYS = tuple(
    key for key, weight in MATRIX_WEIGHTS.items() if float(weight) > 0
)


def present(value) -> bool:
    return value not in (None, "", "N/A", "Unknown", 0, "0", [], {})


def raw_pre_race_snapshot(raw_horse: dict) -> dict:
    """Return research inputs only; never copy joined result/SP fields."""
    raw_data = raw_horse.get("_data")
    raw_data = raw_data if isinstance(raw_data, dict) else {}
    pf_metrics = raw_data.get("pf_metrics")
    pf_aggregates = (
        pf_metrics.get("pf_aggregates")
        if isinstance(pf_metrics, dict)
        else {}
    )
    return {
        "barrier": raw_horse.get("barrier"),
        "weight": raw_horse.get("weight"),
        "rating": raw_horse.get("rating"),
        # The live pace leaf uses only l600_delta_avg today.  Preserve the
        # other filtered pre-race aggregates so structural alternatives can
        # be evaluated without touching result-bearing data.
        "pf_aggregates": pf_aggregates or {},
        "class_move": raw_horse.get("class_move") or raw_data.get("class_move"),
        # Pre-race partnership history for structural jockey/horse-fit research.
        # These counts come from dated Formguide runs strictly before the target
        # race; they are not the mutable Sportsbet J/H overview summary.
        "current_jockey_formal_rides": raw_data.get("current_jockey_formal_rides"),
        "current_jockey_formal_places": raw_data.get("current_jockey_formal_places"),
        "current_jockey_formal_wins": raw_data.get("current_jockey_formal_wins"),
        **{key: raw_data.get(key) for key in HIGH_POTENTIAL_UNUSED},
    }


def race_metadata(logic_path: Path, logic: dict) -> dict:
    analysis = logic.get("race_analysis") or {}
    meeting = analysis.get("meeting_intelligence") or {}
    distance_raw = (
        analysis.get("distance")
        or analysis.get("race_distance")
        or analysis.get("distance_m")
        or ""
    )
    distance = parse_int(distance_raw)
    going = (
        meeting.get("going")
        or (analysis.get("speed_map") or {}).get("going")
        or analysis.get("going")
        or analysis.get("track_condition")
        or "Unknown"
    )
    race_class = (
        analysis.get("race_class")
        or analysis.get("class")
        or analysis.get("race_type")
        or "Unknown"
    )
    return {
        "date": detect_meeting_date(logic_path.parent),
        "track": detect_meeting_track(logic_path.parent, logic),
        "race_number": parse_int(analysis.get("race_number"))
        or parse_int(logic_path.stem),
        "distance": distance,
        "going": str(going),
        "race_class": str(race_class),
        "field_size": len(logic.get("horses") or {}),
    }


def _horse_id(row: dict) -> tuple[int, str]:
    return int(row["horse_number"]), str(row["horse_name"])


def _field_means(race: list[dict], container: str, keys: tuple[str, ...]) -> dict:
    return {
        key: mean(float(row[container].get(key, 60.0)) for row in race)
        for key in keys
    }


def _drivers(
    row: dict,
    means: dict,
    container: str,
    *,
    direction: str,
    limit: int = 4,
) -> list[dict]:
    deltas = [
        {
            "signal": key,
            "score": round(float(row[container].get(key, 60.0)), 2),
            "field_delta": round(
                float(row[container].get(key, 60.0)) - field_mean,
                2,
            ),
        }
        for key, field_mean in means.items()
    ]
    deltas.sort(
        key=lambda item: item["field_delta"],
        reverse=direction == "high",
    )
    if direction == "low":
        return [item for item in deltas if item["field_delta"] < 0][:limit]
    return [item for item in deltas if item["field_delta"] > 0][:limit]


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    x_mean = mean(xs)
    y_mean = mean(ys)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    denominator = math.sqrt(
        sum((x - x_mean) ** 2 for x in xs)
        * sum((y - y_mean) ** 2 for y in ys)
    )
    return numerator / denominator if denominator else None


def analyze_race(metadata: dict, race: list[dict]) -> dict:
    ranked = sorted(
        race,
        key=lambda row: (-row["score"], row["horse_number"]),
    )
    rank_lookup = {_horse_id(row): index for index, row in enumerate(ranked, 1)}
    actual_top3 = [row for row in race if row["actual_pos"] <= 3]
    predicted_top3 = ranked[:3]
    predicted_top5 = ranked[:5]
    hits_top3 = sum(row["actual_pos"] <= 3 for row in predicted_top3)
    hits_top5 = sum(row["actual_pos"] <= 3 for row in predicted_top5)
    score_values = [row["score"] for row in race]
    matrix_means = _field_means(race, "matrix_scores", PRIMARY_MATRIX_KEYS)
    feature_keys = tuple(race[0]["feature_scores"])
    feature_means = _field_means(race, "feature_scores", feature_keys)

    underrated = []
    for row in sorted(actual_top3, key=lambda item: item["actual_pos"]):
        model_rank = rank_lookup[_horse_id(row)]
        if model_rank <= 5:
            continue
        underrated.append(
            {
                "horse_number": row["horse_number"],
                "horse_name": row["horse_name"],
                "actual_pos": row["actual_pos"],
                "model_rank": model_rank,
                "score": row["score"],
                "sp": row["result_sp_label"],
                "low_matrices": _drivers(
                    row,
                    matrix_means,
                    "matrix_scores",
                    direction="low",
                ),
                "low_features": _drivers(
                    row,
                    feature_means,
                    "feature_scores",
                    direction="low",
                ),
                "evidence_state": row["feature_evidence_state"],
                "coverage": row["data_coverage"],
                "risk_flags": row["risk_flags"],
            }
        )

    overrated = []
    for row in predicted_top5:
        if row["actual_pos"] <= 5:
            continue
        overrated.append(
            {
                "horse_number": row["horse_number"],
                "horse_name": row["horse_name"],
                "actual_pos": row["actual_pos"],
                "model_rank": rank_lookup[_horse_id(row)],
                "score": row["score"],
                "sp": row["result_sp_label"],
                "high_matrices": _drivers(
                    row,
                    matrix_means,
                    "matrix_scores",
                    direction="high",
                ),
                "high_features": _drivers(
                    row,
                    feature_means,
                    "feature_scores",
                    direction="high",
                ),
                "reason_codes": row["reason_codes"],
            }
        )

    outsider_top3 = []
    for row in actual_top3:
        sp = row.get("result_sp_label")
        if sp is None or float(sp) < 31:
            continue
        outsider_top3.append(
            {
                "horse_number": row["horse_number"],
                "horse_name": row["horse_name"],
                "actual_pos": row["actual_pos"],
                "model_rank": rank_lookup[_horse_id(row)],
                "sp": sp,
                "captured_top5": rank_lookup[_horse_id(row)] <= 5,
                "matrix_scores": row["matrix_scores"],
            }
        )

    positions_by_rank = {
        index: row["actual_pos"] for index, row in enumerate(ranked, 1)
    }
    rank_corr = _pearson(
        list(positions_by_rank),
        [positions_by_rank[index] for index in positions_by_rank],
    )
    top3_ranks = [rank_lookup[_horse_id(row)] for row in actual_top3]
    return {
        **metadata,
        "race_id": (
            f"{metadata['date']}|{metadata['track']}|R{metadata['race_number']}"
        ),
        "hits_top3": hits_top3,
        "hits_top5": hits_top5,
        "winner_rank": min(
            (
                rank_lookup[_horse_id(row)]
                for row in actual_top3
                if row["actual_pos"] == 1
            ),
            default=None,
        ),
        "mean_actual_top3_rank": mean(top3_ranks),
        "miss_severity": sum(max(0, rank - 5) for rank in top3_ranks),
        "false_contenders_top5": len(overrated),
        "rank_correlation": rank_corr,
        "separation": {
            "within_race_sd": pstdev(score_values),
            "score_range": max(score_values) - min(score_values),
            "top1_top3_gap": ranked[0]["score"] - ranked[2]["score"],
            "top3_top5_gap": (
                ranked[2]["score"] - ranked[4]["score"]
                if len(ranked) >= 5
                else None
            ),
            "compressed_sd_lt_2": pstdev(score_values) < 2.0,
        },
        "predicted_top5": [
            {
                "rank": index,
                "horse_number": row["horse_number"],
                "horse_name": row["horse_name"],
                "score": row["score"],
                "actual_pos": row["actual_pos"],
                "sp": row["result_sp_label"],
            }
            for index, row in enumerate(predicted_top5, 1)
        ],
        "actual_top3": [
            {
                "actual_pos": row["actual_pos"],
                "horse_number": row["horse_number"],
                "horse_name": row["horse_name"],
                "model_rank": rank_lookup[_horse_id(row)],
                "score": row["score"],
                "sp": row["result_sp_label"],
            }
            for row in sorted(actual_top3, key=lambda item: item["actual_pos"])
        ],
        "underrated": underrated,
        "overrated": overrated,
        "outsider_top3": outsider_top3,
        "positions_by_rank": positions_by_rank,
    }


def _cohort_summary(records: list[dict], key: str) -> dict:
    buckets = defaultdict(list)
    for record in records:
        value = record.get(key)
        if key == "distance" and value:
            value = f"{int(value) // 200 * 200}-{int(value) // 200 * 200 + 199}m"
        elif key == "field_size":
            value = "1-8" if value <= 8 else ("9-12" if value <= 12 else "13+")
        buckets[str(value or "Unknown")].append(record)
    output = {}
    for label, rows in buckets.items():
        output[label] = {
            "races": len(rows),
            "zero_hit_rate": sum(row["hits_top3"] == 0 for row in rows) / len(rows),
            "one_hit_rate": sum(row["hits_top3"] == 1 for row in rows) / len(rows),
            "mean_hits_top5": mean(row["hits_top5"] for row in rows),
            "mean_ndcg_proxy_rank_correlation": mean(
                row["rank_correlation"]
                for row in rows
                if row["rank_correlation"] is not None
            ),
            "compressed_rate": sum(
                row["separation"]["compressed_sd_lt_2"] for row in rows
            )
            / len(rows),
        }
    return dict(
        sorted(
            output.items(),
            key=lambda item: (-item[1]["races"], item[0]),
        )
    )


def summarize(
    records: list[dict],
    field_available: Counter,
    total_horses: int,
) -> dict:
    underrated = [horse for race in records for horse in race["underrated"]]
    overrated = [horse for race in records for horse in race["overrated"]]
    low_matrix = Counter(
        item["signal"]
        for horse in underrated
        for item in horse["low_matrices"][:2]
    )
    low_feature = Counter(
        item["signal"]
        for horse in underrated
        for item in horse["low_features"][:3]
    )
    high_matrix = Counter(
        item["signal"]
        for horse in overrated
        for item in horse["high_matrices"][:2]
    )
    high_feature = Counter(
        item["signal"]
        for horse in overrated
        for item in horse["high_features"][:3]
    )
    missed_evidence = Counter(
        f"{feature}:{state}"
        for horse in underrated
        for feature, state in horse["evidence_state"].items()
        if state in {"missing", "fallback"}
    )
    rank_positions = defaultdict(list)
    for race in records:
        for rank, actual_pos in race["positions_by_rank"].items():
            rank_positions[int(rank)].append(int(actual_pos))
    outsider_rows = [
        row for race in records for row in race["outsider_top3"]
    ]
    separation = [race["separation"] for race in records]
    failure_records = [
        race for race in records if race["hits_top3"] <= 1
    ]
    return {
        "races": len(records),
        "horses": total_horses,
        "hit_distribution_top3": {
            str(hits): sum(race["hits_top3"] == hits for race in records)
            for hits in range(4)
        },
        "zero_hit_rate": sum(race["hits_top3"] == 0 for race in records)
        / len(records),
        "one_hit_rate": sum(race["hits_top3"] == 1 for race in records)
        / len(records),
        "top3_capture_at5": sum(race["hits_top5"] for race in records)
        / (3 * len(records)),
        "winner_top3_rate": sum(
            race["winner_rank"] is not None and race["winner_rank"] <= 3
            for race in records
        )
        / len(records),
        "winner_top5_rate": sum(
            race["winner_rank"] is not None and race["winner_rank"] <= 5
            for race in records
        )
        / len(records),
        "false_contender_rate_top5": sum(
            race["false_contenders_top5"] for race in records
        )
        / (5 * len(records)),
        "mean_actual_finish_by_predicted_rank": {
            str(rank): mean(values)
            for rank, values in sorted(rank_positions.items())
        },
        "mean_rank_correlation": mean(
            race["rank_correlation"]
            for race in records
            if race["rank_correlation"] is not None
        ),
        "separation": {
            "mean_within_race_sd": mean(
                row["within_race_sd"] for row in separation
            ),
            "median_within_race_sd": sorted(
                row["within_race_sd"] for row in separation
            )[len(separation) // 2],
            "mean_score_range": mean(row["score_range"] for row in separation),
            "mean_top1_top3_gap": mean(
                row["top1_top3_gap"] for row in separation
            ),
            "mean_top3_top5_gap": mean(
                row["top3_top5_gap"]
                for row in separation
                if row["top3_top5_gap"] is not None
            ),
            "compressed_races_sd_lt_2": sum(
                row["compressed_sd_lt_2"] for row in separation
            ),
            "compressed_rate": sum(
                row["compressed_sd_lt_2"] for row in separation
            )
            / len(separation),
            "zero_hit_mean_sd": mean(
                race["separation"]["within_race_sd"]
                for race in records
                if race["hits_top3"] == 0
            ),
            "two_plus_hit_mean_sd": mean(
                race["separation"]["within_race_sd"]
                for race in records
                if race["hits_top3"] >= 2
            ),
        },
        "failure_analysis": {
            "zero_or_one_hit_races": len(failure_records),
            "underrated_top3_below_rank5": len(underrated),
            "overrated_top5_finishing_below_fifth": len(overrated),
            "recurring_low_matrices": low_matrix.most_common(),
            "recurring_low_features": low_feature.most_common(),
            "recurring_high_matrices": high_matrix.most_common(),
            "recurring_high_features": high_feature.most_common(),
            "missed_horse_missing_or_fallback": missed_evidence.most_common(),
        },
        "outsiders_sp31": {
            "actual_top3": len(outsider_rows),
            "captured_top5": sum(row["captured_top5"] for row in outsider_rows),
            "capture_top5_rate": (
                sum(row["captured_top5"] for row in outsider_rows)
                / len(outsider_rows)
                if outsider_rows
                else None
            ),
            "mean_model_rank": (
                mean(row["model_rank"] for row in outsider_rows)
                if outsider_rows
                else None
            ),
        },
        "cohorts": {
            key: _cohort_summary(records, key)
            for key in (
                "track",
                "distance",
                "going",
                "race_class",
                "field_size",
            )
        },
        "racenet_field_coverage": {
            field: {
                "available": field_available[field],
                "available_rate": field_available[field] / max(1, total_horses),
                "classification": (
                    "scored"
                    if field in USED_IN_SCORING
                    else (
                        "loaded_not_scored"
                        if field in UNUSED_IN_SCORING
                        else "market_or_context"
                    )
                ),
                "high_potential_unused": field in HIGH_POTENTIAL_UNUSED,
            }
            for field in LOADED_DATA_FIELDS
        },
    }


def render_markdown(report: dict) -> str:
    summary = report["summary"]
    failure = summary["failure_analysis"]
    sep = summary["separation"]
    outsider = summary["outsiders_sp31"]
    lines = [
        "# AU Runtime Failure Audit",
        "",
        f"- Aligned races / horses: {summary['races']} / {summary['horses']}",
        "- Actual position/SP 只喺 current RacingEngine 完成評分後加入。",
        f"- 0-hit / 1-hit: {summary['hit_distribution_top3']['0']} / {summary['hit_distribution_top3']['1']} "
        f"({summary['zero_hit_rate'] * 100:.1f}% / {summary['one_hit_rate'] * 100:.1f}%)",
        f"- Top-3 capture@5: {summary['top3_capture_at5'] * 100:.1f}%",
        f"- Winner@3 / Winner@5: {summary['winner_top3_rate'] * 100:.1f}% / {summary['winner_top5_rate'] * 100:.1f}%",
        f"- False contender rate（model Top 5、實際第 6+）: {summary['false_contender_rate_top5'] * 100:.1f}%",
        "",
        "## Score separation",
        "",
        f"- Mean / median within-race SD: {sep['mean_within_race_sd']:.3f} / {sep['median_within_race_sd']:.3f}",
        f"- Compressed SD<2: {sep['compressed_races_sd_lt_2']} ({sep['compressed_rate'] * 100:.1f}%)",
        f"- Mean Top1-Top3 / Top3-Top5 gap: {sep['mean_top1_top3_gap']:.3f} / {sep['mean_top3_top5_gap']:.3f}",
        f"- 0-hit mean SD vs 2+-hit mean SD: {sep['zero_hit_mean_sd']:.3f} / {sep['two_plus_hit_mean_sd']:.3f}",
        "",
        "## Recurring failure drivers",
        "",
        f"- Underrated actual Top 3 below rank 5: {failure['underrated_top3_below_rank5']}",
        f"- Overrated model Top 5 finishing 6+: {failure['overrated_top5_finishing_below_fifth']}",
        "- Low matrices on missed contenders: "
        + ", ".join(f"{key}={count}" for key, count in failure["recurring_low_matrices"][:7]),
        "- Low features on missed contenders: "
        + ", ".join(f"{key}={count}" for key, count in failure["recurring_low_features"][:10]),
        "- High matrices on false contenders: "
        + ", ".join(f"{key}={count}" for key, count in failure["recurring_high_matrices"][:7]),
        "- High features on false contenders: "
        + ", ".join(f"{key}={count}" for key, count in failure["recurring_high_features"][:10]),
        "",
        "## Extreme outsiders",
        "",
        f"- SP≥31 actual Top 3: {outsider['actual_top3']}",
        f"- Captured Top 5: {outsider['captured_top5']} ({outsider['capture_top5_rate'] * 100:.1f}%)",
        f"- Mean model rank: {outsider['mean_model_rank']:.2f}",
        "",
        "## Worst repeatable-review races",
        "",
        "| Race | Hits@3 | Hits@5 | Miss severity | SD | Underrated |",
        "|---|---:|---:|---:|---:|---|",
    ]
    worst = sorted(
        report["failure_records"],
        key=lambda row: (
            row["hits_top3"],
            -row["miss_severity"],
            row["date"],
            row["race_number"],
        ),
    )[:25]
    for race in worst:
        underrated = ", ".join(
            f"{horse['horse_name']}→R{horse['model_rank']}"
            for horse in race["underrated"]
        ) or "—"
        lines.append(
            f"| {race['race_id']} | {race['hits_top3']} | {race['hits_top5']} | "
            f"{race['miss_severity']} | {race['separation']['within_race_sd']:.2f} | "
            f"{underrated} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--results-csv", type=Path, required=True)
    parser.add_argument("--materialize-on-demand", action="store_true")
    parser.add_argument("--prefetch-workers", type=int, default=8)
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("/private/tmp/au_runtime_failure_audit.json"),
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=Path("/private/tmp/au_runtime_failure_audit.md"),
    )
    parser.add_argument(
        "--dataset-json",
        type=Path,
        help=(
            "Optional fixed current-runtime feature snapshot for fast, "
            "result-separated architecture experiments."
        ),
    )
    args = parser.parse_args()

    materialized, placeholders = discover_logic_files(args.archive_root)
    if args.require_complete and placeholders and not args.materialize_on_demand:
        raise SystemExit(
            f"Archive incomplete: {len(materialized)} materialized, "
            f"{len(placeholders)} placeholders."
        )
    files = materialized + placeholders if args.materialize_on_demand else materialized
    files.sort(key=lambda path: (path.parent.name, parse_int(path.stem, 999)))
    historical_results = load_historical_results(args.results_csv)
    records = []
    rejections = Counter()
    field_available = Counter()
    total_horses = 0
    dataset_races = []
    aligned_iter = iter_aligned_races(
        files,
        historical_results,
        prefetch_workers=(
            args.prefetch_workers if args.materialize_on_demand else 1
        ),
    )
    for index, (logic_path, aligned) in enumerate(aligned_iter, 1):
        if aligned[0] is None:
            rejections[aligned[1]] += 1
            continue
        logic, aligned_rows = aligned
        prepared_logic, facts_path = prepare_logic_for_scoring(logic, logic_path)
        for source in aligned_rows:
            prepared_horse = (
                prepared_logic["horses"].get(str(source["horse_number"]))
                or prepared_logic["horses"].get(source["horse_number"])
                or source["horse"]
            )
            data = prepared_horse.get("_data")
            data = data if isinstance(data, dict) else {}
            total_horses += 1
            for field in LOADED_DATA_FIELDS:
                if present(data.get(field)):
                    field_available[field] += 1
        scored = score_variant(
            logic,
            aligned_rows,
            logic_path,
            [],
            include_details=True,
            prepared_logic=prepared_logic,
            facts_path=facts_path,
        )
        metadata = race_metadata(logic_path, prepared_logic)
        records.append(analyze_race(metadata, scored))
        if args.dataset_json:
            raw_lookup = {
                int(source["horse_number"]): (
                    prepared_logic["horses"].get(str(source["horse_number"]))
                    or prepared_logic["horses"].get(source["horse_number"])
                    or source["horse"]
                )
                for source in aligned_rows
            }
            dataset_rows = []
            for row in scored:
                raw_horse = raw_lookup[int(row["horse_number"])]
                dataset_row = dict(row)
                dataset_row["raw_pre_race"] = raw_pre_race_snapshot(raw_horse)
                dataset_rows.append(dataset_row)
            dataset_races.append(
                {
                    "metadata": metadata,
                    "speed_map": (
                        (logic.get("race_analysis") or {}).get("speed_map")
                        or {}
                    ),
                    "rows": dataset_rows,
                }
            )
        if index == 1 or index % 25 == 0:
            print(f"Audited {index}/{len(files)} Logic races", flush=True)

    read_failures = sum(
        count
        for reason, count in rejections.items()
        if reason.startswith("logic_read_error:")
    )
    if args.require_complete and read_failures:
        raise SystemExit(
            f"Archive read failed for {read_failures} Logic files: "
            f"{dict(rejections)}"
        )
    if not records:
        raise SystemExit("No aligned races available.")

    summary = summarize(records, field_available, total_horses)
    report = {
        "design": {
            "archive_root": str(args.archive_root.resolve()),
            "results_csv": str(args.results_csv.resolve()),
            "outcome_only_fields": ["actual_pos", "result_sp_label"],
            "rejections": dict(rejections),
        },
        "summary": summary,
        "failure_records": [
            record for record in records if record["hits_top3"] <= 1
        ],
    }
    write_json_atomic(args.output_json, report)
    write_text_atomic(args.output_md, render_markdown(report))
    if args.dataset_json:
        write_json_atomic(
            args.dataset_json,
            {
                "design": {
                    "model": "current RacingEngine",
                    "aligned_races": len(dataset_races),
                    "horses": total_horses,
                    "pre_race_containers": [
                        "feature_scores",
                        "matrix_scores",
                        "feature_evidence_state",
                        "raw_pre_race",
                        "speed_map",
                    ],
                    "outcome_only_fields": [
                        "actual_pos",
                        "result_sp_label",
                    ],
                },
                "races": dataset_races,
            },
        )
    print(f"Aligned races: {len(records)}")
    print(f"JSON: {args.output_json}")
    print(f"Markdown: {args.output_md}")
    if args.dataset_json:
        print(f"Dataset: {args.dataset_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
