#!/usr/bin/env python3
"""
hkjc_market_free_weight_search.py — HKJC Wong Choi ML Weight Search
"""

from __future__ import annotations

import argparse
import random
import sys
import json
from pathlib import Path
from collections import defaultdict

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from review_auto_weighting import (
    CURRENT_MATRIX_FORMULAS,
    CURRENT_MATRIX_WEIGHTS,
    build_results_index,
    compute_ability,
    compute_full_feature_scores,
    compute_matrix_scores,
    dedup_race_key,
    hk_meeting_dirs,
    load_results,
    meeting_date,
    race_num_from_path,
    venue_from_meeting_dir,
    _normalize_distance,
    _normalize_venue,
)
from hkjc_results_db import (
    get_analysis_archive_root,
    get_season_results_roots,
)

OUTPUT_MD = get_analysis_archive_root().parent / "HKJC_Auto_Market_Free_Weight_Search.md"

SEED = 20260527
ITERATIONS = 12000
TOP_KEEP = 25

FEATURE_KEYS = (
    "sectional",
    "trainer_signal",
    "stability",
    "race_shape",
    "class_advantage",
    "horse_health",
    "form_line",
)

INTERACTION_KEYS = (
    "hv_race_shape",
    "hv_sectional",
    "st_class_advantage",
    "wet_track_stability",
    "sprint_sectional",
)

ALL_KEYS = FEATURE_KEYS + INTERACTION_KEYS


def centered(value) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = 60.0
    return (score - 60.0) / 10.0


def vector_for(horse: dict, race_context: dict) -> dict:
    matrix = horse.get("matrix_scores", {})
    vec = {key: centered(matrix.get(key, 60.0)) for key in FEATURE_KEYS}
    
    venue = _normalize_venue(race_context.get("venue"))
    distance = _normalize_distance(race_context.get("distance"))
    track_condition = race_context.get("track_condition", "")
    
    is_hv = (venue == "跑馬地")
    is_st = (venue == "沙田")
    is_sprint = (distance in {"1000", "1200", "1000m", "1200m"})
    is_wet = ("黏" in track_condition or "軟" in track_condition or "爛" in track_condition)
    
    vec["hv_race_shape"] = vec["race_shape"] if is_hv else 0.0
    vec["hv_sectional"] = vec["sectional"] if is_hv else 0.0
    vec["st_class_advantage"] = vec["class_advantage"] if is_st else 0.0
    vec["wet_track_stability"] = vec["stability"] if is_wet else 0.0
    vec["sprint_sectional"] = vec["sectional"] if is_sprint else 0.0
    
    return vec


def prepare_races(races: list[dict]) -> list[dict]:
    for race in races:
        for horse in race["horses"]:
            vec = vector_for(horse, race["race_context"])
            horse["_weight_vector"] = tuple(vec.get(key, 0.0) for key in ALL_KEYS)
    return races


def candidate_delta(weights: tuple[float, ...], horse: dict) -> float:
    vec = horse.get("_weight_vector") or ()
    # Calculate delta on ability
    delta = sum(weight * value for weight, value in zip(weights, vec))
    return max(-3.5, min(3.5, delta))


def new_bucket() -> dict:
    return {
        "races": 0,
        "top3_slots": 0,
        "top3_places": 0,
        "gold": 0,
        "good": 0,
        "minimum": 0,
        "champion": 0,
        "winner_in_top3": 0,
        "hit_distribution": defaultdict(int),
    }


def evaluate_weighted(races: list[dict], weights: tuple[float, ...]) -> dict:
    bucket = new_bucket()
    for race in races:
        actual_pos = race["actual_pos"]
        actual_top3 = set([h for h, pos in sorted(actual_pos.items(), key=lambda x: x[1])[:3]])
        winner = [h for h, pos in sorted(actual_pos.items(), key=lambda x: x[1])][0] if actual_pos else None

        ranked = sorted(
            race["horses"],
            key=lambda horse: (
                -(horse["ability"] + candidate_delta(weights, horse)),
                horse["horse_num"],
            ),
        )
        
        top3 = ranked[:3]
        top4 = ranked[:4]
        
        hits_top3 = sum(1 for horse in top3 if horse["horse_num"] in actual_top3)
        hits_top4 = sum(1 for horse in top4 if horse["horse_num"] in actual_top3) # technically good=2 in top4, etc.
        
        bucket["races"] += 1
        bucket["top3_places"] += hits_top3
        bucket["top3_slots"] += 3
        bucket["hit_distribution"][hits_top3] += 1
        
        if ranked[0]["horse_num"] == winner:
            bucket["champion"] += 1
        if any(horse["horse_num"] == winner for horse in top3):
            bucket["winner_in_top3"] += 1
            
        if hits_top3 == 3:
            bucket["gold"] += 1
            
        # Good: 2 hits in top 4 picks (mimicking Pass/Good logic or Top 2 hits)
        if hits_top4 >= 2:
            bucket["minimum"] += 1
        if hits_top3 >= 2:
            bucket["good"] += 1

    return bucket


def evaluate_races(races: list[dict], _name: str) -> tuple[dict, dict]:
    # Baseline logic (weights all 0.0)
    zero_weights = tuple([0.0] * len(ALL_KEYS))
    bucket = evaluate_weighted(races, zero_weights)
    return bucket, {}


def delta_report(base: dict, test: dict) -> dict:
    base_races = base["races"] or 1
    test_races = test["races"] or 1
    
    # Calculate percentages
    base_gold = base["gold"] / base_races * 100
    test_gold = test["gold"] / test_races * 100
    
    base_good = base["good"] / base_races * 100
    test_good = test["good"] / test_races * 100
    
    base_pass = base["minimum"] / base_races * 100
    test_pass = test["minimum"] / test_races * 100
    
    base_place = base["top3_places"] / (base["top3_slots"] or 1) * 100
    test_place = test["top3_places"] / (test["top3_slots"] or 1) * 100
    
    return {
        "gold_delta": test_gold - base_gold,
        "good_delta": test_good - base_good,
        "pass_delta": test_pass - base_pass,
        "place_delta": test_place - base_place,
        "0hit_delta": test["hit_distribution"][0] - base["hit_distribution"][0],
        "1hit_delta": test["hit_distribution"][1] - base["hit_distribution"][1],
    }


def objective(bucket: dict) -> float:
    races = bucket["races"] or 1
    slots = bucket["top3_slots"] or 1
    pass_rate = bucket["minimum"] / races
    good_rate = bucket["good"] / races
    gold_rate = bucket["gold"] / races
    place_rate = bucket["top3_places"] / slots
    top3_win_rate = bucket["winner_in_top3"] / races
    zero_hit_rate = bucket["hit_distribution"][0] / races
    
    return (
        pass_rate * 3.0
        + good_rate * 1.5
        + gold_rate * 1.0
        + place_rate * 1.4
        + top3_win_rate * 0.8
        - zero_hit_rate * 2.0
    )


def random_weights(rng: random.Random) -> tuple[float, ...]:
    values = []
    for key in ALL_KEYS:
        span = 0.35 if key in FEATURE_KEYS else 0.50
        values.append(rng.uniform(-span, span))
    return tuple(values)


def report_summary(bucket: dict, name: str) -> dict:
    return {
        "gold": bucket["gold"],
        "good": bucket["good"],
        "pass": bucket["minimum"],
        "0hit": bucket["hit_distribution"][0],
        "1hit": bucket["hit_distribution"][1],
        "2hit": bucket["hit_distribution"][2],
        "3hit": bucket["hit_distribution"][3],
    }


def fmt_delta(delta: dict) -> str:
    return (
        f"Gold {delta['gold_delta']:+.1f}pp / Good {delta['good_delta']:+.1f}pp / "
        f"Pass {delta['pass_delta']:+.1f}pp / Place {delta['place_delta']:+.1f}pp / "
        f"0H {delta['0hit_delta']:+d} / 1H {delta['1hit_delta']:+d}"
    )


def load_all_races() -> list[dict]:
    archive_root = get_analysis_archive_root()
    results_roots = get_season_results_roots()
    
    results_index = build_results_index(results_roots)
    meeting_roots = [archive_root]
    meetings = hk_meeting_dirs(meeting_roots)
    
    all_races: list[dict] = []
    seen_race_keys: set[tuple[str | None, str, int]] = set()

    for meeting_dir in meetings:
        date = meeting_date(meeting_dir)
        result_path = results_index.get(date or "")
        if not result_path:
            continue
            
        actual_results = load_results(result_path)
        meeting_venue = venue_from_meeting_dir(meeting_dir)
        
        for logic_path in sorted(meeting_dir.glob("Race_*_Logic.json"), key=race_num_from_path):
            race_num = race_num_from_path(logic_path)
            actual_pos = actual_results.get(race_num)
            if not actual_pos:
                continue
                
            race_key = dedup_race_key(date, meeting_venue, race_num)
            if race_key in seen_race_keys:
                continue
            seen_race_keys.add(race_key)
            
            logic = json.loads(logic_path.read_text(encoding="utf-8"))
            race_context = logic.get("race_analysis", {})
            race_context = dict(race_context)
            race_context.setdefault("venue", meeting_venue)
            
            horses = []
            for horse_num_text, horse in logic.get("horses", {}).items():
                try:
                    horse_num = int(horse_num_text)
                except ValueError:
                    continue
                
                features = compute_full_feature_scores(horse, race_context)
                matrix_scores = compute_matrix_scores(features, CURRENT_MATRIX_FORMULAS)
                ability = compute_ability(matrix_scores, CURRENT_MATRIX_WEIGHTS)
                
                horses.append({
                    "horse_num": horse_num,
                    "horse_name": horse.get("horse_name", ""),
                    "matrix_scores": matrix_scores,
                    "ability": ability,
                })
                
            if not horses:
                continue
                
            all_races.append({
                "meeting": str(meeting_dir),
                "date": date,
                "race_no": race_num,
                "race_context": race_context,
                "actual_pos": actual_pos,
                "horses": horses,
            })
            
    return all_races


def race_sort_key(race: dict) -> tuple:
    return (race.get("date", ""), int(race.get("race_no") or 0))


def main():
    parser = argparse.ArgumentParser(description="HKJC Market-Free Weight Search")
    parser.add_argument("--iterations", type=int, default=ITERATIONS, help="Number of Monte Carlo iterations")
    parser.add_argument("--fast", action="store_true", help="Run 100 iterations only for testing")
    args = parser.parse_args()

    iters = 100 if args.fast else args.iterations

    rng = random.Random(SEED)
    races = prepare_races(sorted(load_all_races(), key=race_sort_key))
    
    if not races:
        print("No races found. Check data directories.")
        return
        
    split_at = max(1, int(len(races) * 0.70))
    train = races[:split_at]
    valid = races[split_at:]

    train_base = evaluate_races(train, "train_base")[0]
    valid_base = evaluate_races(valid, "valid_base")[0]
    full_base = evaluate_races(races, "full_base")[0]

    kept: list[tuple[float, dict, dict]] = []
    
    print(f"Loaded {len(races)} races. (Train: {len(train)}, Valid: {len(valid)})")
    print(f"Running {iters} iterations...")
    
    for _ in range(iters):
        weights = random_weights(rng)
        train_bucket = evaluate_weighted(train, weights)
        train_delta = delta_report(train_base, train_bucket)
        if train_delta["pass_delta"] < 0 or train_delta["0hit_delta"] > 2:
            continue
        score = objective(train_bucket)
        kept.append((score, weights, train_delta))
        kept.sort(key=lambda row: row[0], reverse=True)
        kept = kept[:TOP_KEEP]

    validated = []
    for _, weights, train_delta in kept:
        valid_bucket = evaluate_weighted(valid, weights)
        full_bucket = evaluate_weighted(races, weights)
        valid_delta = delta_report(valid_base, valid_bucket)
        full_delta = delta_report(full_base, full_bucket)
        validated.append(
            {
                "weights": weights,
                "train_delta": train_delta,
                "valid_bucket": valid_bucket,
                "valid_delta": valid_delta,
                "full_bucket": full_bucket,
                "full_delta": full_delta,
                "score": objective(valid_bucket),
            }
        )

    validated.sort(
        key=lambda row: (
            row["valid_delta"]["pass_delta"],
            row["valid_delta"]["good_delta"],
            -row["valid_delta"]["0hit_delta"],
            row["valid_delta"]["place_delta"],
        ),
        reverse=True,
    )

    md = [
        "# HKJC Auto Market-Free Weight Search",
        "",
        "- Search uses only existing matrix scores and race metadata interactions.",
        f"- Random seed: `{SEED}`",
        f"- Iterations: `{iters}`",
        f"- Split: train `{len(train)}` races / validation `{len(valid)}` races",
        "",
        "## Baseline (Current Matrix Weights)",
        "",
        f"- Train: {report_summary(train_base, 'train')['gold']} Gold / {report_summary(train_base, 'train')['good']} Good / {report_summary(train_base, 'train')['pass']} Pass / 0H {report_summary(train_base, 'train')['0hit']}",
        f"- Validation: {report_summary(valid_base, 'valid')['gold']} Gold / {report_summary(valid_base, 'valid')['good']} Good / {report_summary(valid_base, 'valid')['pass']} Pass / 0H {report_summary(valid_base, 'valid')['0hit']}",
        f"- Full: {report_summary(full_base, 'full')['gold']} Gold / {report_summary(full_base, 'full')['good']} Good / {report_summary(full_base, 'full')['pass']} Pass / 0H {report_summary(full_base, 'full')['0hit']}",
        "",
        "## Validation Candidates",
        "",
        "| Rank | Validation | Full | Weights |",
        "|---:|---|---|---|",
    ]
    for idx, row in enumerate(validated[:15], 1):
        non_zero = [(key, value) for key, value in zip(ALL_KEYS, row["weights"]) if abs(value) >= 0.08]
        weight_text = "; ".join(f"{key} {value:+.2f}" for key, value in non_zero)
        md.append(
            f"| {idx} | {fmt_delta(row['valid_delta'])} | {fmt_delta(row['full_delta'])} | {weight_text} |"
        )

    promote = [
        row
        for row in validated
        if row["valid_delta"]["pass_delta"] > 0
        and row["valid_delta"]["good_delta"] >= 0
        and row["valid_delta"]["0hit_delta"] <= 0
        and row["full_delta"]["pass_delta"] > 0
        and row["full_delta"]["0hit_delta"] <= 0
    ]
    md.extend(["", "## Promotion Gate", ""])
    if promote:
        best = promote[0]
        md.append("PASSED")
        md.append("")
        md.append(f"- Validation: {fmt_delta(best['valid_delta'])}")
        md.append(f"- Full: {fmt_delta(best['full_delta'])}")
        
        # Log Best Weights for production usage
        md.append("\n### Best Delta Weights (To be merged with Current Matrix)")
        md.append("```python")
        md.append("ML_DELTA_WEIGHTS = {")
        for key, value in zip(ALL_KEYS, best["weights"]):
            if abs(value) >= 0.01:
                md.append(f'    "{key}": {value:+.4f},')
        md.append("}")
        md.append("```")
    else:
        md.append("FAILED")
        md.append("")
        md.append("No candidate improved validation Pass/Good while keeping validation and full 0-hit flat or lower.")

    OUTPUT_MD.write_text("\n".join(md), encoding="utf-8")

    print(f"Loaded races: {len(races)}")
    print("Baseline full:", report_summary(full_base, "full"))
    print(f"Candidates kept: {len(kept)}")
    if validated:
        print("Best validation:", fmt_delta(validated[0]["valid_delta"]))
        print("Best full:", fmt_delta(validated[0]["full_delta"]))
    print(f"Promotion candidates: {len(promote)}")
    print(f"Report: {OUTPUT_MD}")


if __name__ == "__main__":
    main()
