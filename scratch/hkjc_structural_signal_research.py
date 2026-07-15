#!/usr/bin/env python3
"""Market-free HKJC structural signal research.

Research-only: this script reads the frozen horse-level ranking dataset and
performs rolling-origin tests.  It never changes the live 7D engine.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import warnings
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import binomtest, wilcoxon
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)
warnings.filterwarnings("ignore", message="Skipping features without any observed values")


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = (
    ROOT
    / ".agents/skills/hkjc_racing/hkjc_reflector/artifacts/hkjc_ranking_dataset.csv"
)
DEFAULT_OUTPUT = ROOT / "scratch/hkjc_structural_signal_research.json"

BASELINE = "current_live_rank_score"
MIN_TRAIN_MEETINGS = 5
RNG_SEED = 20260713


BLOCKS: dict[str, list[str]] = {
    "official_rating": [
        "card_rating",
        "card_rating_change",
        "card_age",
        "card_priority_rank",
        "weight_carried",
        "card_claim_lbs",
        "card_declared_bodyweight",
    ],
    "distance_course_record": [
        "same_distance_starts",
        "same_distance_wins",
        "same_distance_seconds",
        "same_distance_thirds",
        "same_venue_distance_starts",
        "same_venue_distance_wins",
        "same_venue_distance_seconds",
        "same_venue_distance_thirds",
        "season_starts",
        "season_wins",
        "season_seconds",
        "season_thirds",
        "flag_best_distance_match",
        "flag_best_distance_unproven",
    ],
    "trackwork_trial": [
        "tw_entries_count",
        "tw_gallop_count",
        "tw_flags_count",
        "tw_confidence_low",
        "tw_jockey_present",
        "flag_trackwork_slowing",
        "flag_medical_issue",
        "days_since_last",
    ],
    "gear": [
        "card_gear_count",
        "card_gear_first_time",
        "card_gear_tt",
        "card_gear_cp",
        "card_gear_blinkers",
    ],
    "trip_hidden_merit": [
        "raw_last_finish",
        "raw_last_margin",
        "flag_hidden_form",
        "flag_forgiveness",
        "flag_position_up",
        "flag_position_down",
        "flag_finish_competitive",
        "flag_finish_slow",
        "flag_margin_narrowing",
        "flag_margin_widening",
    ],
    "variant_sectional": [
        "raw_finish_time_adj",
        "raw_l400",
        "flag_energy_up",
        "flag_energy_down",
        "flag_l400_up",
        "flag_l400_down",
        "flag_finish_competitive",
        "flag_finish_slow",
    ],
    "historical_professional_priors": [
        "prior_combo_starts",
        "prior_combo_win_rate",
        "prior_combo_place_rate",
        "prior_jockey_cd_starts",
        "prior_jockey_cd_win_rate",
        "prior_jockey_cd_place_rate",
        "prior_trainer_cd_starts",
        "prior_trainer_cd_win_rate",
        "prior_trainer_cd_place_rate",
        "prior_class_distance_starts",
        "prior_class_distance_win_rate",
        "prior_class_distance_place_rate",
        "prior_draw_class_starts",
        "prior_draw_class_win_rate",
        "prior_draw_class_place_rate",
        "prior_weight_class_starts",
        "prior_weight_class_win_rate",
        "prior_weight_class_place_rate",
        "prior_rest_bucket_starts",
        "prior_rest_bucket_win_rate",
        "prior_rest_bucket_place_rate",
        "prior_horse_cd_starts",
        "prior_horse_cd_win_rate",
        "prior_horse_cd_place_rate",
        "prior_horse_rest_starts",
        "prior_horse_rest_win_rate",
        "prior_horse_rest_place_rate",
    ],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--min-train-meetings", type=int, default=MIN_TRAIN_MEETINGS)
    return parser.parse_args()


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce")


def prepare(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    df = raw.copy()
    df["date"] = df["date"].astype(str)
    df["race_key"] = df["meeting"].astype(str) + "::" + df["race_number"].astype(str)
    df["venue_hv"] = (df["venue"] == "跑馬地").astype(float)
    df["venue_st"] = (df["venue"] == "沙田").astype(float)
    distance = _numeric(df, "distance_num").fillna(0)
    df["is_sprint"] = distance.isin([1000, 1200]).astype(float)
    df["is_middle"] = distance.isin([1600, 1650, 1800]).astype(float)

    chinese_class = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5}

    def fixed_class(value: object) -> float:
        text = str(value or "").strip()
        if "級賽" in text or text.upper().startswith(("G1", "G2", "G3", "GROUP")):
            return 0.0
        match = re.search(r"(?:CLASS\s*|C)([1-5])", text, flags=re.IGNORECASE)
        if match:
            return float(match.group(1))
        match = re.search(r"第?([一二三四五])班", text)
        if match:
            return float(chinese_class[match.group(1)])
        match = re.fullmatch(r"([1-5])", text)
        return float(match.group(1)) if match else np.nan

    df["race_class_fixed"] = df["race_class"].map(fixed_class)
    df["is_group_race"] = (df["race_class_fixed"] == 0).astype(float)
    for class_num in range(1, 6):
        df[f"class_{class_num}"] = (df["race_class_fixed"] == class_num).astype(float)
        df[f"rating_x_class_{class_num}"] = _numeric(df, "card_rating") * df[f"class_{class_num}"]
        df[f"rating_change_x_class_{class_num}"] = _numeric(df, "card_rating_change") * df[f"class_{class_num}"]

    def smoothed_rate(starts: str, successes: list[str], prefix: str) -> None:
        n = _numeric(df, starts)
        success = sum((_numeric(df, col) for col in successes), start=pd.Series(0.0, index=df.index))
        df[f"{prefix}_rate"] = (success + 1.5) / (n + 6.0)
        df[f"{prefix}_evidence"] = np.log1p(n.clip(lower=0))

    smoothed_rate("season_starts", ["season_wins", "season_seconds", "season_thirds"], "season_place")
    smoothed_rate(
        "same_distance_starts",
        ["same_distance_wins", "same_distance_seconds", "same_distance_thirds"],
        "same_distance_place",
    )
    smoothed_rate(
        "same_venue_distance_starts",
        ["same_venue_distance_wins", "same_venue_distance_seconds", "same_venue_distance_thirds"],
        "same_venue_distance_place",
    )

    course = df["course"].fillna("Unknown").astype(str)
    valid_turf_course = course.isin(["A", "B", "C", "C+3"])
    df["course_valid_turf"] = valid_turf_course.astype(float)
    for token in ["A", "B", "C", "C+3"]:
        safe = token.replace("+", "plus")
        df[f"course_{safe}"] = (course == token).astype(float)
        df[f"draw_x_course_{safe}"] = _numeric(df, "barrier").fillna(0) * df[f"course_{safe}"]
    df["draw_x_hv"] = _numeric(df, "barrier").fillna(0) * df["venue_hv"]
    df["draw_x_sprint"] = _numeric(df, "barrier").fillna(0) * df["is_sprint"]

    df["rating_x_hv"] = _numeric(df, "card_rating") * df["venue_hv"]
    df["rating_x_sprint"] = _numeric(df, "card_rating") * df["is_sprint"]
    df["rating_change_x_class"] = _numeric(df, "card_rating_change") * _numeric(df, "race_class_num")
    df["trackwork_density"] = _numeric(df, "tw_gallop_count") / (1.0 + _numeric(df, "tw_entries_count"))
    df["hidden_merit_oneoff"] = (
        _numeric(df, "flag_hidden_form").fillna(0)
        * (1.0 - _numeric(df, "flag_position_down").fillna(0))
        * _numeric(df, "flag_finish_competitive").fillna(0)
    )
    df["repeated_trip_risk"] = (
        _numeric(df, "flag_forgiveness").fillna(0)
        * _numeric(df, "flag_position_down").fillna(0)
        + _numeric(df, "flag_finish_slow").fillna(0)
    )

    blocks = {name: [col for col in columns if col in df] for name, columns in BLOCKS.items()}
    blocks["distance_course_record"] += [
        "season_place_rate",
        "season_place_evidence",
        "same_distance_place_rate",
        "same_distance_place_evidence",
        "same_venue_distance_place_rate",
        "same_venue_distance_place_evidence",
    ]
    blocks["rail_draw_condition"] = [
        "barrier",
        "field_size",
        "venue_hv",
        "venue_st",
        "is_sprint",
        "is_middle",
        "course_valid_turf",
        "course_A",
        "course_B",
        "course_C",
        "course_Cplus3",
        "draw_x_course_A",
        "draw_x_course_B",
        "draw_x_course_C",
        "draw_x_course_Cplus3",
        "draw_x_hv",
        "draw_x_sprint",
    ]
    blocks["condition_specific_rating"] = blocks["official_rating"] + [
        "venue_hv",
        "venue_st",
        "is_sprint",
        "is_middle",
        "rating_x_hv",
        "rating_x_sprint",
        "rating_change_x_class",
    ]
    blocks["fixed_class_rating"] = [
        "card_rating",
        "card_rating_change",
        "weight_carried",
        "card_claim_lbs",
        "venue_hv",
        "venue_st",
        "is_sprint",
        "is_middle",
        "is_group_race",
        *[f"class_{number}" for number in range(1, 6)],
        *[f"rating_x_class_{number}" for number in range(1, 6)],
        *[f"rating_change_x_class_{number}" for number in range(1, 6)],
    ]
    blocks["trackwork_trial"] += ["trackwork_density"]
    blocks["trip_hidden_merit"] += ["hidden_merit_oneoff", "repeated_trip_risk"]

    candidate_numeric = sorted({BASELINE, *[col for cols in blocks.values() for col in cols]})
    rel_columns: dict[str, list[str]] = defaultdict(list)
    for column in candidate_numeric:
        values = _numeric(df, column)
        grouped = values.groupby(df["race_key"])
        mean = grouped.transform("mean")
        std = grouped.transform(lambda x: x.std(ddof=0))
        rel = (values - mean) / std.replace(0, np.nan)
        rel_name = f"{column}__race_rel"
        df[rel_name] = rel.fillna(0.0)
        rel_columns[column].append(rel_name)

    expanded: dict[str, list[str]] = {}
    for name, columns in blocks.items():
        expanded[name] = list(dict.fromkeys(columns + [r for col in columns for r in rel_columns[col]]))
    # Clean structural variants deliberately avoid feeding both the raw and
    # race-relative copy of every concept into the same small-sample model.
    expanded["clean_official_rating"] = [
        "card_rating__race_rel",
        "card_rating_change__race_rel",
        "card_age__race_rel",
        "card_priority_rank__race_rel",
        "weight_carried__race_rel",
        "card_claim_lbs__race_rel",
    ]
    expanded["clean_distance_course"] = [
        "season_place_rate__race_rel",
        "season_place_evidence__race_rel",
        "same_distance_place_rate__race_rel",
        "same_distance_place_evidence__race_rel",
        "same_venue_distance_place_rate__race_rel",
        "same_venue_distance_place_evidence__race_rel",
        "flag_best_distance_match",
        "flag_best_distance_unproven",
    ]
    expanded["clean_trackwork_trial"] = [
        "tw_entries_count__race_rel",
        "tw_gallop_count__race_rel",
        "trackwork_density",
        "tw_jockey_present__race_rel",
        "flag_trackwork_slowing__race_rel",
        "flag_medical_issue__race_rel",
        "days_since_last__race_rel",
    ]
    expanded["clean_variant_sectional"] = [
        "raw_finish_time_adj__race_rel",
        "raw_l400__race_rel",
        "flag_finish_competitive",
        "flag_finish_slow",
        "flag_energy_up",
        "flag_energy_down",
        "flag_l400_up",
        "flag_l400_down",
    ]
    expanded["clean_trip_hidden"] = [
        "raw_last_finish__race_rel",
        "raw_last_margin__race_rel",
        "hidden_merit_oneoff",
        "repeated_trip_risk",
        "flag_margin_narrowing",
        "flag_margin_widening",
    ]
    expanded["clean_fixed_class_rating"] = [
        "card_rating__race_rel",
        "card_rating_change__race_rel",
        "weight_carried__race_rel",
        "card_claim_lbs__race_rel",
        "venue_hv",
        "venue_st",
        "is_sprint",
        "is_middle",
        "is_group_race",
        *[f"class_{number}" for number in range(1, 6)],
        *[f"rating_x_class_{number}__race_rel" for number in range(1, 6)],
        *[f"rating_change_x_class_{number}__race_rel" for number in range(1, 6)],
    ]
    return df, expanded


def model_pipeline(c: float = 0.18) -> Pipeline:
    return Pipeline(
        [
            ("impute", SimpleImputer(strategy="median", add_indicator=True)),
            ("scale", StandardScaler()),
            ("model", LogisticRegression(C=c, max_iter=2000, solver="liblinear")),
        ]
    )


def _race_z(values: pd.Series, race_key: pd.Series) -> pd.Series:
    grouped = values.groupby(race_key)
    mean = grouped.transform("mean")
    std = grouped.transform(lambda x: x.std(ddof=0)).replace(0, np.nan)
    return ((values - mean) / std).fillna(0.0)


def predict_block(train: pd.DataFrame, test: pd.DataFrame, columns: list[str]) -> np.ndarray:
    features = [BASELINE, f"{BASELINE}__race_rel", *columns]
    features = list(dict.fromkeys(features))
    model = model_pipeline()
    model.fit(train[features], train["is_top3"].astype(int))
    return model.predict_proba(test[features])[:, 1]


def predict_support(train: pd.DataFrame, test: pd.DataFrame, columns: list[str]) -> pd.Series:
    """Fit a standalone supporting dimension, leaving the 7D baseline fixed."""
    model = model_pipeline()
    model.fit(train[columns], train["is_top3"].astype(int))
    probability = pd.Series(model.predict_proba(test[columns])[:, 1], index=test.index)
    return _race_z(probability, test["race_key"])


def predict_dual_head(train: pd.DataFrame, test: pd.DataFrame, columns: list[str]) -> np.ndarray:
    features = [BASELINE, f"{BASELINE}__race_rel", *columns]
    features = list(dict.fromkeys(features))
    place_model = model_pipeline(0.18)
    win_model = model_pipeline(0.10)
    place_model.fit(train[features], train["is_top3"].astype(int))
    win_model.fit(train[features], train["is_win"].astype(int))
    place_p = pd.Series(place_model.predict_proba(test[features])[:, 1], index=test.index)
    win_p = pd.Series(win_model.predict_proba(test[features])[:, 1], index=test.index)
    return (
        0.80 * _race_z(place_p, test["race_key"])
        + 0.20 * _race_z(win_p, test["race_key"])
    ).to_numpy()


def race_rows(frame: pd.DataFrame, score_column: str, model: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for race_key, race in frame.groupby("race_key", sort=False):
        ranked = race.sort_values([score_column, "horse_number"], ascending=[False, True])
        positions = ranked["finish_pos"].astype(int).tolist()
        top2_hits = sum(pos <= 3 for pos in positions[:2])
        top3_hits = sum(pos <= 3 for pos in positions[:3])
        top4_hits = sum(pos <= 3 for pos in positions[:4])
        top5_hits = sum(pos <= 3 for pos in positions[:5])
        winner_rank = positions.index(1) + 1
        first = ranked.iloc[0]
        distance_value = pd.to_numeric(pd.Series([first["distance_num"]]), errors="coerce").iloc[0]
        rows.append(
            {
                "model": model,
                "race_key": race_key,
                "date": str(first["date"]),
                "meeting_name": str(first["meeting_name"]),
                "venue": str(first["venue"]),
                "distance": str(first["distance"]),
                "distance_num": int(distance_value) if pd.notna(distance_value) else -1,
                "race_class": str(first["race_class_label"]),
                "track": str(first["track"]),
                "course": str(first["course"]),
                "top1_win": int(positions[0] == 1),
                "top2_hits": int(top2_hits),
                "both_top2_place": int(top2_hits == 2),
                "top3_hits": int(top3_hits),
                "top4_hits": int(top4_hits),
                "top4_all": int(top4_hits == 3),
                "top5_hits": int(top5_hits),
                "top5_all": int(top5_hits == 3),
                "winner_rank": int(winner_rank),
                "winner_mrr": 1.0 / winner_rank,
                "pick1_finish": int(positions[0]),
            }
        )
    return rows


def summary(rows: pd.DataFrame) -> dict[str, Any]:
    n = len(rows)
    return {
        "races": n,
        "top1_wins": int(rows["top1_win"].sum()),
        "top1_rate": round(float(rows["top1_win"].mean()), 4),
        "top2_place_hits": int(rows["top2_hits"].sum()),
        "top2_individual_place_rate": round(float(rows["top2_hits"].sum() / (2 * n)), 4),
        "both_top2_place": int(rows["both_top2_place"].sum()),
        "both_top2_place_rate": round(float(rows["both_top2_place"].mean()), 4),
        "avg_top3_hits": round(float(rows["top3_hits"].mean()), 4),
        "avg_top4_hits": round(float(rows["top4_hits"].mean()), 4),
        "top4_all": int(rows["top4_all"].sum()),
        "top4_all_rate": round(float(rows["top4_all"].mean()), 4),
        "avg_top5_hits": round(float(rows["top5_hits"].mean()), 4),
        "top5_all": int(rows["top5_all"].sum()),
        "mean_winner_rank": round(float(rows["winner_rank"].mean()), 4),
        "winner_mrr": round(float(rows["winner_mrr"].mean()), 4),
        "mean_pick1_finish": round(float(rows["pick1_finish"].mean()), 4),
    }


def _mcnemar_exact(base: pd.Series, candidate: pd.Series) -> dict[str, Any]:
    lost = int(((base == 1) & (candidate == 0)).sum())
    gained = int(((base == 0) & (candidate == 1)).sum())
    discordant = lost + gained
    p = float(binomtest(min(lost, gained), discordant, 0.5).pvalue) if discordant else 1.0
    return {"gained": gained, "lost": lost, "p_value": round(p, 6)}


def _paired_continuous(base: pd.Series, candidate: pd.Series) -> dict[str, Any]:
    delta = candidate.to_numpy(float) - base.to_numpy(float)
    nonzero = delta[np.abs(delta) > 1e-12]
    p = float(wilcoxon(nonzero).pvalue) if len(nonzero) else 1.0
    rng = np.random.default_rng(RNG_SEED)
    samples = rng.choice(delta, size=(10000, len(delta)), replace=True).mean(axis=1)
    return {
        "mean_delta": round(float(delta.mean()), 4),
        "bootstrap_95_ci": [round(float(np.quantile(samples, 0.025)), 4), round(float(np.quantile(samples, 0.975)), 4)],
        "wilcoxon_p_value": round(p, 6),
    }


def compare(base: pd.DataFrame, candidate: pd.DataFrame) -> dict[str, Any]:
    joined = base.set_index("race_key").join(
        candidate.set_index("race_key"), lsuffix="_base", rsuffix="_candidate", how="inner"
    )
    return {
        "top1_win": _mcnemar_exact(joined["top1_win_base"], joined["top1_win_candidate"]),
        "both_top2_place": _mcnemar_exact(
            joined["both_top2_place_base"], joined["both_top2_place_candidate"]
        ),
        "top4_all": _mcnemar_exact(joined["top4_all_base"], joined["top4_all_candidate"]),
        "top2_hits": _paired_continuous(joined["top2_hits_base"], joined["top2_hits_candidate"]),
        "top4_hits": _paired_continuous(joined["top4_hits_base"], joined["top4_hits_candidate"]),
        "winner_mrr": _paired_continuous(joined["winner_mrr_base"], joined["winner_mrr_candidate"]),
    }


def slice_summary(rows: pd.DataFrame, minimum: int = 5) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for column in ["venue", "distance_num", "race_class", "course"]:
        groups = {}
        for value, group in rows.groupby(column, dropna=False):
            if len(group) >= minimum:
                groups[str(value)] = summary(group)
        output[column] = groups
    return output


def run(dataset: Path, min_train_meetings: int) -> dict[str, Any]:
    raw = pd.read_csv(dataset, encoding="utf-8-sig")
    df, blocks = prepare(raw)
    meetings = [group.copy() for _, group in df.groupby("date", sort=True)]
    if len(meetings) <= min_train_meetings:
        raise ValueError("Not enough meetings for walk-forward evaluation")

    combined_columns = list(
        dict.fromkeys(
            blocks["official_rating"]
            + blocks["distance_course_record"]
            + blocks["trackwork_trial"]
            + blocks["trip_hidden_merit"]
            + blocks["variant_sectional"]
            + blocks["rail_draw_condition"]
            + blocks["historical_professional_priors"]
        )
    )
    candidates = {**blocks, "combined_all": combined_columns}
    support_specs = {
        "support_official_rating_20": {"official_rating": 0.20},
        "support_distance_course_20": {"distance_course_record": 0.20},
        "support_trackwork_trial_20": {"trackwork_trial": 0.20},
        "support_gear_20": {"gear": 0.20},
        "support_trip_hidden_20": {"trip_hidden_merit": 0.20},
        "support_variant_sectional_10": {"variant_sectional": 0.10},
        "support_priors_20": {"historical_professional_priors": 0.20},
        "support_rail_draw_20": {"rail_draw_condition": 0.20},
        "support_tw20_variant10": {"trackwork_trial": 0.20, "variant_sectional": 0.10},
        "support_tw20_variant10_distance10": {
            "trackwork_trial": 0.20,
            "variant_sectional": 0.10,
            "distance_course_record": 0.10,
        },
        "support_tw20_variant10_prior10_rail10": {
            "trackwork_trial": 0.20,
            "variant_sectional": 0.10,
            "historical_professional_priors": 0.10,
            "rail_draw_condition": 0.10,
        },
        "support_clean_rating_20": {"clean_official_rating": 0.20},
        "support_clean_distance_20": {"clean_distance_course": 0.20},
        "support_clean_trackwork_20": {"clean_trackwork_trial": 0.20},
        "support_clean_variant_10": {"clean_variant_sectional": 0.10},
        "support_clean_trip_20": {"clean_trip_hidden": 0.20},
        "support_clean_tw20_variant10": {
            "clean_trackwork_trial": 0.20,
            "clean_variant_sectional": 0.10,
        },
        "support_clean_tw20_variant10_distance10": {
            "clean_trackwork_trial": 0.20,
            "clean_variant_sectional": 0.10,
            "clean_distance_course": 0.10,
        },
        "support_fixed_class_rating_20": {"fixed_class_rating": 0.20},
        "support_clean_fixed_class_rating_20": {"clean_fixed_class_rating": 0.20},
    }
    prediction_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    folds = []
    for index in range(min_train_meetings, len(meetings)):
        train = pd.concat(meetings[:index], ignore_index=True)
        test = meetings[index].copy()
        test["score__baseline"] = _numeric(test, BASELINE)
        prediction_rows["baseline"].extend(race_rows(test, "score__baseline", "baseline"))
        fold = {
            "date": str(test["date"].iloc[0]),
            "train_meetings": index,
            "train_races": int(train["race_key"].nunique()),
            "test_races": int(test["race_key"].nunique()),
        }
        for name, columns in candidates.items():
            test[f"score__{name}"] = predict_block(train, test, columns)
            prediction_rows[name].extend(race_rows(test, f"score__{name}", name))
        required_supports = sorted({block for spec in support_specs.values() for block in spec})
        support_scores = {
            block: predict_support(train, test, blocks[block]) for block in required_supports
        }
        baseline_z = _race_z(_numeric(test, BASELINE), test["race_key"])
        for name, spec in support_specs.items():
            score = baseline_z.copy()
            for block, strength in spec.items():
                score = score + strength * support_scores[block]
            test[f"score__{name}"] = score
            prediction_rows[name].extend(race_rows(test, f"score__{name}", name))
        test["score__dual_head_combined"] = predict_dual_head(train, test, combined_columns)
        prediction_rows["dual_head_combined"].extend(
            race_rows(test, "score__dual_head_combined", "dual_head_combined")
        )
        folds.append(fold)

    frames = {name: pd.DataFrame(rows) for name, rows in prediction_rows.items()}
    baseline = frames["baseline"]
    models: dict[str, Any] = {}
    for name, frame in frames.items():
        entry = {
            "summary": summary(frame),
            "slices": slice_summary(frame),
            "race_rows": frame.to_dict(orient="records"),
        }
        if name != "baseline":
            entry["vs_baseline"] = compare(baseline, frame)
        entry["meeting_summary"] = {
            meeting: summary(group) for meeting, group in frame.groupby("meeting_name", sort=True)
        }
        models[name] = entry

    awt_rows = df["track"].astype(str).str.upper().eq("AWT")
    awt_course_ok = bool(
        awt_rows.any()
        and df.loc[awt_rows, "course"].astype(str).str.upper().eq("AWT").all()
    )
    surface_quality = (
        "PASS: Turf/AWT surface and AWT course are normalized"
        if awt_course_ok
        else "WARNING: AWT surface/course normalization is incomplete or unavailable"
    )
    coverage = {
        "dataset_rows": int(len(df)),
        "dataset_meetings": int(df["date"].nunique()),
        "dataset_races": int(df["race_key"].nunique()),
        "heldout_meetings": len(meetings) - min_train_meetings,
        "heldout_races": int(baseline["race_key"].nunique()),
        "date_range": [str(df["date"].min()), str(df["date"].max())],
        "heldout_date_range": [str(baseline["date"].min()), str(baseline["date"].max())],
        "surface_quality": surface_quality,
    }
    feature_coverage = {}
    for name, columns in blocks.items():
        raw_cols = [col for col in columns if not col.endswith("__race_rel")]
        feature_coverage[name] = {
            col: round(float(_numeric(df, col).notna().mean()), 4) for col in raw_cols
        }
    return {
        "research_only": True,
        "market_features_used": [],
        "dataset": str(dataset),
        "coverage": coverage,
        "folds": folds,
        "feature_coverage": feature_coverage,
        "models": models,
    }


def main() -> int:
    args = parse_args()
    result = run(Path(args.dataset), args.min_train_meetings)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"coverage": result["coverage"], "summaries": {k: v["summary"] for k, v in result["models"].items()}}, ensure_ascii=False, indent=2))
    print(f"Report: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
