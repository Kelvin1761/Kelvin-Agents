#!/usr/bin/env python3
"""Step-5b fixed surgical replacements on the current HKJC matrix scaffold.

Candidate ranks for all splits are created without result files.  Only the
development reference layer is loaded after ranks are frozen.  Official outer
weights remain unchanged; candidates progressively replace contaminated or
approved dimensions and neutralize race shape at 60.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from hkjc_rating_matrix_audit import DEFAULT_ARCHIVE, DEFAULT_MANIFEST, DEBUT_MATRIX_WEIGHTS, MATRIX_WEIGHTS
from hkjc_rebuilt_matrix_candidates import (
    baseline_selections,
    compare_candidate,
    development_gate,
    development_races,
    load_development_reference,
    selection_metrics,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIMENSIONS = ROOT / "scratch" / "hkjc_rebuilt_dimensions.csv"
DEVELOPMENT_SPLIT = "archive_development"

CANDIDATES = {
    "surgical_speed_shape_neutral": {
        "replacements": {
            "sectional": "dim_speed_engine",
            "race_shape": 60.0,
        },
        "hypothesis": "只移除going／draw污染：sectional換純L400 speed，race-shape回中性60。",
    },
    "surgical_plus_trainer": {
        "replacements": {
            "sectional": "dim_speed_engine",
            "race_shape": 60.0,
            "trainer_signal": "dim_trainer_signal",
        },
        "hypothesis": "在污染清理上，再換入Step 4通過嘅sample-shrunk trainer。",
    },
    "surgical_plus_trainer_stability": {
        "replacements": {
            "sectional": "dim_speed_engine",
            "race_shape": 60.0,
            "trainer_signal": "dim_trainer_signal",
            "stability": "dim_stability",
        },
        "hypothesis": "再換入9/9 development賽日正向嘅拆重stability。",
    },
}


def as_float(value: Any, default: float = 60.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def horse_key(dataset: str, meeting: str, race_number: int, horse_number: int) -> tuple[str, str, int, int]:
    return dataset, meeting, race_number, horse_number


def load_rebuilt_dimensions(path: Path) -> dict[tuple[str, str, int, int], dict[str, Any]]:
    output = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            key = horse_key(row["dataset"], row["meeting"], as_int(row["race_number"]), as_int(row["horse_number"]))
            output[key] = {
                "split": row["split"],
                "horse_name": row.get("horse_name", ""),
                "is_debut": as_int(row.get("is_debut")),
                "dim_speed_engine": as_float(row.get("dim_speed_engine")),
                "dim_trainer_signal": as_float(row.get("dim_trainer_signal")),
                "dim_stability": as_float(row.get("dim_stability")),
            }
    return output


def load_current_matrix(
    manifest_path: Path,
    archive_path: Path,
    rebuilt: dict[tuple[str, str, int, int], dict[str, Any]],
) -> tuple[dict[tuple[str, str, int, int], dict[str, float]], list[dict[str, Any]]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    valid = [record for record in manifest["records"] if record.get("valid")]
    archive_keys = {
        (record["meeting"], record["race_number"])
        for record in valid
        if record["dataset"] == "archive"
    }
    matrix = {}
    errors = []
    with archive_path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            meeting = str(row.get("meeting_name") or Path(str(row.get("meeting") or "")).name)
            race_number = as_int(row.get("race_number"))
            number = as_int(row.get("horse_number"))
            key = horse_key("archive", meeting, race_number, number)
            if (meeting, race_number) not in archive_keys or key not in rebuilt:
                continue
            matrix[key] = {
                dimension: as_float(row.get(f"matrix_{dimension}"))
                for dimension in MATRIX_WEIGHTS
            }

    for record in valid:
        if record["dataset"] == "archive":
            continue
        logic_path = Path(str(record["source"]).split(" | ", 1)[0])
        payload = json.loads(logic_path.read_text(encoding="utf-8"))
        for horse_number, horse in (payload.get("horses") or {}).items():
            number = as_int(horse_number)
            key = horse_key(record["dataset"], record["meeting"], record["race_number"], number)
            if key not in rebuilt:
                continue
            auto = horse.get("python_auto") if isinstance(horse.get("python_auto"), dict) else {}
            scores = auto.get("matrix_scores") if isinstance(auto.get("matrix_scores"), dict) else {}
            if not scores:
                errors.append({"key": key, "reason": "missing_matrix_scores"})
                continue
            matrix[key] = {dimension: as_float(scores.get(dimension)) for dimension in MATRIX_WEIGHTS}
    missing = sorted(set(rebuilt) - set(matrix))
    if missing:
        errors.append({"reason": "missing_current_matrix_rows", "count": len(missing), "examples": missing[:5]})
    return matrix, errors


def compute_score(
    matrix: dict[str, float],
    rebuilt: dict[str, Any],
    replacements: dict[str, str | float],
) -> float:
    adjusted = dict(matrix)
    for dimension, replacement in replacements.items():
        adjusted[dimension] = float(replacement) if isinstance(replacement, (int, float)) else float(rebuilt[replacement])
    weights = DEBUT_MATRIX_WEIGHTS if rebuilt["is_debut"] else MATRIX_WEIGHTS
    return round(sum(adjusted.get(dimension, 60.0) * weight for dimension, weight in weights.items()), 4)


def build_rows(
    rebuilt: dict[tuple[str, str, int, int], dict[str, Any]],
    current_matrix: dict[tuple[str, str, int, int], dict[str, float]],
) -> tuple[list[dict[str, Any]], dict[str, dict[tuple[str, str, int], list[int]]], dict[str, dict[str, Any]]]:
    rows = []
    grouped: defaultdict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for key in sorted(rebuilt):
        if key not in current_matrix:
            continue
        info = rebuilt[key]
        record = {
            "dataset": key[0],
            "split": info["split"],
            "meeting": key[1],
            "race_number": key[2],
            "horse_number": key[3],
            "horse_name": info["horse_name"],
            "is_debut": info["is_debut"],
        }
        baseline_weights = DEBUT_MATRIX_WEIGHTS if info["is_debut"] else MATRIX_WEIGHTS
        record["score_pure_scaffold"] = round(
            sum(current_matrix[key].get(dimension, 60.0) * weight for dimension, weight in baseline_weights.items()),
            4,
        )
        for name, candidate in CANDIDATES.items():
            record[f"score_{name}"] = compute_score(current_matrix[key], info, candidate["replacements"])
        rows.append(record)
        grouped[key[:3]].append(record)

    names = ("pure_scaffold", *CANDIDATES)
    selections: dict[str, dict[tuple[str, str, int], list[int]]] = {name: {} for name in names}
    tie_stats = {}
    for name in names:
        tie_all = 0
        tie_dev = 0
        dev_races = 0
        for current_race, race_rows in grouped.items():
            ranked = sorted(race_rows, key=lambda row: (-row[f"score_{name}"], row["horse_number"]))
            for rank, row in enumerate(ranked, start=1):
                row[f"rank_{name}"] = rank
            selections[name][current_race] = [row["horse_number"] for row in ranked[:2]]
            tied = len(ranked) >= 3 and abs(ranked[1][f"score_{name}"] - ranked[2][f"score_{name}"]) < 1e-9
            tie_all += int(tied)
            if ranked[0]["split"] == DEVELOPMENT_SPLIT:
                dev_races += 1
                tie_dev += int(tied)
        tie_stats[name] = {
            "all_races": len(grouped),
            "all_boundary_ties": tie_all,
            "all_boundary_tie_rate": round(tie_all / len(grouped) * 100, 1),
            "development_races": dev_races,
            "development_boundary_ties": tie_dev,
            "development_boundary_tie_rate": round(tie_dev / dev_races * 100, 1),
        }
    return rows, selections, tie_stats


def validate(
    rows: list[dict[str, Any]],
    load_errors: list[dict[str, Any]],
    tie_stats: dict[str, dict[str, Any]],
) -> list[str]:
    errors = []
    if load_errors:
        errors.append(f"matrix load errors: {len(load_errors)}")
    if len(rows) != 3054:
        errors.append(f"rows {len(rows)} != 3054")
    if any(column.startswith(("label_", "reference_")) for column in rows[0]):
        errors.append("outcome/reference leaked into candidate output")
    for row in rows:
        for name in ("pure_scaffold", *CANDIDATES):
            if not 0.0 <= float(row[f"score_{name}"]) <= 100.0:
                errors.append(f"score out of range {name}")
            if int(row[f"rank_{name}"]) < 1:
                errors.append(f"rank out of range {name}")
    if any(stats["all_races"] != 245 or stats["development_races"] != 88 for stats in tie_stats.values()):
        errors.append("race count mismatch")
    return errors


def write_outputs(
    rows: list[dict[str, Any]],
    tie_stats: dict[str, dict[str, Any]],
    original_baseline: dict[str, Any],
    scaffold_baseline: dict[str, Any],
    metrics: dict[str, dict[str, Any]],
    comparisons: dict[str, dict[str, Any]],
    scaffold_comparisons: dict[str, dict[str, Any]],
    gates: dict[str, dict[str, Any]],
    load_errors: list[dict[str, Any]],
    errors: list[str],
    output_prefix: Path,
) -> None:
    csv_path = output_prefix.with_suffix(".csv")
    json_path = output_prefix.with_suffix(".json")
    report_path = output_prefix.with_name(output_prefix.name + "_report").with_suffix(".md")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    def compact(metric: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in metric.items() if key != "per_race"}

    payload = {
        "method": {
            "fixed_before_development_measurement": True,
            "grid_search": False,
            "official_outer_weights_unchanged": True,
            "race_shape_fixed_neutral_60": True,
            "held_out_result_files_read": False,
            "full_race_rerank": True,
            "micro_tiebreak": False,
            "blind_swap": False,
        },
        "official_weights": MATRIX_WEIGHTS,
        "debut_weights": DEBUT_MATRIX_WEIGHTS,
        "candidates": CANDIDATES,
        "development_original_baseline": compact(original_baseline),
        "development_pure_scaffold_baseline": compact(scaffold_baseline),
        "development_candidates": {name: compact(metric) for name, metric in metrics.items()},
        "comparisons_vs_original": comparisons,
        "comparisons_vs_pure_scaffold": scaffold_comparisons,
        "development_gates": gates,
        "tie_stats": tie_stats,
        "matrix_load_errors": load_errors,
        "validation_errors": errors,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    original_dist = original_baseline["distribution"]
    scaffold_dist = scaffold_baseline["distribution"]
    lines = [
        "# HKJC Dimension重建 Step 5b — 外科式Dimension替換",
        "",
        "## 方法鎖定",
        "",
        "- 沿用現行官方outer weights；候選只逐步替換dimension，無搜尋權重。",
        "- 三候選全部將sectional換成純L400 speed，race-shape固定中性60；第二案再換trainer，第三案再換stability。",
        "- 其餘class、health、form-line沿用現行matrix分；初出馬沿用現行debut weights，但race-shape同樣固定60。",
        "- 每場完整重排；無micro tie-break或第二／第三選盲換。",
        "- 全245場分數及排名先凍結；只載入development reference，未讀其他結果檔。",
        "",
        "## 固定候選",
        "",
        "| 候選 | 替換 | 假設 |",
        "|---|---|---|",
    ]
    for name, candidate in CANDIDATES.items():
        replacement_text = ", ".join(
            f"{dimension}→{replacement}" for dimension, replacement in candidate["replacements"].items()
        )
        lines.append(f"| {name} | {replacement_text} | {candidate['hypothesis']} |")
    lines.extend(
        [
            "",
            "## Development雙基準",
            "",
            f"- 原模型Top2：0／1／2 hit {original_dist['0']}/{original_dist['1']}/{original_dist['2']}；總hits {original_baseline['total_top2_hits']}；頭馬Top2 {original_baseline['winner_top2']}。",
            f"- 原matrix純加權骨架：0／1／2 hit {scaffold_dist['0']}/{scaffold_dist['1']}/{scaffold_dist['2']}；總hits {scaffold_baseline['total_top2_hits']}；頭馬Top2 {scaffold_baseline['winner_top2']}。",
            "",
            "## 候選結果",
            "",
            "| 候選 | 0/1/2 hit | 對原模型Δhits/Δ頭馬/Δ0 | 對純骨架Δhits/Δ頭馬/Δ0 | helped/harmed | 第三選有效/有害/淨值 | 邊界同分 | Step 6 |",
            "|---|---|---|---|---:|---:|---:|---|",
        ]
    )
    for name in CANDIDATES:
        metric = metrics[name]
        dist = metric["distribution"]
        gate = gates[name]
        compare = comparisons[name]
        scaffold_compare = scaffold_comparisons[name]
        lines.append(
            f"| {name} | {dist['0']}/{dist['1']}/{dist['2']} | "
            f"{gate['top2_hit_delta']:+d}/{gate['winner_top2_delta']:+d}/{gate['zero_hit_delta']:+d} | "
            f"{metric['total_top2_hits'] - scaffold_baseline['total_top2_hits']:+d}/"
            f"{metric['winner_top2'] - scaffold_baseline['winner_top2']:+d}/"
            f"{dist['0'] - scaffold_dist['0']:+d} | "
            f"{compare['hit_helped']}/{compare['hit_harmed']} | "
            f"{compare['effective_rank3_rescues']}/{compare['harmful_rank3_promotions']}/{compare['rank3_rescue_net']:+d} | "
            f"{tie_stats[name]['development_boundary_ties']} | "
            f"{'是－' + gate['path'] if gate['advances_to_step6'] else '否'} |"
        )
    advancing = [name for name, gate in gates.items() if gate["advances_to_step6"]]
    lines.extend(
        [
            "",
            "## Step 5b結論",
            "",
            f"- 可解封Step 6嘅候選：{', '.join(advancing) if advancing else '無'}。",
            f"- Matrix load errors：{len(load_errors)}；validation errors：{len(errors)}。",
            "- 正式Auto engine保持不變。",
        ]
    )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "csv": str(csv_path),
                "json": str(json_path),
                "report": str(report_path),
                "advancing": advancing,
                "matrix_load_errors": load_errors,
                "validation_errors": errors,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--dimensions", type=Path, default=DEFAULT_DIMENSIONS)
    parser.add_argument("--replay", type=Path, default=ROOT / "scratch" / "hkjc_prerace_replay.csv")
    parser.add_argument(
        "--output-prefix",
        type=Path,
        default=ROOT / "scratch" / "hkjc_surgical_dimension_candidates",
    )
    args = parser.parse_args()
    rebuilt = load_rebuilt_dimensions(args.dimensions)
    current_matrix, load_errors = load_current_matrix(args.manifest, args.archive, rebuilt)
    rows, selections, tie_stats = build_rows(rebuilt, current_matrix)
    reference = load_development_reference(args.replay)
    races = development_races(reference)
    original_baseline = selection_metrics(baseline_selections(races), races)
    scaffold_baseline = selection_metrics(
        {race: picks for race, picks in selections["pure_scaffold"].items() if race in races},
        races,
    )
    metrics = {
        name: selection_metrics({race: picks for race, picks in selections[name].items() if race in races}, races)
        for name in CANDIDATES
    }
    comparisons = {name: compare_candidate(original_baseline, metrics[name], races) for name in CANDIDATES}
    scaffold_comparisons = {name: compare_candidate(scaffold_baseline, metrics[name], races) for name in CANDIDATES}
    gates = {
        name: development_gate(original_baseline, metrics[name], comparisons[name], tie_stats[name])
        for name in CANDIDATES
    }
    errors = validate(rows, load_errors, tie_stats)
    write_outputs(
        rows,
        tie_stats,
        original_baseline,
        scaffold_baseline,
        metrics,
        comparisons,
        scaffold_comparisons,
        gates,
        load_errors,
        errors,
        args.output_prefix,
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
