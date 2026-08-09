#!/usr/bin/env python3
"""Gate dimension-reconstruction candidates against the current HKJC model.

Candidates change complete matrix dimensions before the official 7D outer
weights are applied.  There are no rank swaps, boundary tie-breaks, odds, or
post-race inputs.  Each candidate is evaluated on development, chronological
holdout, full archive, adjusted normal races, adjusted holdout, and the
independent 2026-07-15 meeting.
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
SHARED = ROOT / ".agents" / "skills" / "shared_racing"
ENGINE = (
    ROOT / ".agents" / "skills" / "hkjc_racing"
    / "hkjc_wong_choi_auto" / "scripts" / "racing_engine"
)
sys.path.insert(0, str(SHARED))
sys.path.insert(0, str(ENGINE))

from eval_metrics import race_metrics, summarize_races  # noqa: E402
from scoring import MATRIX_WEIGHTS  # noqa: E402
from hkjc_iterative_feature_audit import (  # noqa: E402
    DEFAULT_ANNOTATIONS,
    DEFAULT_INPUTS,
    DEFAULT_MANIFEST,
    SIGNALS,
    as_float,
    as_int,
    horse_key,
    race_key,
    read_csv,
)


DEFAULT_JSON = ROOT / "scratch" / "hkjc_iterative_dimension_gate.json"
DEFAULT_REPORT = ROOT / "scratch" / "hkjc_iterative_dimension_gate_report.md"
MATRIX_NAMES = tuple(MATRIX_WEIGHTS)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", default=[])
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--report-output", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def split_meetings(
    grouped: dict[tuple[str, int], list[dict[str, Any]]],
) -> dict[str, set[str]]:
    dates = {
        meeting: min(
            str(row.get("date") or meeting[:10])
            for key, rows in grouped.items()
            if key[0] == meeting
            for row in rows
        )
        for meeting in {key[0] for key in grouped}
    }
    ordered = [meeting for meeting, _date in sorted(dates.items(), key=lambda item: (item[1], item[0]))]
    cut = max(1, math.floor(len(ordered) * 0.70))
    return {
        "development": set(ordered[:cut]),
        "temporal_holdout": set(ordered[cut:]),
        "all": set(ordered),
        "2026_07_15": {meeting for meeting in ordered if meeting.startswith("2026-07-15")},
    }


def relative_score(
    rows: list[dict[str, Any]],
    signal: str,
) -> dict[int, float]:
    extractor = SIGNALS[signal]
    values = {
        as_int(row["horse_number"]): extractor(row)
        for row in rows
    }
    valid = {horse: float(value) for horse, value in values.items() if value is not None}
    if len(valid) < 2:
        return {horse: 60.0 for horse in values}
    denominator = len(valid) - 1
    output = {}
    for horse, value in values.items():
        if value is None:
            output[horse] = 60.0
            continue
        others = [item for other, item in valid.items() if other != horse]
        worse = sum(item < value for item in others)
        ties = sum(item == value for item in others)
        output[horse] = 45.0 + 30.0 * (worse + 0.5 * ties) / denominator
    return output


def specs() -> dict[str, list[tuple[str, str, float]]]:
    output: dict[str, list[tuple[str, str, float]]] = {"baseline": []}

    def add_family(
        prefix: str,
        dimension: str,
        signal: str,
        alphas: tuple[float, ...],
    ) -> None:
        for alpha in alphas:
            output[f"{prefix}_{int(alpha * 100):02d}"] = [(dimension, signal, alpha)]

    add_family("stability_last6_mean", "stability", "last6_mean_finish", (0.10, 0.20, 0.30, 0.40, 0.50))
    add_family("stability_last6_top5", "stability", "last6_top5_count", (0.10, 0.20, 0.30))
    add_family("stability_last_margin", "stability", "raw_last_margin", (0.10, 0.20, 0.30))
    # The current form-line dimension is substantially weaker than stability.
    # Test recent-form evidence here as a semantic reconstruction instead of
    # double-counting it inside the already-strong stability dimension.
    add_family(
        "formline_last6_mean",
        "form_line",
        "last6_mean_finish",
        (0.10, 0.20, 0.30, 0.50, 0.75, 1.00),
    )
    add_family(
        "formline_last6_top5",
        "form_line",
        "last6_top5_count",
        (0.10, 0.20, 0.30, 0.50, 0.75, 1.00),
    )
    add_family(
        "formline_last_margin",
        "form_line",
        "raw_last_margin",
        (0.10, 0.20, 0.30, 0.50, 0.75, 1.00),
    )
    add_family(
        "formline_last_finish",
        "form_line",
        "raw_last_finish",
        (0.10, 0.20, 0.30, 0.50, 0.75, 1.00),
    )
    add_family("sectional_finish_time", "sectional", "raw_finish_time_adj", (0.10, 0.20, 0.30, 0.40))
    add_family("sectional_l400", "sectional", "raw_l400", (0.10, 0.20, 0.30))
    add_family("trainer_jockey_cd", "trainer_signal", "prior_jockey_cd_place_edge", (0.10, 0.20, 0.30))
    add_family("trainer_combo", "trainer_signal", "prior_combo_place_edge", (0.10, 0.20, 0.30))
    add_family("class_rating_change", "class_advantage", "card_rating_change", (0.10, 0.20, 0.30))
    add_family("class_weight_prior", "class_advantage", "prior_weight_class_place_edge", (0.10, 0.20))
    add_family("stability_forensic", "stability", "forensic_flag_balance", (0.10, 0.20))

    for alpha in (0.10, 0.15, 0.20):
        output[f"stability_sectional_core_{int(alpha * 100):02d}"] = [
            ("stability", "last6_mean_finish", alpha),
            ("sectional", "raw_finish_time_adj", alpha),
        ]
        output[f"three_core_{int(alpha * 100):02d}"] = [
            ("stability", "last6_mean_finish", alpha),
            ("sectional", "raw_finish_time_adj", alpha),
            ("trainer_signal", "prior_jockey_cd_place_edge", alpha),
        ]
        output[f"four_core_{int(alpha * 100):02d}"] = [
            ("stability", "last6_mean_finish", alpha),
            ("sectional", "raw_finish_time_adj", alpha),
            ("trainer_signal", "prior_jockey_cd_place_edge", alpha),
            ("class_advantage", "card_rating_change", alpha),
        ]
    return output


CANDIDATES = specs()


def matrix_scores(row: dict[str, Any]) -> dict[str, float]:
    return {
        name: float(as_float(row.get(f"matrix_{name}"), 60.0) or 60.0)
        for name in MATRIX_NAMES
    }


def score_rows(
    rows: list[dict[str, Any]],
    spec: list[tuple[str, str, float]],
) -> list[dict[str, Any]]:
    relative = {
        signal: relative_score(rows, signal)
        for _dimension, signal, _alpha in spec
    }
    ranked = []
    for row in rows:
        matrices = matrix_scores(row)
        horse = as_int(row["horse_number"])
        for dimension, signal, alpha in spec:
            matrices[dimension] = round(
                (1.0 - alpha) * matrices[dimension] + alpha * relative[signal][horse],
                2,
            )
        ability = sum(matrices[name] * weight for name, weight in MATRIX_WEIGHTS.items())
        ranked.append({**row, "_candidate_ability": ability})
    return sorted(
        ranked,
        key=lambda row: (-float(row["_candidate_ability"]), as_int(row["horse_number"])),
    )


def evaluate(
    races: list[list[dict[str, Any]]],
    spec: list[tuple[str, str, float]],
) -> tuple[dict[str, Any], dict[tuple[str, int], dict[str, Any]]]:
    metrics = []
    details = {}
    for rows in races:
        ranked = score_rows(rows, spec)
        picks = [as_int(row["horse_number"]) for row in ranked]
        positions = {
            as_int(row["horse_number"]): as_int(row["finish_pos"], 99)
            for row in ranked
        }
        actual_top3 = [horse for horse, position in positions.items() if position <= 3]
        metric = race_metrics(picks, actual_top3, actual_pos=positions, field_size=len(rows))
        metrics.append(metric)
        details[race_key(ranked[0])] = {
            "top2_hits": metric["top2_hits"],
            "picks": picks,
            "positions": positions,
        }
    if not metrics:
        return {
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
        }, details
    summary = summarize_races(metrics)
    comp = summary["competitiveness"]
    distribution = Counter(metric["top2_hits"] for metric in metrics)
    return {
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
    }, details


def delta(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    return {
        key: round(candidate[key] - baseline[key], 6)
        for key in candidate
        if key != "races"
    }


def compare(
    baseline: dict[tuple[str, int], dict[str, Any]],
    candidate: dict[tuple[str, int], dict[str, Any]],
) -> dict[str, int]:
    helped = harmed = unchanged = 0
    for key, item in baseline.items():
        change = candidate[key]["top2_hits"] - item["top2_hits"]
        helped += change > 0
        harmed += change < 0
        unchanged += change == 0
    return {
        "helped": helped,
        "harmed": harmed,
        "unchanged": unchanged,
        "net": helped - harmed,
    }


def passes_gate(result: dict[str, Any]) -> dict[str, bool]:
    overall = result["all"]["delta"]
    adjusted = result["all_adjusted"]["delta"]
    development = result["development"]["delta"]
    holdout = result["temporal_holdout"]["delta"]
    adjusted_holdout = result["temporal_holdout_adjusted"]["delta"]
    external = result["2026_07_15"]["delta"]

    broad_improvement = (
        overall["zero_hit"] <= 0
        and overall["top2_total_hits"] >= 0
        and overall["top3_capture_at5"] >= 0
        and overall["competitive_recall_at5"] >= 0
        and overall["ndcg_at5"] >= 0.002
        and overall["winner_in_top5"] >= -0.005
        and overall["mrr"] >= -0.005
        and adjusted["zero_hit"] <= 0
        and adjusted["top2_total_hits"] >= 0
        and adjusted["top3_capture_at5"] >= 0
        and adjusted["competitive_recall_at5"] >= 0
        and adjusted["ndcg_at5"] >= 0.002
        and adjusted["winner_in_top5"] >= -0.005
        and adjusted["mrr"] >= -0.005
    )
    no_split_harm = all(
        item["zero_hit"] <= 1
        and item["top2_total_hits"] >= -1
        and item["top3_capture_at5"] >= -0.006
        and item["competitive_recall_at5"] >= -0.006
        and item["ndcg_at5"] >= -0.006
        and item["winner_in_top5"] >= -0.012
        and item["mrr"] >= -0.012
        for item in (development, holdout, adjusted_holdout)
    )
    external_safe = (
        external["zero_hit"] <= 1
        and external["top2_total_hits"] >= -1
        and external["top3_capture_at5"] >= -0.04
        and external["ndcg_at5"] >= -0.025
        and external["winner_in_top5"] >= -0.12
        and external["mrr"] >= -0.06
    )
    balanced = result["comparison"]["helped"] >= result["comparison"]["harmed"]
    return {
        "passes": broad_improvement and no_split_harm and external_safe and balanced,
        "broad_improvement": broad_improvement,
        "no_split_harm": no_split_harm,
        "external_safe": external_safe,
        "balanced": balanced,
    }


def main() -> int:
    args = parse_args()
    sources = [Path(path) for path in args.input] or DEFAULT_INPUTS
    by_horse = {}
    for source in sources:
        for row in read_csv(source):
            by_horse[horse_key(row)] = row
    rows = list(by_horse.values())

    if args.manifest.exists():
        valid = {
            (row["meeting"], as_int(row["race_number"]))
            for row in read_csv(args.manifest)
            if str(row.get("valid", "")).strip().lower() in ("true", "1", "yes")
        }
        rows = [row for row in rows if race_key(row) in valid]

    abnormal = set()
    if args.annotations.exists():
        for row in read_csv(args.annotations):
            if any(
                str(row.get(flag, "")).strip().lower() in ("true", "1", "yes")
                for flag in ("extreme_outsider", "major_incident", "interference", "injury", "abnormal")
            ):
                abnormal.add((row["meeting"], as_int(row["race_number"])))

    grouped: defaultdict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[race_key(row)].append(row)
    meeting_splits = split_meetings(dict(grouped))
    slices = {
        name: [
            race_rows
            for (meeting, _race), race_rows in grouped.items()
            if meeting in meetings
        ]
        for name, meetings in meeting_splits.items()
    }
    slices["all_adjusted"] = [
        race_rows for key, race_rows in grouped.items() if key not in abnormal
    ]
    slices["development_adjusted"] = [
        race_rows
        for key, race_rows in grouped.items()
        if key[0] in meeting_splits["development"] and key not in abnormal
    ]
    slices["temporal_holdout_adjusted"] = [
        race_rows
        for key, race_rows in grouped.items()
        if key[0] in meeting_splits["temporal_holdout"] and key not in abnormal
    ]

    baseline = {}
    baseline_races = {}
    for split, races in slices.items():
        baseline[split], baseline_races[split] = evaluate(races, CANDIDATES["baseline"])

    results = {}
    gates = {}
    for name, spec in CANDIDATES.items():
        if name == "baseline":
            continue
        result = {}
        details = {}
        for split, races in slices.items():
            metrics, race_details = evaluate(races, spec)
            result[split] = {
                "baseline": baseline[split],
                "candidate": metrics,
                "delta": delta(metrics, baseline[split]),
            }
            details[split] = race_details
        result["comparison"] = compare(baseline_races["all"], details["all"])
        results[name] = result
        gates[name] = passes_gate(result)

    passing = [name for name, gate in gates.items() if gate["passes"]]
    payload = {
        "method": {
            "baseline": "current live 7D production weights and matrices",
            "full_field_rerank": True,
            "dimension_blend_before_outer_weights": True,
            "micro_tiebreak": False,
            "blind_swap": False,
            "odds_in_score": False,
            "post_race_incident_in_score": False,
        },
        "coverage": {
            "meetings": len(meeting_splits["all"]),
            "races": len(grouped),
            "runners": len(rows),
            "adjusted_races": len(slices["all_adjusted"]),
        },
        "baseline": baseline,
        "results": results,
        "gates": gates,
        "passing_candidates": passing,
        "recommendation": "PROMOTE_REVIEW" if passing else "HOLD_ALL",
    }
    args.json_output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    ranked = sorted(
        results,
        key=lambda name: (
            not gates[name]["passes"],
            -results[name]["all_adjusted"]["delta"]["ndcg_at5"],
            -results[name]["all"]["delta"]["ndcg_at5"],
            -results[name]["all"]["delta"]["top2_total_hits"],
        ),
    )
    lines = [
        "# HKJC Iterative Dimension Gate",
        "",
        f"- Coverage: {payload['coverage']['meetings']} meetings / {payload['coverage']['races']} races / {payload['coverage']['runners']} runners",
        f"- Adjusted: {payload['coverage']['adjusted_races']} races",
        f"- Recommendation: **{payload['recommendation']}**",
        "",
        "| Candidate | Pass | 0-hit Δ | Top2 Δ | Top3@5 Δ | Recall@5 Δ | NDCG Δ | Winner@5 Δ | MRR Δ | Adj 0-hit Δ | Adj Top2 Δ | Adj Top3@5 Δ | Adj NDCG Δ | Help/Harm |",
        "|---|:---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in ranked:
        overall = results[name]["all"]["delta"]
        adjusted = results[name]["all_adjusted"]["delta"]
        comparison = results[name]["comparison"]
        lines.append(
            f"| {name} | {'PASS' if gates[name]['passes'] else 'FAIL'} | "
            f"{overall['zero_hit']:+.0f} | {overall['top2_total_hits']:+.0f} | "
            f"{overall['top3_capture_at5']:+.4f} | {overall['competitive_recall_at5']:+.4f} | "
            f"{overall['ndcg_at5']:+.4f} | {overall['winner_in_top5']:+.4f} | "
            f"{overall['mrr']:+.4f} | {adjusted['zero_hit']:+.0f} | "
            f"{adjusted['top2_total_hits']:+.0f} | {adjusted['top3_capture_at5']:+.4f} | "
            f"{adjusted['ndcg_at5']:+.4f} | {comparison['helped']}/{comparison['harmed']} |"
        )
    args.report_output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(payload["coverage"], ensure_ascii=False))
    print(f"passing={passing}")
    print(f"report={args.report_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
