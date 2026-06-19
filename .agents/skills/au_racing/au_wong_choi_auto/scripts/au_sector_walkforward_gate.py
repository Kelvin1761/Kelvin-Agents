#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[4]

from au_archive_calibrator import FEATURE_SCORE_KEYS, MATRIX_KEYS
from au_cached_walkforward_ml import (
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

OUTPUT_MD = PROJECT_ROOT / "2026-06-10 AU Sector Walkforward Gate.md"

MATRIX_FEATURES = tuple(f"mx_{key}" for key in MATRIX_KEYS)
STAGE_MODELS = {
    "stage1_all_small_sectors": FEATURE_SCORE_KEYS,
    "stage2_all_7d_matrix": MATRIX_FEATURES,
    "stage1_plus_stage2": FEATURE_SCORE_KEYS + MATRIX_FEATURES,
    "stage4_base_7d_to_ability_overlay": ("ability_score",) + FEATURE_SCORE_KEYS + MATRIX_FEATURES,
}


def score_by_column(races: list[list[dict]], column: str) -> list[list[dict]]:
    return [
        [{**row, "_score": as_float(row.get(column), 60.0)} for row in race]
        for race in races
    ]


def rows_to_xy(rows: list[dict], features: tuple[str, ...]) -> tuple[np.ndarray, np.ndarray]:
    x = np.array([[as_float(row.get(key), 60.0) for key in features] for row in rows], dtype=float)
    y = np.array([int(row.get("is_top3") or 0) for row in rows], dtype=int)
    return x, y


def train_model(train: list[list[dict]], features: tuple[str, ...], seed: int) -> GradientBoostingClassifier:
    x, y = rows_to_xy(flatten(train), features)
    model = GradientBoostingClassifier(
        n_estimators=90,
        learning_rate=0.04,
        max_depth=2,
        min_samples_leaf=16,
        subsample=0.82,
        random_state=seed,
    )
    model.fit(x, y)
    return model


def predict_model(model: GradientBoostingClassifier, valid: list[list[dict]], features: tuple[str, ...]) -> list[list[dict]]:
    scored = []
    for race in valid:
        x, _ = rows_to_xy(race, features)
        probs = model.predict_proba(x)[:, 1]
        scored.append([{**row, "_score": float(prob)} for row, prob in zip(race, probs)])
    return scored


def walkforward_model(races: list[list[dict]], features: tuple[str, ...], seed: int) -> tuple[list[list[dict]], list[dict]]:
    folds = date_folds(races)
    scored: list[list[dict]] = []
    fold_rows = []
    for idx, (train, valid) in enumerate(folds, 1):
        model = train_model(train, features, seed + idx)
        valid_scored = predict_model(model, valid, features)
        scored.extend(valid_scored)
        fold_rows.append(
            {
                "fold": idx,
                "train_races": len(train),
                "valid_races": len(valid),
                "baseline": metrics_for_races(score_baseline(valid, "ability_score")),
                "candidate": metrics_for_races(valid_scored),
            }
        )
    return scored, fold_rows


def delta_text(base: dict, cand: dict) -> str:
    return (
        f"Gold {cand['gold'] - base['gold']:+d}, Good {cand['good'] - base['good']:+d}, "
        f"Pass {cand['pass'] - base['pass']:+d}, Miss {cand['miss'] - base['miss']:+d}, "
        f"Top3 {(cand['top3_precision'] - base['top3_precision']) * 100:+.1f}pp, "
        f"W-in-T3 {(cand['winner_in_top3'] - base['winner_in_top3']) * 100:+.1f}pp"
    )


def gate_passed(base: dict, cand: dict) -> bool:
    return (
        cand["miss"] <= base["miss"]
        and cand["winner_in_top3"] >= base["winner_in_top3"]
        and cand["good"] >= base["good"]
        and cand["pass"] >= base["pass"]
        and (cand["good"] > base["good"] or cand["pass"] > base["pass"])
    )


def render_score_table(title: str, rows: list[tuple[str, dict, dict]]) -> list[str]:
    lines = [
        f"## {title}",
        "",
        "| Candidate | Result | Delta vs ability | Gate |",
        "|---|---|---|---|",
    ]
    for name, base, cand in rows:
        lines.append(
            f"| `{name}` | {fmt_metrics(cand)} | {delta_text(base, cand)} | "
            f"{'PASSED' if gate_passed(base, cand) else 'FAILED'} |"
        )
    return lines


def top_importance(scored_rows: list[tuple[str, list[dict]]], limit: int = 12) -> list[tuple[str, int]]:
    counts = Counter()
    for _, rows in scored_rows:
        for row in rows[:limit]:
            counts[row["name"]] += 1
    return counts.most_common(limit)


def render_report(
    races: list[list[dict]],
    validation_races: list[list[dict]],
    baseline_metrics: dict,
    feature_rows: list[tuple[str, dict, dict]],
    matrix_rows: list[tuple[str, dict, dict]],
    model_rows: list[tuple[str, dict, dict, list[dict]]],
) -> str:
    promoted = [name for name, _, metrics, _ in model_rows if gate_passed(baseline_metrics, metrics)]
    lines = [
        "# AU Sector Walk-Forward Gate",
        "",
        "## Dataset",
        "",
        f"- Races: **{len(races)}**",
        f"- Validation races: **{len(validation_races)}**",
        f"- Horses: **{sum(len(race) for race in races)}**",
        f"- Cache: `{DATASET_CSV}`",
        "",
        "## Baseline",
        "",
        f"- Current `ability_score`: {fmt_metrics(baseline_metrics)}",
        "",
        *render_score_table("Stage 1: Individual Small Sectors", feature_rows),
        "",
        *render_score_table("Stage 2: Individual 7D Matrix Scores", matrix_rows),
        "",
        "## Stage 3 / 4: Walk-Forward ML Candidates",
        "",
        "| Candidate | Result | Delta vs ability | Gate |",
        "|---|---|---|---|",
    ]
    for name, base, metrics, _ in model_rows:
        lines.append(
            f"| `{name}` | {fmt_metrics(metrics)} | {delta_text(base, metrics)} | "
            f"{'PASSED' if gate_passed(base, metrics) else 'FAILED'} |"
        )
    lines.extend(["", "## Fold Detail", "", "| Candidate | Fold | Train | Valid | Result | Delta |", "|---|---:|---:|---:|---|---|"])
    for name, _, _, folds in model_rows:
        for fold in folds:
            lines.append(
                f"| `{name}` | {fold['fold']} | {fold['train_races']} | {fold['valid_races']} | "
                f"{fmt_metrics(fold['candidate'])} | {delta_text(fold['baseline'], fold['candidate'])} |"
            )
    lines.extend(["", "## Promotion Gate", ""])
    if promoted:
        lines.append("PASSED")
        lines.append("")
        lines.append("- Candidate(s) passed diagnostic gate: " + ", ".join(f"`{name}`" for name in promoted))
        lines.append("- Keep these in shadow until full archive recompute also passes before changing live weights.")
    else:
        lines.append("FAILED")
        lines.append("")
        lines.append("- No sector or ML candidate beat the current `ability_score` with flat/lower Miss and no winner-in-top3 loss.")
        lines.append("- Live AU scoring weights should remain unchanged.")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run staged AU sector and 7D walk-forward ML gate.")
    parser.add_argument("--rebuild-cache", action="store_true")
    parser.add_argument("--seed", type=int, default=20260610)
    parser.add_argument("--output", type=Path, default=OUTPUT_MD)
    args = parser.parse_args()

    rows = materialize_dataset(rebuild=args.rebuild_cache)
    races = group_races(rows)
    folds = date_folds(races)
    if not folds:
        raise SystemExit("Not enough dated races for walk-forward sector gate.")

    validation_races = [race for _, valid in folds for race in valid]
    baseline_scored = score_baseline(validation_races, "ability_score")
    baseline_metrics = metrics_for_races(baseline_scored)

    feature_rows = []
    for key in FEATURE_SCORE_KEYS:
        metrics = metrics_for_races(score_by_column(validation_races, key))
        feature_rows.append((key, baseline_metrics, metrics))
    feature_rows.sort(key=lambda row: (row[2]["pass"], row[2]["good"], -row[2]["miss"], row[2]["top3_precision"]), reverse=True)

    matrix_rows = []
    for key in MATRIX_FEATURES:
        metrics = metrics_for_races(score_by_column(validation_races, key))
        matrix_rows.append((key, baseline_metrics, metrics))
    matrix_rows.sort(key=lambda row: (row[2]["pass"], row[2]["good"], -row[2]["miss"], row[2]["top3_precision"]), reverse=True)

    model_rows = []
    for name, features in STAGE_MODELS.items():
        scored, fold_rows = walkforward_model(races, features, args.seed)
        model_rows.append((name, baseline_metrics, metrics_for_races(scored), fold_rows))
    model_rows.sort(key=lambda row: (gate_passed(row[1], row[2]), row[2]["pass"], row[2]["good"], -row[2]["miss"]), reverse=True)

    report = render_report(races, validation_races, baseline_metrics, feature_rows, matrix_rows, model_rows)
    args.output.write_text(report, encoding="utf-8")
    print(f"Races: {len(races)}")
    print(f"Validation races: {len(validation_races)}")
    print(f"Ability baseline: {fmt_metrics(baseline_metrics)}")
    for name, _, metrics, _ in model_rows:
        print(f"{name}: {fmt_metrics(metrics)} | {delta_text(baseline_metrics, metrics)}")
    print(f"Report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
