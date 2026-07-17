#!/usr/bin/env python3
"""AU Wong Choi failure-cohort localization and error attribution.

Phase 4 of the 2026-07-17 AU review. Slices the cached 710-race archive by
month / venue / going / class / field size / score-gap / feature coverage,
ranks underperforming cohorts (n>=30), then attributes errors per matrix
dimension with leave-one-dimension-out and ±10%/±20% weight perturbations,
plus winner-vs-top2 matrix deltas in zero-hit races.

Research-only: reads the cached dataset, writes report files, never touches
Logic files or live weights.

Usage:
    python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_failure_cohorts.py \
        [--min-races 30] [--report-date YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import mean

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[4]
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR / "racing_engine"))
sys.path.insert(0, str(PROJECT_ROOT / ".agents" / "skills" / "shared_racing"))

from au_archive_calibrator import MATRIX_KEYS, normalize_condition_bucket  # noqa: E402
from au_cached_walkforward_ml import (  # noqa: E402
    as_float,
    group_races,
    materialize_dataset,
    metrics_for_races,
)
from scoring import MATRIX_WEIGHTS  # noqa: E402

FEATURE_KEYS_FOR_COVERAGE = (
    "form_score",
    "trial_score",
    "sectional_score",
    "pace_map_score",
    "jockey_score",
    "trainer_score",
    "class_score",
    "rating_score",
)


def production_scored(races: list[list[dict]]) -> list[list[dict]]:
    return [[{**row, "_score": as_float(row["ability_score"], 60.0)} for row in race] for race in races]


def reconstructed_scored(races: list[list[dict]], weights: dict[str, float]) -> list[list[dict]]:
    total = sum(weights.values()) or 1.0
    scale = sum(MATRIX_WEIGHTS.values()) / total
    return [
        [
            {
                **row,
                "_score": scale * sum(
                    weights.get(key, 0.0) * as_float(row.get(f"mx_{key}"), 60.0) for key in MATRIX_KEYS
                ),
            }
            for row in race
        ]
        for race in races
    ]


def field_band(count: int) -> str:
    if count <= 8:
        return "<=8"
    if count <= 11:
        return "9-11"
    return "12+"


def coverage_band(race: list[dict]) -> str:
    defaults = []
    for row in race:
        vals = [as_float(row.get(key), 60.0) for key in FEATURE_KEYS_FOR_COVERAGE]
        defaults.append(sum(1 for value in vals if abs(value - 60.0) < 1e-9) / len(vals))
    avg = mean(defaults)
    if avg < 0.15:
        return "rich (<15% default)"
    if avg < 0.35:
        return "medium (15-35% default)"
    return "thin (>=35% default)"


def score_gap_band(race: list[dict]) -> str:
    ranked = sorted((as_float(row["ability_score"], 60.0) for row in race), reverse=True)
    gap = ranked[0] - ranked[2] if len(ranked) >= 3 else 0.0
    if gap < 2.0:
        return "tight (top1-top3 < 2)"
    if gap < 5.0:
        return "medium (2-5)"
    return "clear (>=5)"


def race_class_family(value: str) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return "Unknown"
    if text.startswith(("G1", "G2", "G3", "GROUP", "LR", "LISTED")):
        return "Stakes/Listed"
    if "MDN" in text or "MAIDEN" in text:
        return "Maiden"
    if text.startswith("BM") or "BENCHMARK" in text:
        return "Benchmark"
    if "CL" in text or "CLASS" in text:
        return "Class"
    return "Other"


SLICERS = {
    "month": lambda race: str(race[0]["date"])[:7],
    "venue": lambda race: str(race[0].get("track") or "Unknown"),
    "going_family": lambda race: normalize_condition_bucket(str(race[0].get("condition_bucket") or "")),
    "going_detail": lambda race: str(race[0].get("condition_bucket") or "Unknown"),
    "race_class": lambda race: race_class_family(race[0].get("race_class")),
    "field_size": lambda race: field_band(len(race)),
    "score_gap": score_gap_band,
    "feature_coverage": coverage_band,
}

KPI_KEYS = ("good_positional", "winner_in_top3", "top3_precision", "miss")


def cohort_table(races: list[list[dict]], min_races: int) -> list[dict]:
    overall = metrics_for_races(production_scored(races))
    overall_rates = {
        "good_positional": overall["good_positional"] / overall["races"],
        "winner_in_top3": overall["winner_in_top3"],
        "top3_precision": overall["top3_precision"],
        "miss_rate": overall["miss"] / overall["races"],
    }
    rows = []
    for slicer_name, slicer in SLICERS.items():
        groups: dict[str, list[list[dict]]] = defaultdict(list)
        for race in races:
            groups[slicer(race)].append(race)
        for value, members in groups.items():
            metrics = metrics_for_races(production_scored(members))
            n = metrics["races"]
            rows.append(
                {
                    "slice": slicer_name,
                    "cohort": value,
                    "races": n,
                    "underpowered": n < min_races,
                    "good_positional_rate": metrics["good_positional"] / n,
                    "good_any2_rate": metrics["good"] / n,
                    "winner_in_top3": metrics["winner_in_top3"],
                    "top3_precision": metrics["top3_precision"],
                    "miss_rate": metrics["miss"] / n,
                    "delta_good_positional": metrics["good_positional"] / n - overall_rates["good_positional"],
                    "delta_winner_in_top3": metrics["winner_in_top3"] - overall_rates["winner_in_top3"],
                    "delta_top3_precision": metrics["top3_precision"] - overall_rates["top3_precision"],
                    "delta_miss_rate": metrics["miss"] / n - overall_rates["miss_rate"],
                }
            )
    rows.sort(key=lambda row: (row["underpowered"], row["delta_top3_precision"]))
    return rows


def lodo_and_perturbation(races: list[list[dict]], cohorts: dict[str, list[list[dict]]]) -> dict:
    """Compare reconstructed baseline vs per-dimension variants, overall and per cohort."""
    baseline = {name: metrics_for_races(reconstructed_scored(members, dict(MATRIX_WEIGHTS)))
                for name, members in cohorts.items()}
    out = {"baseline": baseline, "dimensions": {}}
    for key in MATRIX_KEYS:
        variants = {}
        weight = MATRIX_WEIGHTS.get(key, 0.0)
        candidates = {"drop": 0.0, "-20%": weight * 0.8, "-10%": weight * 0.9,
                      "+10%": weight * 1.1, "+20%": weight * 1.2}
        if weight == 0.0:
            # dimension currently unused: probe re-enabling it at modest weights
            candidates = {"enable@0.05": 0.05, "enable@0.10": 0.10}
        for label, new_weight in candidates.items():
            weights = dict(MATRIX_WEIGHTS)
            weights[key] = new_weight
            variants[label] = {
                name: metrics_for_races(reconstructed_scored(members, weights))
                for name, members in cohorts.items()
            }
        out["dimensions"][key] = variants
    return out


def zero_hit_winner_deltas(races: list[list[dict]]) -> dict:
    """In 0-hit races: winner's matrix scores minus the model top-2 average."""
    deltas: dict[str, list[float]] = defaultdict(list)
    count = 0
    for race in production_scored(races):
        ranked = sorted(race, key=lambda row: (-row["_score"], int(row["horse_number"])))
        top3 = ranked[:3]
        if any(int(row["actual_pos"]) <= 3 for row in top3):
            continue
        winner = next((row for row in race if int(row["actual_pos"]) == 1), None)
        if winner is None:
            continue
        count += 1
        top2 = ranked[:2]
        for key in MATRIX_KEYS:
            top2_avg = mean(as_float(row.get(f"mx_{key}"), 60.0) for row in top2)
            deltas[key].append(as_float(winner.get(f"mx_{key}"), 60.0) - top2_avg)
    return {
        "zero_hit_races": count,
        "winner_minus_top2_avg": {key: round(mean(values), 3) for key, values in deltas.items() if values},
    }


def fmt_pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def main() -> int:
    parser = argparse.ArgumentParser(description="AU failure cohort localization")
    parser.add_argument("--min-races", type=int, default=30)
    parser.add_argument("--report-date", default=date.today().isoformat())
    args = parser.parse_args()

    races = group_races(materialize_dataset())
    table = cohort_table(races, args.min_races)

    # attribution cohorts: overall + the known problem slices
    cohorts = {
        "ALL": races,
        "Soft": [race for race in races if SLICERS["going_family"](race) == "Soft"],
        "Heavy": [race for race in races if SLICERS["going_family"](race) == "Heavy"],
        "field 12+": [race for race in races if field_band(len(race)) == "12+"],
    }
    attribution = lodo_and_perturbation(races, cohorts)
    zero_hit = zero_hit_winner_deltas(races)

    lines = [
        f"# AU Wong Choi Failure Cohorts & Error Attribution ({args.report_date})",
        "",
        f"> Cached 710-race archive, production ranking = stored `ability_score`. "
        f"Cohorts under {args.min_races} races are marked underpowered.",
        "",
        "## Ranked cohort table (worst Top3-precision delta first)",
        "",
        "| Slice | Cohort | Races | Good pos. | Good any-2 | W-in-T3 | Top3 prec | Miss | ΔGood pos. | ΔW-in-T3 | ΔTop3 | ΔMiss |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in table:
        marker = " *(underpowered)*" if row["underpowered"] else ""
        lines.append(
            f"| {row['slice']} | {row['cohort']}{marker} | {row['races']} | "
            f"{fmt_pct(row['good_positional_rate'])} | {fmt_pct(row['good_any2_rate'])} | "
            f"{fmt_pct(row['winner_in_top3'])} | {fmt_pct(row['top3_precision'])} | "
            f"{fmt_pct(row['miss_rate'])} | {fmt_pct(row['delta_good_positional'])} | "
            f"{fmt_pct(row['delta_winner_in_top3'])} | {fmt_pct(row['delta_top3_precision'])} | "
            f"{fmt_pct(row['delta_miss_rate'])} |"
        )

    lines += [
        "",
        "## Matrix-dimension attribution (reconstructed weights baseline)",
        "",
        "Baseline = matrix reconstruction with live weights (mean |err| vs stored ability ≈ 0.4 pt).",
        "Values shown: Top3 precision (Good-positional rate) per cohort.",
        "",
        "| Dimension | Variant | " + " | ".join(cohorts.keys()) + " |",
        "|---|---|" + "---|" * len(cohorts),
    ]
    baseline = attribution["baseline"]
    lines.append(
        "| _baseline_ | live weights | "
        + " | ".join(
            f"{fmt_pct(baseline[name]['top3_precision'])} ({fmt_pct(baseline[name]['good_positional'] / baseline[name]['races'])})"
            for name in cohorts
        )
        + " |"
    )
    for key, variants in attribution["dimensions"].items():
        for label, per_cohort in variants.items():
            lines.append(
                f"| {key} (w={MATRIX_WEIGHTS.get(key, 0.0):.3f}) | {label} | "
                + " | ".join(
                    f"{fmt_pct(per_cohort[name]['top3_precision'])} ({fmt_pct(per_cohort[name]['good_positional'] / per_cohort[name]['races'])})"
                    for name in cohorts
                )
                + " |"
            )

    lines += [
        "",
        "## Zero-hit races: winner vs model top-2 matrix deltas",
        "",
        f"Zero-hit races with a matched winner: **{zero_hit['zero_hit_races']}**. "
        "Positive = the winner beat the model's top 2 on that dimension (signal existed but was outweighed).",
        "",
        "| Dimension | Winner − top2 avg |",
        "|---|---:|",
    ]
    for key, delta in sorted(zero_hit["winner_minus_top2_avg"].items(), key=lambda item: -item[1]):
        lines.append(f"| {key} | {delta:+.2f} |")
    lines.append("")

    report = "\n".join(lines)
    out_md = PROJECT_ROOT / f"{args.report_date} AU Failure Cohorts and Attribution.md"
    out_json = PROJECT_ROOT / "scratch" / "au_failure_cohorts.json"
    out_md.write_text(report, encoding="utf-8")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(
        json.dumps(
            {"report_date": args.report_date, "cohort_table": table,
             "attribution": attribution, "zero_hit": zero_hit},
            ensure_ascii=False, indent=1, default=str),
        encoding="utf-8",
    )
    print(f"Wrote {out_md}")
    print(f"Wrote {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
