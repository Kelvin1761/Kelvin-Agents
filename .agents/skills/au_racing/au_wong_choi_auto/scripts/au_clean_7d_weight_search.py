#!/usr/bin/env python3
from __future__ import annotations

import random
import re
import sys
import argparse
from collections import Counter
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.append(str(SCRIPT_DIR / "racing_engine"))

from au_archive_calibrator import (  # noqa: E402
    ARCHIVE_ROOT,
    HISTORICAL_RESULTS_CSV,
    MATRIX_KEYS,
    iter_logic_rows,
    load_historical_results,
)
from scoring import MATRIX_WEIGHTS  # noqa: E402


OUTPUT_MD = ARCHIVE_ROOT / "AU_Clean_7D_Weight_Search.md"
SEED = 20260612
ITERATIONS_PER_FOLD = 1200
TOP_KEEP = 20


def parse_date(meeting: str) -> str:
    match = re.search(r"(\d{4}-\d{2}-\d{2})", str(meeting or ""))
    return match.group(1) if match else ""


def normalize(weights: dict[str, float]) -> dict[str, float]:
    clean = {key: max(0.0, float(weights.get(key, 0.0))) for key in MATRIX_KEYS}
    total = sum(clean.values()) or 1.0
    return {key: clean[key] / total for key in MATRIX_KEYS}


def score(row: dict, weights: dict[str, float]) -> float:
    matrix = row.get("matrix_scores") or {}
    return sum(float(matrix.get(key, 60.0) or 60.0) * weights.get(key, 0.0) for key in MATRIX_KEYS)


def load_races() -> list[list[dict]]:
    historical = load_historical_results(HISTORICAL_RESULTS_CSV)
    races = []
    for race_rows in iter_logic_rows(ARCHIVE_ROOT, historical):
        if sum(1 for row in race_rows if int(row["actual_pos"]) <= 3) < 3:
            continue
        rows = []
        for row in race_rows:
            item = dict(row)
            item["date"] = parse_date(item.get("meeting", ""))
            rows.append(item)
        if rows and rows[0]["date"]:
            races.append(rows)
    return sorted(races, key=lambda race: (race[0]["date"], race[0].get("meeting", ""), int(race[0].get("race") or 0)))


def date_folds(races: list[list[dict]], folds: int = 5, min_train_ratio: float = 0.50) -> list[tuple[list[list[dict]], list[list[dict]]]]:
    dates = sorted({race[0]["date"] for race in races if race[0]["date"]})
    start = max(1, int(len(dates) * min_train_ratio))
    valid_dates = dates[start:]
    fold_size = max(1, (len(valid_dates) + folds - 1) // folds)
    output = []
    for idx in range(0, len(valid_dates), fold_size):
        fold_dates = set(valid_dates[idx: idx + fold_size])
        first_valid = min(fold_dates)
        train = [race for race in races if race[0]["date"] < first_valid]
        valid = [race for race in races if race[0]["date"] in fold_dates]
        if train and valid:
            output.append((train, valid))
    return output


def metrics(races: list[list[dict]], weights: dict[str, float]) -> dict:
    bucket = Counter()
    for race in races:
        ranked = sorted(race, key=lambda row: (-score(row, weights), int(row["horse_number"])))
        top3 = ranked[:3]
        top5 = ranked[:5]
        hits = sum(1 for row in top3 if int(row["actual_pos"]) <= 3)
        top2_hits = sum(1 for row in ranked[:2] if int(row["actual_pos"]) <= 3)
        bucket["races"] += 1
        bucket[f"{hits}hit"] += 1
        bucket["top3_places"] += hits
        bucket["top3_slots"] += len(top3)
        bucket["winner_top3"] += 1 if any(int(row["actual_pos"]) == 1 for row in top3) else 0
        bucket["winner_top5"] += 1 if any(int(row["actual_pos"]) == 1 for row in top5) else 0
        bucket["champion"] += 1 if ranked and int(ranked[0]["actual_pos"]) == 1 else 0
        bucket["gold"] += 1 if hits == 3 else 0
        bucket["good"] += 1 if top2_hits == 2 else 0
        bucket["pass"] += 1 if hits >= 2 else 0
    races_n = bucket["races"] or 1
    slots = bucket["top3_slots"] or 1
    return {
        "races": bucket["races"],
        "champion": bucket["champion"],
        "gold": bucket["gold"],
        "good": bucket["good"],
        "pass": bucket["pass"],
        "winner_top3": bucket["winner_top3"],
        "winner_top5": bucket["winner_top5"],
        "top3_places": bucket["top3_places"],
        "top3_precision": bucket["top3_places"] / slots,
        "0hit": bucket["0hit"],
        "1hit": bucket["1hit"],
        "2hit": bucket["2hit"],
        "3hit": bucket["3hit"],
        "winner_top3_rate": bucket["winner_top3"] / races_n,
        "winner_top5_rate": bucket["winner_top5"] / races_n,
    }


def objective(item: dict) -> float:
    races = item["races"] or 1
    return (
        (item["pass"] / races) * 3.2
        + (item["good"] / races) * 1.5
        + (item["gold"] / races) * 0.45
        + item["top3_precision"] * 1.8
        + item["winner_top5_rate"] * 0.8
        - (item["0hit"] / races) * 2.4
    )


def random_near_current(rng: random.Random, spread: float = 0.075) -> dict[str, float]:
    return normalize({key: MATRIX_WEIGHTS.get(key, 0.0) + rng.uniform(-spread, spread) for key in MATRIX_KEYS})


def random_simplex(rng: random.Random) -> dict[str, float]:
    values = {key: rng.gammavariate(1.25, 1.0) for key in MATRIX_KEYS}
    return normalize(values)


def candidate_weights(rng: random.Random, iterations: int) -> list[dict[str, float]]:
    candidates = [
        normalize(MATRIX_WEIGHTS),
        normalize({key: 1.0 for key in MATRIX_KEYS}),
        normalize({
            "stability": 0.30,
            "sectional": 0.12,
            "race_shape": 0.22,
            "jockey_trainer": 0.22,
            "class_weight": 0.06,
            "track": 0.08,
            "form_line": 0.00,
        }),
        normalize({
            "stability": 0.28,
            "sectional": 0.12,
            "race_shape": 0.24,
            "jockey_trainer": 0.21,
            "class_weight": 0.05,
            "track": 0.08,
            "form_line": 0.02,
        }),
    ]
    for _ in range(iterations):
        if rng.random() < 0.78:
            candidates.append(random_near_current(rng))
        else:
            candidates.append(random_simplex(rng))
    return candidates


def train_fold(train: list[list[dict]], rng: random.Random, iterations: int) -> list[tuple[float, dict[str, float], dict]]:
    baseline = metrics(train, normalize(MATRIX_WEIGHTS))
    kept = []
    for weights in candidate_weights(rng, iterations):
        item = metrics(train, weights)
        if item["0hit"] > baseline["0hit"] + 1:
            continue
        if item["pass"] < baseline["pass"] - 1:
            continue
        score_value = objective(item)
        kept.append((score_value, weights, item))
        kept.sort(key=lambda row: row[0], reverse=True)
        kept = kept[:TOP_KEEP]
    return kept


def delta(base: dict, cand: dict) -> dict:
    return {
        "gold": cand["gold"] - base["gold"],
        "good": cand["good"] - base["good"],
        "pass": cand["pass"] - base["pass"],
        "0hit": cand["0hit"] - base["0hit"],
        "1hit": cand["1hit"] - base["1hit"],
        "top3_places": cand["top3_places"] - base["top3_places"],
        "winner_top5": cand["winner_top5"] - base["winner_top5"],
        "top3_precision_pp": (cand["top3_precision"] - base["top3_precision"]) * 100,
    }


def fmt_metrics(item: dict) -> str:
    races = item["races"] or 1
    return (
        f"Gold {item['gold']} ({item['gold'] / races * 100:.1f}%) / "
        f"Good {item['good']} ({item['good'] / races * 100:.1f}%) / "
        f"Pass {item['pass']} ({item['pass'] / races * 100:.1f}%) / "
        f"0H {item['0hit']} / 1H {item['1hit']} / "
        f"Top3 {item['top3_precision'] * 100:.1f}% / WTop5 {item['winner_top5'] / races * 100:.1f}%"
    )


def fmt_delta(item: dict) -> str:
    return (
        f"Gold {item['gold']:+d}, Good {item['good']:+d}, Pass {item['pass']:+d}, "
        f"0H {item['0hit']:+d}, 1H {item['1hit']:+d}, "
        f"Top3Places {item['top3_places']:+d}, WTop5 {item['winner_top5']:+d}, "
        f"Top3 {item['top3_precision_pp']:+.1f}pp"
    )


def average_weights(rows: list[dict[str, float]]) -> dict[str, float]:
    if not rows:
        return normalize(MATRIX_WEIGHTS)
    return normalize({key: sum(row.get(key, 0.0) for row in rows) / len(rows) for key in MATRIX_KEYS})


def weight_text(weights: dict[str, float]) -> str:
    return ", ".join(f"{key} {weights[key] * 100:.1f}%" for key in MATRIX_KEYS)


def passes_gate(base: dict, cand: dict) -> bool:
    return (
        cand["0hit"] <= base["0hit"]
        and cand["pass"] >= base["pass"]
        and cand["winner_top5"] >= base["winner_top5"]
        and cand["top3_places"] >= base["top3_places"]
        and cand["gold"] >= base["gold"] - 2
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Walk-forward search for clean AU 7D matrix weights.")
    parser.add_argument("--iterations", type=int, default=ITERATIONS_PER_FOLD)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--output", type=Path, default=OUTPUT_MD)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    races = load_races()
    folds = date_folds(races)
    if not folds:
        raise SystemExit("Not enough dated races for walk-forward folds.")

    current = normalize(MATRIX_WEIGHTS)
    validation_races = [race for _, valid in folds for race in valid]
    validation_base = metrics(validation_races, current)
    full_base = metrics(races, current)

    fold_rows = []
    chosen_weights = []
    scored_validation = []
    for fold_idx, (train, valid) in enumerate(folds, 1):
        candidates = train_fold(train, rng, args.iterations)
        valid_base = metrics(valid, current)
        if candidates:
            train_score, weights, train_metrics = candidates[0]
            valid_metrics = metrics(valid, weights)
            best = {
                "weights": weights,
                "train_metrics": train_metrics,
                "valid_metrics": valid_metrics,
                "valid_delta": delta(valid_base, valid_metrics),
                "score": train_score,
            }
        else:
            best = {
                "weights": current,
                "train_metrics": metrics(train, current),
                "valid_metrics": valid_base,
                "valid_delta": delta(valid_base, valid_base),
                "score": objective(valid_base),
            }
        chosen_weights.append(best["weights"])
        scored_validation.extend((valid, best["weights"]))
        fold_rows.append({
            "fold": fold_idx,
            "train_races": len(train),
            "valid_races": len(valid),
            "valid_base": valid_base,
            **best,
        })

    # Re-score each validation fold with its chosen fold-specific weights.
    validation_bucket = Counter()
    validation_metrics_rows = []
    for row in fold_rows:
        validation_metrics_rows.append(row["valid_metrics"])
    for item in validation_metrics_rows:
        for key, value in item.items():
            if key in {"top3_precision", "winner_top3_rate", "winner_top5_rate"}:
                continue
            validation_bucket[key] += value
    slots = validation_bucket["top3_slots"] or (validation_bucket["races"] * 3) or 1
    races_n = validation_bucket["races"] or 1
    validation_ml = dict(validation_bucket)
    validation_ml["top3_precision"] = validation_bucket["top3_places"] / slots
    validation_ml["winner_top3_rate"] = validation_bucket["winner_top3"] / races_n
    validation_ml["winner_top5_rate"] = validation_bucket["winner_top5"] / races_n

    avg_weights = average_weights(chosen_weights)
    full_avg = metrics(races, avg_weights)
    gate = passes_gate(validation_base, validation_ml) and passes_gate(full_base, full_avg)

    lines = [
        "# AU Clean 7D Weight Search",
        "",
        "Shadow test only. This does not change live weights.",
        "",
        "## Guardrails",
        "",
        "- Uses only the seven AU matrix scores.",
        "- No odds, flucs, market rank, formguide price movement, or post-7D modifier is used.",
        "- Walk-forward by date: train on earlier races, validate on later races.",
        f"- Seed: `{args.seed}`; iterations per fold: `{args.iterations}`.",
        "",
        "## Baseline vs Search",
        "",
        f"- Current static 7D validation: {fmt_metrics(validation_base)}",
        f"- Fold-selected validation: {fmt_metrics(validation_ml)}",
        f"- Validation delta: {fmt_delta(delta(validation_base, validation_ml))}",
        f"- Current static 7D full archive: {fmt_metrics(full_base)}",
        f"- Average searched weights full archive: {fmt_metrics(full_avg)}",
        f"- Full archive delta: {fmt_delta(delta(full_base, full_avg))}",
        "",
        "## Gate",
        "",
        "PASSED" if gate else "FAILED",
        "",
        "## Current vs Average Searched Weights",
        "",
        "| Matrix | Current | Searched avg | Delta |",
        "|---|---:|---:|---:|",
    ]
    for key in MATRIX_KEYS:
        current_w = current[key]
        avg_w = avg_weights[key]
        lines.append(f"| `{key}` | {current_w * 100:.1f}% | {avg_w * 100:.1f}% | {(avg_w - current_w) * 100:+.1f}pp |")
    lines.extend([
        "",
        "## Fold Detail",
        "",
        "| Fold | Train | Valid | Validation delta | Weights |",
        "|---:|---:|---:|---|---|",
    ])
    for row in fold_rows:
        lines.append(
            f"| {row['fold']} | {row['train_races']} | {row['valid_races']} | "
            f"{fmt_delta(row['valid_delta'])} | {weight_text(row['weights'])} |"
        )
    lines.extend([
        "",
        "## Recommendation",
        "",
    ])
    if gate:
        lines.append("- Candidate weights passed shadow gate, but should still run in report-only for at least one fresh meeting before replacing official weights.")
    else:
        lines.append("- Do not change live 7D weights yet. Current clean static weights remain the official ranking baseline.")
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Races: {len(races)}")
    print(f"Validation: {fmt_metrics(validation_base)}")
    print(f"Search: {fmt_metrics(validation_ml)}")
    print(f"Validation delta: {fmt_delta(delta(validation_base, validation_ml))}")
    print(f"Average weights full delta: {fmt_delta(delta(full_base, full_avg))}")
    print(f"Gate: {'PASSED' if gate else 'FAILED'}")
    print(f"Report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
