#!/usr/bin/env python3
"""Step 5d: fixed HKJC readiness-slot and trainer-uncertainty candidates.

Candidate ranks for all splits are frozen before development outcomes are
loaded.  Official outer weights remain unchanged.  This script performs a
three-way structural ablation; it does not search weights or thresholds.
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
from hkjc_surgical_dimension_candidates import load_current_matrix


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIMENSIONS = ROOT / "scratch" / "hkjc_rebuilt_dimensions.csv"
DEVELOPMENT_SPLIT = "archive_development"

CANDIDATES = {
    "readiness_slot_only": {
        "readiness_slot": True,
        "trainer_shrink": False,
        "hypothesis": "以重建readiness-risk取代現行health槽，其餘dimension及官方outer weights不變。",
    },
    "trainer_reliability_shrink_only": {
        "readiness_slot": False,
        "trainer_shrink": True,
        "hypothesis": "保留現行trainer分，但按既有pre-race證據可靠度向中性60收縮。",
    },
    "readiness_plus_trainer_shrink": {
        "readiness_slot": True,
        "trainer_shrink": True,
        "hypothesis": "合併readiness health-slot重建與trainer可靠度收縮，無額外互動項。",
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


def key(dataset: str, meeting: str, race_number: int, horse_number: int) -> tuple[str, str, int, int]:
    return dataset, meeting, race_number, horse_number


def load_rebuilt(path: Path) -> dict[tuple[str, str, int, int], dict[str, Any]]:
    output = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            item = key(row["dataset"], row["meeting"], as_int(row["race_number"]), as_int(row["horse_number"]))
            output[item] = {
                "split": row["split"],
                "horse_name": row.get("horse_name", ""),
                "is_debut": as_int(row.get("is_debut")),
                "dim_readiness_risk": as_float(row.get("dim_readiness_risk")),
                "reliability_readiness_risk": as_float(row.get("reliability_readiness_risk"), 0.0),
                "reliability_trainer_signal": as_float(row.get("reliability_trainer_signal"), 0.0),
            }
    return output


def candidate_components(
    matrix: dict[str, float],
    rebuilt: dict[str, Any],
    candidate: dict[str, Any],
) -> tuple[dict[str, float], float, float]:
    adjusted = dict(matrix)
    readiness_value = matrix["horse_health"]
    trainer_value = matrix["trainer_signal"]
    if candidate["readiness_slot"]:
        readiness_value = rebuilt["dim_readiness_risk"]
        adjusted["horse_health"] = readiness_value
    if candidate["trainer_shrink"]:
        reliability = max(0.0, min(1.0, rebuilt["reliability_trainer_signal"]))
        trainer_value = 60.0 + reliability * (matrix["trainer_signal"] - 60.0)
        adjusted["trainer_signal"] = trainer_value
    return adjusted, round(readiness_value, 4), round(trainer_value, 4)


def weighted_score(matrix: dict[str, float], is_debut: int) -> float:
    weights = DEBUT_MATRIX_WEIGHTS if is_debut else MATRIX_WEIGHTS
    return round(sum(matrix.get(dimension, 60.0) * weight for dimension, weight in weights.items()), 4)


def build_rows(
    rebuilt: dict[tuple[str, str, int, int], dict[str, Any]],
    current_matrix: dict[tuple[str, str, int, int], dict[str, float]],
) -> tuple[list[dict[str, Any]], dict[str, dict[tuple[str, str, int], list[int]]], dict[str, dict[str, Any]]]:
    rows = []
    grouped: defaultdict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for item in sorted(rebuilt):
        if item not in current_matrix:
            continue
        info = rebuilt[item]
        matrix = current_matrix[item]
        row = {
            "dataset": item[0],
            "split": info["split"],
            "meeting": item[1],
            "race_number": item[2],
            "horse_number": item[3],
            "horse_name": info["horse_name"],
            "is_debut": info["is_debut"],
            "current_horse_health": round(matrix["horse_health"], 4),
            "rebuilt_readiness_risk": round(info["dim_readiness_risk"], 4),
            "readiness_reliability": round(info["reliability_readiness_risk"], 4),
            "current_trainer_signal": round(matrix["trainer_signal"], 4),
            "trainer_reliability": round(info["reliability_trainer_signal"], 4),
            "score_pure_scaffold": weighted_score(matrix, info["is_debut"]),
        }
        for name, candidate in CANDIDATES.items():
            adjusted, readiness_value, trainer_value = candidate_components(matrix, info, candidate)
            row[f"adjusted_health_{name}"] = readiness_value
            row[f"adjusted_trainer_{name}"] = trainer_value
            row[f"score_{name}"] = weighted_score(adjusted, info["is_debut"])
        rows.append(row)
        grouped[item[:3]].append(row)

    names = ("pure_scaffold", *CANDIDATES)
    selections: dict[str, dict[tuple[str, str, int], list[int]]] = {name: {} for name in names}
    tie_stats = {}
    for name in names:
        all_ties = 0
        development_ties = 0
        development_count = 0
        for race, race_rows in grouped.items():
            ranked = sorted(race_rows, key=lambda row: (-row[f"score_{name}"], row["horse_number"]))
            for rank, row in enumerate(ranked, start=1):
                row[f"rank_{name}"] = rank
            selections[name][race] = [row["horse_number"] for row in ranked[:2]]
            tied = len(ranked) >= 3 and abs(ranked[1][f"score_{name}"] - ranked[2][f"score_{name}"]) < 1e-9
            all_ties += int(tied)
            if ranked[0]["split"] == DEVELOPMENT_SPLIT:
                development_count += 1
                development_ties += int(tied)
        tie_stats[name] = {
            "all_races": len(grouped),
            "all_boundary_ties": all_ties,
            "all_boundary_tie_rate": round(all_ties / len(grouped) * 100, 1),
            "development_races": development_count,
            "development_boundary_ties": development_ties,
            "development_boundary_tie_rate": round(development_ties / development_count * 100, 1),
        }
    return rows, selections, tie_stats


def validate(
    rows: list[dict[str, Any]],
    tie_stats: dict[str, dict[str, Any]],
    load_errors: list[dict[str, Any]],
) -> list[str]:
    errors = []
    if load_errors:
        errors.append(f"matrix load errors: {len(load_errors)}")
    if len(rows) != 3054:
        errors.append(f"rows {len(rows)} != 3054")
    if any(column.startswith(("label_", "reference_")) for column in rows[0]):
        errors.append("outcome/reference leaked into candidate output")
    for row in rows:
        if not 0.0 <= row["trainer_reliability"] <= 1.0:
            errors.append("trainer reliability out of range")
            break
        for name in ("pure_scaffold", *CANDIDATES):
            if not 0.0 <= float(row[f"score_{name}"]) <= 100.0:
                errors.append(f"score out of range: {name}")
            if int(row[f"rank_{name}"]) < 1:
                errors.append(f"rank out of range: {name}")
        for name in CANDIDATES:
            if not 0.0 <= float(row[f"adjusted_health_{name}"]) <= 100.0:
                errors.append(f"health component out of range: {name}")
            if not 0.0 <= float(row[f"adjusted_trainer_{name}"]) <= 100.0:
                errors.append(f"trainer component out of range: {name}")
    if any(stats["all_races"] != 245 or stats["development_races"] != 88 for stats in tie_stats.values()):
        errors.append("race count mismatch")
    return sorted(set(errors))


def compact(metric: dict[str, Any]) -> dict[str, Any]:
    return {name: value for name, value in metric.items() if name != "per_race"}


def development_profiles(
    rows: list[dict[str, Any]],
    original_baseline: dict[str, Any],
    metrics: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    debut_lookup = {
        (row["dataset"], row["meeting"], row["race_number"], row["horse_number"]): bool(row["is_debut"])
        for row in rows
    }
    profiles = {}
    for name, metric in metrics.items():
        days: defaultdict[str, dict[str, int]] = defaultdict(
            lambda: {"races": 0, "hit_delta": 0, "winner_delta": 0, "zero_delta": 0}
        )
        changed_races = 0
        debut_involved_changed = 0
        debut_involved_helped = 0
        debut_involved_harmed = 0
        for race, base in original_baseline["per_race"].items():
            candidate = metric["per_race"][race]
            meeting = race[1]
            days[meeting]["races"] += 1
            days[meeting]["hit_delta"] += candidate["hits"] - base["hits"]
            days[meeting]["winner_delta"] += candidate["winner"] - base["winner"]
            days[meeting]["zero_delta"] += int(candidate["hits"] == 0) - int(base["hits"] == 0)
            changed = set(candidate["selected"]) != set(base["selected"])
            if not changed:
                continue
            changed_races += 1
            changed_horses = set(candidate["selected"]) ^ set(base["selected"])
            debut_involved = any(debut_lookup.get((*race, horse_number), False) for horse_number in changed_horses)
            debut_involved_changed += int(debut_involved)
            debut_involved_helped += int(debut_involved and candidate["hits"] > base["hits"])
            debut_involved_harmed += int(debut_involved and candidate["hits"] < base["hits"])
        day_rows = [dict(meeting=meeting, **values) for meeting, values in sorted(days.items())]
        profiles[name] = {
            "changed_races": changed_races,
            "debut_involved_changed_races": debut_involved_changed,
            "debut_involved_helped_races": debut_involved_helped,
            "debut_involved_harmed_races": debut_involved_harmed,
            "hit_days_positive_equal_negative": [
                sum(day["hit_delta"] > 0 for day in day_rows),
                sum(day["hit_delta"] == 0 for day in day_rows),
                sum(day["hit_delta"] < 0 for day in day_rows),
            ],
            "winner_days_positive_equal_negative": [
                sum(day["winner_delta"] > 0 for day in day_rows),
                sum(day["winner_delta"] == 0 for day in day_rows),
                sum(day["winner_delta"] < 0 for day in day_rows),
            ],
            "zero_days_better_equal_worse": [
                sum(day["zero_delta"] < 0 for day in day_rows),
                sum(day["zero_delta"] == 0 for day in day_rows),
                sum(day["zero_delta"] > 0 for day in day_rows),
            ],
            "per_meeting": day_rows,
        }
    return profiles


def write_outputs(
    output_prefix: Path,
    rows: list[dict[str, Any]],
    tie_stats: dict[str, dict[str, Any]],
    original_baseline: dict[str, Any],
    scaffold_baseline: dict[str, Any],
    metrics: dict[str, dict[str, Any]],
    comparisons: dict[str, dict[str, Any]],
    scaffold_comparisons: dict[str, dict[str, Any]],
    gates: dict[str, dict[str, Any]],
    profiles: dict[str, dict[str, Any]],
    load_errors: list[dict[str, Any]],
    errors: list[str],
) -> dict[str, str]:
    csv_path = output_prefix.with_suffix(".csv")
    json_path = output_prefix.with_suffix(".json")
    report_path = output_prefix.with_name(output_prefix.name + "_report").with_suffix(".md")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    advancing = [name for name, gate in gates.items() if gate["advances_to_step6"]]
    payload = {
        "method": {
            "candidate_definitions": CANDIDATES,
            "official_outer_weights": MATRIX_WEIGHTS,
            "official_debut_outer_weights": DEBUT_MATRIX_WEIGHTS,
            "trainer_shrink_formula": "60 + reliability_trainer_signal * (current_trainer_signal - 60)",
            "weight_or_threshold_search": False,
            "formal_auto_changed": False,
        },
        "original_baseline": compact(original_baseline),
        "pure_scaffold_baseline": compact(scaffold_baseline),
        "candidate_metrics": {name: compact(metric) for name, metric in metrics.items()},
        "comparisons_to_original": comparisons,
        "comparisons_to_pure_scaffold": scaffold_comparisons,
        "tie_stats": tie_stats,
        "development_gates": gates,
        "development_profiles": profiles,
        "advancing_to_step6": advancing,
        "matrix_load_errors": load_errors,
        "validation_errors": errors,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    base_dist = original_baseline["distribution"]
    scaffold_dist = scaffold_baseline["distribution"]
    lines = [
        "# HKJC Dimension重建 Step 5d — 不確定性槽固定候選",
        "",
        "## 方法鎖定",
        "",
        "- 三案只做readiness health-slot及trainer證據可靠度收縮嘅固定ablation；無搜尋權重、threshold或收縮倍率。",
        "- Trainer收縮公式固定為：60 + reliability ×（現行trainer分 − 60）；可靠度0回中性60，可靠度1保留原分。",
        "- 沿用現行官方outer weights及初出馬weights；全245場先完整重排，再載入88場development結果。",
        "- 無micro tie-break、無第二／第三選盲換；正式Auto保持不變。",
        "",
        "## 固定候選",
        "",
        "| 候選 | Readiness槽 | Trainer收縮 | 假設 |",
        "|---|---:|---:|---|",
    ]
    for name, candidate in CANDIDATES.items():
        lines.append(
            f"| {name} | {'是' if candidate['readiness_slot'] else '否'} | "
            f"{'是' if candidate['trainer_shrink'] else '否'} | {candidate['hypothesis']} |"
        )
    lines.extend(
        [
            "",
            "## Development雙基準",
            "",
            f"- 原模型Top2：0／1／2 hit {base_dist['0']}/{base_dist['1']}/{base_dist['2']}；總hits {original_baseline['total_top2_hits']}；頭馬Top2 {original_baseline['winner_top2']}。",
            f"- 原matrix純加權骨架：0／1／2 hit {scaffold_dist['0']}/{scaffold_dist['1']}/{scaffold_dist['2']}；總hits {scaffold_baseline['total_top2_hits']}；頭馬Top2 {scaffold_baseline['winner_top2']}。",
            "",
            "## 候選結果",
            "",
            "| 候選 | 0/1/2 hit | 對原模型Δhits/Δ頭馬/Δ0 | Top2變動 | helped/harmed | 第三選有效/有害/淨值 | 邊界同分 | Step 6 |",
            "|---|---|---|---:|---:|---:|---:|---|",
        ]
    )
    for name in CANDIDATES:
        metric = metrics[name]
        comparison = comparisons[name]
        gate = gates[name]
        distribution = metric["distribution"]
        lines.append(
            f"| {name} | {distribution['0']}/{distribution['1']}/{distribution['2']} | "
            f"{gate['top2_hit_delta']:+d}/{gate['winner_top2_delta']:+d}/{gate['zero_hit_delta']:+d} | "
            f"{comparison['top2_set_changes']} | {comparison['hit_helped']}/{comparison['hit_harmed']} | "
            f"{comparison['effective_rank3_rescues']}/{comparison['harmful_rank3_promotions']}/{comparison['rank3_rescue_net']:+d} | "
            f"{tie_stats[name]['development_boundary_ties']} | {'是' if gate['advances_to_step6'] else '否'} |"
        )
    lines.extend(
        [
            "",
            "## Development分散度與初出馬影響",
            "",
            "| 候選 | hits賽日 +/=/- | 頭馬賽日 +/=/- | 0-hit賽日 改善/不變/轉差 | 變動場次含初出 | 初出相關 helped/harmed |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for name in CANDIDATES:
        profile = profiles[name]
        hit_days = "/".join(str(value) for value in profile["hit_days_positive_equal_negative"])
        winner_days = "/".join(str(value) for value in profile["winner_days_positive_equal_negative"])
        zero_days = "/".join(str(value) for value in profile["zero_days_better_equal_worse"])
        lines.append(
            f"| {name} | {hit_days} | {winner_days} | {zero_days} | "
            f"{profile['debut_involved_changed_races']}/{profile['changed_races']} | "
            f"{profile['debut_involved_helped_races']}/{profile['debut_involved_harmed_races']} |"
        )
    lines.extend(
        [
            "",
            "## Step 5d結論",
            "",
            f"- 可解封Step 6嘅候選：{', '.join(advancing) if advancing else '無'}。",
            f"- Matrix load errors：{len(load_errors)}；validation errors：{len(errors)}。",
            "- 未通過候選唔會用holdout結果再調公式；正式Auto保持不變。",
        ]
    )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"csv": str(csv_path), "json": str(json_path), "report": str(report_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--dimensions", type=Path, default=DEFAULT_DIMENSIONS)
    parser.add_argument("--replay", type=Path, default=ROOT / "scratch" / "hkjc_prerace_replay.csv")
    parser.add_argument("--output-prefix", type=Path, default=ROOT / "scratch" / "hkjc_uncertainty_slot_candidates")
    args = parser.parse_args()

    rebuilt = load_rebuilt(args.dimensions)
    current_matrix, load_errors = load_current_matrix(args.manifest, args.archive, rebuilt)
    rows, selections, tie_stats = build_rows(rebuilt, current_matrix)
    reference = load_development_reference(args.replay)
    races = development_races(reference)
    original_baseline = selection_metrics(baseline_selections(races), races)
    scaffold_baseline = selection_metrics(
        {race: picks for race, picks in selections["pure_scaffold"].items() if race in races}, races
    )
    metrics = {
        name: selection_metrics({race: picks for race, picks in selections[name].items() if race in races}, races)
        for name in CANDIDATES
    }
    comparisons = {name: compare_candidate(original_baseline, metrics[name], races) for name in CANDIDATES}
    scaffold_comparisons = {
        name: compare_candidate(scaffold_baseline, metrics[name], races) for name in CANDIDATES
    }
    gates = {
        name: development_gate(original_baseline, metrics[name], comparisons[name], tie_stats[name])
        for name in CANDIDATES
    }
    profiles = development_profiles(rows, original_baseline, metrics)
    errors = validate(rows, tie_stats, load_errors)
    outputs = write_outputs(
        args.output_prefix,
        rows,
        tie_stats,
        original_baseline,
        scaffold_baseline,
        metrics,
        comparisons,
        scaffold_comparisons,
        gates,
        profiles,
        load_errors,
        errors,
    )
    advancing = [name for name, gate in gates.items() if gate["advances_to_step6"]]
    print(json.dumps({**outputs, "advancing": advancing, "validation_errors": errors}, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
