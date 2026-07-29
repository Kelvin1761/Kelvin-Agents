#!/usr/bin/env python3
"""Archive-wide HKJC competitiveness signal gate.

The archive contains two evidence layers:

* a 245-race common replay with the historical published order plus primitives
  that can be reconstructed consistently across scorer versions; and
* a smaller rich replay with exact matrix/features.

This gate operates on the common 245-race layer.  It never uses outcomes in a
candidate score.  Candidate definitions are fixed, full-field residuals based
on reliable positive pre-race evidence; they are not boundary swaps or
race-specific corrections.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "shared_racing"))

from eval_metrics import race_metrics, summarize_races  # noqa: E402


REPLAY = ROOT / "scratch" / "hkjc_prerace_replay.csv"
DIMENSIONS = ROOT / "scratch" / "hkjc_rebuilt_dimensions.csv"
WEAK_RACES = ROOT / "scratch" / "hkjc_competitiveness_weak_races.csv"
OUTPUT = ROOT / "scratch" / "hkjc_competitiveness_signal_gate.json"
REPORT = ROOT / "scratch" / "hkjc_competitiveness_signal_gate_report.md"

SPLITS = (
    "archive_development",
    "archive_temporal_holdout",
    "independent_recent",
    "external_2026_07_15",
)
TARGET_CAUSES = (
    "整體競爭群辨識不足",
    "競爭層已捕捉但頭二排序不足",
    "騎練訊號辨識不足",
    "班次／負磅context辨識不足",
    "form line辨識不足",
)


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


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def horse_key(row: dict[str, Any]) -> tuple[str, str, int, int]:
    return (
        str(row["dataset"]),
        str(row["meeting"]),
        as_int(row["race_number"]),
        as_int(row["horse_number"]),
    )


def race_key(row: dict[str, Any]) -> tuple[str, str, int]:
    return horse_key(row)[:3]


def positive_evidence(dim: dict[str, str], name: str, floor: float = 0.25) -> float:
    reliability = as_float(dim.get(f"reliability_{name}"))
    if reliability < floor:
        return 0.0
    return max(0.0, as_float(dim.get(f"dim_{name}"), 60.0) - 60.0) * reliability


def signal_sum(
    dim: dict[str, str],
    weights: dict[str, float],
    *,
    floor: float = 0.25,
) -> float:
    return sum(
        weight * positive_evidence(dim, name, floor)
        for name, weight in weights.items()
    )


def consensus_signal(
    dim: dict[str, str],
    *,
    dimensions: tuple[str, ...],
    multiplier: float,
    floor: float = 0.35,
    minimum_signals: int = 2,
) -> float:
    signals = sorted(
        (positive_evidence(dim, name, floor) for name in dimensions),
        reverse=True,
    )
    supported = [value for value in signals if value > 0.0]
    if len(supported) < minimum_signals:
        return 0.0
    return multiplier * sum(supported[:2]) / 2.0


def confirmed_signal(
    dim: dict[str, str],
    *,
    primary: str,
    confirmations: tuple[str, ...],
    multiplier: float,
    require_all: bool = False,
    floor: float = 0.25,
) -> float:
    primary_value = positive_evidence(dim, primary, floor)
    if primary_value <= 0.0:
        return 0.0
    support = [positive_evidence(dim, name, floor) > 0.0 for name in confirmations]
    confirmed = all(support) if require_all else any(support)
    return multiplier * primary_value if confirmed else 0.0


Candidate = Callable[[dict[str, str]], float]


def _weighted_candidate(weights: dict[str, float], floor: float = 0.25) -> Candidate:
    return lambda dim: signal_sum(dim, weights, floor=floor)


CANDIDATES: dict[str, Candidate] = {
    "trainer_positive_08": _weighted_candidate({"trainer_signal": 0.08}),
    "trainer_positive_12": _weighted_candidate({"trainer_signal": 0.12}),
    "class_positive_08": _weighted_candidate({"class_weight": 0.08}),
    "class_positive_12": _weighted_candidate({"class_weight": 0.12}),
    "formline_positive_06": _weighted_candidate({"form_line": 0.06}),
    "formline_positive_10": _weighted_candidate({"form_line": 0.10}),
    "target_stack_positive_05": _weighted_candidate(
        {"trainer_signal": 0.05, "class_weight": 0.05, "form_line": 0.05}
    ),
    "target_stack_positive_08": _weighted_candidate(
        {"trainer_signal": 0.08, "class_weight": 0.08, "form_line": 0.08}
    ),
    "competitive_consensus_08": lambda dim: consensus_signal(
        dim,
        dimensions=("speed_engine", "stability", "trainer_signal", "class_weight", "form_line"),
        multiplier=0.08,
    ),
    "competitive_consensus_12": lambda dim: consensus_signal(
        dim,
        dimensions=("speed_engine", "stability", "trainer_signal", "class_weight", "form_line"),
        multiplier=0.12,
    ),
    "target_consensus_12": lambda dim: consensus_signal(
        dim,
        dimensions=("trainer_signal", "class_weight", "form_line"),
        multiplier=0.12,
    ),
    "class_rating_experience_positive_06": _weighted_candidate(
        {"class_rating_experience": 0.06}
    ),
    "class_rating_experience_positive_10": _weighted_candidate(
        {"class_rating_experience": 0.10}
    ),
    "trainer_class_v2_positive_06": _weighted_candidate(
        {"trainer_signal": 0.06, "class_rating_experience": 0.06}
    ),
    "trainer_class_v2_positive_10": _weighted_candidate(
        {"trainer_signal": 0.10, "class_rating_experience": 0.10}
    ),
    "competitive_core_v2_positive_06": _weighted_candidate(
        {
            "stability": 0.06,
            "trainer_signal": 0.06,
            "class_rating_experience": 0.06,
        }
    ),
    "competitive_core_v2_positive_10": _weighted_candidate(
        {
            "stability": 0.10,
            "trainer_signal": 0.10,
            "class_rating_experience": 0.10,
        }
    ),
    "class_v2_trainer_confirmed_08": lambda dim: confirmed_signal(
        dim,
        primary="class_rating_experience",
        confirmations=("trainer_signal",),
        multiplier=0.08,
    ),
    "class_v2_stability_confirmed_08": lambda dim: confirmed_signal(
        dim,
        primary="class_rating_experience",
        confirmations=("stability",),
        multiplier=0.08,
    ),
    "class_v2_any_confirmed_08": lambda dim: confirmed_signal(
        dim,
        primary="class_rating_experience",
        confirmations=("trainer_signal", "stability"),
        multiplier=0.08,
    ),
    "class_v2_both_confirmed_10": lambda dim: confirmed_signal(
        dim,
        primary="class_rating_experience",
        confirmations=("trainer_signal", "stability"),
        multiplier=0.10,
        require_all=True,
    ),
    "class_v2_both_confirmed_06": lambda dim: confirmed_signal(
        dim,
        primary="class_rating_experience",
        confirmations=("trainer_signal", "stability"),
        multiplier=0.06,
        require_all=True,
    ),
    "class_v2_both_confirmed_08": lambda dim: confirmed_signal(
        dim,
        primary="class_rating_experience",
        confirmations=("trainer_signal", "stability"),
        multiplier=0.08,
        require_all=True,
    ),
    "trainer_class_v2_consensus_12": lambda dim: consensus_signal(
        dim,
        dimensions=("trainer_signal", "class_rating_experience"),
        multiplier=0.12,
        minimum_signals=2,
    ),
    "stability_positive_08": _weighted_candidate({"stability": 0.08}),
    "stability_trainer_positive_06": _weighted_candidate(
        {"stability": 0.06, "trainer_signal": 0.06}
    ),
    "recent_mean_finish_positive_08": _weighted_candidate(
        {"recent_mean_finish": 0.08}
    ),
    "recent_mean_trainer_positive_06": _weighted_candidate(
        {"recent_mean_finish": 0.06, "trainer_signal": 0.06}
    ),
    "recent_mean_trainer_class_v2_positive_06": _weighted_candidate(
        {
            "recent_mean_finish": 0.06,
            "trainer_signal": 0.06,
            "class_rating_experience": 0.06,
        }
    ),
}


def load() -> tuple[
    dict[tuple[str, str, int], list[dict[str, Any]]],
    dict[tuple[str, str, int, int], dict[str, str]],
    dict[tuple[str, str, int], str],
]:
    dimensions = {horse_key(row): row for row in read_csv(DIMENSIONS)}
    grouped: defaultdict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in read_csv(REPLAY):
        grouped[race_key(row)].append(dict(row))

    # Preserve the archived order if historical score values contain an exact
    # tie or were produced by different scorer generations.
    for rows in grouped.values():
        previous = float("inf")
        for row in sorted(rows, key=lambda item: as_int(item["reference_original_rank"])):
            raw = as_float(row["reference_original_ability"])
            row["_baseline_score"] = min(raw, previous - 0.001)
            previous = row["_baseline_score"]

        def relative(column: str, *, higher_is_better: bool = True) -> dict[int, float]:
            values = {
                as_int(row["horse_number"]): (
                    as_float(row.get(column))
                    if row.get(column) not in (None, "")
                    else None
                )
                for row in rows
            }
            valid = {horse: value for horse, value in values.items() if value is not None}
            if len(valid) < 2:
                return {horse: 60.0 for horse in values}
            output = {}
            denominator = len(valid) - 1
            for horse, value in values.items():
                if value is None:
                    output[horse] = 60.0
                    continue
                others = [item for other, item in valid.items() if other != horse]
                worse = (
                    sum(item < value for item in others)
                    if higher_is_better
                    else sum(item > value for item in others)
                )
                ties = sum(item == value for item in others)
                output[horse] = 50.0 + 20.0 * (worse + 0.5 * ties) / denominator
            return output

        rating = relative("card_rating")
        experience = relative("starts")
        mean_finish = relative("last6_mean_finish", higher_is_better=False)
        for row in rows:
            horse = as_int(row["horse_number"])
            dim = dimensions[horse_key(row)]
            dim["dim_class_rating_experience"] = str(
                0.80 * rating[horse] + 0.20 * experience[horse]
            )
            dim["reliability_class_rating_experience"] = (
                "1.0" if row.get("card_rating") not in (None, "") else "0.0"
            )
            runs = as_float(row.get("last6_runs"))
            dim["dim_recent_mean_finish"] = str(mean_finish[horse])
            dim["reliability_recent_mean_finish"] = str(min(max(runs / 4.0, 0.0), 1.0))

    weak_causes = {
        (row["dataset"], row["meeting"], as_int(row["race_number"])): row["primary_cause"]
        for row in read_csv(WEAK_RACES)
    }
    return dict(grouped), dimensions, weak_causes


def score(
    row: dict[str, Any],
    dimensions: dict[tuple[str, str, int, int], dict[str, str]],
    candidate: str,
) -> float:
    baseline = float(row["_baseline_score"])
    if candidate == "published_baseline":
        return baseline
    return baseline + CANDIDATES[candidate](dimensions[horse_key(row)])


def evaluate(
    races: list[list[dict[str, Any]]],
    dimensions: dict[tuple[str, str, int, int], dict[str, str]],
    candidate: str,
) -> tuple[dict[str, Any], dict[tuple[str, str, int], dict[str, Any]]]:
    rows = []
    per_race = {}
    for race in races:
        ranked = sorted(
            race,
            key=lambda row: (
                -score(row, dimensions, candidate),
                as_int(row["reference_original_rank"]),
                as_int(row["horse_number"]),
            ),
        )
        picks = [as_int(row["horse_number"]) for row in ranked]
        positions = {
            as_int(row["horse_number"]): as_int(row["label_finish_position"])
            for row in ranked
        }
        actual_top3 = [horse for horse, position in positions.items() if position <= 3]
        metric = race_metrics(
            picks,
            actual_top3,
            actual_pos=positions,
            field_size=len(positions),
        )
        rows.append(metric)
        per_race[race_key(ranked[0])] = {
            "top2_hits": metric["top2_hits"],
            "top3_hits": metric["hits"],
            "winner_rank": metric["winner_rank"],
            "top3_capture_at5": metric["top3_capture_at5"],
            "ndcg_at5": metric["ndcg_at5"],
            "picks": picks,
        }
    summary = summarize_races(rows)
    comp = summary["competitiveness"]
    distribution = Counter(row["top2_hits"] for row in rows)
    return (
        {
            "races": len(rows),
            "zero_hit": distribution[0],
            "one_hit": distribution[1],
            "two_hit": distribution[2],
            "top2_total_hits": sum(row["top2_hits"] for row in rows),
            "top3_capture_at5": round(comp["mean_top3_capture_at5"], 6),
            "top3_all_within_top5": round(comp["top3_all_within_top5"]["rate"], 6),
            "competitive_recall_at5": round(comp["mean_competitive_recall_at5"], 6),
            "ndcg_at5": round(comp["mean_ndcg_at5"], 6),
            "winner_in_top5": round(summary["rates"]["winner_in_top5"], 6),
            "mrr": round(summary["mrr"], 6),
        },
        per_race,
    )


def metric_delta(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    return {
        key: round(candidate[key] - baseline[key], 6)
        for key in candidate
        if key != "races"
    }


def compare_races(
    baseline: dict[tuple[str, str, int], dict[str, Any]],
    candidate: dict[tuple[str, str, int], dict[str, Any]],
    causes: dict[tuple[str, str, int], str],
) -> dict[str, Any]:
    helped = harmed = unchanged = 0
    cause_rows: defaultdict[str, dict[str, int]] = defaultdict(
        lambda: {"races": 0, "helped": 0, "harmed": 0, "zero_rescued": 0, "one_to_two": 0}
    )
    meeting_delta: defaultdict[str, int] = defaultdict(int)
    for key, base in baseline.items():
        cand = candidate[key]
        hit_delta = cand["top2_hits"] - base["top2_hits"]
        helped += int(hit_delta > 0)
        harmed += int(hit_delta < 0)
        unchanged += int(hit_delta == 0)
        meeting_delta[key[1]] += hit_delta
        cause = causes.get(key)
        if cause:
            bucket = cause_rows[cause]
            bucket["races"] += 1
            bucket["helped"] += int(hit_delta > 0)
            bucket["harmed"] += int(hit_delta < 0)
            bucket["zero_rescued"] += int(base["top2_hits"] == 0 and cand["top2_hits"] > 0)
            bucket["one_to_two"] += int(base["top2_hits"] == 1 and cand["top2_hits"] == 2)
    return {
        "races_helped": helped,
        "races_harmed": harmed,
        "races_unchanged": unchanged,
        "net_helped": helped - harmed,
        "meetings_improved": sum(delta > 0 for delta in meeting_delta.values()),
        "meetings_harmed": sum(delta < 0 for delta in meeting_delta.values()),
        "meetings_unchanged": sum(delta == 0 for delta in meeting_delta.values()),
        "target_causes": {
            cause: dict(cause_rows.get(cause, {"races": 0, "helped": 0, "harmed": 0, "zero_rescued": 0, "one_to_two": 0}))
            for cause in TARGET_CAUSES
        },
    }


def gate(result: dict[str, Any]) -> dict[str, Any]:
    split_names = ("archive_temporal_holdout", "independent_recent", "external_2026_07_15")
    ranking_metrics = (
        "top3_capture_at5",
        "competitive_recall_at5",
        "ndcg_at5",
        "winner_in_top5",
        "mrr",
    )
    holdout_no_material_harm = all(
        result[split]["delta"]["zero_hit"] <= 1
        and result[split]["delta"]["top2_total_hits"] >= -1
        and all(result[split]["delta"][name] >= -0.0025 for name in ranking_metrics)
        for split in split_names
    )
    total = result["all"]["delta"]
    aggregate_improvement = (
        total["zero_hit"] <= 0
        and total["top2_total_hits"] >= 1
        and total["top3_capture_at5"] >= 0.002
        and total["competitive_recall_at5"] >= 0.002
        and total["ndcg_at5"] >= 0.002
    )
    race_balance = (
        result["comparison"]["races_helped"] > result["comparison"]["races_harmed"]
        and result["comparison"]["meetings_improved"] >= result["comparison"]["meetings_harmed"]
    )
    return {
        "passes": holdout_no_material_harm and aggregate_improvement and race_balance,
        "holdout_no_material_harm": holdout_no_material_harm,
        "aggregate_improvement": aggregate_improvement,
        "race_balance": race_balance,
    }


def main() -> int:
    grouped, dimensions, causes = load()
    slices = {"all": list(grouped.values())}
    for split in SPLITS:
        slices[split] = [
            rows
            for rows in grouped.values()
            if rows[0]["split"] == split
        ]

    baseline_metrics = {}
    baseline_races = {}
    for split, races in slices.items():
        baseline_metrics[split], baseline_races[split] = evaluate(
            races, dimensions, "published_baseline"
        )

    results = {}
    gates = {}
    for candidate in CANDIDATES:
        candidate_result = {}
        candidate_races = {}
        for split, races in slices.items():
            metrics, per_race = evaluate(races, dimensions, candidate)
            candidate_result[split] = {
                "baseline": baseline_metrics[split],
                "candidate": metrics,
                "delta": metric_delta(metrics, baseline_metrics[split]),
            }
            candidate_races[split] = per_race
        candidate_result["comparison"] = compare_races(
            baseline_races["all"], candidate_races["all"], causes
        )
        results[candidate] = candidate_result
        gates[candidate] = gate(candidate_result)

    passing = [name for name, item in gates.items() if item["passes"]]
    payload = {
        "method": {
            "archive_wide": True,
            "races": len(grouped),
            "meetings": len({key[1] for key in grouped}),
            "full_field_rerank": True,
            "micro_tiebreak": False,
            "blind_swap": False,
            "outcome_features_in_score": False,
            "candidate_family": "reliable positive pre-race evidence residual",
        },
        "coverage": {
            "races": len(grouped),
            "meetings": len({key[1] for key in grouped}),
            "horses": sum(len(rows) for rows in grouped.values()),
            "by_split": {name: len(rows) for name, rows in slices.items()},
        },
        "baseline": baseline_metrics,
        "results": results,
        "gates": gates,
        "passing_candidates": passing,
        "recommendation": "PROMOTE_TO_RICH_GATE" if passing else "HOLD_ALL",
    }
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# HKJC 全 Archive 正面訊號 Gate",
        "",
        f"- Coverage: {payload['coverage']['meetings']} meetings / {payload['coverage']['races']} races / {payload['coverage']['horses']} runners",
        f"- Recommendation: **{payload['recommendation']}**",
        "",
        "| Candidate | Pass | 0-hit Δ | Top2 hits Δ | Top3@5 Δ | Competitive recall@5 Δ | NDCG@5 Δ | Winner@5 Δ | MRR Δ | Help/Harm |",
        "|---|:---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in CANDIDATES:
        delta = results[name]["all"]["delta"]
        comparison = results[name]["comparison"]
        lines.append(
            f"| {name} | {'PASS' if gates[name]['passes'] else 'FAIL'} | "
            f"{delta['zero_hit']:+.0f} | {delta['top2_total_hits']:+.0f} | "
            f"{delta['top3_capture_at5']:+.4f} | {delta['competitive_recall_at5']:+.4f} | "
            f"{delta['ndcg_at5']:+.4f} | {delta['winner_in_top5']:+.4f} | "
            f"{delta['mrr']:+.4f} | {comparison['races_helped']}/{comparison['races_harmed']} |"
        )
    lines.extend(
        [
            "",
            "候選只可以進入 rich production gate；通過本表並不等於可以直接修改 live engine。",
        ]
    )
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "recommendation": payload["recommendation"],
                "passing_candidates": passing,
                "coverage": payload["coverage"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
