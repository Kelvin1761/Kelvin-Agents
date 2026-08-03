#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[4]
sys.path.append(str(SCRIPT_DIR))

from au_archive_calibrator import normalize_condition_bucket  # noqa: E402
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


OUTPUT_MD = PROJECT_ROOT / "2026-06-07 AU Soft Track Simplification Test.md"

MATRIX_KEYS = ("mx_track", "mx_stability", "mx_sectional", "mx_race_shape")
PROMOTION_CANDIDATES = ("race_shape_plus", "simple_soft_guard")

VARIANTS: dict[str, dict[str, float]] = {
    "baseline": {},
    "track_plus": {"mx_track": 1.0},
    "track_minus": {"mx_track": -1.0},
    "stability_plus": {"mx_stability": 1.0},
    "stability_minus": {"mx_stability": -1.0},
    "sectional_plus": {"mx_sectional": 1.0},
    "sectional_minus": {"mx_sectional": -1.0},
    "race_shape_plus": {"mx_race_shape": 1.0},
    "race_shape_minus": {"mx_race_shape": -1.0},
    "track_stability_plus": {"mx_track": 0.8, "mx_stability": 0.8},
    "track_plus_sectional_minus": {"mx_track": 1.0, "mx_sectional": -0.8},
    "stability_plus_shape_minus": {"mx_stability": 1.0, "mx_race_shape": -0.8},
    "simple_soft_guard": {"mx_track": 0.8, "mx_stability": 0.8, "mx_sectional": -0.5, "mx_race_shape": -0.5},
}


def centered(score) -> float:
    return (as_float(score, 60.0) - 60.0) / 10.0


def is_soft_race(race: list[dict]) -> bool:
    return normalize_condition_bucket(race[0].get("condition_bucket", "")) == "Soft"


def variant_score(row: dict, weights: dict[str, float]) -> float:
    score = as_float(row.get("ability_score"), 0.0)
    for key, weight in weights.items():
        score += weight * centered(row.get(key, 60.0))
    return score


def apply_variant(races: list[list[dict]], weights: dict[str, float]) -> list[list[dict]]:
    scored = []
    for race in races:
        soft = is_soft_race(race)
        scored_race = []
        for row in race:
            item = dict(row)
            item["_score"] = variant_score(row, weights) if soft else as_float(row.get("ability_score"), 0.0)
            scored_race.append(item)
        scored.append(scored_race)
    return scored


def filter_condition(races: list[list[dict]], condition: str) -> list[list[dict]]:
    return [race for race in races if normalize_condition_bucket(race[0].get("condition_bucket", "")) == condition]


def field_bucket(race: list[dict]) -> str:
    count = len(race)
    if count <= 8:
        return "Field <=8"
    if count <= 12:
        return "Field 9-12"
    return "Field 13+"


def venue_bucket(race: list[dict]) -> str:
    track = str(race[0].get("track") or "Unknown").strip()
    return track if track in {"Randwick", "Flemington"} else "Other"


def date_fold_bucket(race: list[dict]) -> str:
    date = str(race[0].get("date") or "")
    if date < "2026-03-01":
        return "early"
    if date < "2026-05-01":
        return "mid"
    return "late"


def bucket_metrics(races: list[list[dict]], bucket_fn) -> dict[str, dict]:
    grouped: dict[str, list[list[dict]]] = defaultdict(list)
    for race in races:
        grouped[bucket_fn(race)].append(race)
    return {key: metrics_for_races(value) for key, value in sorted(grouped.items())}


def bucket_delta_rows(base_races: list[list[dict]], candidate_races: list[list[dict]], bucket_fn) -> list[dict]:
    base_by_id = {(race[0]["meeting"], race[0]["race"]): race for race in base_races}
    candidate_by_id = {(race[0]["meeting"], race[0]["race"]): race for race in candidate_races}
    grouped_base: dict[str, list[list[dict]]] = defaultdict(list)
    grouped_candidate: dict[str, list[list[dict]]] = defaultdict(list)
    for race_id, base_race in base_by_id.items():
        candidate_race = candidate_by_id.get(race_id)
        if not candidate_race:
            continue
        bucket = bucket_fn(base_race)
        grouped_base[bucket].append(base_race)
        grouped_candidate[bucket].append(candidate_race)
    rows = []
    for bucket in sorted(grouped_base):
        base = metrics_for_races(grouped_base[bucket])
        candidate = metrics_for_races(grouped_candidate[bucket])
        rows.append(
            {
                "bucket": bucket,
                "base": base,
                "candidate": candidate,
                "top3_delta": candidate["top3_precision"] - base["top3_precision"],
                "winner_delta": candidate["winner_in_top3"] - base["winner_in_top3"],
                "miss_delta": candidate["miss"] - base["miss"],
                "pass_delta": candidate["pass"] - base["pass"],
            }
        )
    return rows


def gate_candidate(base_soft: dict, base_overall: dict, candidate: dict) -> tuple[str, list[str]]:
    soft = candidate["soft"]
    overall = candidate["overall"]
    bucket_rows = candidate["bucket_rows"]
    reasons = []
    if soft["top3_precision"] <= base_soft["top3_precision"]:
        reasons.append("Soft Top3 precision did not improve")
    if soft["miss"] > base_soft["miss"]:
        reasons.append("Soft Miss increased")
    if overall["miss"] > base_overall["miss"]:
        reasons.append("Overall Miss increased")
    positive_buckets = sum(1 for row in bucket_rows if row["top3_delta"] > 0 and row["miss_delta"] <= 0)
    negative_buckets = sum(1 for row in bucket_rows if row["top3_delta"] < 0 or row["miss_delta"] > 0)
    if positive_buckets < 2:
        reasons.append("Fewer than two positive Soft buckets")
    if negative_buckets > positive_buckets:
        reasons.append("Negative Soft buckets exceed positives")
    return ("PASSED" if not reasons else "FAILED", reasons)


def actual_top3_factor_lift(races: list[list[dict]]) -> list[dict]:
    rows = []
    soft_races = filter_condition(races, "Soft")
    for key in MATRIX_KEYS:
        top3_values = []
        other_values = []
        for race in soft_races:
            for row in race:
                target = top3_values if int(row.get("actual_pos") or 99) <= 3 else other_values
                target.append(as_float(row.get(key), 60.0))
        top3_avg = sum(top3_values) / len(top3_values) if top3_values else 0.0
        other_avg = sum(other_values) / len(other_values) if other_values else 0.0
        rows.append(
            {
                "factor": key,
                "top3_avg": top3_avg,
                "other_avg": other_avg,
                "lift": top3_avg - other_avg,
            }
        )
    return sorted(rows, key=lambda row: abs(row["lift"]), reverse=True)


def delta(base: dict, candidate: dict) -> str:
    return (
        f"Gold {candidate['gold'] - base['gold']:+d}, "
        f"Good {candidate['good'] - base['good']:+d}, "
        f"Pass {candidate['pass'] - base['pass']:+d}, "
        f"Miss {candidate['miss'] - base['miss']:+d}, "
        f"Top3 {(candidate['top3_precision'] - base['top3_precision']) * 100:+.1f}pp, "
        f"W-in-T3 {(candidate['winner_in_top3'] - base['winner_in_top3']) * 100:+.1f}pp"
    )


def render_bucket_section(candidate: dict) -> list[str]:
    lines = [
        f"## Bucket Gate: {candidate['name']}",
        "",
        f"- Gate: **{candidate['gate']}**",
    ]
    if candidate["gate_reasons"]:
        lines.append(f"- Reasons: {'; '.join(candidate['gate_reasons'])}")
    lines.extend([
        "",
        "| Bucket | Base | Candidate | Delta |",
        "|---|---|---|---|",
    ])
    for row in candidate["bucket_rows"]:
        lines.append(
            f"| {row['bucket']} | {fmt_metrics(row['base'])} | {fmt_metrics(row['candidate'])} | "
            f"Top3 {row['top3_delta'] * 100:+.1f}pp / W-in-T3 {row['winner_delta'] * 100:+.1f}pp / "
            f"Miss {row['miss_delta']:+d} / Pass {row['pass_delta']:+d} |"
        )
    return lines


def render_report(validation_races: list[list[dict]], rows: list[dict], lifts: list[dict]) -> str:
    condition_counts = Counter(normalize_condition_bucket(race[0].get("condition_bucket", "")) for race in validation_races)
    soft_base = next(row for row in rows if row["name"] == "baseline")["soft"]
    overall_base = next(row for row in rows if row["name"] == "baseline")["overall"]
    ranked = sorted(
        [row for row in rows if row["name"] != "baseline"],
        key=lambda row: (
            row["soft"]["top3_precision"] - soft_base["top3_precision"],
            row["soft"]["winner_in_top3"] - soft_base["winner_in_top3"],
            -(row["soft"]["miss"] - soft_base["miss"]),
            row["overall"]["top3_precision"] - overall_base["top3_precision"],
        ),
        reverse=True,
    )
    best = ranked[0] if ranked else None
    simple_gate_passed = bool(
        best
        and best["soft"]["top3_precision"] > soft_base["top3_precision"]
        and best["soft"]["winner_in_top3"] >= soft_base["winner_in_top3"]
        and best["overall"]["miss"] <= overall_base["miss"]
    )
    bucket_gate_passed = any(row.get("gate") == "PASSED" for row in rows if row["name"] in PROMOTION_CANDIDATES)
    lines = [
        "# AU Soft Track Simplification Test",
        "",
        "## Dataset",
        "",
        f"- Validation races: **{len(validation_races)}**",
        f"- Conditions: {', '.join(f'{key} {value}' for key, value in condition_counts.most_common())}",
        f"- Cache: `{DATASET_CSV}`",
        "",
        "## Soft Factor Signal",
        "",
        "| Factor | Actual Top3 Avg | Others Avg | Lift | Read |",
        "|---|---:|---:|---:|---|",
    ]
    for row in lifts:
        read = "signal" if abs(row["lift"]) >= 1.0 else "weak/noisy"
        lines.append(f"| `{row['factor']}` | {row['top3_avg']:.2f} | {row['other_avg']:.2f} | {row['lift']:+.2f} | {read} |")

    lines.extend([
        "",
        "## Variant Results",
        "",
        "| Variant | Soft Result | Soft Delta | Overall Delta |",
        "|---|---|---|---|",
        f"| baseline | {fmt_metrics(soft_base)} | - | - |",
    ])
    for row in ranked:
        lines.append(
            f"| `{row['name']}` | {fmt_metrics(row['soft'])} | {delta(soft_base, row['soft'])} | {delta(overall_base, row['overall'])} |"
        )

    lines.extend([
        "",
        "## Gate",
        "",
        "SHADOW PASSED" if bucket_gate_passed else ("PASSED" if simple_gate_passed else "FAILED"),
        "",
    ])
    if bucket_gate_passed:
        passed_names = ", ".join(f"`{row['name']}`" for row in rows if row["name"] in PROMOTION_CANDIDATES and row.get("gate") == "PASSED")
        lines.append(f"- Bucket gate passed for {passed_names}; keep as shadow candidate before live bake.")
    elif simple_gate_passed:
        lines.append(f"- Candidate `{best['name']}` improved Soft without worsening overall Miss.")
    else:
        lines.append("- No simple Soft modifier is safe to promote yet.")
    for row in rows:
        if row["name"] in PROMOTION_CANDIDATES:
            lines.extend(["", *render_bucket_section(row)])
    lines.extend([
        "",
        "## Recommendation",
        "",
        "- Keep live `ability_score` ranking unchanged.",
        "- Do not create an 8D matrix for Soft yet.",
        "- Current simple test treats `race_shape` and `sectional` as possible Soft noise candidates; only promote if repeated walk-forward stays positive.",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Test simple Soft-track AU modifiers against cached walk-forward validation races.")
    parser.add_argument("--rebuild-cache", action="store_true")
    parser.add_argument("--output", type=Path, default=OUTPUT_MD)
    args = parser.parse_args()

    rows = materialize_dataset(rebuild=args.rebuild_cache)
    races = group_races(rows)
    folds = date_folds(races)
    validation_races = [race for _, valid in folds for race in valid]
    if not validation_races:
        raise SystemExit("No validation races available.")

    results = []
    baseline_scored = score_baseline(validation_races, "ability_score")
    baseline_soft = filter_condition(baseline_scored, "Soft")
    for name, weights in VARIANTS.items():
        scored = baseline_scored if name == "baseline" else apply_variant(validation_races, weights)
        soft_scored = filter_condition(scored, "Soft")
        row = {
            "name": name,
            "overall": metrics_for_races(scored),
            "soft": metrics_for_races(soft_scored),
            "bucket_rows": [],
            "gate": "N/A",
            "gate_reasons": [],
        }
        if name in PROMOTION_CANDIDATES:
            bucket_rows = []
            for label, fn in (("venue", venue_bucket), ("field", field_bucket), ("date", date_fold_bucket)):
                for bucket_row in bucket_delta_rows(baseline_soft, soft_scored, fn):
                    bucket_rows.append({**bucket_row, "bucket": f"{label}:{bucket_row['bucket']}"})
            row["bucket_rows"] = bucket_rows
            row["gate"], row["gate_reasons"] = gate_candidate(
                metrics_for_races(baseline_soft),
                metrics_for_races(baseline_scored),
                row,
            )
        results.append(row)

    report = render_report(validation_races, results, actual_top3_factor_lift(validation_races))
    args.output.write_text(report, encoding="utf-8")
    baseline = next(row for row in results if row["name"] == "baseline")
    print(f"Validation races: {len(validation_races)}")
    print(f"Soft baseline: {fmt_metrics(baseline['soft'])}")
    for row in sorted(results, key=lambda item: item["soft"]["top3_precision"], reverse=True)[:5]:
        print(f"{row['name']}: {fmt_metrics(row['soft'])}")
    print(f"Report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
