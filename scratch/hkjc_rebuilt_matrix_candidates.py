#!/usr/bin/env python3
"""Step-5 freeze of three non-grid HKJC rebuilt-matrix candidates.

Scores/ranks are generated for every split without outcomes.  Only development
labels are loaded afterwards for the pre-holdout gate.  Held Step-4 dimensions
have zero candidate weight.  Exact ties use horse number only as a stable sort,
and their frequency is reported rather than treated as a scoring rule.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIMENSIONS = ROOT / "scratch" / "hkjc_rebuilt_dimensions.csv"
DEFAULT_REPLAY = ROOT / "scratch" / "hkjc_prerace_replay.csv"
DEVELOPMENT_SPLIT = "archive_development"

CANDIDATES = {
    "balanced_core": {
        "hypothesis": "三個通過dimension等權，避免單一訊號主導。",
        "weights": {"speed_engine": 0.3334, "stability": 0.3333, "trainer_signal": 0.3333},
    },
    "stability_led": {
        "hypothesis": "按development最強且9/9正向嘅stability主導，trainer次之，speed作支持。",
        "weights": {"speed_engine": 0.20, "stability": 0.50, "trainer_signal": 0.30},
    },
    "winner_guard": {
        "hypothesis": "提高development頭馬AUC強嘅trainer比重，stability保留主體，speed只作確認。",
        "weights": {"speed_engine": 0.15, "stability": 0.40, "trainer_signal": 0.45},
    },
}

DEBUT_FORMULA = {
    "neutral_anchor": 0.50,
    "trainer_signal": 0.50,
    "note": "初出馬缺正式賽證據，三候選統一用50%中性60＋50%trainer；不使用draw或被暫緩dimension。",
}


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


def key(row: dict[str, Any]) -> tuple[str, str, int, int]:
    return (
        str(row["dataset"]),
        str(row["meeting"]),
        as_int(row["race_number"]),
        as_int(row["horse_number"]),
    )


def race_key(row: dict[str, Any]) -> tuple[str, str, int]:
    item = key(row)
    return item[:3]


def validate_contract() -> None:
    allowed = {"speed_engine", "stability", "trainer_signal"}
    for name, candidate in CANDIDATES.items():
        if set(candidate["weights"]) != allowed:
            raise ValueError(f"{name} dimension set mismatch")
        if abs(sum(candidate["weights"].values()) - 1.0) > 1e-9:
            raise ValueError(f"{name} weights do not sum to 1")
        if any(weight <= 0 for weight in candidate["weights"].values()):
            raise ValueError(f"{name} has non-positive weight")
    if abs(DEBUT_FORMULA["neutral_anchor"] + DEBUT_FORMULA["trainer_signal"] - 1.0) > 1e-9:
        raise ValueError("debut formula does not sum to 1")


def build_candidate_rows(path: Path) -> tuple[list[dict[str, Any]], dict[str, dict[tuple[str, str, int], list[int]]], dict[str, dict[str, Any]]]:
    source = list(csv.DictReader(path.open(encoding="utf-8-sig", newline="")))
    rows = []
    grouped: defaultdict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for raw in source:
        record = {
            "dataset": raw["dataset"],
            "split": raw["split"],
            "meeting": raw["meeting"],
            "race_number": as_int(raw["race_number"]),
            "horse_number": as_int(raw["horse_number"]),
            "horse_name": raw.get("horse_name", ""),
            "is_debut": as_int(raw.get("is_debut")),
        }
        for dimension in ("speed_engine", "stability", "trainer_signal"):
            record[f"dim_{dimension}"] = as_float(raw.get(f"dim_{dimension}"), 60.0)
        for name, candidate in CANDIDATES.items():
            if record["is_debut"]:
                score = 60.0 * DEBUT_FORMULA["neutral_anchor"] + record["dim_trainer_signal"] * DEBUT_FORMULA["trainer_signal"]
            else:
                score = sum(record[f"dim_{dimension}"] * weight for dimension, weight in candidate["weights"].items())
            record[f"score_{name}"] = round(score, 4)
        rows.append(record)
        grouped[race_key(record)].append(record)

    selections: dict[str, dict[tuple[str, str, int], list[int]]] = {name: {} for name in CANDIDATES}
    tie_stats: dict[str, dict[str, Any]] = {}
    for name in CANDIDATES:
        tie_all = 0
        tie_dev = 0
        dev_races = 0
        for current_race, race_rows in grouped.items():
            ranked = sorted(race_rows, key=lambda row: (-row[f"score_{name}"], row["horse_number"]))
            for rank, row in enumerate(ranked, start=1):
                row[f"rank_{name}"] = rank
            selections[name][current_race] = [row["horse_number"] for row in ranked[:2]]
            boundary_tie = len(ranked) >= 3 and abs(ranked[1][f"score_{name}"] - ranked[2][f"score_{name}"]) < 1e-9
            tie_all += int(boundary_tie)
            if ranked[0]["split"] == DEVELOPMENT_SPLIT:
                dev_races += 1
                tie_dev += int(boundary_tie)
        tie_stats[name] = {
            "all_races": len(grouped),
            "all_boundary_ties": tie_all,
            "all_boundary_tie_rate": round(tie_all / len(grouped) * 100, 1),
            "development_races": dev_races,
            "development_boundary_ties": tie_dev,
            "development_boundary_tie_rate": round(tie_dev / dev_races * 100, 1) if dev_races else 0.0,
        }
    return rows, selections, tie_stats


def load_development_reference(path: Path) -> dict[tuple[str, str, int, int], dict[str, Any]]:
    reference = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("split") != DEVELOPMENT_SPLIT:
                continue
            reference[key(row)] = {
                "finish": as_int(row["label_finish_position"]),
                "is_top3": bool(as_int(row["label_is_top3"])),
                "is_winner": bool(as_int(row["label_is_winner"])),
                "original_rank": as_int(row["reference_original_rank"]),
            }
    return reference


def development_races(reference: dict[tuple[str, str, int, int], dict[str, Any]]) -> dict[tuple[str, str, int], dict[int, dict[str, Any]]]:
    races: defaultdict[tuple[str, str, int], dict[int, dict[str, Any]]] = defaultdict(dict)
    for item, label in reference.items():
        races[item[:3]][item[3]] = label
    return dict(races)


def selection_metrics(
    selections: dict[tuple[str, str, int], list[int]],
    races: dict[tuple[str, str, int], dict[int, dict[str, Any]]],
) -> dict[str, Any]:
    distribution = Counter()
    total_hits = 0
    winners = 0
    per_race = {}
    for current_race, horse_labels in races.items():
        selected = selections[current_race]
        hits = sum(horse_labels[number]["is_top3"] for number in selected)
        winner = int(any(horse_labels[number]["is_winner"] for number in selected))
        distribution[hits] += 1
        total_hits += hits
        winners += winner
        per_race[current_race] = {"selected": selected, "hits": hits, "winner": winner}
    return {
        "races": len(races),
        "distribution": {str(hit): distribution.get(hit, 0) for hit in (0, 1, 2)},
        "total_top2_hits": total_hits,
        "winner_top2": winners,
        "per_race": per_race,
    }


def baseline_selections(races: dict[tuple[str, str, int], dict[int, dict[str, Any]]]) -> dict[tuple[str, str, int], list[int]]:
    return {
        current_race: [number for number, label in sorted(horses.items(), key=lambda item: item[1]["original_rank"]) if label["original_rank"] <= 2]
        for current_race, horses in races.items()
    }


def compare_candidate(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    races: dict[tuple[str, str, int], dict[int, dict[str, Any]]],
) -> dict[str, Any]:
    changes = 0
    helped = 0
    harmed = 0
    zero_to_positive = 0
    one_to_two = 0
    one_to_zero = 0
    winner_helped = 0
    winner_harmed = 0
    rank3_promotions = 0
    effective_rank3_rescues = 0
    harmful_rank3_promotions = 0
    for current_race, horse_labels in races.items():
        base = baseline["per_race"][current_race]
        cand = candidate["per_race"][current_race]
        base_set = set(base["selected"])
        cand_set = set(cand["selected"])
        if base_set != cand_set:
            changes += 1
        helped += int(cand["hits"] > base["hits"])
        harmed += int(cand["hits"] < base["hits"])
        zero_to_positive += int(base["hits"] == 0 and cand["hits"] > 0)
        one_to_two += int(base["hits"] == 1 and cand["hits"] == 2)
        one_to_zero += int(base["hits"] == 1 and cand["hits"] == 0)
        winner_helped += int(cand["winner"] > base["winner"])
        winner_harmed += int(cand["winner"] < base["winner"])

        original_rank3 = next(number for number, label in horse_labels.items() if label["original_rank"] == 3)
        if original_rank3 in cand_set and original_rank3 not in base_set:
            rank3_promotions += 1
            excluded = base_set - cand_set
            rank3_placed = horse_labels[original_rank3]["is_top3"]
            excluded_miss = any(not horse_labels[number]["is_top3"] for number in excluded)
            excluded_hit = any(horse_labels[number]["is_top3"] for number in excluded)
            effective_rank3_rescues += int(rank3_placed and excluded_miss)
            harmful_rank3_promotions += int((not rank3_placed) and excluded_hit)
    return {
        "top2_set_changes": changes,
        "hit_helped": helped,
        "hit_harmed": harmed,
        "zero_to_positive": zero_to_positive,
        "one_to_two": one_to_two,
        "one_to_zero": one_to_zero,
        "winner_helped": winner_helped,
        "winner_harmed": winner_harmed,
        "rank3_promotions": rank3_promotions,
        "effective_rank3_rescues": effective_rank3_rescues,
        "harmful_rank3_promotions": harmful_rank3_promotions,
        "rank3_rescue_net": effective_rank3_rescues - harmful_rank3_promotions,
    }


def development_gate(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    comparison: dict[str, Any],
    tie_stats: dict[str, Any],
) -> dict[str, Any]:
    base_zero = baseline["distribution"]["0"]
    candidate_zero = candidate["distribution"]["0"]
    common = (
        candidate["total_top2_hits"] >= baseline["total_top2_hits"]
        and candidate["winner_top2"] >= baseline["winner_top2"]
        and comparison["top2_set_changes"] >= 5
        and tie_stats["development_boundary_tie_rate"] <= 5.0
    )
    primary = common and candidate_zero < base_zero
    secondary = common and candidate_zero == base_zero and comparison["rank3_rescue_net"] > 0
    return {
        "advances_to_step6": primary or secondary,
        "path": "LOWER_ZERO_HIT" if primary else ("RANK3_RESCUE" if secondary else "FAIL"),
        "common_no_harm": common,
        "zero_hit_delta": candidate_zero - base_zero,
        "top2_hit_delta": candidate["total_top2_hits"] - baseline["total_top2_hits"],
        "winner_top2_delta": candidate["winner_top2"] - baseline["winner_top2"],
        "rank3_rescue_net": comparison["rank3_rescue_net"],
    }


def validate(
    rows: list[dict[str, Any]],
    reference: dict[tuple[str, str, int, int], dict[str, Any]],
    tie_stats: dict[str, dict[str, Any]],
) -> list[str]:
    errors = []
    if len(rows) != 3054:
        errors.append(f"candidate rows {len(rows)} != 3054")
    if len(reference) != 1093:
        errors.append(f"development labels {len(reference)} != 1093")
    if any(column.startswith(("label_", "reference_")) for column in rows[0]):
        errors.append("outcome/reference leaked into candidate rank output")
    for row in rows:
        for name in CANDIDATES:
            score = row[f"score_{name}"]
            rank = row[f"rank_{name}"]
            if not 0.0 <= score <= 100.0:
                errors.append(f"score out of range {name}")
            if rank < 1:
                errors.append(f"rank out of range {name}")
    if any(stats["all_races"] != 245 or stats["development_races"] != 88 for stats in tie_stats.values()):
        errors.append("race count mismatch")
    return errors


def write_outputs(
    rows: list[dict[str, Any]],
    tie_stats: dict[str, dict[str, Any]],
    baseline: dict[str, Any],
    candidate_metrics: dict[str, dict[str, Any]],
    comparisons: dict[str, dict[str, Any]],
    gates: dict[str, dict[str, Any]],
    errors: list[str],
    output_prefix: Path,
) -> None:
    csv_path = output_prefix.with_suffix(".csv")
    json_path = output_prefix.with_suffix(".json")
    report_path = output_prefix.with_name(output_prefix.name + "_report").with_suffix(".md")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda row: (row["meeting"], row["race_number"], row["horse_number"])))
    serializable_baseline = {key: value for key, value in baseline.items() if key != "per_race"}
    serializable_metrics = {
        name: {key: value for key, value in metric.items() if key != "per_race"}
        for name, metric in candidate_metrics.items()
    }
    payload = {
        "method": {
            "candidate_definitions_frozen_before_measurement": True,
            "grid_search": False,
            "held_dimensions_weight": 0.0,
            "held_out_outcomes_loaded": False,
            "full_race_rerank": True,
            "micro_tiebreak": False,
            "blind_swap": False,
            "exact_tie_sort": "horse_number only; frequency reported",
        },
        "candidates": CANDIDATES,
        "debut_formula": DEBUT_FORMULA,
        "development_baseline": serializable_baseline,
        "development_candidates": serializable_metrics,
        "development_comparisons": comparisons,
        "development_gates": gates,
        "tie_stats": tie_stats,
        "validation_errors": errors,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    base_dist = baseline["distribution"]
    lines = [
        "# HKJC Dimension重建 Step 5 — 三個凍結完整矩陣候選",
        "",
        "## 候選鎖定",
        "",
        "- 三候選在量development表現前固定；無grid search、無逐場改權重。",
        "- 非初出馬只用Step 4通過嘅speed-engine、stability、trainer；其餘四維權重為0。",
        f"- {DEBUT_FORMULA['note']}",
        "- 每場完整重排；無micro tie-break或第二／第三選盲換。完全同分只以馬號固定排序，並另計發生率。",
        "- 只載入development結果；其他三段候選分及排名已outcome-free凍結。",
        "",
        "| 候選 | Speed | Stability | Trainer | 假設 |",
        "|---|---:|---:|---:|---|",
    ]
    for name, candidate in CANDIDATES.items():
        weights = candidate["weights"]
        lines.append(
            f"| {name} | {weights['speed_engine']:.2f} | {weights['stability']:.2f} | "
            f"{weights['trainer_signal']:.2f} | {candidate['hypothesis']} |"
        )
    lines.extend(
        [
            "",
            "## Development基準",
            "",
            f"- 原模型Top2：0／1／2 hit = {base_dist['0']}/{base_dist['1']}/{base_dist['2']}；總hits {baseline['total_top2_hits']}；頭馬Top2 {baseline['winner_top2']}。",
            "",
            "## 候選結果與前進閘",
            "",
            "| 候選 | 0/1/2 hit | Δhits | Δ頭馬 | 變動場 | helped/harmed | 救0-hit | 1→2/1→0 | 第三選升格有效/有害/淨值 | 邊界同分 | Step 6 |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for name in CANDIDATES:
        metric = candidate_metrics[name]
        comparison = comparisons[name]
        gate = gates[name]
        dist = metric["distribution"]
        lines.append(
            f"| {name} | {dist['0']}/{dist['1']}/{dist['2']} | {gate['top2_hit_delta']:+d} | "
            f"{gate['winner_top2_delta']:+d} | {comparison['top2_set_changes']} | "
            f"{comparison['hit_helped']}/{comparison['hit_harmed']} | {comparison['zero_to_positive']} | "
            f"{comparison['one_to_two']}/{comparison['one_to_zero']} | "
            f"{comparison['effective_rank3_rescues']}/{comparison['harmful_rank3_promotions']}/{comparison['rank3_rescue_net']:+d} | "
            f"{tie_stats[name]['development_boundary_ties']} | "
            f"{'是－' + gate['path'] if gate['advances_to_step6'] else '否'} |"
        )
    advancing = [name for name, gate in gates.items() if gate["advances_to_step6"]]
    lines.extend(
        [
            "",
            "## Step 5結論",
            "",
            f"- 可解封Step 6驗證嘅凍結候選：{', '.join(advancing) if advancing else '無'}。",
            f"- Validation errors：{len(errors)}。",
            "- 候選排名CSV不含賽果或原模型rank；正式Auto engine保持不變。",
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
        default=ROOT / "scratch" / "hkjc_rebuilt_matrix_candidates",
    )
    args = parser.parse_args()
    validate_contract()
    rows, selections, tie_stats = build_candidate_rows(args.dimensions)
    reference = load_development_reference(args.replay)
    races = development_races(reference)
    baseline = selection_metrics(baseline_selections(races), races)
    candidate_metrics = {
        name: selection_metrics(
            {current_race: picks for current_race, picks in all_selections.items() if current_race[0] == "archive" and current_race in races},
            races,
        )
        for name, all_selections in selections.items()
    }
    comparisons = {
        name: compare_candidate(baseline, candidate_metrics[name], races)
        for name in CANDIDATES
    }
    gates = {
        name: development_gate(baseline, candidate_metrics[name], comparisons[name], tie_stats[name])
        for name in CANDIDATES
    }
    errors = validate(rows, reference, tie_stats)
    write_outputs(rows, tie_stats, baseline, candidate_metrics, comparisons, gates, errors, args.output_prefix)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
