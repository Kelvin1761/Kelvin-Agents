#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[4]
sys.path.append(str(SCRIPT_DIR))

from au_archive_calibrator import (  # noqa: E402
    ARCHIVE_ROOT,
    FEATURE_SCORE_KEYS,
    HISTORICAL_RESULTS_CSV,
    MATRIX_KEYS,
    choose_track_rows,
    detect_meeting_date,
    load_scoring_rows,
    load_historical_results,
    normalize_horse_name,
    normalize_condition_bucket,
    parse_int,
)


CACHE_DIR = Path("/private/tmp/au_wong_choi_ml_cache")
DATASET_CSV = CACHE_DIR / "au_labelled_horse_rows.csv"
MANIFEST_JSON = CACHE_DIR / "manifest.json"
OUTPUT_MD = PROJECT_ROOT / "2026-06-06 AU Cached Walkforward ML.md"

BASE_FEATURES = (
    "ability_score",
    "mx_stability",
    "mx_sectional",
    "mx_race_shape",
    "mx_jockey_trainer",
    "mx_class_weight",
    "mx_track",
    "mx_form_line",
)

WET_FEATURES = (
    "wet_flag",
    "wet_track",
    "wet_stability",
    "wet_sectional",
    "wet_class_weight",
    "wet_race_shape",
)

SOFT_HEAVY_FEATURES = (
    "soft_flag",
    "soft_track",
    "soft_stability",
    "soft_sectional",
    "soft_race_shape",
    "heavy_flag",
    "heavy_track",
    "heavy_stability",
    "heavy_sectional",
    "heavy_race_shape",
)


def as_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def is_wet(condition: str) -> bool:
    text = str(condition or "").lower()
    return "soft" in text or "heavy" in text


def condition_family(condition: str) -> str:
    return normalize_condition_bucket(condition or "")


def centered(score: float) -> float:
    return (as_float(score, 60.0) - 60.0) / 10.0


def row_id(row: dict) -> tuple[str, int]:
    return (row["meeting"], int(row["race"]))


def meeting_track_from_name(meeting_dir: Path) -> str:
    name = meeting_dir.name
    if name[:10].count("-") == 2:
        name = name[11:]
    for suffix in (" Race 1-10", " Race 1-9", " Race 1-8", " Race 1-7", " Race 1-6"):
        name = name.replace(suffix, "")
    return name.strip()


def iter_scoring_race_rows(historical_results) -> tuple[list[dict], int]:
    rows: list[dict] = []
    skipped_races = 0
    meeting_dirs = sorted(path for path in ARCHIVE_ROOT.iterdir() if path.is_dir())
    for idx, meeting_dir in enumerate(meeting_dirs, 1):
        if idx == 1 or idx % 10 == 0:
            print(f"Scanning scoring CSV cache: {idx}/{len(meeting_dirs)} {meeting_dir.name}", flush=True)
        meeting_date = detect_meeting_date(meeting_dir)
        meeting_track = meeting_track_from_name(meeting_dir)
        if not meeting_date or not meeting_track:
            continue
        for scoring_path in sorted(meeting_dir.glob("Race_*_Auto_Scoring.csv")):
            race_no = parse_int(scoring_path.stem)
            if not race_no:
                skipped_races += 1
                continue
            result_rows = choose_track_rows(historical_results.get((meeting_date, race_no), []), meeting_track)
            if not result_rows:
                skipped_races += 1
                continue
            race_lookup = {row["horse_slug"]: row for row in result_rows}
            scoring_rows = load_scoring_rows(scoring_path)
            race_rows = []
            for scoring_row in scoring_rows:
                result_row = race_lookup.get(normalize_horse_name(scoring_row.get("horse_name", "")))
                if not result_row:
                    continue
                race_rows.append(
                    {
                        "date": meeting_date,
                        "meeting": meeting_dir.name,
                        "track": meeting_track,
                        "race": race_no,
                        "race_class": "",
                        "condition": result_row.get("condition", ""),
                        "condition_bucket": result_row.get("condition", ""),
                        "horse_number": scoring_row["horse_number"],
                        "horse_name": scoring_row["horse_name"],
                        "actual_pos": int(result_row["pos"]),
                        "ability_score": scoring_row["ability_score"],
                        "rank_score": scoring_row["rank_score"],
                        "feature_scores": scoring_row.get("feature_scores") or {},
                        "matrix_scores": scoring_row.get("matrix_scores") or {},
                    }
                )
            if len(race_rows) < 4 or sum(1 for row in race_rows if row["actual_pos"] <= 3) < 3:
                skipped_races += 1
                continue
            rows.extend(race_rows)
    return rows, skipped_races


def materialize_dataset(rebuild: bool = False) -> list[dict]:
    if DATASET_CSV.exists() and not rebuild:
        return load_dataset(DATASET_CSV)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    print("Loading historical results labels...", flush=True)
    historical_results = load_historical_results(HISTORICAL_RESULTS_CSV)
    print(f"Historical race labels loaded: {len(historical_results)} date/race keys", flush=True)
    rows: list[dict] = []
    source_rows, skipped_races = iter_scoring_race_rows(historical_results)

    for race_rows in group_source_races(source_rows):
        field_count = len(race_rows)
        for source in race_rows:
            condition = source.get("condition_bucket") or source.get("condition")
            bucket = condition_family(condition)
            wet = bucket in {"Soft", "Heavy"}
            soft = bucket == "Soft"
            heavy = bucket == "Heavy"
            matrix = source.get("matrix_scores") or {}
            features = source.get("feature_scores") or {}
            row = {
                "date": source.get("date", ""),
                "meeting": source.get("meeting", ""),
                "track": source.get("track", ""),
                "race": source.get("race", ""),
                "race_class": source.get("race_class", ""),
                "condition_bucket": source.get("condition_bucket", ""),
                "field_count": field_count,
                "horse_number": source.get("horse_number", ""),
                "horse_name": source.get("horse_name", ""),
                "actual_pos": source.get("actual_pos", ""),
                "is_top3": 1 if int(source.get("actual_pos") or 99) <= 3 else 0,
                "is_winner": 1 if int(source.get("actual_pos") or 99) == 1 else 0,
                "ability_score": source.get("ability_score", 0.0),
                "rank_score": source.get("rank_score", source.get("ability_score", 0.0)),
                "wet_flag": 1 if wet else 0,
                "soft_flag": 1 if soft else 0,
                "heavy_flag": 1 if heavy else 0,
            }
            for key in MATRIX_KEYS:
                value = as_float(matrix.get(key), 60.0)
                row[f"mx_{key}"] = value
                row[f"wet_{key}"] = value if wet else 60.0
                row[f"soft_{key}"] = value if soft else 60.0
                row[f"heavy_{key}"] = value if heavy else 60.0
            for key in FEATURE_SCORE_KEYS:
                row[key] = as_float(features.get(key), 60.0)
            rows.append(row)

    fieldnames = list(rows[0].keys()) if rows else []
    with DATASET_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    manifest = {
        "archive_root": str(ARCHIVE_ROOT),
        "historical_results_csv": str(HISTORICAL_RESULTS_CSV),
        "historical_results_mtime": HISTORICAL_RESULTS_CSV.stat().st_mtime if HISTORICAL_RESULTS_CSV.exists() else None,
        "rows": len(rows),
        "races": len({(row["meeting"], row["race"]) for row in rows}),
        "skipped_races": skipped_races,
    }
    MANIFEST_JSON.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return rows


def group_source_races(rows: list[dict]) -> list[list[dict]]:
    grouped: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for row in rows:
        grouped[(row["meeting"], int(row["race"]))].append(row)
    return list(grouped.values())


def load_dataset(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = []
        for row in reader:
            for key in (
                "race",
                "field_count",
                "horse_number",
                "actual_pos",
                "is_top3",
                "is_winner",
                "wet_flag",
                "soft_flag",
                "heavy_flag",
            ):
                row[key] = int(as_float(row.get(key), 0))
            for key in (
                "ability_score",
                "rank_score",
                *[f"mx_{m}" for m in MATRIX_KEYS],
                *[f"wet_{m}" for m in MATRIX_KEYS],
                *[f"soft_{m}" for m in MATRIX_KEYS],
                *[f"heavy_{m}" for m in MATRIX_KEYS],
                *FEATURE_SCORE_KEYS,
            ):
                if key == "health_score" and key not in row and "readiness_score" in row:
                    row[key] = as_float(row.get("readiness_score"), 60.0)
                if key in row:
                    row[key] = as_float(row.get(key), 60.0)
            rows.append(row)
        return rows


def group_races(rows: list[dict]) -> list[list[dict]]:
    grouped: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row_id(row)].append(row)
    races = [race for race in grouped.values() if len(race) >= 4 and sum(1 for row in race if row["actual_pos"] <= 3) >= 3]
    return sorted(races, key=lambda race: (race[0]["date"], race[0]["meeting"], race[0]["race"]))


def metrics_for_races(races: list[list[dict]], score_key: str = "_score") -> dict:
    bucket = Counter()
    top3_hits = 0
    top3_slots = 0
    for race in races:
        ranked = sorted(race, key=lambda row: (-as_float(row[score_key]), int(row["horse_number"])))
        top3 = ranked[:3]
        hits = sum(1 for row in top3 if row["actual_pos"] <= 3)
        bucket["races"] += 1
        bucket[f"{hits}hit"] += 1
        bucket["top3_hits"] += hits
        bucket["top3_slots"] += len(top3)
        bucket["winner_in_top3"] += 1 if any(row["actual_pos"] == 1 for row in top3) else 0
        bucket["top1_wins"] += 1 if ranked and ranked[0]["actual_pos"] == 1 else 0
        bucket["gold"] += 1 if hits == 3 else 0
        bucket["good"] += 1 if hits >= 2 else 0
        bucket["pass"] += 1 if hits >= 1 else 0
    races_n = max(1, bucket["races"])
    slots = max(1, bucket["top3_slots"])
    return {
        "races": bucket["races"],
        "gold": bucket["gold"],
        "good": bucket["good"],
        "pass": bucket["pass"],
        "miss": bucket["0hit"],
        "one_hit": bucket["1hit"],
        "top3_precision": bucket["top3_hits"] / slots,
        "winner_in_top3": bucket["winner_in_top3"] / races_n,
        "top1_win": bucket["top1_wins"] / races_n,
    }


def standardizer(rows: list[dict], feature_names: tuple[str, ...]) -> tuple[dict[str, float], dict[str, float]]:
    means = {}
    scales = {}
    for key in feature_names:
        values = [feature_value(row, key) for row in rows]
        avg = mean(values) if values else 0.0
        var = mean([(value - avg) ** 2 for value in values]) if values else 1.0
        means[key] = avg
        scales[key] = math.sqrt(var) or 1.0
    return means, scales


def feature_value(row: dict, key: str) -> float:
    if key in {"wet_flag", "soft_flag", "heavy_flag"}:
        return float(row.get(key, 0))
    if key.startswith("soft_"):
        return centered(row.get(key, 60.0)) * float(row.get("soft_flag", 0))
    if key.startswith("heavy_"):
        return centered(row.get(key, 60.0)) * float(row.get("heavy_flag", 0))
    if key.startswith("wet_"):
        return centered(row.get(key, 60.0)) * float(row.get("wet_flag", 0))
    if key.startswith("mx_") or key.endswith("_score") or key == "ability_score":
        return centered(row.get(key, 60.0))
    return as_float(row.get(key), 0.0)


def sigmoid(value: float) -> float:
    if value < -40:
        return 0.0
    if value > 40:
        return 1.0
    return 1.0 / (1.0 + math.exp(-value))


def train_logistic(rows: list[dict], feature_names: tuple[str, ...], epochs: int, lr: float, l2: float, seed: int) -> dict:
    rng = random.Random(seed)
    means, scales = standardizer(rows, feature_names)
    weights = {key: 0.0 for key in feature_names}
    bias = 0.0
    indexed = list(rows)
    for _ in range(epochs):
        rng.shuffle(indexed)
        for row in indexed:
            z = bias
            xs = {}
            for key in feature_names:
                x = (feature_value(row, key) - means[key]) / scales[key]
                xs[key] = x
                z += weights[key] * x
            pred = sigmoid(z)
            err = pred - float(row["is_top3"])
            bias -= lr * err
            for key in feature_names:
                weights[key] -= lr * (err * xs[key] + l2 * weights[key])
    return {"weights": weights, "bias": bias, "means": means, "scales": scales}


def predict(model: dict, row: dict, feature_names: tuple[str, ...]) -> float:
    z = model["bias"]
    for key in feature_names:
        x = (feature_value(row, key) - model["means"][key]) / model["scales"][key]
        z += model["weights"][key] * x
    return sigmoid(z)


def date_folds(races: list[list[dict]], folds: int = 5, min_train_ratio: float = 0.5) -> list[tuple[list[list[dict]], list[list[dict]]]]:
    dates = sorted({race[0]["date"] for race in races if race[0]["date"]})
    if len(dates) < 4:
        return []
    start = max(1, int(len(dates) * min_train_ratio))
    valid_dates = dates[start:]
    fold_size = max(1, math.ceil(len(valid_dates) / folds))
    output = []
    for idx in range(0, len(valid_dates), fold_size):
        fold_dates = set(valid_dates[idx : idx + fold_size])
        first_valid = min(fold_dates)
        train = [race for race in races if race[0]["date"] < first_valid]
        valid = [race for race in races if race[0]["date"] in fold_dates]
        if train and valid:
            output.append((train, valid))
    return output


def flatten(races: list[list[dict]]) -> list[dict]:
    return [row for race in races for row in race]


def evaluate_model(races: list[list[dict]], feature_names: tuple[str, ...], seed: int) -> tuple[list[list[dict]], dict[str, float]]:
    folds = date_folds(races)
    scored_folds = []
    weight_totals = Counter()
    weight_counts = Counter()
    for fold_idx, (train, valid) in enumerate(folds, 1):
        model = train_logistic(flatten(train), feature_names, epochs=90, lr=0.018, l2=0.0015, seed=seed + fold_idx)
        for key, value in model["weights"].items():
            weight_totals[key] += value
            weight_counts[key] += 1
        scored_valid = []
        for race in valid:
            scored_race = []
            for row in race:
                item = dict(row)
                item["_score"] = predict(model, row, feature_names)
                scored_race.append(item)
            scored_valid.append(scored_race)
        scored_folds.extend(scored_valid)
    avg_weights = {key: weight_totals[key] / max(1, weight_counts[key]) for key in feature_names}
    return scored_folds, avg_weights


def score_baseline(races: list[list[dict]], score_source: str) -> list[list[dict]]:
    scored = []
    for race in races:
        scored.append([{**row, "_score": as_float(row.get(score_source), 0.0)} for row in race])
    return scored


def fmt_metrics(metrics: dict) -> str:
    return (
        f"{metrics['gold']} Gold / {metrics['good']} Good / {metrics['pass']} Pass / "
        f"{metrics['one_hit']} 1H / {metrics['miss']} Miss / "
        f"Top3 {metrics['top3_precision'] * 100:.1f}% / W-in-T3 {metrics['winner_in_top3'] * 100:.1f}%"
    )


def by_condition_metrics(races: list[list[dict]]) -> dict[str, dict]:
    grouped: dict[str, list[list[dict]]] = defaultdict(list)
    for race in races:
        grouped[condition_family(race[0]["condition_bucket"] or "Unknown")].append(race)
    return {key: metrics_for_races(value) for key, value in sorted(grouped.items())}


def render_condition_table(title: str, rows: dict[str, dict]) -> list[str]:
    lines = [
        f"## {title}",
        "",
        "| Condition | Races | Result |",
        "|---|---:|---|",
    ]
    for condition, metrics in rows.items():
        lines.append(f"| {condition} | {metrics['races']} | {fmt_metrics(metrics)} |")
    return lines


def render_report(
    races: list[list[dict]],
    baseline: dict,
    seven_d: dict,
    wet: dict,
    split_wet: dict,
    baseline_condition: dict[str, dict],
    split_wet_condition: dict[str, dict],
    seven_weights: dict,
    wet_weights: dict,
    split_wet_weights: dict,
) -> str:
    condition_counts = Counter(normalize_condition_bucket(race[0]["condition_bucket"] or "Unknown") for race in races)
    venue_counts = Counter(race[0]["track"] or "Unknown" for race in races)
    top_wet = sorted(wet_weights.items(), key=lambda item: abs(item[1]), reverse=True)[:12]
    top_split = sorted(split_wet_weights.items(), key=lambda item: abs(item[1]), reverse=True)[:14]
    gate_passed = (
        wet["top3_precision"] > baseline["top3_precision"]
        and wet["winner_in_top3"] >= baseline["winner_in_top3"]
        and wet["miss"] <= baseline["miss"]
    )
    lines = [
        "# AU Cached Walk-Forward ML",
        "",
        "## Dataset",
        "",
        f"- Races: **{len(races)}**",
        f"- Horses: **{sum(len(race) for race in races)}**",
        f"- Cache: `{DATASET_CSV}`",
        f"- Conditions: {', '.join(f'{key} {value}' for key, value in condition_counts.most_common())}",
        f"- Top venues: {', '.join(f'{key} {value}' for key, value in venue_counts.most_common(8))}",
        "",
        "## Walk-Forward Result",
        "",
        "| Model | Result |",
        "|---|---|",
        f"| Ability baseline | {fmt_metrics(baseline)} |",
        f"| 7D ML | {fmt_metrics(seven_d)} |",
        f"| 7D + wet interactions ML | {fmt_metrics(wet)} |",
        f"| 7D + Soft/Heavy split interactions ML | {fmt_metrics(split_wet)} |",
        "",
        *render_condition_table("Ability Baseline By Condition", baseline_condition),
        "",
        *render_condition_table("Soft/Heavy Split ML By Condition", split_wet_condition),
        "",
        "## Wet Interaction Weights",
        "",
        "| Feature | Avg logistic weight |",
        "|---|---:|",
    ]
    for key, value in top_wet:
        lines.append(f"| `{key}` | {value:+.4f} |")
    lines.extend([
        "",
        "## Soft / Heavy Split Interaction Weights",
        "",
        "| Feature | Avg logistic weight |",
        "|---|---:|",
    ])
    for key, value in top_split:
        lines.append(f"| `{key}` | {value:+.4f} |")
    lines.extend([
        "",
        "## Promotion Gate",
        "",
        "PASSED" if gate_passed else "FAILED",
        "",
    ])
    if gate_passed:
        lines.append("- Wet interaction model improved Top3 precision without increasing Miss and without losing winner-in-top3.")
    else:
        lines.append("- Do not bake wet interaction into live AU scoring yet; keep it as shadow diagnostics until it passes walk-forward and venue buckets.")
    lines.extend([
        "",
        "## Recommendation",
        "",
        "- Keep live ranking on `ability_score` only.",
        "- Treat wet track as a 7D interaction first: dynamic emphasis inside `track`, `stability`, `sectional`, and `race_shape` when condition is Soft/Heavy.",
        "- Split Soft and Heavy in diagnostics and candidate tuning; Heavy should require stronger proof because archive sample size is much smaller.",
        "- Only promote an 8th dimension if the wet-only ablation beats 7D on out-of-sample races and at least the major venue buckets.",
    ])
    _ = seven_weights
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build cached AU ML dataset and run date walk-forward diagnostics.")
    parser.add_argument("--rebuild-cache", action="store_true")
    parser.add_argument("--output", type=Path, default=OUTPUT_MD)
    parser.add_argument("--seed", type=int, default=20260606)
    args = parser.parse_args()

    rows = materialize_dataset(rebuild=args.rebuild_cache)
    races = group_races(rows)
    if not races:
        raise SystemExit("No labelled AU races available for ML.")

    folds = date_folds(races)
    if not folds:
        raise SystemExit("Not enough dated races for walk-forward ML.")
    validation_races = [race for _, valid in folds for race in valid]
    baseline_races = score_baseline(validation_races, "ability_score")
    baseline = metrics_for_races(baseline_races)

    seven_features = BASE_FEATURES
    wet_features = BASE_FEATURES + WET_FEATURES
    split_wet_features = BASE_FEATURES + SOFT_HEAVY_FEATURES
    seven_scored, seven_weights = evaluate_model(races, seven_features, args.seed)
    wet_scored, wet_weights = evaluate_model(races, wet_features, args.seed)
    split_wet_scored, split_wet_weights = evaluate_model(races, split_wet_features, args.seed)
    seven_metrics = metrics_for_races(seven_scored)
    wet_metrics = metrics_for_races(wet_scored)
    split_wet_metrics = metrics_for_races(split_wet_scored)

    args.output.write_text(
        render_report(
            races,
            baseline,
            seven_metrics,
            wet_metrics,
            split_wet_metrics,
            by_condition_metrics(baseline_races),
            by_condition_metrics(split_wet_scored),
            seven_weights,
            wet_weights,
            split_wet_weights,
        ),
        encoding="utf-8",
    )
    print(f"Cached rows: {len(rows)}")
    print(f"Races: {len(races)}")
    print(f"Validation races: {len(validation_races)}")
    print(f"Ability baseline: {fmt_metrics(baseline)}")
    print(f"7D ML: {fmt_metrics(seven_metrics)}")
    print(f"7D + wet ML: {fmt_metrics(wet_metrics)}")
    print(f"7D + soft/heavy split ML: {fmt_metrics(split_wet_metrics)}")
    print(f"Report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
