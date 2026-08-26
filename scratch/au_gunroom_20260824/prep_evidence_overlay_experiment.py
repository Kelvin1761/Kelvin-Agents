#!/usr/bin/env python3
"""Test a narrow prep-stage × evidence × volatile-support risk rail.

Candidate scope:
* the current model top pick returned within a short window after a long spell;
* that return run was unplaced;
* multiple scored leaves remain at the neutral/no-evidence default; and
* a large share of the score above neutral comes from wet-form and pace-performance.

The action is rank-only: demote the risky top pick by one or two positions.  It
never changes the top-three membership when two positions are selected.  Search
uses development dates only; the contract holdout is evaluated once after lock.
No market or starting-price field is read.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import au_eval  # noqa: E402
from au_racing_engine.scoring import MATRIX_WEIGHTS  # noqa: E402
from post_spell_experiment import annotate as annotate_spell  # noqa: E402
from post_spell_experiment import official_runs, parse_date  # noqa: E402


SCORED_LEAVES = (
    "form_score",
    "performance_quality_score",
    "pace_figure_score",
    "trial_score",
    "jockey_score",
    "trainer_score",
    "jockey_horse_fit_score",
    "rating_score",
    "track_score",
)


def default_leaf_count(features: dict) -> int:
    count = 0
    for key in SCORED_LEAVES:
        value = features.get(key)
        if value is None:
            continue
        try:
            if abs(float(value) - 60.0) < 0.005:
                count += 1
        except (TypeError, ValueError):
            continue
    return count


def volatile_support(row: dict) -> tuple[float, float, float]:
    matrices = au_eval.matrix_mapper.map_features_to_matrix_scores(row["features"])
    pace_lift = max(
        0.0,
        (float(matrices.get("pace_perf", 60.0)) - 60.0)
        * float(MATRIX_WEIGHTS.get("pace_perf", 0.0)),
    )
    wet_lift = max(0.0, float(row.get("wet") or 0.0))
    lift = pace_lift + wet_lift
    score_lift = max(float(row["_base_score"]) - 60.0, 0.5)
    return pace_lift, wet_lift, lift / score_lift


def annotate(races: list[dict]) -> None:
    annotate_spell(races)
    for race in races:
        for row in race["rows"]:
            row["_base_score"] = float(au_eval.default_scorer(row))
            row["_default_count"] = default_leaf_count(row["features"])
            pace_lift, wet_lift, volatile_share = volatile_support(row)
            row["_pace_lift"] = pace_lift
            row["_wet_lift"] = wet_lift
            row["_volatile_share"] = volatile_share


def post_risk(row: dict, spell_min: int, since_max: int) -> bool:
    info = row.get("post_spell") or {}
    return bool(
        info.get("prior_spell_days", 0) >= spell_min
        and 0 < info.get("days_since_return", 9999) <= since_max
        and info.get("return_unplaced")
    )


def qualifies(
    row: dict,
    *,
    spell_min: int,
    since_max: int,
    default_min: int,
    share_min: float,
    conditions: frozenset[str] = frozenset({"post", "thin", "volatile"}),
) -> bool:
    checks = {
        "post": post_risk(row, spell_min, since_max),
        "thin": int(row.get("_default_count", 0)) >= default_min,
        "volatile": float(row.get("_volatile_share", 0.0)) >= share_min,
    }
    return all(checks[name] for name in conditions)


def configure_candidate(
    races: list[dict],
    *,
    spell_min: int,
    since_max: int,
    default_min: int,
    share_min: float,
    demote_positions: int,
    conditions: frozenset[str] = frozenset({"post", "thin", "volatile"}),
) -> list[dict]:
    triggers = []
    for race in races:
        for row in race["rows"]:
            row["_candidate_score"] = row["_base_score"]
        order = sorted(race["rows"], key=lambda row: row["_base_score"], reverse=True)
        if len(order) <= demote_positions:
            continue
        top = order[0]
        if not qualifies(
            top,
            spell_min=spell_min,
            since_max=since_max,
            default_min=default_min,
            share_min=share_min,
            conditions=conditions,
        ):
            continue

        target_index = demote_positions
        upper = float(order[target_index]["_base_score"])
        if len(order) > target_index + 1:
            lower = float(order[target_index + 1]["_base_score"])
            candidate_score = (upper + lower) / 2.0
        else:
            candidate_score = upper - 1e-6
        top["_candidate_score"] = candidate_score
        triggers.append(
            {
                "date": race.get("date"),
                "track": (race.get("metadata") or {}).get("track"),
                "race_number": (race.get("metadata") or {}).get("race_number"),
                "horse": top.get("horse_name"),
                "actual_pos": top.get("pos"),
                "base_score": top["_base_score"],
                "candidate_score": candidate_score,
                "default_count": top["_default_count"],
                "volatile_share": top["_volatile_share"],
                "pace_lift": top["_pace_lift"],
                "wet_lift": top["_wet_lift"],
                "post_spell": top.get("post_spell"),
            }
        )
    return triggers


def base_scorer(row: dict) -> float:
    return float(row["_base_score"])


def candidate_scorer(row: dict) -> float:
    return float(row["_candidate_score"])


def time_folds(races: list[dict], indices: list[int], count: int = 5) -> list[list[int]]:
    dates = sorted({races[index].get("date") for index in indices})
    folds = []
    for fold in range(count):
        lo = math.floor(len(dates) * fold / count)
        hi = math.floor(len(dates) * (fold + 1) / count)
        chosen = set(dates[lo:hi])
        folds.append([index for index in indices if races[index].get("date") in chosen])
    return folds


def auc_delta(races: list[dict], indices: list[int], base_pairs=None) -> float:
    base_pairs = base_pairs or au_eval._pairs(races, base_scorer, True)
    candidate_pairs = au_eval._pairs(races, candidate_scorer, True)
    return (
        au_eval._auc_indices(candidate_pairs, indices)
        - au_eval._auc_indices(base_pairs, indices)
    )


def trigger_summary(triggers: list[dict], allowed_dates: set[str]) -> str:
    chosen = [row for row in triggers if row["date"] in allowed_dates]
    placed = sum(int(row.get("actual_pos") or 999) <= 3 for row in chosen)
    won = sum(int(row.get("actual_pos") or 999) == 1 for row in chosen)
    rate = 100.0 * placed / len(chosen) if chosen else float("nan")
    return f"n={len(chosen)}, placed={placed} ({rate:.2f}%), won={won}"


def metric_deltas(races: list[dict], indices: list[int]) -> dict:
    subset = [races[index] for index in indices]
    base = au_eval._counts(subset, base_scorer)
    candidate = au_eval._counts(subset, candidate_scorer)
    return {key: round(candidate[key] - base[key], 4) for key in candidate if key in base}


def field_bucket_deltas(races: list[dict], indices: list[int]) -> dict:
    subset = [races[index] for index in indices]
    base = au_eval._counts_by_field(subset, base_scorer)
    candidate = au_eval._counts_by_field(subset, candidate_scorer)
    output = {}
    for bucket, candidate_row in candidate.items():
        base_row = base.get(bucket) or {}
        output[bucket] = {
            key: round(value - base_row.get(key, value), 4)
            for key, value in candidate_row.items()
            if key != "races"
        }
        output[bucket]["races"] = candidate_row.get("races", 0)
    return output


def evaluate_randwick_r1(meeting_dir: Path, params: dict) -> dict:
    logic = json.loads((meeting_dir / "Race_1_Logic.json").read_text(encoding="utf-8"))
    csv_rows = {}
    with (meeting_dir / "Meeting_Auto_Scoring.csv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if int(row["race_number"]) == 1:
                csv_rows[str(row["horse_number"])] = row

    target_date = parse_date("2026-08-22")
    rows = []
    for horse_no, horse in (logic.get("horses") or {}).items():
        auto = horse.get("python_auto") or {}
        source = csv_rows.get(str(horse_no))
        if not source:
            continue
        facts = (horse.get("_data") or {}).get("facts_section", "")
        history = [run for run in official_runs(facts) if run["date"] < target_date]
        post = None
        if len(history) >= 2:
            post = {
                "days_since_return": (target_date - history[0]["date"]).days,
                "prior_spell_days": (history[0]["date"] - history[1]["date"]).days,
                "return_unplaced": bool(history[0]["unplaced"]),
                "return_finish": history[0]["finish"],
            }
        matrix_scores = auto.get("matrix_scores") or {}
        score = float(source["ability_score"])
        pace_lift = max(
            0.0,
            (float(matrix_scores.get("pace_perf", 60.0)) - 60.0)
            * float(MATRIX_WEIGHTS.get("pace_perf", 0.0)),
        )
        wet_lift = max(0.0, float(source.get("wet_form_feature") or 0.0))
        rows.append(
            {
                "horse_no": int(horse_no),
                "horse_name": source["horse_name"],
                "_base_score": score,
                "_candidate_score": score,
                "_default_count": default_leaf_count(auto.get("feature_scores") or {}),
                "_pace_lift": pace_lift,
                "_wet_lift": wet_lift,
                "_volatile_share": (pace_lift + wet_lift) / max(score - 60.0, 0.5),
                "post_spell": post,
            }
        )

    race = {"date": "2026-08-22", "metadata": {"track": "Randwick", "race_number": 1}, "rows": rows}
    triggers = configure_candidate([race], **params)
    original = sorted(rows, key=lambda row: row["_base_score"], reverse=True)
    candidate = sorted(rows, key=lambda row: row["_candidate_score"], reverse=True)
    gunroom = next(row for row in rows if row["horse_name"].lower() == "gunroom")
    return {
        "triggered": bool(triggers),
        "gunroom_diagnostics": {
            key: gunroom.get(key)
            for key in (
                "_base_score",
                "_candidate_score",
                "_default_count",
                "_pace_lift",
                "_wet_lift",
                "_volatile_share",
                "post_spell",
            )
        },
        "original_top5": [
            [rank, row["horse_name"], round(row["_base_score"], 4)]
            for rank, row in enumerate(original[:5], 1)
        ],
        "candidate_top5": [
            [rank, row["horse_name"], round(row["_candidate_score"], 4)]
            for rank, row in enumerate(candidate[:5], 1)
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset")
    parser.add_argument("--randwick-dir", type=Path)
    args = parser.parse_args()

    races = au_eval.load_races(args.dataset)
    annotate(races)
    dev, holdout = au_eval.date_partitions(races)
    dev_dates = {races[index]["date"] for index in dev}
    holdout_dates = {races[index]["date"] for index in holdout}
    folds = time_folds(races, dev)
    base_pairs = au_eval._pairs(races, base_scorer, True)

    candidates = []
    for spell_min in (90, 120, 180):
        for since_max in (21, 30, 45):
            for default_min in (1, 2):
                for share_min in (0.30, 0.40, 0.50):
                    for demote_positions in (1, 2):
                        params = {
                            "spell_min": spell_min,
                            "since_max": since_max,
                            "default_min": default_min,
                            "share_min": share_min,
                            "demote_positions": demote_positions,
                        }
                        triggers = configure_candidate(races, **params)
                        dev_trigger_count = sum(row["date"] in dev_dates for row in triggers)
                        if dev_trigger_count == 0:
                            continue
                        delta = auc_delta(races, dev, base_pairs)
                        fold_deltas = [auc_delta(races, fold, base_pairs) for fold in folds]
                        candidates.append(
                            {
                                "params": params,
                                "dev_delta": delta,
                                "fold_deltas": fold_deltas,
                                "fold_nonnegative": sum(value >= 0 for value in fold_deltas),
                                "dev_triggers": dev_trigger_count,
                            }
                        )

    powered = [row for row in candidates if row["dev_triggers"] >= 8]
    eligible = [
        row for row in candidates
        if row["dev_triggers"] >= 8
        and row["dev_delta"] >= 0
        and row["fold_nonnegative"] >= 4
    ]
    search_pool = eligible or powered or candidates
    chosen = max(
        search_pool,
        key=lambda row: (
            row["dev_delta"],
            row["fold_nonnegative"],
            -row["params"]["demote_positions"],
        ),
    )
    params = chosen["params"]
    triggers = configure_candidate(races, **params)

    print(f"races={len(races)} dev={len(dev)} holdout={len(holdout)}")
    print(
        f"powered_candidates={len(powered)} eligible_candidates={len(eligible)} "
        f"underpowered_search={not bool(powered)}"
    )
    print("top development candidates (holdout unseen):")
    for row in sorted(candidates, key=lambda item: item["dev_delta"], reverse=True)[:15]:
        print(
            f"  {row['params']} dev={row['dev_delta']:+.6f} "
            f"folds={row['fold_nonnegative']}/5 "
            f"[{', '.join(f'{value:+.5f}' for value in row['fold_deltas'])}] "
            f"triggers={row['dev_triggers']}"
        )

    print("\nlocked candidate:")
    print(json.dumps(chosen, ensure_ascii=False, indent=2))
    print("dev trigger cohort:", trigger_summary(triggers, dev_dates))
    print("\none-shot contract holdout:")
    verdict = au_eval.compare(races, base_scorer, candidate_scorer, label="prep_evidence_volatile_rank_rail")
    print(verdict)
    print("holdout trigger cohort:", trigger_summary(triggers, holdout_dates))
    print("all metric deltas:", json.dumps(metric_deltas(races, list(range(len(races)))), ensure_ascii=False))
    print("dev metric deltas:", json.dumps(metric_deltas(races, dev), ensure_ascii=False))
    print("holdout metric deltas:", json.dumps(metric_deltas(races, holdout), ensure_ascii=False))
    print("holdout field buckets:", json.dumps(field_bucket_deltas(races, holdout), ensure_ascii=False, indent=2))

    print("\nablation at locked thresholds:")
    ablations = (
        ("post", frozenset({"post"})),
        ("thin", frozenset({"thin"})),
        ("volatile", frozenset({"volatile"})),
        ("post+thin", frozenset({"post", "thin"})),
        ("post+volatile", frozenset({"post", "volatile"})),
        ("thin+volatile", frozenset({"thin", "volatile"})),
        ("all_three", frozenset({"post", "thin", "volatile"})),
    )
    for label, conditions in ablations:
        ablation_triggers = configure_candidate(races, **params, conditions=conditions)
        result = au_eval.compare(
            races,
            base_scorer,
            candidate_scorer,
            label=label,
            with_counts=False,
        )
        print(
            f"  {label:13s} dev={result.top_dev:+.6f} "
            f"hold={result.top_hold:+.6f} "
            f"ci=[{result.top_hold_ci[0]:+.6f},{result.top_hold_ci[1]:+.6f}] "
            f"ship={result.ship} triggers_dev={sum(x['date'] in dev_dates for x in ablation_triggers)} "
            f"triggers_hold={sum(x['date'] in holdout_dates for x in ablation_triggers)}"
        )

    strict_params = {
        "spell_min": 180,
        "since_max": 30,
        "default_min": 2,
        "share_min": 0.40,
        "demote_positions": 2,
    }
    strict_triggers = configure_candidate(races, **strict_params)
    strict_result = au_eval.compare(
        races,
        base_scorer,
        candidate_scorer,
        label="gunroom_shaped_strict_rule",
    )
    print("\npre-declared strict Gunroom-shaped rule:")
    print(json.dumps(strict_params, ensure_ascii=False))
    print(strict_result)
    print("dev trigger cohort:", trigger_summary(strict_triggers, dev_dates))
    print("holdout trigger cohort:", trigger_summary(strict_triggers, holdout_dates))

    # The locked three-way interaction is too rare to evaluate.  As a declared
    # ablation follow-up, search the less sparse post+volatile interaction on
    # development only.  Its holdout is exploratory because the locked
    # three-way run above has already exposed two related terminal cases.
    secondary_candidates = []
    post_volatile = frozenset({"post", "volatile"})
    for spell_min in (60, 90, 120, 180):
        for since_max in (21, 30, 45):
            for share_min in (0.20, 0.30, 0.40, 0.50):
                for demote_positions in (1, 2):
                    secondary_params = {
                        "spell_min": spell_min,
                        "since_max": since_max,
                        "default_min": 1,
                        "share_min": share_min,
                        "demote_positions": demote_positions,
                    }
                    secondary_triggers = configure_candidate(
                        races,
                        **secondary_params,
                        conditions=post_volatile,
                    )
                    trigger_count = sum(row["date"] in dev_dates for row in secondary_triggers)
                    if trigger_count < 8:
                        continue
                    delta = auc_delta(races, dev, base_pairs)
                    fold_deltas = [auc_delta(races, fold, base_pairs) for fold in folds]
                    secondary_candidates.append(
                        {
                            "params": secondary_params,
                            "dev_delta": delta,
                            "fold_deltas": fold_deltas,
                            "fold_nonnegative": sum(value >= 0 for value in fold_deltas),
                            "dev_triggers": trigger_count,
                        }
                    )
    secondary_eligible = [
        row for row in secondary_candidates
        if row["dev_delta"] >= 0 and row["fold_nonnegative"] >= 4
    ]
    print("\nsecondary post+volatile development search:")
    if secondary_eligible:
        secondary = max(
            secondary_eligible,
            key=lambda row: (
                row["dev_delta"],
                row["fold_nonnegative"],
                -row["params"]["demote_positions"],
            ),
        )
        secondary_triggers = configure_candidate(
            races,
            **secondary["params"],
            conditions=post_volatile,
        )
        secondary_result = au_eval.compare(
            races,
            base_scorer,
            candidate_scorer,
            label="post_volatile_secondary_exploratory",
        )
        print(json.dumps(secondary, ensure_ascii=False, indent=2))
        print(secondary_result)
        print("dev trigger cohort:", trigger_summary(secondary_triggers, dev_dates))
        print("holdout trigger cohort:", trigger_summary(secondary_triggers, holdout_dates))
    else:
        print("no candidate had >=8 development triggers, non-negative dev, and >=4/5 non-negative folds")

    # Restore the locked all-three candidate after the ablation mutations.
    configure_candidate(races, **params)
    if args.randwick_dir:
        print("\nRandwick R1 frozen pre-race snapshot:")
        print(json.dumps(evaluate_randwick_r1(args.randwick_dir, params), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
