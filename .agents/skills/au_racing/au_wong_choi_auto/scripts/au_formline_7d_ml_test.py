#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[4]
sys.path.append(str(SCRIPT_DIR))
sys.path.append(str(SCRIPT_DIR / "racing_engine"))

from au_archive_calibrator import (  # noqa: E402
    ARCHIVE_ROOT,
    HISTORICAL_RESULTS_CSV,
    MATRIX_KEYS,
    choose_track_rows,
    detect_meeting_date,
    detect_meeting_track,
    load_historical_results,
    normalize_horse_name,
    parse_int,
)
from au_auto_orchestrator import _build_field_summary  # noqa: E402
from engine_core import RacingEngine  # noqa: E402
from scoring import MATRIX_WEIGHTS  # noqa: E402


OUTPUT_MD = ARCHIVE_ROOT / "AU_Formline_7D_ML_Test.md"
SEED = 20260612
ITERATIONS_PER_FOLD = 1200


def normalize(weights: dict[str, float]) -> dict[str, float]:
    clean = {key: max(0.0, float(weights.get(key, 0.0))) for key in MATRIX_KEYS}
    total = sum(clean.values()) or 1.0
    return {key: clean[key] / total for key in MATRIX_KEYS}


def with_formline_share(share: float) -> dict[str, float]:
    base = normalize(MATRIX_WEIGHTS)
    existing_form = base.get("form_line", 0.0)
    if existing_form >= share:
        return base
    non_form_total = sum(value for key, value in base.items() if key != "form_line") or 1.0
    scale = (1.0 - share) / non_form_total
    return normalize({key: (share if key == "form_line" else base[key] * scale) for key in MATRIX_KEYS})


def score(row: dict, weights: dict[str, float]) -> float:
    matrix = row.get("matrix_scores") or {}
    return sum(float(matrix.get(key, 60.0) or 60.0) * weights.get(key, 0.0) for key in MATRIX_KEYS)


def ranked(race: list[dict], weights: dict[str, float]) -> list[dict]:
    return sorted(race, key=lambda row: (-score(row, weights), int(row["horse_number"])))


def metrics(races: list[list[dict]], weights: dict[str, float]) -> dict:
    bucket = Counter()
    for race in races:
        order = ranked(race, weights)
        top3 = order[:3]
        top5 = order[:5]
        hits = sum(1 for row in top3 if int(row["actual_pos"]) <= 3)
        top2_hits = sum(1 for row in order[:2] if int(row["actual_pos"]) <= 3)
        bucket["races"] += 1
        bucket[f"{hits}hit"] += 1
        bucket["top3_places"] += hits
        bucket["top3_slots"] += len(top3)
        bucket["winner_top5"] += 1 if any(int(row["actual_pos"]) == 1 for row in top5) else 0
        bucket["gold"] += 1 if hits == 3 else 0
        bucket["good"] += 1 if top2_hits == 2 else 0
        bucket["pass"] += 1 if hits >= 2 else 0
    races_n = bucket["races"] or 1
    slots = bucket["top3_slots"] or 1
    return {
        "races": bucket["races"],
        "gold": bucket["gold"],
        "good": bucket["good"],
        "pass": bucket["pass"],
        "winner_top5": bucket["winner_top5"],
        "top3_places": bucket["top3_places"],
        "top3_precision": bucket["top3_places"] / slots,
        "0hit": bucket["0hit"],
        "1hit": bucket["1hit"],
        "2hit": bucket["2hit"],
        "3hit": bucket["3hit"],
        "winner_top5_rate": bucket["winner_top5"] / races_n,
    }


def objective(item: dict) -> float:
    races = item["races"] or 1
    return (
        (item["pass"] / races) * 3.2
        + (item["good"] / races) * 1.4
        + (item["gold"] / races) * 0.35
        + item["top3_precision"] * 1.8
        + item["winner_top5_rate"] * 0.7
        - (item["0hit"] / races) * 2.5
    )


def fmt_metrics(item: dict) -> str:
    races = item["races"] or 1
    return (
        f"Gold {item['gold']} ({item['gold'] / races * 100:.1f}%) / "
        f"Good {item['good']} ({item['good'] / races * 100:.1f}%) / "
        f"Pass {item['pass']} ({item['pass'] / races * 100:.1f}%) / "
        f"0H {item['0hit']} / 1H {item['1hit']} / "
        f"Top3 {item['top3_precision'] * 100:.1f}% / WTop5 {item['winner_top5'] / races * 100:.1f}%"
    )


def delta(base: dict, cand: dict) -> dict:
    return {
        "gold": cand["gold"] - base["gold"],
        "good": cand["good"] - base["good"],
        "pass": cand["pass"] - base["pass"],
        "0hit": cand["0hit"] - base["0hit"],
        "1hit": cand["1hit"] - base["1hit"],
        "top3_places": cand["top3_places"] - base["top3_places"],
        "winner_top5": cand["winner_top5"] - base["winner_top5"],
        "top3_precision_pp": (cand["top3_precision"] - base["top3_precision"]) * 100.0,
    }


def fmt_delta(item: dict) -> str:
    return (
        f"Gold {item['gold']:+d}, Good {item['good']:+d}, Pass {item['pass']:+d}, "
        f"0H {item['0hit']:+d}, 1H {item['1hit']:+d}, "
        f"Top3Places {item['top3_places']:+d}, WTop5 {item['winner_top5']:+d}, "
        f"Top3 {item['top3_precision_pp']:+.1f}pp"
    )


def actual_rows_for_race(historical: dict, meeting_dir: Path, sample_logic: dict, race_no: int) -> list[dict]:
    meeting_date = detect_meeting_date(meeting_dir)
    meeting_track = detect_meeting_track(meeting_dir, sample_logic)
    if not meeting_date or not meeting_track:
        return []
    return choose_track_rows(historical.get((meeting_date, race_no), []), meeting_track)


def horse_name(horse_num: str, horse: dict) -> str:
    facts = (horse.get("_data") or {}).get("facts_section") or ""
    match = re.search(r"^\[\d+\]\s+([^(]+?)(?:\s+\(\d+\))?\n", facts)
    if match:
        return match.group(1).strip()
    return str(horse.get("horse_name") or horse.get("name") or horse_num).strip()


def recompute_race(logic_path: Path, actual_rows: list[dict]) -> list[dict]:
    logic = json.loads(logic_path.read_text(encoding="utf-8"))
    race_context = copy.deepcopy(logic.get("race_analysis") or {})
    horses = logic.get("horses") or {}
    race_context["field_summary"] = _build_field_summary(horses)
    by_slug = {row["horse_slug"]: row for row in actual_rows}
    rows = []
    for horse_num, horse in horses.items():
        slug = normalize_horse_name(horse_name(horse_num, horse))
        actual = by_slug.get(slug)
        if not actual:
            continue
        data = horse.get("_data", {}) if isinstance(horse.get("_data"), dict) else {}
        engine = RacingEngine(
            copy.deepcopy(horse),
            race_context,
            facts_section=data.get("facts_section", ""),
            facts_path=None,
        )
        auto = engine.analyze_horse()
        rows.append(
            {
                "meeting": logic_path.parent.name,
                "date": detect_meeting_date(logic_path.parent),
                "race": parse_int(logic_path.stem) or parse_int((logic.get("race_analysis") or {}).get("race_number")) or 0,
                "horse_number": parse_int(horse_num) or 999,
                "horse_name": horse_name(horse_num, horse),
                "actual_pos": int(actual["pos"]),
                "matrix_scores": {key: float((auto.get("matrix_scores") or {}).get(key) or 60.0) for key in MATRIX_KEYS},
                "formline_score": float((auto.get("feature_scores") or {}).get("formline_score") or 60.0),
                "formline_rows": len(engine._formline_rows()),
            }
        )
    if len(rows) >= 4 and sum(1 for row in rows if row["actual_pos"] <= 3) >= 3:
        return rows
    return []


def load_recomputed_races(limit: int | None = None) -> tuple[list[list[dict]], list[str]]:
    historical = load_historical_results(HISTORICAL_RESULTS_CSV)
    races = []
    errors = []
    meeting_dirs = sorted(path for path in ARCHIVE_ROOT.iterdir() if path.is_dir())
    for idx, meeting_dir in enumerate(meeting_dirs, 1):
        logic_files = sorted(meeting_dir.glob("Race_*_Logic.json"), key=lambda path: parse_int(path.stem) or 999)
        if not logic_files:
            continue
        try:
            sample_logic = json.loads(logic_files[0].read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"{meeting_dir.name}: sample logic read failed: {exc}")
            continue
        if idx == 1 or idx % 10 == 0:
            print(f"Recomputing formline 7D dataset: {idx}/{len(meeting_dirs)} {meeting_dir.name}", flush=True)
        for logic_path in logic_files:
            race_no = parse_int(logic_path.stem) or 0
            actuals = actual_rows_for_race(historical, meeting_dir, sample_logic, race_no)
            if not actuals:
                continue
            try:
                race = recompute_race(logic_path, actuals)
            except Exception as exc:
                errors.append(f"{meeting_dir.name} {logic_path.stem}: {exc}")
                continue
            if race:
                races.append(race)
                if limit and len(races) >= limit:
                    return sorted_races(races), errors
    return sorted_races(races), errors


def sorted_races(races: list[list[dict]]) -> list[list[dict]]:
    return sorted(races, key=lambda race: (race[0]["date"], race[0]["meeting"], int(race[0]["race"])))


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


def random_weights(rng: random.Random, formline_cap: float) -> dict[str, float]:
    base = normalize(MATRIX_WEIGHTS)
    form_share = rng.uniform(0.0, formline_cap)
    weights = {key: max(0.0, base[key] + rng.uniform(-0.075, 0.075)) for key in MATRIX_KEYS if key != "form_line"}
    weights["form_line"] = form_share
    non_form_total = sum(value for key, value in weights.items() if key != "form_line") or 1.0
    for key in MATRIX_KEYS:
        if key != "form_line":
            weights[key] = weights[key] / non_form_total * (1.0 - form_share)
    return normalize(weights)


def train_fold(train: list[list[dict]], rng: random.Random, iterations: int, formline_cap: float) -> tuple[dict[str, float], dict]:
    baseline_weights = normalize(MATRIX_WEIGHTS)
    baseline = metrics(train, baseline_weights)
    best_weights = baseline_weights
    best_metrics = baseline
    best_score = objective(baseline)
    candidates = [baseline_weights] + [with_formline_share(share) for share in (0.01, 0.02, 0.04, 0.06, 0.08, formline_cap)]
    candidates += [random_weights(rng, formline_cap) for _ in range(iterations)]
    for weights in candidates:
        item = metrics(train, weights)
        if item["0hit"] > baseline["0hit"] + 1:
            continue
        if item["pass"] < baseline["pass"] - 1:
            continue
        value = objective(item)
        if value > best_score:
            best_score = value
            best_weights = weights
            best_metrics = item
    return best_weights, best_metrics


def aggregate(items: list[dict]) -> dict:
    bucket = Counter()
    for item in items:
        for key, value in item.items():
            if key in {"top3_precision", "winner_top5_rate"}:
                continue
            bucket[key] += value
    races_n = bucket["races"] or 1
    slots = bucket["top3_slots"] or (bucket["races"] * 3) or 1
    output = dict(bucket)
    output["top3_precision"] = bucket["top3_places"] / slots
    output["winner_top5_rate"] = bucket["winner_top5"] / races_n
    return output


def average_weights(rows: list[dict[str, float]]) -> dict[str, float]:
    if not rows:
        return normalize(MATRIX_WEIGHTS)
    return normalize({key: sum(row.get(key, 0.0) for row in rows) / len(rows) for key in MATRIX_KEYS})


def passes_gate(base: dict, cand: dict) -> bool:
    return (
        cand["0hit"] <= base["0hit"]
        and cand["pass"] >= base["pass"]
        and cand["winner_top5"] >= base["winner_top5"]
        and cand["top3_places"] >= base["top3_places"]
        and cand["gold"] >= base["gold"] - 2
    )


def weight_text(weights: dict[str, float]) -> str:
    return ", ".join(f"{key} {weights[key] * 100:.1f}%" for key in MATRIX_KEYS)


def formline_coverage(races: list[list[dict]]) -> str:
    horses = [row for race in races for row in race]
    with_rows = sum(1 for row in horses if row.get("formline_rows", 0) > 0)
    avg_score = sum(row.get("formline_score", 60.0) for row in horses) / max(1, len(horses))
    return f"{with_rows}/{len(horses)} horses with parsed formline rows; avg formline_score {avg_score:.1f}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Recomputed AU 7D formline ML shadow test.")
    parser.add_argument("--iterations", type=int, default=ITERATIONS_PER_FOLD)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--formline-cap", type=float, default=0.10)
    parser.add_argument("--limit-races", type=int)
    parser.add_argument("--output", type=Path, default=OUTPUT_MD)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    races, errors = load_recomputed_races(limit=args.limit_races)
    folds = date_folds(races)
    if not folds:
        raise SystemExit("Not enough dated races for formline 7D test.")

    current = normalize(MATRIX_WEIGHTS)
    validation_races = [race for _, valid in folds for race in valid]
    validation_base = metrics(validation_races, current)
    full_base = metrics(races, current)

    fixed_rows = []
    for share in (0.01, 0.02, 0.04, 0.06, 0.08, min(0.10, args.formline_cap)):
        weights = with_formline_share(share)
        fixed_rows.append((share, metrics(validation_races, weights), metrics(races, weights), weights))

    fold_rows = []
    fold_metrics = []
    chosen_weights = []
    for fold_idx, (train, valid) in enumerate(folds, 1):
        weights, train_metrics = train_fold(train, rng, args.iterations, args.formline_cap)
        valid_base = metrics(valid, current)
        valid_metrics = metrics(valid, weights)
        fold_metrics.append(valid_metrics)
        chosen_weights.append(weights)
        fold_rows.append(
            {
                "fold": fold_idx,
                "train_races": len(train),
                "valid_races": len(valid),
                "train_metrics": train_metrics,
                "valid_delta": delta(valid_base, valid_metrics),
                "weights": weights,
            }
        )

    validation_ml = aggregate(fold_metrics)
    avg_weights = average_weights(chosen_weights)
    full_avg = metrics(races, avg_weights)
    gate = passes_gate(validation_base, validation_ml) and passes_gate(full_base, full_avg)

    lines = [
        "# AU Formline 7D ML Test",
        "",
        "Shadow test only. This recomputes archive races with the current engine, so the fixed formline parser is included. It does not change live ranking.",
        "",
        "## Guardrails",
        "",
        "- Uses only the seven AU matrix scores.",
        "- No odds, flucs, market rank, formguide price movement, or post-7D modifier is used.",
        "- `form_line` is tested as a clean matrix weight, capped during search.",
        f"- Seed: `{args.seed}`; iterations per fold: `{args.iterations}`; formline cap: `{args.formline_cap * 100:.1f}%`.",
        "",
        "## Data",
        "",
        f"- Races: **{len(races)}**",
        f"- Validation races: **{len(validation_races)}**",
        f"- Formline coverage: {formline_coverage(races)}",
        f"- Recompute errors: `{len(errors)}`",
        "",
        "## Baseline vs Formline Search",
        "",
        f"- Current static 7D validation: {fmt_metrics(validation_base)}",
        f"- Fold-selected formline validation: {fmt_metrics(validation_ml)}",
        f"- Validation delta: {fmt_delta(delta(validation_base, validation_ml))}",
        f"- Current static 7D full archive: {fmt_metrics(full_base)}",
        f"- Average searched weights full archive: {fmt_metrics(full_avg)}",
        f"- Full archive delta: {fmt_delta(delta(full_base, full_avg))}",
        "",
        "## Fixed Formline Share Tests",
        "",
        "| Formline share | Validation | Validation delta | Full archive delta |",
        "|---:|---|---|---|",
    ]
    for share, validation_item, full_item, _weights in fixed_rows:
        lines.append(
            f"| {share * 100:.1f}% | {fmt_metrics(validation_item)} | "
            f"{fmt_delta(delta(validation_base, validation_item))} | {fmt_delta(delta(full_base, full_item))} |"
        )
    lines.extend([
        "",
        "## Gate",
        "",
        "PASSED" if gate else "FAILED",
        "",
        "## Current vs Average Searched Weights",
        "",
        "| Matrix | Current | Searched avg | Delta |",
        "|---|---:|---:|---:|",
    ])
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
    lines.extend(["", "## Recommendation", ""])
    if gate:
        lines.append("- Formline passed the clean 7D shadow gate. Promote only as a small matrix weight after one fresh-meeting shadow run.")
    else:
        lines.append("- Do not re-add formline to live ranking yet. Keep the fixed parser for report/watchlist and keep testing on fresh recomputed archives.")
    if errors:
        lines.extend(["", "## First Recompute Errors", ""])
        lines.extend(f"- {err}" for err in errors[:20])

    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Races: {len(races)}")
    print(f"Formline coverage: {formline_coverage(races)}")
    print(f"Validation: {fmt_metrics(validation_base)}")
    print(f"Formline ML: {fmt_metrics(validation_ml)}")
    print(f"Validation delta: {fmt_delta(delta(validation_base, validation_ml))}")
    print(f"Average weights full delta: {fmt_delta(delta(full_base, full_avg))}")
    print(f"Average searched weights: {weight_text(avg_weights)}")
    print(f"Gate: {'PASSED' if gate else 'FAILED'}")
    print(f"Report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
