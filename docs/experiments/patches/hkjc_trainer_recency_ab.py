#!/usr/bin/env python3
"""Strict-PIT trainer-recency A/B for EXP-20261005-01.

Research only: no Logic, scoring, stats or scheduler artifact is modified.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd


REPO = Path(__file__).resolve().parents[3]
REFLECTOR = REPO / ".agents/skills/hkjc_racing/hkjc_reflector/scripts"
SHARED = REPO / ".agents/skills/shared_racing/scripts"
for path in (REFLECTOR, SHARED, REPO):
    sys.path.insert(0, str(path))

import pit_backtest as pit  # noqa: E402
import rescore_backtest as bt  # noqa: E402
from corpus_paths import meeting_dirs  # noqa: E402
from hkjc_racing_engine import engine_core, live_priors  # noqa: E402
from hkjc_racing_engine.live_priors import JT_RATING_PARAMS  # noqa: E402
from wongchoi_paths import HK_RACING, is_materialized_file  # noqa: E402


HALF_LIVES = (90, 180, 365)
DEV_START, DEV_END = "2026-05-06", "2026-06-13"
TERMINAL_START, TERMINAL_END = "2026-06-21", "2026-07-12"
NEW_START, NEW_END = "2026-09-06", "2026-10-01"
BOOTSTRAP_DRAWS = 5000
BOOTSTRAP_SEED = 20261005


def build_recency_trainer_ratings(
    prior_rows: pd.DataFrame,
    target_date: str,
    half_life_days: int,
) -> dict[str, dict[str, float]]:
    """Build production-math trainer ratings with date-decayed row weights."""
    target = pd.Timestamp(target_date)
    rows = prior_rows.copy()
    dates = pd.to_datetime(rows["Date"], errors="raise")
    if (dates >= target).any():
        raise ValueError("recency prior received target-day/future rows")
    age_days = (target - dates).dt.days.astype(float)
    if (age_days <= 0).any():
        raise ValueError("recency prior age must be strictly positive")
    rows["_w"] = np.power(0.5, age_days / float(half_life_days))
    rows["_wins"] = pd.to_numeric(rows["Win"], errors="coerce").fillna(0.0) * rows["_w"]
    rows["_places"] = pd.to_numeric(rows["Place"], errors="coerce").fillna(0.0) * rows["_w"]
    rows["Trainer"] = rows["Trainer"].astype(str).str.strip()
    rows = rows[rows["Trainer"] != ""]
    grouped = rows.groupby("Trainer")[["_wins", "_places", "_w"]].sum().reset_index()
    total = float(grouped["_w"].sum()) or 1.0
    global_win = float(grouped["_wins"].sum()) / total
    global_place = float(grouped["_places"].sum()) / total
    params = JT_RATING_PARAMS
    output: dict[str, dict[str, float]] = {}
    for row in grouped.to_dict("records"):
        starts = float(row["_w"])
        if starts <= 0:
            continue
        score = pit._eb_score(
            float(row["_wins"]),
            starts,
            float(row["_places"]),
            global_win,
            global_place,
            float(params["trainer_neg_scale"]),
            float(params["trainer_floor"]),
        )
        output[str(row["Trainer"])] = {
            "score": score,
            "starts": starts,
            "win_rate": float(row["_wins"]) / starts * 100.0,
            "place_rate": float(row["_places"]) / starts * 100.0,
        }
    return output


def _is_debut(horse: dict) -> bool:
    return bool(
        horse.get("is_debut")
        or horse.get("debut_runner")
        or horse.get("career_tag") == "DEBUT"
    )


def _is_st_turf(context: dict) -> bool:
    venue = " ".join(
        str(context.get(key) or "")
        for key in ("venue", "course", "racecourse")
    ).upper()
    surface = " ".join(
        str(context.get(key) or "")
        for key in ("venue", "track", "surface", "track_type")
    ).upper()
    is_st = "沙田" in venue or "SHA TIN" in venue or "SHATIN" in venue
    is_awt = any(token in surface for token in ("AWT", "ALL WEATHER", "全天候", "泥地"))
    return is_st and not is_awt


def _score_logic(
    logic: dict,
    baseline_ratings: pit._Ratings,
    candidate_ratings: pit._Ratings | None,
) -> dict:
    """Production-equivalent score with a per-horse trainer-rating switch."""
    scored = copy.deepcopy(logic)
    context = scored.get("race_analysis", {})
    horses = scored.get("horses", {})
    bt._enrich_horse_headers(horses, {}, keep_embedded_combo_prior=False)
    if isinstance(context, dict):
        context["field_horse_names"] = [
            horse.get("horse_name")
            for horse in horses.values()
            if isinstance(horse, dict) and horse.get("horse_name")
        ]
    candidate_race = candidate_ratings is not None and _is_st_turf(context)
    for horse in horses.values():
        if not isinstance(horse, dict):
            continue
        live_priors._JT_RATINGS = (
            candidate_ratings
            if candidate_race and not _is_debut(horse)
            else baseline_ratings
        )
        horse["python_auto"] = bt.RacingEngine(horse, context).analyze_horse()
    bt._apply_sip_enhancements(horses)
    bt.ensure_verdict(scored)
    return scored


def _race_record(scored: dict, actual: dict[int, int], race_key: str, cohort: str) -> dict:
    ranked = []
    for horse_number, horse in (scored.get("horses") or {}).items():
        try:
            ranked.append(
                (
                    int(horse_number),
                    float(horse["python_auto"]["ability_score"]),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    ranked.sort(key=lambda item: (-item[1], item[0]))
    order = [horse for horse, _score in ranked]
    top3 = {horse for horse, pos in actual.items() if pos <= 3}
    best = min(actual.values())
    winners = {horse for horse, pos in actual.items() if pos == best}
    model_rank = {horse: index for index, horse in enumerate(order, start=1)}
    top3_ranks = [model_rank.get(horse, len(order) + 1) for horse in top3]
    picks4, picks5 = order[:4], order[:5]

    gains = []
    for horse in picks5:
        position = actual.get(horse, 999)
        gains.append(3.0 if position == 1 else 2.0 if position == 2 else 1.0 if position == 3 else 0.0)
    ideal = sorted(gains, reverse=True)

    def dcg(values: list[float]) -> float:
        return sum((2.0 ** value - 1.0) / math.log2(index + 2.0) for index, value in enumerate(values))

    ideal_dcg = dcg(ideal)
    candidate_top = picks5
    positive = [horse for horse in candidate_top if horse in top3]
    negative = [horse for horse in candidate_top if horse not in top3]
    comparisons = [
        float(model_rank[pos] < model_rank[neg])
        for pos in positive
        for neg in negative
    ]
    hits3 = sum(horse in top3 for horse in order[:3])
    return {
        "race_key": race_key,
        "cohort": cohort,
        "field_size": len(actual),
        "canonical_gold": float(bool(top3) and top3.issubset(set(picks4))),
        "gold_strict": float(len(order) >= 3 and all(horse in top3 for horse in order[:3])),
        "good_positional": float(len(order) >= 2 and order[0] in top3 and order[1] in top3),
        "min_threshold": float(hits3 >= 2),
        "single": float(hits3 >= 1),
        "champion": float(bool(order) and order[0] in winners),
        "winner_in_top3": float(bool(winners & set(order[:3]))),
        "top3_capture_at5": float(len(top3 & set(picks5)) / len(top3)) if top3 else 0.0,
        "mean_top3_model_rank": float(np.mean(top3_ranks)) if top3_ranks else 0.0,
        "ndcg_at5": float(dcg(gains) / ideal_dcg) if ideal_dcg else 0.0,
        "top5_pairwise_auc": float(np.mean(comparisons)) if comparisons else 0.5,
    }


METRICS = (
    "canonical_gold",
    "gold_strict",
    "good_positional",
    "min_threshold",
    "single",
    "champion",
    "winner_in_top3",
    "top3_capture_at5",
    "mean_top3_model_rank",
    "ndcg_at5",
    "top5_pairwise_auc",
)


def _summary(rows: list[dict]) -> dict:
    result = {"races": len(rows)}
    if not rows:
        return result
    for metric in METRICS:
        value = float(np.mean([row[metric] for row in rows]))
        result[metric] = round(value if metric == "mean_top3_model_rank" else value * 100.0, 4)
    return result


def _paired(candidate: list[dict], baseline: list[dict]) -> dict:
    base_by_key = {row["race_key"]: row for row in baseline}
    pairs = [(base_by_key[row["race_key"]], row) for row in candidate if row["race_key"] in base_by_key]
    output = {"races": len(pairs)}
    if not pairs:
        return output
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    for metric in METRICS:
        delta = np.asarray([cand[metric] - base[metric] for base, cand in pairs], dtype=float)
        draws = np.empty(BOOTSTRAP_DRAWS, dtype=float)
        for index in range(BOOTSTRAP_DRAWS):
            sample = rng.integers(0, len(delta), size=len(delta))
            draws[index] = float(delta[sample].mean())
        scale = 1.0 if metric == "mean_top3_model_rank" else 100.0
        output[metric] = {
            "delta": round(scale * float(delta.mean()), 4),
            "ci95": [
                round(scale * float(np.quantile(draws, 0.025)), 4),
                round(scale * float(np.quantile(draws, 0.975)), 4),
            ],
        }
    return output


def _field_bucket(size: int) -> str:
    if size <= 8:
        return "lte8"
    if size <= 10:
        return "9_10"
    if size <= 12:
        return "11_12"
    return "13plus"


def _partition(date_value: str) -> str | None:
    if DEV_START <= date_value <= DEV_END:
        return "dev"
    if TERMINAL_START <= date_value <= TERMINAL_END:
        return "terminal"
    if NEW_START <= date_value <= NEW_END:
        return "new_season_diagnostic"
    return None


def _score_meeting(
    meeting: Path,
    all_rows: pd.DataFrame,
    half_lives: tuple[int, ...],
) -> tuple[dict[str, list[dict]], list[str], dict]:
    meeting_date = pit.meeting_date_from_dir(meeting)
    prior_count = pit.inject_as_of(all_rows, meeting_date)
    baseline_ratings = live_priors._JT_RATINGS
    prior_rows = all_rows[all_rows["Date"] < meeting_date].copy()
    recency = {
        half_life: pit._Ratings(
            baseline_ratings.jockey,
            build_recency_trainer_ratings(prior_rows, meeting_date, half_life),
            meeting_date,
        )
        for half_life in half_lives
    }
    result_path = bt.find_results_json(meeting)
    if result_path is None:
        return {}, [], {"meeting": meeting.name, "prior_rows": prior_count, "races": 0}
    actual = bt.load_results(result_path)
    arms: dict[str, list[dict]] = defaultdict(list)
    errors: list[str] = []
    for logic_path in sorted(meeting.glob("Race_*_Logic.json"), key=bt.race_num_from_path):
        if not is_materialized_file(logic_path):
            continue
        race_number = bt.race_num_from_path(logic_path)
        if race_number not in actual:
            continue
        logic = json.loads(logic_path.read_text(encoding="utf-8"))
        try:
            context = bt.resolve_meeting_context(logic, meeting)
            cohort = "ST_TURF" if _is_st_turf(context) else (
                "ST_AWT" if "ShaTin" in meeting.name else "HV_TURF"
            )
            race_key = f"{meeting.name}/R{race_number}"
            for arm, candidate in [("baseline", None)] + [
                (f"hl{half_life}", recency[half_life]) for half_life in half_lives
            ]:
                scored = _score_logic(logic, baseline_ratings, candidate)
                arms[arm].append(_race_record(scored, actual[race_number], race_key, cohort))
        except Exception as exc:  # research report must retain every failure
            errors.append(f"{meeting.name} R{race_number}: {exc}")
    live_priors._JT_RATINGS = baseline_ratings
    return arms, errors, {
        "meeting": meeting.name,
        "prior_rows": prior_count,
        "latest_prior_date": str(prior_rows["Date"].max()) if len(prior_rows) else "",
        "races": len(arms.get("baseline", [])),
    }


def _select_dev(report: dict) -> str | None:
    eligible = []
    for half_life in HALF_LIVES:
        arm = f"hl{half_life}"
        delta = report["partitions"]["dev"][arm]["paired_delta"]
        gold = delta["canonical_gold"]["delta"]
        good = delta["good_positional"]["delta"]
        if gold < 0 or good < 0:
            continue
        eligible.append(
            (
                gold,
                good,
                delta["ndcg_at5"]["delta"],
                delta["top3_capture_at5"]["delta"],
                half_life,
                arm,
            )
        )
    if not eligible:
        return None
    return max(eligible)[-1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    all_rows = pit.load_all_rows()
    targets = sorted(
        path
        for path in meeting_dirs(HK_RACING)
        if _partition(path.name[:10]) is not None
        and bt.find_results_json(path) is not None
        and not bt.meeting_is_legacy_schema(path)
    )
    collected: dict[str, dict[str, list[dict]]] = {
        partition: defaultdict(list)
        for partition in ("dev", "terminal", "new_season_diagnostic")
    }
    meetings = []
    errors = []
    for target in targets:
        partition = _partition(target.name[:10])
        meeting_arms, meeting_errors, manifest = _score_meeting(target, all_rows, HALF_LIVES)
        manifest["partition"] = partition
        meetings.append(manifest)
        errors.extend(meeting_errors)
        for arm, rows in meeting_arms.items():
            collected[partition][arm].extend(rows)

    report = {
        "experiment": "EXP-20261005-01",
        "mode": "strict_point_in_time_research_only",
        "half_lives": list(HALF_LIVES),
        "scope": "Sha Tin turf non-debut trainer master rating only",
        "cutoff_rule": "Date < target meeting date",
        "partitions": {},
        "meetings": meetings,
        "errors": errors,
    }
    for partition, arms in collected.items():
        baseline = arms["baseline"]
        partition_payload = {
            "baseline": {"summary": _summary(baseline)},
        }
        for half_life in HALF_LIVES:
            arm = f"hl{half_life}"
            candidate = arms[arm]
            field_payload = {}
            for bucket in ("lte8", "9_10", "11_12", "13plus"):
                b_rows = [row for row in baseline if _field_bucket(row["field_size"]) == bucket]
                c_rows = [row for row in candidate if _field_bucket(row["field_size"]) == bucket]
                field_payload[bucket] = {
                    "baseline": _summary(b_rows),
                    "candidate": _summary(c_rows),
                    "paired_delta": _paired(c_rows, b_rows),
                }
            cohort_payload = {}
            for cohort in ("ST_TURF", "ST_AWT", "HV_TURF"):
                b_rows = [row for row in baseline if row["cohort"] == cohort]
                c_rows = [row for row in candidate if row["cohort"] == cohort]
                cohort_payload[cohort] = {
                    "baseline": _summary(b_rows),
                    "candidate": _summary(c_rows),
                    "paired_delta": _paired(c_rows, b_rows),
                }
            no_op_rows = [
                row for row in candidate
                if row["cohort"] in {"ST_AWT", "HV_TURF"}
            ]
            no_op_keys = {row["race_key"] for row in no_op_rows}
            no_op_base = [row for row in baseline if row["race_key"] in no_op_keys]
            no_op_delta = _paired(no_op_rows, no_op_base)
            partition_payload[arm] = {
                "summary": _summary(candidate),
                "paired_delta": _paired(candidate, baseline),
                "field_size": field_payload,
                "cohort": cohort_payload,
                "no_op_integrity": {
                    "races": len(no_op_rows),
                    "all_metric_deltas_zero": all(
                        no_op_delta[metric]["delta"] == 0.0 for metric in METRICS
                    ) if no_op_rows else True,
                },
            }
        report["partitions"][partition] = partition_payload

    report["dev_selected_arm"] = _select_dev(report)
    selected = report["dev_selected_arm"]
    if selected:
        terminal_delta = report["partitions"]["terminal"][selected]["paired_delta"]
        primary_regression = any(
            terminal_delta[metric]["delta"] < 0
            for metric in ("canonical_gold", "good_positional")
        )
        report["decision"] = (
            "REJECT_PRIMARY_REGRESSION"
            if primary_regression
            else "FORWARD_SHADOW_ONLY_RETROSPECTIVE_NOT_BLIND"
        )
    else:
        report["decision"] = "REJECT_NO_DEV_ELIGIBLE_ARM"

    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
