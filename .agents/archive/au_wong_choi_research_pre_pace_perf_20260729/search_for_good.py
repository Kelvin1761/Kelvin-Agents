#!/usr/bin/env python3
from __future__ import annotations

import random
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.append(str(SCRIPT_DIR))

from au_market_free_ablation import load_all_races  # noqa: E402
from au_sip_tester import ARCHIVE_ROOT, delta_report, evaluate_races, new_bucket, report_summary  # noqa: E402


OUTPUT_MD = ARCHIVE_ROOT / "AU_Auto_Market_Free_Weight_Search.md"

SEED = 20260515
ITERATIONS = 12000
TOP_KEEP = 25

FEATURE_KEYS = (
    "stability",
    "sectional",
    "race_shape",
    "jockey_trainer",
    "class_weight",
    "track",
    "form_line",
)

INTERACTION_KEYS = (
    "field13_race_shape",
    "field13_sectional",
    "field13_form_line",
    "field912_form_line",
    "field912_stability",
    "bm_class_weight",
    "wet_track",
    "wet_stability",
)

ALL_KEYS = FEATURE_KEYS + INTERACTION_KEYS


def race_sort_key(race: dict) -> tuple:
    return (race.get("meeting", ""), int(race.get("race_no") or 0))


def centered(value) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = 60.0
    return (score - 60.0) / 10.0


def vector_for(horse: dict, race: dict) -> dict:
    matrix = horse.get("matrix_scores", {})
    vec = {key: centered(matrix.get(key, 60.0)) for key in FEATURE_KEYS}
    field = race.get("field_size_bucket", "")
    race_class = race.get("race_class_bucket", "")
    condition = race.get("condition_bucket", "")
    vec["field13_race_shape"] = vec["race_shape"] if field == "Field 13+" else 0.0
    vec["field13_sectional"] = vec["sectional"] if field == "Field 13+" else 0.0
    vec["field13_form_line"] = vec["form_line"] if field == "Field 13+" else 0.0
    vec["field912_form_line"] = vec["form_line"] if field == "Field 9-12" else 0.0
    vec["field912_stability"] = vec["stability"] if field == "Field 9-12" else 0.0
    vec["bm_class_weight"] = vec["class_weight"] if race_class in {"BM58-70", "BM72-84", "BM88+"} else 0.0
    vec["wet_track"] = vec["track"] if condition in {"Soft", "Heavy"} else 0.0
    vec["wet_stability"] = vec["stability"] if condition in {"Soft", "Heavy"} else 0.0
    return vec


def prepare_races(races: list[dict]) -> list[dict]:
    for race in races:
        for horse in race["horses"]:
            vec = vector_for(horse, race)
            horse["_weight_vector"] = tuple(vec.get(key, 0.0) for key in ALL_KEYS)
    return races


def candidate_delta(weights: tuple[float, ...], horse: dict) -> float:
    vec = horse.get("_weight_vector") or ()
    delta = sum(weight * value for weight, value in zip(weights, vec))
    return max(-3.5, min(3.5, delta))


def evaluate_weighted(races: list[dict], weights: tuple[float, ...]) -> dict:
    bucket = new_bucket()
    for race in races:
        ranked = sorted(
            race["horses"],
            key=lambda horse: (
                -(float(horse["rank_score"]) + candidate_delta(weights, horse)),
                horse["horse_number"],
            ),
        )
        top3 = ranked[:3]
        top2 = ranked[:2]
        hits_top3 = sum(1 for horse in top3 if horse["actual_pos"] <= 3)
        hits_top2 = sum(1 for horse in top2 if horse["actual_pos"] <= 3)
        bucket["races"] += 1
        bucket["top3_places"] += hits_top3
        bucket["top3_slots"] += 3
        bucket["hit_distribution"][hits_top3] += 1
        if ranked[0]["actual_pos"] == 1:
            bucket["champion"] += 1
        if any(horse["actual_pos"] == 1 for horse in top3):
            bucket["winner_in_top3"] += 1
        if hits_top3 == 3:
            bucket["gold"] += 1
        if hits_top2 == 2:
            bucket["good"] += 1
        if hits_top3 >= 2:
            bucket["minimum"] += 1
    return bucket


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
        pass_rate * 1.0
        + good_rate * 6.0
        + gold_rate * 0.9
        + place_rate * 1.4
        + top3_win_rate * 0.6
        - zero_hit_rate * 2.0
    )


def random_weights(rng: random.Random) -> tuple[float, ...]:
    values = []
    for key in ALL_KEYS:
        span = 0.45 if key in FEATURE_KEYS else 0.65
        values.append(rng.uniform(-span, span))
    return tuple(values)


def evaluate_with_weights(races: list[dict], weights: dict):
    return evaluate_weighted(races, weights)


def fmt_delta(delta: dict) -> str:
    return (
        f"Gold {delta['gold_delta']:+.1f}pp / Good {delta['good_delta']:+.1f}pp / "
        f"Pass {delta['pass_delta']:+.1f}pp / Place {delta['place_delta']:+.1f}pp / "
        f"0H {delta['0hit_delta']:+d} / 1H {delta['1hit_delta']:+d}"
    )


def main():
    rng = random.Random(SEED)
    races = prepare_races(sorted(load_all_races(), key=race_sort_key))
    split_at = max(1, int(len(races) * 0.70))
    train = races[:split_at]
    valid = races[split_at:]

    train_base = evaluate_races(train, "train_base")[0]
    valid_base = evaluate_races(valid, "valid_base")[0]
    full_base = evaluate_races(races, "full_base")[0]

    kept: list[tuple[float, dict, dict]] = []
    for _ in range(ITERATIONS):
        weights = random_weights(rng)
        train_bucket = evaluate_with_weights(train, weights)
        train_delta = delta_report(train_base, train_bucket)
        if train_delta["pass_delta"] < 0 or train_delta["0hit_delta"] > 2:
            continue
        score = objective(train_bucket)
        kept.append((score, weights, train_delta))
        kept.sort(key=lambda row: row[0], reverse=True)
        kept = kept[:TOP_KEEP]

    validated = []
    for _, weights, train_delta in kept:
        valid_bucket = evaluate_with_weights(valid, weights)
        full_bucket = evaluate_with_weights(races, weights)
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
        "# AU Auto Market-Free Weight Search",
        "",
        "- Search uses only existing section scores and race metadata interactions.",
        "- No market odds, SP, favourite rank, price movement, or market field is used.",
        f"- Random seed: `{SEED}`",
        f"- Iterations: `{ITERATIONS}`",
        f"- Split: train `{len(train)}` races / validation `{len(valid)}` races",
        "",
        "## Baseline",
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
