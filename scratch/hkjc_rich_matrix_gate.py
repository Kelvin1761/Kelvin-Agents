#!/usr/bin/env python3
"""Gate HKJC matrix changes on the rich production replay.

The 245-race common replay is the broad screen.  This script is the second
gate: it uses meetings with complete Logic-derived matrix/features and
recomputes the entire field under fixed candidate formulas.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "shared_racing"))
sys.path.insert(
    0,
    str(
        ROOT
        / ".agents"
        / "skills"
        / "hkjc_racing"
        / "hkjc_wong_choi_auto"
        / "scripts"
        / "au_racing_engine"
    ),
)

from eval_metrics import race_metrics, summarize_races  # noqa: E402
from au_racing_engine.scoring import MATRIX_WEIGHTS as LIVE_MATRIX_WEIGHTS  # noqa: E402


DEFAULT_INPUT = (
    ROOT
    / ".agents"
    / "skills"
    / "hkjc_racing"
    / "hkjc_reflector"
    / "artifacts"
    / "hkjc_ranking_dataset.csv"
)
DEFAULT_MANIFEST = ROOT / "scratch" / "hkjc_zero_one_hit_manifest.csv"
DEFAULT_ANNOTATIONS = ROOT / "scratch" / "hkjc_anomaly_annotations.csv"
OUTPUT = ROOT / "scratch" / "hkjc_rich_matrix_gate.json"
REPORT = ROOT / "scratch" / "hkjc_rich_matrix_gate_report.md"
# Pin the pre-change production contract so this research gate remains
# reproducible after a passing candidate is promoted to the live engine.
BASELINE_WEIGHTS = {
    "sectional": 0.1849,
    "trainer_signal": 0.2209,
    "stability": 0.0919,
    "race_shape": 0.2560,
    "class_advantage": 0.1335,
    "horse_health": 0.0378,
    "form_line": 0.0749,
}
MATRIX_NAMES = tuple(BASELINE_WEIGHTS)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", action="append", default=[])
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--annotations", default=str(DEFAULT_ANNOTATIONS))
    parser.add_argument("--output", default=str(OUTPUT))
    parser.add_argument("--report", default=str(REPORT))
    return parser.parse_args()


def as_float(value: Any, default: float | None = 0.0) -> float | None:
    if value in (None, ""):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return default if math.isnan(number) else number


def as_int(value: Any, default: int = 0) -> int:
    number = as_float(value, None)
    return int(number) if number is not None else default


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def race_key(row: dict[str, Any]) -> tuple[str, int]:
    return str(row["meeting_name"]), as_int(row["race_number"])


def relative(rows: list[dict[str, Any]], column: str) -> dict[int, float]:
    values = {
        as_int(row["horse_number"]): as_float(row.get(column), None)
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
        worse = sum(item < value for item in others)
        ties = sum(item == value for item in others)
        output[horse] = 50.0 + 20.0 * (worse + 0.5 * ties) / denominator
    return output


def matrix(row: dict[str, Any]) -> dict[str, float]:
    return {
        name: float(as_float(row.get(f"matrix_{name}"), 60.0) or 60.0)
        for name in MATRIX_NAMES
    }


def weighted_ability(scores: dict[str, float], weights: dict[str, float]) -> float:
    return sum(scores[name] * weights[name] for name in MATRIX_NAMES)


WEIGHT_CANDIDATES = {
    "baseline": dict(BASELINE_WEIGHTS),
    "formline_to_trainer": {
        **BASELINE_WEIGHTS,
        "form_line": 0.0250,
        "trainer_signal": BASELINE_WEIGHTS["trainer_signal"] + 0.0499,
    },
    "formline_to_core": {
        **BASELINE_WEIGHTS,
        "form_line": 0.0250,
        "trainer_signal": BASELINE_WEIGHTS["trainer_signal"] + 0.0249,
        "stability": BASELINE_WEIGHTS["stability"] + 0.0150,
        "class_advantage": BASELINE_WEIGHTS["class_advantage"] + 0.0100,
    },
    "shape_to_core": {
        **BASELINE_WEIGHTS,
        "race_shape": BASELINE_WEIGHTS["race_shape"] - 0.0300,
        "trainer_signal": BASELINE_WEIGHTS["trainer_signal"] + 0.0150,
        "stability": BASELINE_WEIGHTS["stability"] + 0.0100,
        "class_advantage": BASELINE_WEIGHTS["class_advantage"] + 0.0050,
    },
    "shape_to_core_equal": {
        **BASELINE_WEIGHTS,
        "race_shape": BASELINE_WEIGHTS["race_shape"] - 0.0300,
        "trainer_signal": BASELINE_WEIGHTS["trainer_signal"] + 0.0100,
        "stability": BASELINE_WEIGHTS["stability"] + 0.0100,
        "class_advantage": BASELINE_WEIGHTS["class_advantage"] + 0.0100,
    },
    "shape_to_core_stability_led": {
        **BASELINE_WEIGHTS,
        "race_shape": BASELINE_WEIGHTS["race_shape"] - 0.0300,
        "trainer_signal": BASELINE_WEIGHTS["trainer_signal"] + 0.0080,
        "stability": BASELINE_WEIGHTS["stability"] + 0.0170,
        "class_advantage": BASELINE_WEIGHTS["class_advantage"] + 0.0050,
    },
    "shape_to_trainer_stability": {
        **BASELINE_WEIGHTS,
        "race_shape": BASELINE_WEIGHTS["race_shape"] - 0.0300,
        "trainer_signal": BASELINE_WEIGHTS["trainer_signal"] + 0.0150,
        "stability": BASELINE_WEIGHTS["stability"] + 0.0150,
    },
    "shape_to_core_01": {
        **BASELINE_WEIGHTS,
        "race_shape": BASELINE_WEIGHTS["race_shape"] - 0.0100,
        "trainer_signal": BASELINE_WEIGHTS["trainer_signal"] + 0.0050,
        "stability": BASELINE_WEIGHTS["stability"] + 0.0033,
        "class_advantage": BASELINE_WEIGHTS["class_advantage"] + 0.0017,
    },
    "shape_to_core_02": {
        **BASELINE_WEIGHTS,
        "race_shape": BASELINE_WEIGHTS["race_shape"] - 0.0200,
        "trainer_signal": BASELINE_WEIGHTS["trainer_signal"] + 0.0100,
        "stability": BASELINE_WEIGHTS["stability"] + 0.0067,
        "class_advantage": BASELINE_WEIGHTS["class_advantage"] + 0.0033,
    },
    "formline_shape_to_core": {
        **BASELINE_WEIGHTS,
        "form_line": 0.0250,
        "race_shape": BASELINE_WEIGHTS["race_shape"] - 0.0200,
        "trainer_signal": BASELINE_WEIGHTS["trainer_signal"] + 0.0349,
        "stability": BASELINE_WEIGHTS["stability"] + 0.0200,
        "class_advantage": BASELINE_WEIGHTS["class_advantage"] + 0.0150,
    },
}

if set(WEIGHT_CANDIDATES["shape_to_core_equal"]) != set(LIVE_MATRIX_WEIGHTS) or any(
    abs(WEIGHT_CANDIDATES["shape_to_core_equal"][name] - LIVE_MATRIX_WEIGHTS[name]) > 1e-9
    for name in MATRIX_NAMES
):
    raise RuntimeError(
        "Live matrix weights no longer match the promoted shape_to_core_equal candidate; "
        "review this gate before using it."
    )


def candidate_score(
    row: dict[str, Any],
    *,
    name: str,
    class_v2: float,
) -> float:
    scores = matrix(row)
    baseline = weighted_ability(scores, WEIGHT_CANDIDATES["baseline"])
    if name in WEIGHT_CANDIDATES:
        return weighted_ability(scores, WEIGHT_CANDIDATES[name])
    if name == "class_v2_replace":
        scores["class_advantage"] = class_v2
        return weighted_ability(scores, WEIGHT_CANDIDATES["baseline"])
    if name == "class_v2_blend":
        scores["class_advantage"] = 0.50 * scores["class_advantage"] + 0.50 * class_v2
        return weighted_ability(scores, WEIGHT_CANDIDATES["baseline"])
    if name in ("class_v2_confirmed_boost_08", "class_v2_confirmed_boost_10"):
        multiplier = 0.08 if name.endswith("_08") else 0.10
        confirmed = scores["trainer_signal"] > 60.0 and scores["stability"] > 60.0
        return baseline + (multiplier * max(0.0, class_v2 - 60.0) if confirmed else 0.0)
    if name == "class_v2_blend_formline_to_core":
        scores["class_advantage"] = 0.50 * scores["class_advantage"] + 0.50 * class_v2
        return weighted_ability(scores, WEIGHT_CANDIDATES["formline_to_core"])
    raise KeyError(name)


CANDIDATES = (
    "baseline",
    "class_v2_replace",
    "class_v2_blend",
    "class_v2_confirmed_boost_08",
    "class_v2_confirmed_boost_10",
    "formline_to_trainer",
    "formline_to_core",
    "shape_to_core_01",
    "shape_to_core_02",
    "shape_to_core",
    "shape_to_core_equal",
    "shape_to_core_stability_led",
    "shape_to_trainer_stability",
    "formline_shape_to_core",
    "class_v2_blend_formline_to_core",
)


def split_meetings(grouped: dict[tuple[str, int], list[dict[str, Any]]]) -> dict[str, set[str]]:
    dates = {
        meeting: min(str(row.get("date") or "") for rows in grouped.values() for row in rows if row["meeting_name"] == meeting)
        for meeting in {key[0] for key in grouped}
    }
    ordered = [meeting for meeting, _ in sorted(dates.items(), key=lambda item: (item[1], item[0]))]
    cut = max(1, math.floor(len(ordered) * 0.70))
    return {
        "development": set(ordered[:cut]),
        "temporal_holdout": set(ordered[cut:]),
        "all": set(ordered),
    }


def evaluate(
    races: list[list[dict[str, Any]]],
    candidate: str,
) -> tuple[dict[str, Any], dict[tuple[str, int], dict[str, Any]]]:
    if not races:
        return (
            {
                "races": 0,
                "zero_hit": 0,
                "one_hit": 0,
                "two_hit": 0,
                "top2_total_hits": 0,
                "top3_capture_at5": 0.0,
                "top3_all_within_top5": 0.0,
                "competitive_recall_at5": 0.0,
                "ndcg_at5": 0.0,
                "winner_in_top5": 0.0,
                "mrr": 0.0,
            },
            {},
        )
    metrics = []
    per_race = {}
    for rows in races:
        rating = relative(rows, "card_rating")
        experience = relative(rows, "starts")
        class_v2 = {
            horse: 0.80 * rating[horse] + 0.20 * experience[horse]
            for horse in rating
        }
        ranked = sorted(
            rows,
            key=lambda row: (
                -candidate_score(
                    row,
                    name=candidate,
                    class_v2=class_v2[as_int(row["horse_number"])],
                ),
                as_int(row["horse_number"]),
            ),
        )
        picks = [as_int(row["horse_number"]) for row in ranked]
        positions = {
            as_int(row["horse_number"]): as_int(row["finish_pos"], 99)
            for row in ranked
        }
        actual_top3 = [horse for horse, position in positions.items() if position <= 3]
        metric = race_metrics(picks, actual_top3, actual_pos=positions, field_size=len(rows))
        metrics.append(metric)
        per_race[race_key(ranked[0])] = {
            "top2_hits": metric["top2_hits"],
            "picks": picks,
            "winner_rank": metric["winner_rank"],
            "positions": positions,
        }
    summary = summarize_races(metrics)
    comp = summary["competitiveness"]
    distribution = Counter(metric["top2_hits"] for metric in metrics)
    return (
        {
            "races": len(metrics),
            "zero_hit": distribution[0],
            "one_hit": distribution[1],
            "two_hit": distribution[2],
            "top2_total_hits": sum(metric["top2_hits"] for metric in metrics),
            "top3_capture_at5": round(comp["mean_top3_capture_at5"], 6),
            "top3_all_within_top5": round(comp["top3_all_within_top5"]["rate"], 6),
            "competitive_recall_at5": round(comp["mean_competitive_recall_at5"], 6),
            "ndcg_at5": round(comp["mean_ndcg_at5"], 6),
            "winner_in_top5": round(summary["rates"]["winner_in_top5"], 6),
            "mrr": round(summary["mrr"], 6),
        },
        per_race,
    )


def delta(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    return {
        key: round(candidate[key] - baseline[key], 6)
        for key in candidate
        if key != "races"
    }


def comparison(
    baseline: dict[tuple[str, int], dict[str, Any]],
    candidate: dict[tuple[str, int], dict[str, Any]],
) -> dict[str, Any]:
    helped = harmed = unchanged = 0
    changes = []
    for key, base in baseline.items():
        change = candidate[key]["top2_hits"] - base["top2_hits"]
        helped += change > 0
        harmed += change < 0
        unchanged += change == 0
        if base["picks"] != candidate[key]["picks"]:
            positions = base["positions"]
            changes.append(
                {
                    "meeting": key[0],
                    "race_number": key[1],
                    "top2_hit_delta": change,
                    "baseline_top5": [
                        {"horse": horse, "finish": positions.get(horse)}
                        for horse in base["picks"][:5]
                    ],
                    "candidate_top5": [
                        {"horse": horse, "finish": positions.get(horse)}
                        for horse in candidate[key]["picks"][:5]
                    ],
                }
            )
    return {
        "helped": helped,
        "harmed": harmed,
        "unchanged": unchanged,
        "net": helped - harmed,
        "changed_races": changes,
    }


def gate(result: dict[str, Any]) -> dict[str, Any]:
    holdout = result["temporal_holdout"]["delta"]
    overall = result["all"]["delta"]
    adjusted = result["all_adjusted"]["delta"]
    adjusted_holdout = result["temporal_holdout_adjusted"]["delta"]
    no_material_holdout_harm = (
        holdout["zero_hit"] <= 1
        and holdout["top2_total_hits"] >= -1
        and holdout["top3_capture_at5"] >= -0.005
        and holdout["competitive_recall_at5"] >= -0.005
        and holdout["ndcg_at5"] >= -0.005
        and holdout["winner_in_top5"] >= -0.01
        and holdout["mrr"] >= -0.01
    )
    overall_improvement = (
        overall["zero_hit"] <= -1
        and overall["top2_total_hits"] >= 3
        and overall["top3_capture_at5"] >= 0.0
        and overall["competitive_recall_at5"] >= 0.0
        and overall["ndcg_at5"] >= 0.003
        and overall["winner_in_top5"] >= 0.0
        and overall["mrr"] >= 0.0
    )
    no_adjusted_harm = (
        adjusted["zero_hit"] <= 0
        and adjusted["top2_total_hits"] >= 0
        and adjusted["top3_capture_at5"] >= -0.002
        and adjusted["competitive_recall_at5"] >= -0.002
        and adjusted["ndcg_at5"] >= -0.002
        and adjusted["winner_in_top5"] >= -0.01
        and adjusted["mrr"] >= -0.01
        and adjusted_holdout["zero_hit"] <= 1
        and adjusted_holdout["top2_total_hits"] >= -1
        and adjusted_holdout["ndcg_at5"] >= -0.005
    )
    balanced = result["comparison"]["helped"] > result["comparison"]["harmed"]
    return {
        "passes": no_material_holdout_harm and overall_improvement and no_adjusted_harm and balanced,
        "no_material_holdout_harm": no_material_holdout_harm,
        "overall_improvement": overall_improvement,
        "no_adjusted_harm": no_adjusted_harm,
        "balanced_race_changes": balanced,
    }


def dimension_auc(rows: list[dict[str, Any]], column: str) -> float:
    positives = [
        float(as_float(row.get(column), 60.0) or 60.0)
        for row in rows
        if as_int(row["finish_pos"], 99) <= min(5, max(3, math.ceil(as_int(row["field_size"]) / 3)))
    ]
    negatives = [
        float(as_float(row.get(column), 60.0) or 60.0)
        for row in rows
        if as_int(row["finish_pos"], 99) > min(5, max(3, math.ceil(as_int(row["field_size"]) / 3)))
    ]
    if not positives or not negatives:
        return 0.5
    wins = ties = 0
    for positive in positives:
        for negative in negatives:
            wins += positive > negative
            ties += positive == negative
    return (wins + 0.5 * ties) / (len(positives) * len(negatives))


def main() -> int:
    args = parse_args()
    sources = [Path(path) for path in args.input] or [DEFAULT_INPUT]
    output_path = Path(args.output)
    report_path = Path(args.report)
    rows_by_horse = {}
    for source in sources:
        for row in read_csv(source):
            rows_by_horse[
                (
                    row["meeting_name"],
                    as_int(row["race_number"]),
                    as_int(row["horse_number"]),
                )
            ] = row
    rows = list(rows_by_horse.values())
    manifest = Path(args.manifest)
    invalid_filtered = 0
    if manifest.exists():
        valid_races = {
            (row["meeting"], as_int(row["race_number"]))
            for row in read_csv(manifest)
            if str(row.get("valid", "")).strip().lower() in ("true", "1", "yes")
        }
        before = len(rows)
        rows = [
            row
            for row in rows
            if (row["meeting_name"], as_int(row["race_number"])) in valid_races
        ]
        invalid_filtered = before - len(rows)
    annotation_path = Path(args.annotations)
    abnormal_races: set[tuple[str, int]] = set()
    if annotation_path.exists():
        for row in read_csv(annotation_path):
            if any(
                str(row.get(flag, "")).strip().lower() in ("true", "1", "yes")
                for flag in (
                    "extreme_outsider",
                    "major_incident",
                    "interference",
                    "injury",
                    "abnormal",
                )
            ):
                abnormal_races.add((row["meeting"], as_int(row["race_number"])))
    grouped: defaultdict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[race_key(row)].append(row)
    meeting_splits = split_meetings(dict(grouped))
    slices = {
        name: [
            race_rows
            for (meeting, _), race_rows in grouped.items()
            if meeting in meetings
        ]
        for name, meetings in meeting_splits.items()
    }
    slices.update(
        {
            "development_adjusted": [
                race_rows
                for key, race_rows in grouped.items()
                if key[0] in meeting_splits["development"] and key not in abnormal_races
            ],
            "temporal_holdout_adjusted": [
                race_rows
                for key, race_rows in grouped.items()
                if key[0] in meeting_splits["temporal_holdout"] and key not in abnormal_races
            ],
            "all_adjusted": [
                race_rows
                for key, race_rows in grouped.items()
                if key not in abnormal_races
            ],
        }
    )

    baseline = {}
    baseline_races = {}
    for split, races in slices.items():
        baseline[split], baseline_races[split] = evaluate(races, "baseline")

    results = {}
    gates = {}
    for candidate in CANDIDATES:
        if candidate == "baseline":
            continue
        result = {}
        per_race = {}
        for split, races in slices.items():
            metrics, race_metrics_by_key = evaluate(races, candidate)
            result[split] = {
                "baseline": baseline[split],
                "candidate": metrics,
                "delta": delta(metrics, baseline[split]),
            }
            per_race[split] = race_metrics_by_key
        result["comparison"] = comparison(baseline_races["all"], per_race["all"])
        results[candidate] = result
        gates[candidate] = gate(result)

    passing = [candidate for candidate, item in gates.items() if item["passes"]]
    payload = {
        "method": {
            "sources": [str(source) for source in sources],
            "validity_manifest": str(manifest) if manifest.exists() else None,
            "anomaly_annotations": str(annotation_path) if annotation_path.exists() else None,
            "full_field_rerank": True,
            "micro_tiebreak": False,
            "blind_swap": False,
            "chronological_holdout": True,
        },
        "coverage": {
            "meetings": len(meeting_splits["all"]),
            "races": len(grouped),
            "runners": len(rows),
            "development_meetings": len(meeting_splits["development"]),
            "holdout_meetings": len(meeting_splits["temporal_holdout"]),
            "invalid_or_out_of_manifest_runners_filtered": invalid_filtered,
            "adjusted_exclusions": sum(key in abnormal_races for key in grouped),
            "adjusted_races": sum(key not in abnormal_races for key in grouped),
        },
        "dimension_competitive_auc": {
            name: round(dimension_auc(rows, f"matrix_{name}"), 6)
            for name in MATRIX_NAMES
        },
        "baseline": baseline,
        "results": results,
        "gates": gates,
        "passing_candidates": passing,
        "recommendation": "PROMOTE_PASSING" if passing else "HOLD_ALL",
    }
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# HKJC Rich Production Matrix Gate",
        "",
        f"- Sources: {', '.join(f'`{source}`' for source in sources)}",
        f"- Coverage: {payload['coverage']['meetings']} meetings / {payload['coverage']['races']} races / {payload['coverage']['runners']} runners",
        f"- Recommendation: **{payload['recommendation']}**",
        "",
        "| Candidate | Pass | 0-hit Δ | Top2 hits Δ | Top3@5 Δ | Competitive recall@5 Δ | NDCG@5 Δ | Winner@5 Δ | MRR Δ | Adjusted 0-hit Δ | Adjusted Top2 Δ | Adjusted NDCG Δ | Help/Harm |",
        "|---|:---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for candidate in results:
        item = results[candidate]["all"]["delta"]
        adjusted = results[candidate]["all_adjusted"]["delta"]
        balance = results[candidate]["comparison"]
        lines.append(
            f"| {candidate} | {'PASS' if gates[candidate]['passes'] else 'FAIL'} | "
            f"{item['zero_hit']:+.0f} | {item['top2_total_hits']:+.0f} | "
            f"{item['top3_capture_at5']:+.4f} | {item['competitive_recall_at5']:+.4f} | "
            f"{item['ndcg_at5']:+.4f} | {item['winner_in_top5']:+.4f} | "
            f"{item['mrr']:+.4f} | {adjusted['zero_hit']:+.0f} | "
            f"{adjusted['top2_total_hits']:+.0f} | {adjusted['ndcg_at5']:+.4f} | "
            f"{balance['helped']}/{balance['harmed']} |"
        )
    lines.extend(["", "## Matrix competitive-tier AUC", ""])
    for name, auc in payload["dimension_competitive_auc"].items():
        lines.append(f"- {name}: {auc:.3f}")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "coverage": payload["coverage"],
                "recommendation": payload["recommendation"],
                "passing_candidates": passing,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
