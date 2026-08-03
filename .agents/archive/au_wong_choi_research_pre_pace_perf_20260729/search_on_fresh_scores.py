#!/usr/bin/env python3
"""Weight search on re-scored archive (P5+P4 + gate removal applied)."""
from __future__ import annotations

import json
import random
import sys
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.append(str(SCRIPT_DIR))
sys.path.append(str(SCRIPT_DIR / "racing_engine"))

from engine_core import RacingEngine
from scoring import MATRIX_WEIGHTS

from au_sip_tester import (
    ARCHIVE_ROOT, HISTORICAL_RESULTS_CSV,
    delta_report, evaluate_races, new_bucket, report_summary,
)
from au_market_free_ablation import (
    MATRIX_KEYS,
    condition_bucket,
    field_size_bucket,
    race_class_bucket,
)
from au_archive_calibrator import (
    choose_track_rows,
    detect_meeting_date,
    detect_meeting_track,
    load_historical_results,
    normalize_horse_name,
    parse_int,
)

OUTPUT_MD = ARCHIVE_ROOT / "AU_Auto_Market_Free_Weight_Search_Fresh.md"

SEED = 20260516
ITERATIONS = 12000
TOP_KEEP = 25

FEATURE_KEYS = (
    "stability", "sectional", "race_shape", "jockey_trainer",
    "class_weight", "track", "form_line",
)

INTERACTION_KEYS = (
    "field13_race_shape", "field13_sectional", "field13_form_line",
    "field912_form_line", "field912_stability",
    "bm_class_weight", "wet_track", "wet_stability",
)

ALL_KEYS = FEATURE_KEYS + INTERACTION_KEYS


def centered(value) -> float:
    try:
        return (float(value) - 60.0) / 10.0
    except (TypeError, ValueError):
        return 0.0


def vector_for(horse: dict, race: dict) -> dict:
    matrix = horse.get("matrix_scores", {})
    vec = {key: centered(matrix.get(key, 60.0)) for key in FEATURE_KEYS}
    field = race.get("field_size_bucket", "")
    rc = race.get("race_class_bucket", "")
    cond = race.get("condition_bucket", "")
    vec["field13_race_shape"] = vec["race_shape"] if field == "Field 13+" else 0.0
    vec["field13_sectional"] = vec["sectional"] if field == "Field 13+" else 0.0
    vec["field13_form_line"] = vec["form_line"] if field == "Field 13+" else 0.0
    vec["field912_form_line"] = vec["form_line"] if field == "Field 9-12" else 0.0
    vec["field912_stability"] = vec["stability"] if field == "Field 9-12" else 0.0
    vec["bm_class_weight"] = vec["class_weight"] if rc in {"BM58-70", "BM72-84", "BM88+"} else 0.0
    vec["wet_track"] = vec["track"] if cond in {"Soft", "Heavy"} else 0.0
    vec["wet_stability"] = vec["stability"] if cond in {"Soft", "Heavy"} else 0.0
    return vec


def pre_race_condition_bucket(race_analysis: dict) -> str:
    return condition_bucket(str((race_analysis or {}).get("going", "") or ""))


def candidate_delta(weights: tuple[float, ...], horse: dict) -> float:
    vec = horse.get("_weight_vector") or ()
    delta = sum(w * v for w, v in zip(weights, vec))
    return max(-3.5, min(3.5, delta))


def evaluate_weighted(races: list[dict], weights: tuple[float, ...]) -> dict:
    bucket = new_bucket()
    for race in races:
        ranked = sorted(
            race["horses"],
            key=lambda h: (
                -(float(h["ability_score"]) + candidate_delta(weights, h)),
                h["horse_number"],
            ),
        )
        top3 = ranked[:3]
        top2 = ranked[:2]
        hits_top3 = sum(1 for h in top3 if h["actual_pos"] <= 3)
        hits_top2 = sum(1 for h in top2 if h["actual_pos"] <= 3)
        bucket["races"] += 1
        bucket["top3_places"] += hits_top3
        bucket["top3_slots"] += 3
        bucket["hit_distribution"][hits_top3] += 1
        if ranked[0]["actual_pos"] == 1:
            bucket["champion"] += 1
        if any(h["actual_pos"] == 1 for h in top3):
            bucket["winner_in_top3"] += 1
        if hits_top3 == 3:
            bucket["gold"] += 1
        if hits_top2 == 2:
            bucket["good"] += 1
        if hits_top3 >= 2:
            bucket["minimum"] += 1
    return bucket


def objective(bucket: dict) -> float:
    r = bucket["races"] or 1
    s = bucket["top3_slots"] or 1
    return (
        bucket["minimum"] / r * 1.0
        + bucket["good"] / r * 6.0
        + bucket["gold"] / r * 0.9
        + bucket["top3_places"] / s * 1.4
        + bucket["winner_in_top3"] / r * 0.6
        - bucket["hit_distribution"][0] / r * 2.0
    )


def random_weights(rng: random.Random) -> tuple[float, ...]:
    return tuple(
        rng.uniform(-0.65, 0.65) if k in INTERACTION_KEYS else rng.uniform(-0.45, 0.45)
        for k in ALL_KEYS
    )


def fmt_delta(d: dict) -> str:
    return (
        f"Gold {d['gold_delta']:+.1f}pp / Good {d['good_delta']:+.1f}pp / "
        f"Pass {d['pass_delta']:+.1f}pp / Place {d['place_delta']:+.1f}pp / "
        f"0H {d['0hit_delta']:+d} / 1H {d['1hit_delta']:+d}"
    )


def build_field_summary(horses: dict) -> dict:
    weights = []
    for horse in horses.values():
        try:
            weights.append(float(horse.get("weight")))
        except (TypeError, ValueError):
            continue
    return {
        "count": len(horses),
        "min_weight": min(weights) if weights else 0,
        "max_weight": max(weights) if weights else 0,
        "avg_weight": sum(weights) / len(weights) if weights else 0,
    }


def re_score_all():
    """Load archive, re-run engine on every horse, return race dicts with fresh scores."""
    historical_results = load_historical_results(HISTORICAL_RESULTS_CSV)
    races = []

    for meeting_dir in sorted(p for p in ARCHIVE_ROOT.iterdir() if p.is_dir()):
        logic_files = sorted(
            meeting_dir.glob("Race_*_Logic.json"),
            key=lambda p: parse_int(p.stem.split("_")[1], 999),
        )
        if not logic_files:
            continue
        sample = json.loads(logic_files[0].read_text(encoding="utf-8"))
        meeting_date = detect_meeting_date(meeting_dir)
        meeting_track = detect_meeting_track(meeting_dir, sample)
        if not meeting_date or not meeting_track:
            continue

        for logic_path in logic_files:
            logic = json.loads(logic_path.read_text(encoding="utf-8"))
            race_analysis = logic.get("race_analysis", {})
            race_no = parse_int(race_analysis.get("race_number")) or parse_int(logic_path.stem.split("_")[1])
            rows = choose_track_rows(historical_results.get((meeting_date, race_no), []), meeting_track)
            if not rows:
                continue
            lookup = {normalize_horse_name(row["horse_slug"]): row for row in rows}

            fresh_horses = []
            for hnum, horse in logic.get("horses", {}).items():
                row = lookup.get(normalize_horse_name(horse.get("horse_name", "")))
                if not row:
                    continue
                race_context = dict(race_analysis)
                race_context["field_summary"] = build_field_summary(logic.get("horses", {}))
                dummy_facts = str(meeting_dir / f"{meeting_date}_dummy.md")
                engine = RacingEngine(horse, race_context, horse.get("_data", {}).get("facts_section", ""), facts_path=dummy_facts)
                result = engine.analyze_horse()

                matrix_scores = result.get("matrix_scores") or {}
                ability_score = float(result.get("ability_score") or result.get("rank_score") or 0.0)
                feature_scores = result.get("feature_scores") or {}

                fresh_horses.append({
                    "horse_number": parse_int(hnum) or 999,
                    "horse_name": horse.get("horse_name", ""),
                    "ability_score": ability_score,
                    "rank_score": ability_score,
                    "actual_pos": int(row["pos"]),
                    "result_condition_bucket": condition_bucket(row.get("condition", "")),
                    "matrix_scores": {key: float(matrix_scores.get(key, 60.0)) for key in MATRIX_KEYS},
                    "feature_scores": feature_scores,
                    "barrier": parse_int(horse.get("barrier")),
                    "going": str(race_analysis.get("going", "") or ""),
                    "meeting_track": meeting_track,
                })

            if len(fresh_horses) < 4:
                continue

            races.append({
                "meeting": meeting_dir.name,
                "race_no": race_no,
                "meeting_track": meeting_track,
                "race_class_bucket": race_class_bucket(race_analysis.get("race_class")),
                "race_class": str(race_analysis.get("race_class") or ""),
                "field_size_bucket": field_size_bucket(len(fresh_horses)),
                "condition_bucket": pre_race_condition_bucket(race_analysis),
                "result_condition_bucket": fresh_horses[0].get("result_condition_bucket", ""),
                "going": str(race_analysis.get("going", "") or ""),
                "field_count": len(fresh_horses),
                "horses": fresh_horses,
            })

    print(f"Re-scored {len(races)} races with fresh engine ({sum(len(r['horses']) for r in races)} horses)")
    return races


def main():
    rng = random.Random(SEED)

    # Step 1: Re-score all archive races with current engine
    races = re_score_all()

    # Step 2: Build feature vectors
    for race in races:
        for horse in race["horses"]:
            vec = vector_for(horse, race)
            horse["_weight_vector"] = tuple(vec.get(k, 0.0) for k in ALL_KEYS)

    races.sort(key=lambda r: (r["meeting"], r["race_no"]))

    split_at = max(1, int(len(races) * 0.70))
    train = races[:split_at]
    valid = races[split_at:]

    train_base = evaluate_races(train, "train_base")[0]
    valid_base = evaluate_races(valid, "valid_base")[0]
    full_base = evaluate_races(races, "full_base")[0]

    print(f"Baseline full (fresh scores): "
          f"{report_summary(full_base, 'full')['gold']} Gold / "
          f"{report_summary(full_base, 'full')['good']} Good / "
          f"{report_summary(full_base, 'full')['pass']} Pass / "
          f"0H {report_summary(full_base, 'full')['0hit']}")

    # Step 3: Random search
    kept = []
    for _ in range(ITERATIONS):
        weights = random_weights(rng)
        tb = evaluate_weighted(train, weights)
        td = delta_report(train_base, tb)
        if td["pass_delta"] < 0 or td["0hit_delta"] > 2:
            continue
        score = objective(tb)
        kept.append((score, weights, td))
        kept.sort(key=lambda x: x[0], reverse=True)
        kept = kept[:TOP_KEEP]

    # Step 4: Validate
    validated = []
    for _, weights, td in kept:
        vb = evaluate_weighted(valid, weights)
        fb = evaluate_weighted(races, weights)
        vd = delta_report(valid_base, vb)
        fd = delta_report(full_base, fb)
        validated.append({
            "weights": weights,
            "train_delta": td,
            "valid_delta": vd,
            "full_delta": fd,
            "score": objective(vb),
        })

    validated.sort(key=lambda r: (r["valid_delta"]["pass_delta"], r["valid_delta"]["good_delta"], -r["valid_delta"]["0hit_delta"], r["valid_delta"]["place_delta"]), reverse=True)

    # Step 5: Report
    md = [
        "# AU Auto Market-Free Weight Search (Fresh Scores)",
        "",
        "- Re-scored all archive races with current mainline engine (P5+P4 + gate removal).",
        f"- Random seed: `{SEED}`",
        f"- Iterations: `{ITERATIONS}`",
        f"- Split: train `{len(train)}` races / validation `{len(valid)}` races",
        "",
        "## Baseline (Fresh Scores)",
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
        nz = [(k, v) for k, v in zip(ALL_KEYS, row["weights"]) if abs(v) >= 0.08]
        wt = "; ".join(f"{k} {v:+.2f}" for k, v in nz)
        md.append(f"| {idx} | {fmt_delta(row['valid_delta'])} | {fmt_delta(row['full_delta'])} | {wt} |")

    promote = [
        row for row in validated
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
        md.append("No candidate improved validation Pass/Good while keeping 0-hit flat or lower on both splits.")

    OUTPUT_MD.write_text("\n".join(md), encoding="utf-8")

    print(f"Candidates kept: {len(kept)}")
    if validated:
        print(f"Best validation: {fmt_delta(validated[0]['valid_delta'])}")
        print(f"Best full: {fmt_delta(validated[0]['full_delta'])}")
    print(f"Promotion candidates: {len(promote)}")
    print(f"Report: {OUTPUT_MD}")


if __name__ == "__main__":
    main()
