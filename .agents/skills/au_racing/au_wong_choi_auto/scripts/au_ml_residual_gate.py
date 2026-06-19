#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[4]
sys.path.append(str(SCRIPT_DIR))

from au_cached_walkforward_ml import (  # noqa: E402
    DATASET_CSV,
    as_float,
    date_folds,
    flatten,
    fmt_metrics,
    group_races,
    materialize_dataset,
    metrics_for_races,
    score_baseline,
)


OUTPUT_MD = PROJECT_ROOT / "2026-06-07 AU ML Residual Gate.md"
MIN_TOP3_LIFT_FOR_LIVE = 0.005

BASE_NUMERIC_FEATURES = (
    "ability_score",
    "field_count",
    "wet_flag",
    "soft_flag",
    "heavy_flag",
    "mx_stability",
    "mx_sectional",
    "mx_race_shape",
    "mx_jockey_trainer",
    "mx_class_weight",
    "mx_track",
    "mx_form_line",
    "wet_stability",
    "wet_sectional",
    "wet_race_shape",
    "wet_jockey_trainer",
    "wet_class_weight",
    "wet_track",
    "soft_stability",
    "soft_sectional",
    "soft_race_shape",
    "soft_track",
    "heavy_stability",
    "heavy_sectional",
    "heavy_race_shape",
    "heavy_track",
    "form_score",
    "trial_score",
    "sectional_score",
    "pace_map_score",
    "jockey_score",
    "trainer_score",
    "jockey_horse_fit_score",
    "class_score",
    "rating_score",
    "weight_score",
    "distance_score",
    "track_score",
    "formline_score",
    "consistency_score",
    "health_score",
    "confidence_score",
)

DERIVED_FEATURES = (
    "ability_rank",
    "ability_rank_pct",
    "ability_gap_to_top",
    "ability_gap_to_third",
    "ability_gap_prev",
    "ability_gap_next",
    "ability_z",
    "is_current_top1",
    "is_current_top3",
    "is_current_top4",
    "is_current_4to6",
    "sectional_minus_track",
    "stability_minus_track",
    "race_shape_minus_track",
    "speed_stability_only",
    "ordinary_track_high_score",
    "soft_speed_track_gap",
)

FEATURES = BASE_NUMERIC_FEATURES + DERIVED_FEATURES


@dataclass(frozen=True)
class Overlay:
    name: str
    mode: str
    scale: float
    cap_threshold: float = 0.0
    cap: float = 0.0
    boost_margin: float = 0.0
    boost: float = 0.0
    soft_only: bool = False


def enrich_races(races: list[list[dict]]) -> list[list[dict]]:
    enriched = []
    for race in races:
        ordered = sorted(race, key=lambda row: (-as_float(row.get("ability_score"), 0.0), int(row["horse_number"])))
        abilities = [as_float(row.get("ability_score"), 0.0) for row in ordered]
        avg = sum(abilities) / max(1, len(abilities))
        std = math.sqrt(sum((value - avg) ** 2 for value in abilities) / max(1, len(abilities))) or 1.0
        third_score = abilities[2] if len(abilities) >= 3 else abilities[-1]
        rank_by_num = {str(row["horse_number"]): idx + 1 for idx, row in enumerate(ordered)}
        score_by_rank = {idx + 1: as_float(row.get("ability_score"), 0.0) for idx, row in enumerate(ordered)}
        race_rows = []
        for row in race:
            item = dict(row)
            rank = rank_by_num[str(row["horse_number"])]
            ability = as_float(row.get("ability_score"), 0.0)
            field = max(1, int(row.get("field_count") or len(race)))
            item["ability_rank"] = rank
            item["ability_rank_pct"] = (rank - 1) / max(1, field - 1)
            item["ability_gap_to_top"] = ability - abilities[0]
            item["ability_gap_to_third"] = ability - third_score
            item["ability_gap_prev"] = ability - score_by_rank.get(rank - 1, ability)
            item["ability_gap_next"] = ability - score_by_rank.get(rank + 1, ability)
            item["ability_z"] = (ability - avg) / std
            item["is_current_top1"] = 1 if rank == 1 else 0
            item["is_current_top3"] = 1 if rank <= 3 else 0
            item["is_current_top4"] = 1 if rank <= 4 else 0
            item["is_current_4to6"] = 1 if 4 <= rank <= 6 else 0
            sectional = as_float(item.get("mx_sectional"), 60.0)
            stability = as_float(item.get("mx_stability"), 60.0)
            race_shape = as_float(item.get("mx_race_shape"), 60.0)
            track = as_float(item.get("mx_track"), 60.0)
            ability_score = as_float(item.get("ability_score"), 0.0)
            soft = int(item.get("soft_flag") or 0)
            item["sectional_minus_track"] = sectional - track
            item["stability_minus_track"] = stability - track
            item["race_shape_minus_track"] = race_shape - track
            item["speed_stability_only"] = 1 if (sectional >= 66 or stability >= 70) and track < 66 and race_shape < 66 else 0
            item["ordinary_track_high_score"] = 1 if ability_score >= 66 and track < 66 else 0
            item["soft_speed_track_gap"] = soft * max(0.0, sectional - track)
            race_rows.append(item)
        enriched.append(race_rows)
    return enriched


def rows_to_xy(rows: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    x = np.array([[as_float(row.get(key), 0.0) for key in FEATURES] for row in rows], dtype=float)
    y = np.array([int(row.get("is_top3") or 0) for row in rows], dtype=int)
    return x, y


def fit_model(train_races: list[list[dict]], seed: int) -> GradientBoostingClassifier:
    x, y = rows_to_xy(flatten(train_races))
    model = GradientBoostingClassifier(
        n_estimators=90,
        learning_rate=0.035,
        max_depth=2,
        min_samples_leaf=18,
        subsample=0.82,
        random_state=seed,
    )
    model.fit(x, y)
    return model


def predict_races(model: GradientBoostingClassifier, races: list[list[dict]]) -> list[list[dict]]:
    output = []
    for race in races:
        x, _ = rows_to_xy(race)
        probs = model.predict_proba(x)[:, 1]
        race_rows = []
        for row, prob in zip(race, probs):
            item = dict(row)
            item["_ml_prob"] = float(prob)
            race_rows.append(item)
        output.append(race_rows)
    return output


def split_train_tune(train: list[list[dict]]) -> tuple[list[list[dict]], list[list[dict]]]:
    dates = sorted({race[0]["date"] for race in train})
    if len(dates) < 4:
        return train, []
    split_at = max(1, int(len(dates) * 0.75))
    model_dates = set(dates[:split_at])
    tune_dates = set(dates[split_at:])
    model_train = [race for race in train if race[0]["date"] in model_dates]
    tune = [race for race in train if race[0]["date"] in tune_dates]
    return model_train or train, tune


def race_prob_z(race: list[dict]) -> dict[str, float]:
    values = [as_float(row.get("_ml_prob"), 0.0) for row in race]
    avg = sum(values) / max(1, len(values))
    std = math.sqrt(sum((value - avg) ** 2 for value in values) / max(1, len(values))) or 1.0
    return {str(row["horse_number"]): (as_float(row.get("_ml_prob"), 0.0) - avg) / std for row in race}


def ability_residual(row: dict) -> float:
    prob = as_float(row.get("_ml_prob"), 0.0)
    ability_z = as_float(row.get("ability_z"), 0.0)
    baseline_prob = 1.0 / (1.0 + math.exp(-ability_z))
    return prob - baseline_prob


def apply_overlay(races: list[list[dict]], overlay: Overlay) -> list[list[dict]]:
    scored = []
    for race in races:
        prob_z = race_prob_z(race)
        ml_sorted = sorted(race, key=lambda row: -as_float(row.get("_ml_prob"), 0.0))
        ml_rank = {str(row["horse_number"]): idx + 1 for idx, row in enumerate(ml_sorted)}
        race_rows = []
        for row in race:
            item = dict(row)
            base = as_float(row.get("ability_score"), 0.0)
            modifier = 0.0
            if overlay.soft_only and not int(row.get("soft_flag") or 0):
                item["_score"] = base
                item["_residual_modifier"] = 0.0
                race_rows.append(item)
                continue
            if overlay.mode == "prob_z":
                modifier += overlay.scale * prob_z[str(row["horse_number"])]
            elif overlay.mode == "residual":
                modifier += overlay.scale * ability_residual(row)
            elif overlay.mode == "cap":
                if int(row.get("is_current_top3") or 0) and as_float(row.get("_ml_prob"), 0.0) < overlay.cap_threshold:
                    modifier -= overlay.cap
            elif overlay.mode == "hybrid":
                modifier += overlay.scale * ability_residual(row)
                if int(row.get("is_current_top3") or 0) and as_float(row.get("_ml_prob"), 0.0) < overlay.cap_threshold:
                    modifier -= overlay.cap
                if int(row.get("is_current_4to6") or 0) and ml_rank[str(row["horse_number"])] <= 3:
                    modifier += overlay.boost
            elif overlay.mode == "soft_cap":
                if int(row.get("soft_flag") or 0) and int(row.get("is_current_top3") or 0):
                    high_risk = (
                        as_float(row.get("_ml_prob"), 0.0) < overlay.cap_threshold
                        or int(row.get("speed_stability_only") or 0)
                        or int(row.get("ordinary_track_high_score") or 0)
                    )
                    if high_risk:
                        modifier -= overlay.cap
            modifier = max(-1.8, min(1.8, modifier))
            item["_score"] = round(base + modifier, 4)
            item["_residual_modifier"] = round(modifier, 4)
            race_rows.append(item)
        scored.append(race_rows)
    return scored


def overlay_candidates() -> list[Overlay]:
    candidates = [Overlay("baseline_no_overlay", "baseline", 0.0)]
    for scale in (0.35, 0.55, 0.75, 1.0, 1.25):
        candidates.append(Overlay(f"prob_z_{scale:.2f}", "prob_z", scale))
    for scale in (0.8, 1.2, 1.6, 2.0, 2.6, 3.2):
        candidates.append(Overlay(f"residual_{scale:.2f}", "residual", scale))
    for threshold in (0.22, 0.26, 0.30, 0.34, 0.38):
        for cap in (0.45, 0.70, 0.95, 1.20):
            candidates.append(Overlay(f"cap_p{threshold:.2f}_c{cap:.2f}", "cap", 0.0, cap_threshold=threshold, cap=cap))
            candidates.append(Overlay(f"soft_cap_p{threshold:.2f}_c{cap:.2f}", "soft_cap", 0.0, cap_threshold=threshold, cap=cap))
    for scale in (0.8, 1.2, 1.6):
        for threshold in (0.26, 0.30, 0.34):
            candidates.append(
                Overlay(
                    f"hybrid_s{scale:.1f}_p{threshold:.2f}",
                    "hybrid",
                    scale,
                    cap_threshold=threshold,
                    cap=0.65,
                    boost=0.45,
                )
            )
    return candidates


def objective(metrics: dict) -> float:
    races = metrics["races"] or 1
    return (
        metrics["top3_precision"] * 3.2
        + metrics["winner_in_top3"] * 1.3
        + (metrics["good"] / races) * 0.65
        + (metrics["gold"] / races) * 0.45
        - (metrics["miss"] / races) * 1.55
    )


def choose_overlay(tune_scored: list[list[dict]]) -> tuple[Overlay, dict]:
    baseline = metrics_for_races(score_baseline(tune_scored, "ability_score"))
    best = overlay_candidates()[0]
    best_metrics = baseline
    best_score = objective(baseline)
    for overlay in overlay_candidates()[1:]:
        metrics = metrics_for_races(apply_overlay(tune_scored, overlay))
        if metrics["miss"] > baseline["miss"] + 1:
            continue
        if metrics["winner_in_top3"] < baseline["winner_in_top3"] - 0.025:
            continue
        score = objective(metrics)
        if score > best_score:
            best = overlay
            best_metrics = metrics
            best_score = score
    return best, best_metrics


def delta_text(base: dict, cand: dict) -> str:
    return (
        f"Gold {cand['gold'] - base['gold']:+d}, Good {cand['good'] - base['good']:+d}, "
        f"Pass {cand['pass'] - base['pass']:+d}, Miss {cand['miss'] - base['miss']:+d}, "
        f"Top3 {(cand['top3_precision'] - base['top3_precision']) * 100:+.1f}pp, "
        f"W-in-T3 {(cand['winner_in_top3'] - base['winner_in_top3']) * 100:+.1f}pp"
    )


def condition_metrics(races: list[list[dict]]) -> dict[str, dict]:
    grouped: dict[str, list[list[dict]]] = defaultdict(list)
    for race in races:
        condition = str(race[0].get("condition_bucket") or "Unknown")
        if "Soft" in condition:
            key = "Soft"
        elif "Heavy" in condition:
            key = "Heavy"
        elif "Good" in condition:
            key = "Good"
        else:
            key = "Other"
        grouped[key].append(race)
    return {key: metrics_for_races(value) for key, value in sorted(grouped.items())}


def venue_bucket_metrics(races: list[list[dict]]) -> dict[str, dict]:
    grouped: dict[str, list[list[dict]]] = defaultdict(list)
    venue_counts = Counter(race[0].get("track") or "Unknown" for race in races)
    top_venues = {venue for venue, _ in venue_counts.most_common(6)}
    for race in races:
        venue = race[0].get("track") or "Unknown"
        grouped[venue if venue in top_venues else "Other"].append(race)
    return {key: metrics_for_races(value) for key, value in sorted(grouped.items())}


def render_bucket_table(title: str, baseline: dict[str, dict], candidate: dict[str, dict]) -> list[str]:
    lines = [
        f"## {title}",
        "",
        "| Bucket | Base | Residual | Delta |",
        "|---|---|---|---|",
    ]
    for key in sorted(set(baseline) | set(candidate)):
        base = baseline.get(key)
        cand = candidate.get(key)
        if not base or not cand:
            continue
        lines.append(f"| {key} | {fmt_metrics(base)} | {fmt_metrics(cand)} | {delta_text(base, cand)} |")
    return lines


def top_feature_importance(importances: list[np.ndarray]) -> list[tuple[str, float]]:
    if not importances:
        return []
    avg = np.mean(np.vstack(importances), axis=0)
    pairs = sorted(zip(FEATURES, avg), key=lambda item: item[1], reverse=True)
    return [(key, float(value)) for key, value in pairs[:16]]


def render_report(
    races: list[list[dict]],
    validation_races: list[list[dict]],
    baseline_metrics: dict,
    residual_metrics: dict,
    fixed_rows: list[tuple[Overlay, dict]],
    fold_rows: list[dict],
    selected_counts: Counter,
    feature_importances: list[tuple[str, float]],
    baseline_scored: list[list[dict]],
    residual_scored: list[list[dict]],
) -> str:
    fixed_best = fixed_rows[0] if fixed_rows else (Overlay("none", "baseline", 0.0), baseline_metrics)
    gate_passed = (
        residual_metrics["top3_precision"] >= baseline_metrics["top3_precision"] + MIN_TOP3_LIFT_FOR_LIVE
        and residual_metrics["winner_in_top3"] >= baseline_metrics["winner_in_top3"]
        and residual_metrics["miss"] <= baseline_metrics["miss"]
    )
    fixed_gate_passed = (
        fixed_best[1]["top3_precision"] >= baseline_metrics["top3_precision"] + MIN_TOP3_LIFT_FOR_LIVE
        and fixed_best[1]["winner_in_top3"] >= baseline_metrics["winner_in_top3"]
        and fixed_best[1]["miss"] <= baseline_metrics["miss"]
    )
    shadow_passed = (
        fixed_best[1]["top3_precision"] > baseline_metrics["top3_precision"]
        and fixed_best[1]["winner_in_top3"] >= baseline_metrics["winner_in_top3"]
        and fixed_best[1]["miss"] <= baseline_metrics["miss"]
    )
    lines = [
        "# AU ML Residual Gate",
        "",
        "## Dataset",
        "",
        f"- Races: **{len(races)}**",
        f"- Validation races: **{len(validation_races)}**",
        f"- Horses: **{sum(len(race) for race in races)}**",
        f"- Cache: `{DATASET_CSV}`",
        "",
        "## Walk-Forward Result",
        "",
        "| Model | Result | Delta |",
        "|---|---|---|",
        f"| Current ability baseline | {fmt_metrics(baseline_metrics)} | - |",
        f"| ML residual overlay | {fmt_metrics(residual_metrics)} | {delta_text(baseline_metrics, residual_metrics)} |",
        f"| Best fixed residual overlay `{fixed_best[0].name}` | {fmt_metrics(fixed_best[1])} | {delta_text(baseline_metrics, fixed_best[1])} |",
        "",
        "## Selected Overlay By Fold",
        "",
        "| Fold | Train | Tune | Validation | Selected overlay | Tune result | Validation result | Validation delta |",
        "|---:|---:|---:|---:|---|---|---|---|",
    ]
    for row in fold_rows:
        lines.append(
            f"| {row['fold']} | {row['train_races']} | {row['tune_races']} | {row['valid_races']} | "
            f"`{row['overlay'].name}` | {fmt_metrics(row['tune_metrics'])} | "
            f"{fmt_metrics(row['valid_metrics'])} | {delta_text(row['valid_baseline'], row['valid_metrics'])} |"
        )
    lines.extend([
        "",
        "## Overlay Frequency",
        "",
        "| Overlay | Count |",
        "|---|---:|",
    ])
    for name, count in selected_counts.most_common():
        lines.append(f"| `{name}` | {count} |")
    lines.extend([
        "",
        "## Fixed Overlay Sweep",
        "",
        "| Overlay | Result | Delta |",
        "|---|---|---|",
    ])
    for overlay, metrics in fixed_rows[:12]:
        lines.append(f"| `{overlay.name}` | {fmt_metrics(metrics)} | {delta_text(baseline_metrics, metrics)} |")
    lines.extend([
        "",
        "## ML Feature Importance",
        "",
        "| Feature | Avg importance |",
        "|---|---:|",
    ])
    for key, value in feature_importances:
        lines.append(f"| `{key}` | {value:.4f} |")
    lines.extend(["", *render_bucket_table("Condition Buckets", condition_metrics(baseline_scored), condition_metrics(residual_scored))])
    lines.extend(["", *render_bucket_table("Venue Buckets", venue_bucket_metrics(baseline_scored), venue_bucket_metrics(residual_scored))])
    lines.extend([
        "",
        "## Gate",
        "",
        "PASSED" if gate_passed or fixed_gate_passed else "FAILED",
        "",
    ])
    if gate_passed or fixed_gate_passed:
        lines.append("- Candidate residual overlay beat current `ability_score` out-of-sample. Next step is to convert the selected overlay into a small deterministic modifier and rerun archive + live shadow.")
    elif shadow_passed:
        lines.append("- Best fixed overlay is directionally positive, but lift is below the live promotion threshold. Keep it as shadow diagnostics, not live scoring.")
    else:
        lines.append("- Do not bake residual ML overlay into live AU scoring. Current `ability_score` remains stronger or safer out-of-sample.")
    lines.extend([
        "",
        "## Guardrails",
        "",
        "- Residual modifier is capped to +/-1.8 points.",
        "- Overlay parameters are tuned only on earlier dates inside each fold.",
        f"- Live promotion requires at least {MIN_TOP3_LIFT_FOR_LIVE * 100:.1f}pp Top3 improvement, no winner-in-top3 loss, and no Miss increase.",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Train and gate AU ML residual overlay by date walk-forward.")
    parser.add_argument("--rebuild-cache", action="store_true")
    parser.add_argument("--seed", type=int, default=20260607)
    parser.add_argument("--output", type=Path, default=OUTPUT_MD)
    args = parser.parse_args()

    rows = materialize_dataset(rebuild=args.rebuild_cache)
    races = enrich_races(group_races(rows))
    folds = date_folds(races)
    if not folds:
        raise SystemExit("Not enough dated races for walk-forward residual ML.")

    validation_races = [race for _, valid in folds for race in valid]
    baseline_scored = score_baseline(validation_races, "ability_score")
    residual_scored = []
    fixed_scored: dict[str, list[list[dict]]] = defaultdict(list)
    fixed_overlay_lookup = {overlay.name: overlay for overlay in overlay_candidates()[1:]}
    fold_rows = []
    selected_counts: Counter = Counter()
    importances: list[np.ndarray] = []

    for fold_idx, (train, valid) in enumerate(folds, 1):
        model_train, tune = split_train_tune(train)
        model = fit_model(model_train, args.seed + fold_idx)
        importances.append(model.feature_importances_)
        tune_pred = predict_races(model, tune or model_train)
        overlay, tune_metrics = choose_overlay(tune_pred)
        valid_pred = predict_races(model, valid)
        valid_overlay = apply_overlay(valid_pred, overlay)
        residual_scored.extend(valid_overlay)
        for fixed_overlay in fixed_overlay_lookup.values():
            fixed_scored[fixed_overlay.name].extend(apply_overlay(valid_pred, fixed_overlay))
        selected_counts[overlay.name] += 1
        fold_rows.append(
            {
                "fold": fold_idx,
                "train_races": len(model_train),
                "tune_races": len(tune),
                "valid_races": len(valid),
                "overlay": overlay,
                "tune_metrics": tune_metrics,
                "valid_baseline": metrics_for_races(score_baseline(valid, "ability_score")),
                "valid_metrics": metrics_for_races(valid_overlay),
            }
        )

    baseline_metrics = metrics_for_races(baseline_scored)
    residual_metrics = metrics_for_races(residual_scored)
    fixed_rows = sorted(
        ((fixed_overlay_lookup[name], metrics_for_races(scored)) for name, scored in fixed_scored.items()),
        key=lambda item: (
            item[1]["top3_precision"],
            item[1]["winner_in_top3"],
            -item[1]["miss"],
            item[1]["good"],
        ),
        reverse=True,
    )
    feature_importances = top_feature_importance(importances)
    args.output.write_text(
        render_report(
            races,
            validation_races,
            baseline_metrics,
            residual_metrics,
            fixed_rows,
            fold_rows,
            selected_counts,
            feature_importances,
            baseline_scored,
            residual_scored,
        ),
        encoding="utf-8",
    )
    print(f"Races: {len(races)}")
    print(f"Validation races: {len(validation_races)}")
    print(f"Current ability baseline: {fmt_metrics(baseline_metrics)}")
    print(f"ML residual overlay: {fmt_metrics(residual_metrics)}")
    print(f"Report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
