#!/usr/bin/env python3
"""Step-4 development-only diagnostics for rebuilt HKJC dimensions.

Only archive_development outcomes are unlocked.  The script never loads labels
for temporal, recent or external splits.  It diagnoses fixed Step-3 dimensions
and an equal-weight ablation reference; it does not tune weights or emit a
candidate ranking formula.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from hkjc_rebuilt_dimension_contract import DIMENSIONS


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIMENSIONS = ROOT / "scratch" / "hkjc_rebuilt_dimensions.csv"
DEFAULT_REPLAY = ROOT / "scratch" / "hkjc_prerace_replay.csv"
DEVELOPMENT_SPLIT = "archive_development"


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def row_key(row: dict[str, Any]) -> tuple[str, str, int, int]:
    return (
        str(row["dataset"]),
        str(row["meeting"]),
        as_int(row["race_number"]),
        as_int(row["horse_number"]),
    )


def load_development(dimension_path: Path, replay_path: Path) -> list[dict[str, Any]]:
    # The filter is applied while reading labels, so held-out outcomes never
    # enter memory in this audit.
    labels = {}
    with replay_path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("split") != DEVELOPMENT_SPLIT:
                continue
            labels[row_key(row)] = {
                "finish": as_int(row.get("label_finish_position")),
                "is_top3": bool(as_int(row.get("label_is_top3"))),
                "is_winner": bool(as_int(row.get("label_is_winner"))),
            }
    rows = []
    with dimension_path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("split") != DEVELOPMENT_SPLIT:
                continue
            key = row_key(row)
            if key not in labels:
                continue
            merged = {
                "dataset": key[0],
                "meeting": key[1],
                "race_number": key[2],
                "horse_number": key[3],
                **labels[key],
            }
            for dimension in DIMENSIONS:
                merged[f"dim_{dimension}"] = as_float(row.get(f"dim_{dimension}"), 60.0)
                merged[f"reliability_{dimension}"] = as_float(row.get(f"reliability_{dimension}"), 0.0)
            rows.append(merged)
    return rows


def group_races(rows: list[dict[str, Any]]) -> dict[tuple[str, int], list[dict[str, Any]]]:
    grouped: defaultdict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["meeting"], row["race_number"])].append(row)
    return dict(grouped)


def pairwise_auc(
    races: dict[tuple[str, int], list[dict[str, Any]]],
    score_key: str,
    target: str,
    reliability_key: str | None = None,
    minimum_reliability: float = 0.0,
) -> tuple[float, int]:
    wins = 0.0
    pairs = 0
    for race_rows in races.values():
        eligible = (
            [row for row in race_rows if row[reliability_key] >= minimum_reliability]
            if reliability_key
            else race_rows
        )
        positives = [row for row in eligible if row[target]]
        negatives = [row for row in eligible if not row[target]]
        for positive in positives:
            for negative in negatives:
                pairs += 1
                if positive[score_key] > negative[score_key]:
                    wins += 1.0
                elif positive[score_key] == negative[score_key]:
                    wins += 0.5
    return (round(wins / pairs, 4) if pairs else 0.5, pairs)


def mean_race_delta(
    races: dict[tuple[str, int], list[dict[str, Any]]], score_key: str, target: str
) -> float:
    deltas = []
    for race_rows in races.values():
        positives = [row[score_key] for row in race_rows if row[target]]
        negatives = [row[score_key] for row in race_rows if not row[target]]
        if positives and negatives:
            deltas.append(statistics.mean(positives) - statistics.mean(negatives))
    return round(statistics.mean(deltas), 4) if deltas else 0.0


def top2_capture(
    races: dict[tuple[str, int], list[dict[str, Any]]], score_key: str
) -> dict[str, Any]:
    distribution = Counter()
    total_hits = 0
    winners = 0
    for race_rows in races.values():
        selected = sorted(race_rows, key=lambda row: (-row[score_key], row["horse_number"]))[:2]
        hits = sum(row["is_top3"] for row in selected)
        distribution[hits] += 1
        total_hits += hits
        winners += int(any(row["is_winner"] for row in selected))
    total = len(races)
    return {
        "races": total,
        "distribution": {str(hit): distribution.get(hit, 0) for hit in (0, 1, 2)},
        "total_top2_hits": total_hits,
        "hits_per_race": round(total_hits / total, 4) if total else 0.0,
        "winner_top2": winners,
        "winner_top2_rate": round(winners / total * 100, 1) if total else 0.0,
    }


def meeting_consistency(rows: list[dict[str, Any]], score_key: str) -> dict[str, Any]:
    by_meeting: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_meeting[row["meeting"]].append(row)
    aucs = []
    for meeting_rows in by_meeting.values():
        auc, _ = pairwise_auc(group_races(meeting_rows), score_key, "is_top3")
        aucs.append(auc)
    return {
        "meetings": len(aucs),
        "positive_meetings": sum(auc >= 0.52 for auc in aucs),
        "negative_meetings": sum(auc <= 0.48 for auc in aucs),
        "median_meeting_auc": round(statistics.median(aucs), 4) if aucs else 0.5,
        "minimum_meeting_auc": round(min(aucs), 4) if aucs else 0.5,
        "maximum_meeting_auc": round(max(aucs), 4) if aucs else 0.5,
    }


def dimension_metrics(rows: list[dict[str, Any]], dimension: str) -> dict[str, Any]:
    races = group_races(rows)
    score_key = f"dim_{dimension}"
    reliability_key = f"reliability_{dimension}"
    top3_auc, top3_pairs = pairwise_auc(races, score_key, "is_top3")
    winner_auc, winner_pairs = pairwise_auc(races, score_key, "is_winner")
    reliable_auc, reliable_pairs = pairwise_auc(
        races,
        score_key,
        "is_top3",
        reliability_key=reliability_key,
        minimum_reliability=0.50,
    )
    capture = top2_capture(races, score_key)
    reliability_values = [row[reliability_key] for row in rows]
    score_values = [row[score_key] for row in rows]
    return {
        "dimension": dimension,
        "top3_auc": top3_auc,
        "top3_pairs": top3_pairs,
        "winner_auc": winner_auc,
        "winner_pairs": winner_pairs,
        "reliable_top3_auc": reliable_auc,
        "reliable_top3_pairs": reliable_pairs,
        "top3_mean_race_delta": mean_race_delta(races, score_key, "is_top3"),
        "winner_mean_race_delta": mean_race_delta(races, score_key, "is_winner"),
        "mean_reliability": round(statistics.mean(reliability_values), 4),
        "reliability_ge_0_5_rate": round(sum(value >= 0.50 for value in reliability_values) / len(rows) * 100, 1),
        "neutral_60_rate": round(sum(abs(value - 60.0) < 1e-9 for value in score_values) / len(rows) * 100, 1),
        "meeting_consistency": meeting_consistency(rows, score_key),
        "standalone_top2": capture,
    }


def add_equal_scores(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        row["diag_equal_all"] = statistics.mean(row[f"dim_{dimension}"] for dimension in DIMENSIONS)
        for omitted in DIMENSIONS:
            row[f"diag_without_{omitted}"] = statistics.mean(
                row[f"dim_{dimension}"] for dimension in DIMENSIONS if dimension != omitted
            )


def ablation_metrics(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    races = group_races(rows)
    full_capture = top2_capture(races, "diag_equal_all")
    full_auc, _ = pairwise_auc(races, "diag_equal_all", "is_top3")
    full_winner_auc, _ = pairwise_auc(races, "diag_equal_all", "is_winner")
    full = {
        **full_capture,
        "top3_auc": full_auc,
        "winner_auc": full_winner_auc,
    }
    ablations = {}
    for dimension in DIMENSIONS:
        key = f"diag_without_{dimension}"
        capture = top2_capture(races, key)
        auc, _ = pairwise_auc(races, key, "is_top3")
        winner_auc, _ = pairwise_auc(races, key, "is_winner")
        ablations[dimension] = {
            **capture,
            "top3_auc": auc,
            "winner_auc": winner_auc,
            "delta_total_top2_hits": capture["total_top2_hits"] - full["total_top2_hits"],
            "delta_zero_hit": capture["distribution"]["0"] - full["distribution"]["0"],
            "delta_winner_top2": capture["winner_top2"] - full["winner_top2"],
            "delta_top3_auc": round(auc - full_auc, 4),
            "delta_winner_auc": round(winner_auc - full_winner_auc, 4),
        }
    return full, ablations


def advancement_decision(metric: dict[str, Any], ablation: dict[str, Any]) -> dict[str, Any]:
    consistency = metric["meeting_consistency"]
    core = (
        metric["top3_auc"] >= 0.53
        and metric["winner_auc"] >= 0.51
        and consistency["positive_meetings"] >= 5
    )
    conditional = (
        metric["top3_auc"] >= 0.50
        and metric["reliable_top3_auc"] >= 0.54
        and metric["reliable_top3_pairs"] >= 200
    )
    clearly_harmful_ablation = (
        ablation["delta_total_top2_hits"] > 0
        and ablation["delta_zero_hit"] < 0
        and ablation["delta_winner_top2"] >= 0
    )
    if core and not clearly_harmful_ablation:
        status = "ADVANCE_CORE"
    elif conditional and not clearly_harmful_ablation:
        status = "ADVANCE_CONDITIONAL"
    else:
        status = "HOLD_OR_REJECT"
    return {
        "status": status,
        "core_gate": core,
        "conditional_gate": conditional,
        "clearly_harmful_equal_ablation": clearly_harmful_ablation,
    }


def validate(rows: list[dict[str, Any]]) -> list[str]:
    errors = []
    if len(rows) != 1093:
        errors.append(f"development horse rows {len(rows)} != 1093")
    if {row["dataset"] for row in rows} != {"archive"}:
        errors.append("non-archive outcomes entered development audit")
    races = group_races(rows)
    if len(races) != 88:
        errors.append(f"development races {len(races)} != 88")
    if len({row["meeting"] for row in rows}) != 9:
        errors.append("development meeting count mismatch")
    for key, race_rows in races.items():
        if sum(row["is_top3"] for row in race_rows) != 3:
            errors.append(f"top3 label mismatch {key}")
        if sum(row["is_winner"] for row in race_rows) != 1:
            errors.append(f"winner label mismatch {key}")
    return errors


def write_outputs(
    metrics: dict[str, Any],
    equal_full: dict[str, Any],
    ablations: dict[str, Any],
    decisions: dict[str, Any],
    errors: list[str],
    output_prefix: Path,
) -> None:
    json_path = output_prefix.with_suffix(".json")
    csv_path = output_prefix.with_suffix(".csv")
    report_path = output_prefix.with_name(output_prefix.name + "_report").with_suffix(".md")
    payload = {
        "method": {
            "outcomes_unlocked": [DEVELOPMENT_SPLIT],
            "held_out_outcomes_loaded": False,
            "fixed_step3_formulas": True,
            "weight_search": False,
            "equal_weight_reference_is_diagnostic_only": True,
            "micro_tiebreak": False,
            "blind_swap": False,
        },
        "coverage": {"meetings": 9, "races": 88, "horses": 1093},
        "dimensions": metrics,
        "equal_weight_diagnostic": equal_full,
        "ablations": ablations,
        "advancement_decisions": decisions,
        "validation_errors": errors,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    fields = [
        "dimension", "decision", "top3_auc", "winner_auc", "reliable_top3_auc", "reliable_top3_pairs",
        "top3_mean_race_delta", "winner_mean_race_delta", "mean_reliability", "reliability_ge_0_5_rate",
        "neutral_60_rate", "positive_meetings", "negative_meetings", "median_meeting_auc",
        "standalone_zero", "standalone_one", "standalone_two", "standalone_total_hits", "standalone_winner_top2",
        "ablation_delta_hits", "ablation_delta_zero", "ablation_delta_winner", "ablation_delta_top3_auc",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for dimension in DIMENSIONS:
            metric = metrics[dimension]
            consistency = metric["meeting_consistency"]
            capture = metric["standalone_top2"]
            distribution = capture["distribution"]
            ablation = ablations[dimension]
            writer.writerow(
                {
                    "dimension": dimension,
                    "decision": decisions[dimension]["status"],
                    "top3_auc": metric["top3_auc"],
                    "winner_auc": metric["winner_auc"],
                    "reliable_top3_auc": metric["reliable_top3_auc"],
                    "reliable_top3_pairs": metric["reliable_top3_pairs"],
                    "top3_mean_race_delta": metric["top3_mean_race_delta"],
                    "winner_mean_race_delta": metric["winner_mean_race_delta"],
                    "mean_reliability": metric["mean_reliability"],
                    "reliability_ge_0_5_rate": metric["reliability_ge_0_5_rate"],
                    "neutral_60_rate": metric["neutral_60_rate"],
                    "positive_meetings": consistency["positive_meetings"],
                    "negative_meetings": consistency["negative_meetings"],
                    "median_meeting_auc": consistency["median_meeting_auc"],
                    "standalone_zero": distribution["0"],
                    "standalone_one": distribution["1"],
                    "standalone_two": distribution["2"],
                    "standalone_total_hits": capture["total_top2_hits"],
                    "standalone_winner_top2": capture["winner_top2"],
                    "ablation_delta_hits": ablation["delta_total_top2_hits"],
                    "ablation_delta_zero": ablation["delta_zero_hit"],
                    "ablation_delta_winner": ablation["delta_winner_top2"],
                    "ablation_delta_top3_auc": ablation["delta_top3_auc"],
                }
            )

    equal_dist = equal_full["distribution"]
    lines = [
        "# HKJC Dimension重建 Step 4 — Development單項診斷與Ablation",
        "",
        "## 方法鎖定",
        "",
        "- 只解封archive development：9個賽日／88場／1093匹；其他三段賽果完全未載入。",
        "- Step 3公式原封不動；無搜尋權重、無逐場規則、無micro tie-break或第二／第三選盲換。",
        "- 七維等權分只係ablation參考，唔係候選或正式排名公式。",
        "- 每個dimension嘅前進閘口在計算前固定：核心閘、可靠樣本條件閘，以及等權ablation明顯有害否決。",
        "",
        "## 七維等權診斷參考",
        "",
        f"- 0／1／2 hit：{equal_dist['0']}/{equal_dist['1']}/{equal_dist['2']}；Top2總hits {equal_full['total_top2_hits']}；頭馬Top2 {equal_full['winner_top2']}。",
        f"- 實際前三AUC {equal_full['top3_auc']:.3f}；頭馬AUC {equal_full['winner_auc']:.3f}。",
        "",
        "## 單項結果",
        "",
        "| Dimension | Top3 AUC | 頭馬AUC | 可靠樣本AUC／pairs | Δ前三分 | 正向賽日 | 單項0/1/2 | 總hits | 頭馬Top2 | 決定 |",
        "|---|---:|---:|---:|---:|---:|---|---:|---:|---|",
    ]
    for dimension in DIMENSIONS:
        metric = metrics[dimension]
        consistency = metric["meeting_consistency"]
        capture = metric["standalone_top2"]
        dist = capture["distribution"]
        lines.append(
            f"| {dimension} | {metric['top3_auc']:.3f} | {metric['winner_auc']:.3f} | "
            f"{metric['reliable_top3_auc']:.3f}/{metric['reliable_top3_pairs']} | "
            f"{metric['top3_mean_race_delta']:+.2f} | {consistency['positive_meetings']}/9 | "
            f"{dist['0']}/{dist['1']}/{dist['2']} | {capture['total_top2_hits']} | "
            f"{capture['winner_top2']} | {decisions[dimension]['status']} |"
        )
    lines.extend(
        [
            "",
            "## 等權Ablation",
            "",
            "正數代表移除該dimension後上升；如果移除後總hits上升、0-hit下降兼頭馬不跌，視為該dimension在等權環境明顯有害。",
            "",
            "| 移除 | Δ總hits | Δ0-hit | Δ頭馬Top2 | ΔTop3 AUC | Δ頭馬AUC |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for dimension in DIMENSIONS:
        row = ablations[dimension]
        lines.append(
            f"| {dimension} | {row['delta_total_top2_hits']:+d} | {row['delta_zero_hit']:+d} | "
            f"{row['delta_winner_top2']:+d} | {row['delta_top3_auc']:+.3f} | {row['delta_winner_auc']:+.3f} |"
        )
    advance_core = [dimension for dimension in DIMENSIONS if decisions[dimension]["status"] == "ADVANCE_CORE"]
    advance_conditional = [dimension for dimension in DIMENSIONS if decisions[dimension]["status"] == "ADVANCE_CONDITIONAL"]
    held = [dimension for dimension in DIMENSIONS if decisions[dimension]["status"] == "HOLD_OR_REJECT"]
    lines.extend(
        [
            "",
            "## Step 4結論",
            "",
            f"- 核心前進：{', '.join(advance_core) if advance_core else '無'}。",
            f"- 條件前進：{', '.join(advance_conditional) if advance_conditional else '無'}。",
            f"- 暫緩／否決：{', '.join(held) if held else '無'}。",
            f"- Validation errors：{len(errors)}。",
            "- 呢個決定只用development；下一步只會由前進dimension組成最多三個預先凍結完整矩陣，仍然唔會打開其他賽果。",
        ]
    )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "json": str(json_path),
                "csv": str(csv_path),
                "report": str(report_path),
                "advance_core": advance_core,
                "advance_conditional": advance_conditional,
                "held": held,
                "validation_errors": errors,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dimensions", type=Path, default=DEFAULT_DIMENSIONS)
    parser.add_argument("--replay", type=Path, default=DEFAULT_REPLAY)
    parser.add_argument(
        "--output-prefix",
        type=Path,
        default=ROOT / "scratch" / "hkjc_rebuilt_dimension_development_audit",
    )
    args = parser.parse_args()
    rows = load_development(args.dimensions, args.replay)
    errors = validate(rows)
    add_equal_scores(rows)
    metrics = {dimension: dimension_metrics(rows, dimension) for dimension in DIMENSIONS}
    equal_full, ablations = ablation_metrics(rows)
    decisions = {
        dimension: advancement_decision(metrics[dimension], ablations[dimension])
        for dimension in DIMENSIONS
    }
    write_outputs(metrics, equal_full, ablations, decisions, errors, args.output_prefix)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
