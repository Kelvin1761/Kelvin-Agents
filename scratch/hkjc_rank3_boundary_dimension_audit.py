#!/usr/bin/env python3
"""Step 5c: fixed dimension audit for HKJC rank-2 versus rank-3 boundary.

This is a diagnostic, not a candidate generator.  Predictors are loaded first,
then development outcomes are joined only to classify fixed rank-2/rank-3
pairs.  No weights, thresholds, ranks, or selections are optimized here.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from hkjc_rating_matrix_audit import DEBUT_MATRIX_WEIGHTS, MATRIX_WEIGHTS


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPLAY = ROOT / "scratch" / "hkjc_prerace_replay.csv"
DEFAULT_REBUILT = ROOT / "scratch" / "hkjc_rebuilt_dimensions.csv"
DEFAULT_ARCHIVE = (
    ROOT
    / ".agents"
    / "skills"
    / "hkjc_racing"
    / "hkjc_reflector"
    / "artifacts"
    / "hkjc_ranking_dataset.csv"
)
DEFAULT_OUTPUT = ROOT / "scratch" / "hkjc_rank3_boundary_dimension_audit"
DEVELOPMENT_SPLIT = "archive_development"

OFFICIAL_DIMENSIONS = tuple(MATRIX_WEIGHTS)
REBUILT_DIMENSIONS = (
    "speed_engine",
    "stability",
    "distance_context",
    "class_weight",
    "trainer_signal",
    "readiness_risk",
    "form_line",
)


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


def horse_key(meeting: str, race_number: int, horse_number: int) -> tuple[str, int, int]:
    return meeting, race_number, horse_number


def auc(labels: list[int], scores: list[float]) -> float | None:
    positives = [score for label, score in zip(labels, scores) if label == 1]
    negatives = [score for label, score in zip(labels, scores) if label == 0]
    if not positives or not negatives:
        return None
    wins = 0.0
    for positive in positives:
        for negative in negatives:
            wins += float(positive > negative) + 0.5 * float(positive == negative)
    return round(wins / (len(positives) * len(negatives)), 4)


def load_development_keys(path: Path) -> set[tuple[str, int, int]]:
    keys = set()
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("split") == DEVELOPMENT_SPLIT:
                keys.add(horse_key(row["meeting"], as_int(row["race_number"]), as_int(row["horse_number"])))
    return keys


def load_official_predictors(
    path: Path,
    development_keys: set[tuple[str, int, int]],
) -> dict[tuple[str, int, int], dict[str, Any]]:
    predictors = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            meeting = str(row.get("meeting_name") or Path(str(row.get("meeting") or "")).name)
            key = horse_key(meeting, as_int(row["race_number"]), as_int(row["horse_number"]))
            if key not in development_keys:
                continue
            is_debut = as_int(row.get("is_debut"))
            matrix = {dimension: as_float(row.get(f"matrix_{dimension}")) for dimension in OFFICIAL_DIMENSIONS}
            weights = DEBUT_MATRIX_WEIGHTS if is_debut else MATRIX_WEIGHTS
            predictors[key] = {
                "is_debut": is_debut,
                "official": matrix,
                "pure_matrix_total": round(
                    sum(matrix.get(dimension, 60.0) * weight for dimension, weight in weights.items()), 4
                ),
            }
    return predictors


def load_rebuilt_predictors(
    path: Path,
    development_keys: set[tuple[str, int, int]],
) -> dict[tuple[str, int, int], dict[str, Any]]:
    predictors = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("split") != DEVELOPMENT_SPLIT:
                continue
            key = horse_key(row["meeting"], as_int(row["race_number"]), as_int(row["horse_number"]))
            if key not in development_keys:
                continue
            predictors[key] = {
                "horse_name": row.get("horse_name", ""),
                "distance_num": as_int(row.get("distance_num")),
                "race_class_num": as_int(row.get("race_class_num")),
                "rebuild_reliability_mean": as_float(row.get("rebuild_reliability_mean"), 0.0),
                "rebuild_uncertainty": as_float(row.get("rebuild_uncertainty"), 1.0),
                "rebuilt": {
                    dimension: as_float(row.get(f"dim_{dimension}")) for dimension in REBUILT_DIMENSIONS
                },
                "reliability": {
                    dimension: as_float(row.get(f"reliability_{dimension}"), 0.0)
                    for dimension in REBUILT_DIMENSIONS
                },
            }
    return predictors


def load_development_reference(path: Path) -> dict[tuple[str, int, int], dict[str, Any]]:
    reference = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("split") != DEVELOPMENT_SPLIT:
                continue
            key = horse_key(row["meeting"], as_int(row["race_number"]), as_int(row["horse_number"]))
            reference[key] = {
                "original_rank": as_int(row["reference_original_rank"]),
                "is_top3": bool(as_int(row["label_is_top3"])),
                "is_winner": bool(as_int(row["label_is_winner"])),
            }
    return reference


def build_races(
    reference: dict[tuple[str, int, int], dict[str, Any]],
) -> dict[tuple[str, int], dict[int, dict[str, Any]]]:
    races: defaultdict[tuple[str, int], dict[int, dict[str, Any]]] = defaultdict(dict)
    for (meeting, race_number, horse_number), labels in reference.items():
        races[(meeting, race_number)][horse_number] = labels
    return dict(races)


def build_pairs(
    races: dict[tuple[str, int], dict[int, dict[str, Any]]],
    official: dict[tuple[str, int, int], dict[str, Any]],
    rebuilt: dict[tuple[str, int, int], dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    pairs = []
    errors = []
    hit_distribution = Counter()
    failure_rank3_placed = Counter()
    boundary_rescues = Counter()
    no_net_rank3 = Counter()
    for race_key, horses in sorted(races.items()):
        ranked = sorted(horses.items(), key=lambda item: item[1]["original_rank"])
        rank_map = {labels["original_rank"]: number for number, labels in ranked}
        if 2 not in rank_map or 3 not in rank_map:
            errors.append(f"missing rank 2/3: {race_key}")
            continue
        top2 = [number for number, labels in ranked if labels["original_rank"] <= 2]
        hits = sum(horses[number]["is_top3"] for number in top2)
        hit_distribution[hits] += 1
        r2_number = rank_map[2]
        r3_number = rank_map[3]
        r2_label = horses[r2_number]
        r3_label = horses[r3_number]
        if hits <= 1 and r3_label["is_top3"]:
            failure_rank3_placed[hits] += 1
            if not r2_label["is_top3"]:
                boundary_rescues[hits] += 1
            else:
                no_net_rank3[hits] += 1
        if r2_label["is_top3"] == r3_label["is_top3"]:
            pair_type = "both_placed" if r2_label["is_top3"] else "both_missed"
            boundary_label = "neutral"
        elif r3_label["is_top3"]:
            pair_type = "rank3_rescue"
            boundary_label = "rank3_better"
        else:
            pair_type = "rank2_protect"
            boundary_label = "rank2_better"
        r2_key = horse_key(race_key[0], race_key[1], r2_number)
        r3_key = horse_key(race_key[0], race_key[1], r3_number)
        if r2_key not in official or r3_key not in official or r2_key not in rebuilt or r3_key not in rebuilt:
            errors.append(f"missing predictors: {race_key}")
            continue
        row = {
            "meeting": race_key[0],
            "race_number": race_key[1],
            "baseline_hits": hits,
            "pair_type": pair_type,
            "boundary_label": boundary_label,
            "rank2_number": r2_number,
            "rank2_name": rebuilt[r2_key]["horse_name"],
            "rank2_is_top3": int(r2_label["is_top3"]),
            "rank3_number": r3_number,
            "rank3_name": rebuilt[r3_key]["horse_name"],
            "rank3_is_top3": int(r3_label["is_top3"]),
            "distance_num": rebuilt[r2_key]["distance_num"],
            "race_class_num": rebuilt[r2_key]["race_class_num"],
            "gap_official_pure_total": round(
                official[r3_key]["pure_matrix_total"] - official[r2_key]["pure_matrix_total"], 4
            ),
        }
        for dimension in OFFICIAL_DIMENSIONS:
            gap = official[r3_key]["official"][dimension] - official[r2_key]["official"][dimension]
            row[f"gap_official_{dimension}"] = round(gap, 4)
            row[f"weighted_gap_official_{dimension}"] = round(gap * MATRIX_WEIGHTS[dimension], 4)
        for dimension in REBUILT_DIMENSIONS:
            row[f"gap_rebuilt_{dimension}"] = round(
                rebuilt[r3_key]["rebuilt"][dimension] - rebuilt[r2_key]["rebuilt"][dimension], 4
            )
            row[f"reliability_rank2_{dimension}"] = round(rebuilt[r2_key]["reliability"][dimension], 4)
            row[f"reliability_rank3_{dimension}"] = round(rebuilt[r3_key]["reliability"][dimension], 4)
        pairs.append(row)
    summary = {
        "races": len(races),
        "baseline_hit_distribution": {str(hit): hit_distribution[hit] for hit in (0, 1, 2)},
        "failure_races": hit_distribution[0] + hit_distribution[1],
        "rank3_placed_in_failures": {str(hit): failure_rank3_placed[hit] for hit in (0, 1)},
        "boundary_rescue_ceiling": {str(hit): boundary_rescues[hit] for hit in (0, 1)},
        "rank3_placed_but_no_boundary_net_gain": {str(hit): no_net_rank3[hit] for hit in (0, 1)},
    }
    rescue_zero = boundary_rescues[0]
    rescue_one = boundary_rescues[1]
    summary["perfect_rank3_boundary_ceiling_distribution"] = {
        "0": hit_distribution[0] - rescue_zero,
        "1": hit_distribution[1] + rescue_zero - rescue_one,
        "2": hit_distribution[2] + rescue_one,
    }
    summary["perfect_rank3_boundary_ceiling_total_hits"] = (
        hit_distribution[1] + 2 * hit_distribution[2] + rescue_zero + rescue_one
    )
    return pairs, summary, errors


def metric_row(
    pairs: list[dict[str, Any]],
    family: str,
    dimension: str,
    gap_column: str,
) -> dict[str, Any]:
    discriminating = [row for row in pairs if row["boundary_label"] != "neutral"]
    rescue = [row for row in discriminating if row["boundary_label"] == "rank3_better"]
    protect = [row for row in discriminating if row["boundary_label"] == "rank2_better"]
    labels = [1 if row["boundary_label"] == "rank3_better" else 0 for row in discriminating]
    gaps = [float(row[gap_column]) for row in discriminating]
    oriented = [gap if label == 1 else -gap for label, gap in zip(labels, gaps)]
    correct = sum(value > 0 for value in oriented)
    ties = sum(value == 0 for value in oriented)
    rescue_gaps = [float(row[gap_column]) for row in rescue]
    protect_gaps = [-float(row[gap_column]) for row in protect]
    rescue_correct = sum(value > 0 for value in rescue_gaps)
    rescue_ties = sum(value == 0 for value in rescue_gaps)
    protect_correct = sum(value > 0 for value in protect_gaps)
    protect_ties = sum(value == 0 for value in protect_gaps)
    rescue_adjusted_rate = (rescue_correct + 0.5 * rescue_ties) / len(rescue_gaps)
    protect_adjusted_rate = (protect_correct + 0.5 * protect_ties) / len(protect_gaps)
    by_day: defaultdict[str, list[float]] = defaultdict(list)
    for row, value in zip(discriminating, oriented):
        by_day[row["meeting"]].append(value)
    day_means = [statistics.mean(values) for values in by_day.values()]
    reliable_pairs = []
    if family == "rebuilt_dimension":
        reliable_pairs = [
            row
            for row in discriminating
            if min(
                float(row[f"reliability_rank2_{dimension}"]),
                float(row[f"reliability_rank3_{dimension}"]),
            )
            >= 0.50
        ]
    reliable_rescue = [row for row in reliable_pairs if row["boundary_label"] == "rank3_better"]
    reliable_protect = [row for row in reliable_pairs if row["boundary_label"] == "rank2_better"]
    reliable_auc = None
    reliable_balanced = None
    if reliable_rescue and reliable_protect:
        reliable_labels = [1 if row["boundary_label"] == "rank3_better" else 0 for row in reliable_pairs]
        reliable_gaps = [float(row[gap_column]) for row in reliable_pairs]
        reliable_auc = auc(reliable_labels, reliable_gaps)
        reliable_rescue_gaps = [float(row[gap_column]) for row in reliable_rescue]
        reliable_protect_gaps = [-float(row[gap_column]) for row in reliable_protect]
        reliable_rescue_rate = (
            sum(value > 0 for value in reliable_rescue_gaps)
            + 0.5 * sum(value == 0 for value in reliable_rescue_gaps)
        ) / len(reliable_rescue_gaps)
        reliable_protect_rate = (
            sum(value > 0 for value in reliable_protect_gaps)
            + 0.5 * sum(value == 0 for value in reliable_protect_gaps)
        ) / len(reliable_protect_gaps)
        reliable_balanced = round((reliable_rescue_rate + reliable_protect_rate) / 2.0, 4)
    return {
        "family": family,
        "dimension": dimension,
        "pairs": len(discriminating),
        "rank3_rescue_pairs": len(rescue),
        "rank2_protect_pairs": len(protect),
        "boundary_auc": auc(labels, gaps),
        "direction_correct": correct,
        "direction_ties": ties,
        "direction_accuracy": round((correct + 0.5 * ties) / len(oriented), 4),
        "balanced_direction_accuracy": round((rescue_adjusted_rate + protect_adjusted_rate) / 2.0, 4),
        "mean_oriented_gap": round(statistics.mean(oriented), 4),
        "median_oriented_gap": round(statistics.median(oriented), 4),
        "rank3_rescue_positive": rescue_correct,
        "rank3_rescue_ties": rescue_ties,
        "rank3_rescue_positive_rate": round(rescue_correct / len(rescue_gaps), 4),
        "rank3_rescue_adjusted_rate": round(rescue_adjusted_rate, 4),
        "rank3_rescue_mean_gap": round(statistics.mean(rescue_gaps), 4),
        "rank2_protect_positive": protect_correct,
        "rank2_protect_ties": protect_ties,
        "rank2_protect_positive_rate": round(protect_correct / len(protect_gaps), 4),
        "rank2_protect_adjusted_rate": round(protect_adjusted_rate, 4),
        "rank2_protect_mean_gap": round(statistics.mean(protect_gaps), 4),
        "positive_days": sum(value > 0 for value in day_means),
        "observed_days": len(day_means),
        "reliable_pairs": len(reliable_pairs),
        "reliable_rank3_rescue_pairs": len(reliable_rescue),
        "reliable_rank2_protect_pairs": len(reliable_protect),
        "reliable_boundary_auc": reliable_auc,
        "reliable_balanced_direction_accuracy": reliable_balanced,
    }


def build_metrics(pairs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [metric_row(pairs, "official_total", "pure_matrix_total", "gap_official_pure_total")]
    rows.extend(
        metric_row(pairs, "official_dimension", dimension, f"gap_official_{dimension}")
        for dimension in OFFICIAL_DIMENSIONS
    )
    rows.extend(
        metric_row(pairs, "rebuilt_dimension", dimension, f"gap_rebuilt_{dimension}")
        for dimension in REBUILT_DIMENSIONS
    )
    return rows


def dominant_blockers(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    rescue = [row for row in pairs if row["pair_type"] == "rank3_rescue"]
    official_counts = Counter()
    rebuilt_counts = Counter()
    for row in rescue:
        official_blocks = {
            dimension: -float(row[f"weighted_gap_official_{dimension}"])
            for dimension in OFFICIAL_DIMENSIONS
        }
        rebuilt_blocks = {
            dimension: -float(row[f"gap_rebuilt_{dimension}"])
            for dimension in REBUILT_DIMENSIONS
        }
        official_dimension, official_value = max(official_blocks.items(), key=lambda item: item[1])
        rebuilt_dimension, rebuilt_value = max(rebuilt_blocks.items(), key=lambda item: item[1])
        if official_value > 0:
            official_counts[official_dimension] += 1
        if rebuilt_value > 0:
            rebuilt_counts[rebuilt_dimension] += 1
    return {
        "official_weighted_dominant_blocker": dict(official_counts.most_common()),
        "rebuilt_raw_dominant_blocker": dict(rebuilt_counts.most_common()),
    }


def validate(
    development_keys: set[tuple[str, int, int]],
    official: dict[tuple[str, int, int], dict[str, Any]],
    rebuilt: dict[tuple[str, int, int], dict[str, Any]],
    reference: dict[tuple[str, int, int], dict[str, Any]],
    pairs: list[dict[str, Any]],
    summary: dict[str, Any],
    build_errors: list[str],
) -> list[str]:
    errors = list(build_errors)
    for label, rows in (
        ("development keys", development_keys),
        ("official predictors", official),
        ("rebuilt predictors", rebuilt),
        ("development reference", reference),
    ):
        if len(rows) != 1093:
            errors.append(f"{label}: {len(rows)} != 1093")
    if len(pairs) != 88 or summary["races"] != 88:
        errors.append(f"race/pair count mismatch: {summary['races']}/{len(pairs)}")
    if summary["baseline_hit_distribution"] != {"0": 21, "1": 40, "2": 27}:
        errors.append(f"baseline distribution mismatch: {summary['baseline_hit_distribution']}")
    if any("label_" in column or "reference_" in column for column in pairs[0]):
        errors.append("raw label/reference field leaked into pair output")
    return errors


def write_outputs(
    output_prefix: Path,
    pairs: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
    summary: dict[str, Any],
    blockers: dict[str, Any],
    errors: list[str],
) -> dict[str, str]:
    pair_path = output_prefix.with_name(output_prefix.name + "_pairs").with_suffix(".csv")
    metric_path = output_prefix.with_name(output_prefix.name + "_metrics").with_suffix(".csv")
    json_path = output_prefix.with_suffix(".json")
    report_path = output_prefix.with_name(output_prefix.name + "_report").with_suffix(".md")
    with pair_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(pairs[0]))
        writer.writeheader()
        writer.writerows(pairs)
    with metric_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(metrics[0]))
        writer.writeheader()
        writer.writerows(metrics)
    payload = {
        "method": {
            "split": DEVELOPMENT_SPLIT,
            "fixed_pair": "original rank 2 versus original rank 3",
            "rank3_rescue": "rank 3 placed and rank 2 missed",
            "rank2_protect": "rank 2 placed and rank 3 missed",
            "optimization": "none",
            "formal_auto_changed": False,
        },
        "summary": summary,
        "dominant_blockers": blockers,
        "metrics": metrics,
        "validation_errors": errors,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    rebuilt_metrics = [row for row in metrics if row["family"] == "rebuilt_dimension"]
    metric_lookup = {(row["family"], row["dimension"]): row for row in metrics}
    best_direction = sorted(
        rebuilt_metrics,
        key=lambda row: (-row["balanced_direction_accuracy"], -row["boundary_auc"]),
    )
    base = summary["baseline_hit_distribution"]
    ceiling = summary["perfect_rank3_boundary_ceiling_distribution"]
    lines = [
        "# HKJC Dimension重建 Step 5c — 第2／第3選邊界失誤分型",
        "",
        "## 方法鎖定",
        "",
        "- 固定比較原模型第2選與第3選；無搜尋權重、threshold或交換規則。",
        "- 第3選實際入前三而第2選甩位，定義為可救邊界；相反情況定義為必須保護。",
        "- 現行dimension及重建dimension用完全相同配對；正分差代表方向正確。",
        "- 本步只做development診斷，未建立候選，正式Auto保持不變。",
        "",
        "## 0／1-hit上限",
        "",
        f"- 原模型88場：0／1／2 hit = {base['0']}/{base['1']}/{base['2']}；0／1-hit合共{summary['failure_races']}場。",
        f"- 0-hit場有{summary['boundary_rescue_ceiling']['0']}場可由第三選正確升格變成1-hit。",
        f"- 1-hit場有{summary['boundary_rescue_ceiling']['1']}場可由第三選正確升格變成2-hit。",
        f"- 完美邊界判斷嘅理論上限：0／1／2 hit = {ceiling['0']}/{ceiling['1']}/{ceiling['2']}；總hits {summary['perfect_rank3_boundary_ceiling_total_hits']}。",
        "",
        "## Dimension方向診斷",
        "",
        "| 類別 | Dimension | 邊界AUC | 平衡方向準確 | 可救方向（含同分） | 保護方向（含同分） | 平均正向分差 | 正向賽日 |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in metrics:
        lines.append(
            f"| {row['family']} | {row['dimension']} | {row['boundary_auc']:.3f} | "
            f"{row['balanced_direction_accuracy'] * 100:.1f}% | "
            f"{row['rank3_rescue_adjusted_rate'] * 100:.1f}% | "
            f"{row['rank2_protect_adjusted_rate'] * 100:.1f}% | {row['mean_oriented_gap']:+.3f} | "
            f"{row['positive_days']}/{row['observed_days']} |"
        )
    lines.extend(
        [
            "",
            "## 重建Dimension可靠度檢查",
            "",
            "- 固定使用Step 4既有門檻：第2及第3選兩匹馬該dimension可靠度均須≥0.50；無重新選threshold。",
            "",
            "| Dimension | 可靠配對（可救/保護） | 可靠配對AUC | 可靠配對平衡方向 |",
            "|---|---:|---:|---:|",
        ]
    )
    for row in rebuilt_metrics:
        reliable_auc_text = "N/A" if row["reliable_boundary_auc"] is None else f"{row['reliable_boundary_auc']:.3f}"
        reliable_balanced_text = (
            "N/A"
            if row["reliable_balanced_direction_accuracy"] is None
            else f"{row['reliable_balanced_direction_accuracy'] * 100:.1f}%"
        )
        lines.append(
            f"| {row['dimension']} | {row['reliable_pairs']} "
            f"({row['reliable_rank3_rescue_pairs']}/{row['reliable_rank2_protect_pairs']}) | "
            f"{reliable_auc_text} | {reliable_balanced_text} |"
        )
    lines.extend(
        [
            "",
            "## 固定讀法",
            "",
            f"- 重建dimension平衡方向最好：{best_direction[0]['dimension']}（{best_direction[0]['balanced_direction_accuracy'] * 100:.1f}%）；其次{best_direction[1]['dimension']}（{best_direction[1]['balanced_direction_accuracy'] * 100:.1f}%）。",
            f"- 現行加權dominant blocker：{json.dumps(blockers['official_weighted_dominant_blocker'], ensure_ascii=False)}。",
            f"- 重建raw dominant blocker：{json.dumps(blockers['rebuilt_raw_dominant_blocker'], ensure_ascii=False)}。",
            f"- Validation errors：{len(errors)}。",
            "",
            "## Step 5c結論",
            "",
            f"- 現行純矩陣偏向保住第2選：可救方向只有{metric_lookup[('official_total', 'pure_matrix_total')]['rank3_rescue_adjusted_rate'] * 100:.1f}%，保護方向{metric_lookup[('official_total', 'pure_matrix_total')]['rank2_protect_adjusted_rate'] * 100:.1f}%。",
            f"- 現行form-line應保留：平衡方向{metric_lookup[('official_dimension', 'form_line')]['balanced_direction_accuracy'] * 100:.1f}%、AUC {metric_lookup[('official_dimension', 'form_line')]['boundary_auc']:.3f}，優於重建form-line。",
            f"- readiness-risk係唯一同時有合理可救及保護方向、而可靠樣本亦無倒退嘅重建項：全配對平衡方向{metric_lookup[('rebuilt_dimension', 'readiness_risk')]['balanced_direction_accuracy'] * 100:.1f}%／AUC {metric_lookup[('rebuilt_dimension', 'readiness_risk')]['boundary_auc']:.3f}；可靠配對{metric_lookup[('rebuilt_dimension', 'readiness_risk')]['reliable_balanced_direction_accuracy'] * 100:.1f}%／AUC {metric_lookup[('rebuilt_dimension', 'readiness_risk')]['reliable_boundary_auc']:.3f}。",
            f"- class-weight雖然可救方向達{metric_lookup[('rebuilt_dimension', 'class_weight')]['rank3_rescue_adjusted_rate'] * 100:.1f}%，但保護方向只有{metric_lookup[('rebuilt_dimension', 'class_weight')]['rank2_protect_adjusted_rate'] * 100:.1f}%，不適合單獨推高。",
            "- speed-engine、distance-context及兩個trainer版本均未顯示可兼顧可救與保護嘅邊界能力；唔據此建立候選。",
            "- 下一步只值得凍結細幅結構候選：以readiness-risk重建現行horse-health細權重槽；trainer只可測試證據可靠度收縮，不能直接換入重建trainer。",
        ]
    )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "pairs": str(pair_path),
        "metrics": str(metric_path),
        "json": str(json_path),
        "report": str(report_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay", type=Path, default=DEFAULT_REPLAY)
    parser.add_argument("--rebuilt", type=Path, default=DEFAULT_REBUILT)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--output-prefix", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    development_keys = load_development_keys(args.replay)
    official = load_official_predictors(args.archive, development_keys)
    rebuilt = load_rebuilt_predictors(args.rebuilt, development_keys)
    reference = load_development_reference(args.replay)
    races = build_races(reference)
    pairs, summary, build_errors = build_pairs(races, official, rebuilt)
    metrics = build_metrics(pairs)
    blockers = dominant_blockers(pairs)
    errors = validate(development_keys, official, rebuilt, reference, pairs, summary, build_errors)
    outputs = write_outputs(args.output_prefix, pairs, metrics, summary, blockers, errors)
    print(json.dumps({**outputs, "validation_errors": errors}, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
