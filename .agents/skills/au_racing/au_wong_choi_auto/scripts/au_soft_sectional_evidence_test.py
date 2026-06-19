#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[4]
sys.path.append(str(SCRIPT_DIR))
sys.path.append(str(SCRIPT_DIR / "racing_engine"))

from au_archive_calibrator import ARCHIVE_ROOT, normalize_condition_bucket  # noqa: E402
from au_cached_walkforward_ml import (  # noqa: E402
    DATASET_CSV,
    as_float,
    date_folds,
    fmt_metrics,
    group_races,
    load_dataset,
    materialize_dataset,
    metrics_for_races,
    score_baseline,
)
from engine_core import _record_rows  # noqa: E402


OUTPUT_MD = PROJECT_ROOT / "2026-06-07 AU Soft Sectional Evidence Test.md"

QUALITY_SCORE = {
    "極快": 2.0,
    "較快": 1.0,
    "快": 1.0,
    "一般": 0.0,
    "較慢": -1.0,
    "慢": -1.0,
    "極慢": -2.0,
}


def is_soft_race(race: list[dict]) -> bool:
    return normalize_condition_bucket(race[0].get("condition_bucket", "")) == "Soft"


def logic_path_for(row: dict) -> Path:
    return ARCHIVE_ROOT / str(row["meeting"]) / f"Race_{int(row['race'])}_Logic.json"


def horse_logic_lookup(logic: dict) -> dict[int, dict]:
    output = {}
    for horse_no, horse in (logic.get("horses") or {}).items():
        try:
            output[int(horse_no)] = horse
        except (TypeError, ValueError):
            continue
    return output


def parse_int(value, default=0) -> int:
    match = re.search(r"-?\d+", str(value or ""))
    return int(match.group(0)) if match else default


def quality_value(text: str) -> float | None:
    for key, value in QUALITY_SCORE.items():
        if key in str(text or ""):
            return value
    return None


def is_soft_entry(cols: list[str]) -> bool:
    going = str(cols[5] if len(cols) > 5 else "")
    if "Soft" in going or "軟" in going:
        return True
    number = parse_int(going, -1)
    return 5 <= number <= 7


def extract_soft_sectional_evidence(horse: dict) -> dict:
    facts = str((horse.get("_data") or {}).get("facts_section") or "")
    official_soft = []
    for cols in _record_rows(facts):
        if len(cols) < 14 or "試閘" in cols[1]:
            continue
        if not is_soft_entry(cols):
            continue
        quality = quality_value(cols[11])
        official_soft.append(
            {
                "pi": parse_int(cols[10], 0),
                "quality": quality,
                "quality_text": cols[11],
                "l600_rt": cols[13],
                "placing": cols[7],
            }
        )
    if not official_soft:
        return {
            "soft_runs": 0,
            "quality_samples": 0,
            "avg_quality": 0.0,
            "avg_pi": 0.0,
            "positive_quality_runs": 0,
            "negative_quality_runs": 0,
        }
    quality_values = [row["quality"] for row in official_soft if row["quality"] is not None]
    return {
        "soft_runs": len(official_soft),
        "quality_samples": len(quality_values),
        "avg_quality": sum(quality_values) / len(quality_values) if quality_values else 0.0,
        "avg_pi": sum(row["pi"] for row in official_soft) / len(official_soft),
        "positive_quality_runs": sum(1 for value in quality_values if value > 0),
        "negative_quality_runs": sum(1 for value in quality_values if value < 0),
    }


def attach_evidence(races: list[list[dict]]) -> list[list[dict]]:
    logic_cache: dict[Path, dict] = {}
    output = []
    for race in races:
        scored_race = []
        for row in race:
            item = dict(row)
            item["_soft_sectional"] = {
                "soft_runs": 0,
                "quality_samples": 0,
                "avg_quality": 0.0,
                "avg_pi": 0.0,
                "positive_quality_runs": 0,
                "negative_quality_runs": 0,
            }
            if is_soft_race(race):
                logic_path = logic_path_for(row)
                if logic_path not in logic_cache:
                    logic_cache[logic_path] = json.loads(logic_path.read_text(encoding="utf-8"))
                horse = horse_logic_lookup(logic_cache[logic_path]).get(int(row["horse_number"]))
                if horse:
                    item["_soft_sectional"] = extract_soft_sectional_evidence(horse)
            scored_race.append(item)
        output.append(scored_race)
    return output


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def modifier(row: dict, variant: str) -> float:
    evidence = row.get("_soft_sectional") or {}
    runs = int(evidence.get("soft_runs") or 0)
    if runs <= 0:
        return 0.0
    avg_quality = as_float(evidence.get("avg_quality"), 0.0)
    avg_pi = as_float(evidence.get("avg_pi"), 0.0)
    if variant == "quality_only":
        return clamp(avg_quality * 0.45, -0.9, 0.9)
    if variant == "pi_only":
        return clamp(avg_pi * 0.20, -0.9, 0.9)
    if variant == "quality_pi_blend":
        return clamp(avg_quality * 0.35 + avg_pi * 0.12, -1.0, 1.0)
    if variant == "positive_only":
        return 0.6 if int(evidence.get("positive_quality_runs") or 0) > 0 else 0.0
    return 0.0


def apply_variant(races: list[list[dict]], variant: str) -> list[list[dict]]:
    output = []
    for race in races:
        scored_race = []
        for row in race:
            item = dict(row)
            item["_score"] = as_float(row.get("ability_score"), 0.0) + (modifier(row, variant) if is_soft_race(race) else 0.0)
            scored_race.append(item)
        output.append(scored_race)
    return output


def filter_soft(races: list[list[dict]]) -> list[list[dict]]:
    return [race for race in races if is_soft_race(race)]


def evidence_summary(races: list[list[dict]]) -> dict:
    soft_races = filter_soft(races)
    horses = [row for race in soft_races for row in race]
    with_soft = [row for row in horses if int((row.get("_soft_sectional") or {}).get("soft_runs") or 0) > 0]
    top3 = [row for row in with_soft if int(row.get("actual_pos") or 99) <= 3]
    others = [row for row in with_soft if int(row.get("actual_pos") or 99) > 3]

    def avg(rows, key):
        vals = [as_float((row.get("_soft_sectional") or {}).get(key), 0.0) for row in rows]
        return sum(vals) / len(vals) if vals else 0.0

    return {
        "soft_races": len(soft_races),
        "horses": len(horses),
        "with_soft_runs": len(with_soft),
        "coverage": len(with_soft) / len(horses) if horses else 0.0,
        "top3_avg_quality": avg(top3, "avg_quality"),
        "others_avg_quality": avg(others, "avg_quality"),
        "top3_avg_pi": avg(top3, "avg_pi"),
        "others_avg_pi": avg(others, "avg_pi"),
    }


def delta(base: dict, candidate: dict) -> str:
    return (
        f"Gold {candidate['gold'] - base['gold']:+d}, Good {candidate['good'] - base['good']:+d}, "
        f"Pass {candidate['pass'] - base['pass']:+d}, Miss {candidate['miss'] - base['miss']:+d}, "
        f"Top3 {(candidate['top3_precision'] - base['top3_precision']) * 100:+.1f}pp, "
        f"W-in-T3 {(candidate['winner_in_top3'] - base['winner_in_top3']) * 100:+.1f}pp"
    )


def render_report(races: list[list[dict]], results: list[dict], summary: dict) -> str:
    baseline = next(row for row in results if row["name"] == "baseline")
    ranked = sorted(
        [row for row in results if row["name"] != "baseline"],
        key=lambda row: (
            row["soft"]["top3_precision"] - baseline["soft"]["top3_precision"],
            -(row["soft"]["miss"] - baseline["soft"]["miss"]),
            row["soft"]["winner_in_top3"] - baseline["soft"]["winner_in_top3"],
        ),
        reverse=True,
    )
    passed = [
        row
        for row in ranked
        if row["soft"]["top3_precision"] > baseline["soft"]["top3_precision"]
        and row["soft"]["miss"] <= baseline["soft"]["miss"]
        and row["overall"]["miss"] <= baseline["overall"]["miss"]
    ]
    lines = [
        "# AU Soft Sectional Evidence Test",
        "",
        "## Dataset",
        "",
        f"- Soft validation races: **{summary['soft_races']}**",
        f"- Soft runners: **{summary['horses']}**",
        f"- Runners with prior Soft runs: **{summary['with_soft_runs']}** ({summary['coverage'] * 100:.1f}%)",
        f"- Cache: `{DATASET_CSV}`",
        "",
        "## Evidence Signal",
        "",
        "| Signal | Actual Top3 | Others | Lift |",
        "|---|---:|---:|---:|",
        f"| Avg Soft sectional quality | {summary['top3_avg_quality']:.3f} | {summary['others_avg_quality']:.3f} | {summary['top3_avg_quality'] - summary['others_avg_quality']:+.3f} |",
        f"| Avg Soft PI | {summary['top3_avg_pi']:.3f} | {summary['others_avg_pi']:.3f} | {summary['top3_avg_pi'] - summary['others_avg_pi']:+.3f} |",
        "",
        "## Variant Results",
        "",
        "| Variant | Soft Result | Soft Delta | Overall Delta |",
        "|---|---|---|---|",
        f"| baseline | {fmt_metrics(baseline['soft'])} | - | - |",
    ]
    for row in ranked:
        lines.append(f"| `{row['name']}` | {fmt_metrics(row['soft'])} | {delta(baseline['soft'], row['soft'])} | {delta(baseline['overall'], row['overall'])} |")
    lines.extend([
        "",
        "## Gate",
        "",
        "PASSED" if passed else "FAILED",
        "",
    ])
    if passed:
        lines.append("- Candidate(s): " + ", ".join(f"`{row['name']}`" for row in passed))
    else:
        lines.append("- No Soft sectional modifier is clean enough to bake.")
    lines.extend([
        "",
        "## Recommendation",
        "",
        "- Keep the baked Soft race-shape modifier as the only live Soft adjustment for now.",
        "- Do not add Soft sectional speed until evidence coverage and out-of-sample lift are stronger.",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Test prior Soft-run sectional evidence as a simple AU modifier.")
    parser.add_argument("--rebuild-cache", action="store_true")
    parser.add_argument("--output", type=Path, default=OUTPUT_MD)
    args = parser.parse_args()

    rows = materialize_dataset(rebuild=args.rebuild_cache)
    races = group_races(rows)
    folds = date_folds(races)
    validation_races = [race for _, valid in folds for race in valid]
    validation_races = attach_evidence(validation_races)
    baseline_scored = score_baseline(validation_races, "ability_score")
    results = [{"name": "baseline", "overall": metrics_for_races(baseline_scored), "soft": metrics_for_races(filter_soft(baseline_scored))}]
    for variant in ("quality_only", "pi_only", "quality_pi_blend", "positive_only"):
        scored = apply_variant(validation_races, variant)
        results.append({"name": variant, "overall": metrics_for_races(scored), "soft": metrics_for_races(filter_soft(scored))})
    args.output.write_text(render_report(validation_races, results, evidence_summary(validation_races)), encoding="utf-8")
    print(f"Report: {args.output}")
    for row in results:
        print(f"{row['name']}: {fmt_metrics(row['soft'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
