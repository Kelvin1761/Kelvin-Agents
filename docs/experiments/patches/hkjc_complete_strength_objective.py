#!/usr/bin/env python3
"""Walk-forward test of a continuous whole-field HKJC strength objective."""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge


REPO = Path(__file__).resolve().parents[3]
PATCHES = Path(__file__).resolve().parent
SHARED = REPO / ".agents/skills/shared_racing"
AUTO_SCRIPTS = REPO / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts"
for path in (PATCHES, SHARED, AUTO_SCRIPTS):
    sys.path.insert(0, str(path))

import hkjc_top2_locked_reranker as shared  # noqa: E402
from hkjc_no_regression_gate import evaluate_stage4_candidate  # noqa: E402
from hkjc_racing_engine.scoring import DISPLAY_SLOPE, MATRIX_WEIGHTS  # noqa: E402


ALPHA = 4.0
MIN_TRAIN_RACES = 55
MIN_VENUE_TRAIN_RACES = 30
ARMS = {
    "strength_global15": {"share": 0.15, "venue_specific": False},
    "strength_global25": {"share": 0.25, "venue_specific": False},
    "strength_venue15": {"share": 0.15, "venue_specific": True},
}
SOURCE_COLUMNS = (
    "feat_speed_score", "feat_class_score", "feat_form_score",
    "feat_consistency_score", "feat_formline_strength_score",
    "feat_distance_score", "card_rating", "card_rating_change",
    "last6_runs", "last6_mean_finish", "last6_top3_count",
    "raw_last_margin", "raw_total_starts", "raw_total_wins",
    "same_distance_starts", "same_distance_wins",
    "same_distance_seconds", "same_distance_thirds",
    "same_venue_distance_starts", "same_venue_distance_wins",
    "same_venue_distance_seconds", "same_venue_distance_thirds",
)
STRENGTH_FEATURES = (
    "strength_speed", "strength_class", "strength_form",
    "strength_consistency", "strength_formline", "strength_distance",
    "strength_rating", "strength_rating_change", "strength_recent_finish",
    "strength_recent_top3_rate", "strength_last_margin",
    "strength_total_win_rate", "strength_same_distance",
    "strength_same_venue_distance",
)


def _numeric(df: pd.DataFrame, column: str, default: float = np.nan) -> pd.Series:
    if column not in df:
        return pd.Series(default, index=df.index, dtype=float)
    return pd.to_numeric(df[column], errors="coerce")


def _shrunk_rate(success: pd.Series, starts: pd.Series, prior_success: float, prior_n: float) -> pd.Series:
    starts = starts.fillna(0.0).clip(lower=0.0)
    success = success.fillna(0.0).clip(lower=0.0)
    return (success + prior_success) / (starts + prior_n)


def _race_percentile(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    observed = numeric.dropna()
    fallback = observed.median() if not observed.empty else 0.0
    return numeric.fillna(float(fallback)).rank(method="average", pct=True)


def _prepare(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df[df["race_label_valid"].fillna(0).astype(int).eq(1)].copy()
    df["race_key"] = df["meeting_name"].astype(str) + "::" + df["race_number"].astype(str)
    for column in (
        *SOURCE_COLUMNS, "matrix_race_shape", "current_live_recomputed_ability",
        "finish_pos", "horse_number", "field_size",
    ):
        df[column] = _numeric(df, column)
    df = df.dropna(subset=[
        "matrix_race_shape", "current_live_recomputed_ability", "finish_pos", "horse_number",
    ])
    df["finish_pos"] = df["finish_pos"].astype(int)
    df["horse_number"] = df["horse_number"].astype(int)

    shape = df["matrix_race_shape"]
    shape_median = df.groupby("race_key")["matrix_race_shape"].transform("median")
    adjusted_shape = shape_median + (shape - shape_median).clip(-10.0, 10.0)
    df["baseline_score"] = (
        df["current_live_recomputed_ability"]
        + MATRIX_WEIGHTS["race_shape"] * (adjusted_shape - shape) * DISPLAY_SLOPE
    )

    df["strength_speed"] = df["feat_speed_score"]
    df["strength_class"] = df["feat_class_score"]
    df["strength_form"] = df["feat_form_score"]
    df["strength_consistency"] = df["feat_consistency_score"]
    df["strength_formline"] = df["feat_formline_strength_score"]
    df["strength_distance"] = df["feat_distance_score"]
    df["strength_rating"] = df["card_rating"]
    df["strength_rating_change"] = df["card_rating_change"]
    df["strength_recent_finish"] = -df["last6_mean_finish"]
    df["strength_recent_top3_rate"] = _shrunk_rate(
        df["last6_top3_count"], df["last6_runs"], 1.0, 3.0
    )
    df["strength_last_margin"] = -df["raw_last_margin"].clip(lower=0.0)
    df["strength_total_win_rate"] = _shrunk_rate(
        df["raw_total_wins"], df["raw_total_starts"], 1.0, 5.0
    )
    distance_utility = (
        3.0 * df["same_distance_wins"]
        + 2.0 * df["same_distance_seconds"]
        + df["same_distance_thirds"]
    )
    df["strength_same_distance"] = _shrunk_rate(
        distance_utility, 3.0 * df["same_distance_starts"], 1.0, 12.0
    )
    venue_distance_utility = (
        3.0 * df["same_venue_distance_wins"]
        + 2.0 * df["same_venue_distance_seconds"]
        + df["same_venue_distance_thirds"]
    )
    df["strength_same_venue_distance"] = _shrunk_rate(
        venue_distance_utility, 3.0 * df["same_venue_distance_starts"], 1.0, 12.0
    )

    grouped = df.groupby("race_key", sort=False)
    for feature in STRENGTH_FEATURES:
        df[f"rank_{feature}"] = grouped[feature].transform(_race_percentile)
    df["base_rank_strength"] = grouped["baseline_score"].transform(_race_percentile)
    fallback_size = grouped["horse_number"].transform("count")
    field_denominator = (df["field_size"].fillna(fallback_size) - 1).clip(lower=1)
    df["finish_strength_target"] = 1.0 - (df["finish_pos"] - 1.0) / field_denominator
    return df.sort_values(["date", "meeting_name", "race_number", "horse_number"]).reset_index(drop=True)


def _fit(train: pd.DataFrame) -> Ridge:
    columns = [f"rank_{feature}" for feature in STRENGTH_FEATURES]
    model = Ridge(alpha=ALPHA, positive=True)
    model.fit(train[columns].to_numpy(float), train["finish_strength_target"].to_numpy(float))
    return model


def _predict(
    train: pd.DataFrame, valid: pd.DataFrame, venue_specific: bool,
) -> tuple[pd.Series, list[dict[str, Any]]]:
    columns = [f"rank_{feature}" for feature in STRENGTH_FEATURES]
    prediction = valid["base_rank_strength"].copy()
    audit: list[dict[str, Any]] = []
    cohorts = sorted(valid["venue"].astype(str).unique()) if venue_specific else ["ALL"]
    for cohort in cohorts:
        train_part = train if cohort == "ALL" else train[train["venue"].astype(str).eq(cohort)]
        valid_mask = (
            pd.Series(True, index=valid.index)
            if cohort == "ALL"
            else valid["venue"].astype(str).eq(cohort)
        )
        train_races = int(train_part["race_key"].nunique())
        minimum = MIN_TRAIN_RACES if cohort == "ALL" else MIN_VENUE_TRAIN_RACES
        active = train_races >= minimum
        coefficients: dict[str, float] = {}
        if active and valid_mask.any():
            model = _fit(train_part)
            prediction.loc[valid_mask] = model.predict(
                valid.loc[valid_mask, columns].to_numpy(float)
            )
            coefficients = {
                feature: round(float(value), 8)
                for feature, value in zip(STRENGTH_FEATURES, model.coef_)
            }
        audit.append({
            "cohort": cohort,
            "train_races": train_races,
            "active": active,
            "coefficients": coefficients,
        })
    return prediction, audit


def _score_folds(
    dev: pd.DataFrame, dates: list[str], venue_specific: bool,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    output = dev.copy()
    output["strength_prediction"] = output["base_rank_strength"]
    audit: list[dict[str, Any]] = []
    for number, block in enumerate(shared._date_blocks(dates), start=1):
        block_set = set(block)
        train = dev[dev["date"].astype(str) < min(block_set)]
        valid = output[output["date"].astype(str).isin(block_set)]
        prediction, cohort_audit = _predict(train, valid, venue_specific)
        output.loc[valid.index, "strength_prediction"] = prediction
        audit.append({
            "fold": number,
            "dates": [min(block_set), max(block_set)],
            "cohorts": cohort_audit,
        })
    output["strength_rank"] = output.groupby("race_key")["strength_prediction"].transform(
        _race_percentile
    )
    return output, audit


def _records(df: pd.DataFrame, arm: str, share: float) -> list[dict[str, Any]]:
    output = []
    score_column = f"score_{arm}"
    frame = df.copy()
    frame[score_column] = (
        (1.0 - share) * frame["base_rank_strength"] + share * frame["strength_rank"]
    )
    for race_key, race in frame.groupby("race_key", sort=False):
        actual = dict(zip(race["horse_number"].astype(int), race["finish_pos"].astype(int)))
        baseline = race.sort_values(
            ["baseline_score", "horse_number"], ascending=[False, True]
        )["horse_number"].astype(int).tolist()
        candidate = race.sort_values(
            [score_column, "baseline_score", "horse_number"],
            ascending=[False, False, True],
        )["horse_number"].astype(int).tolist()
        output.append({
            "race_key": str(race_key),
            "meeting": str(race.iloc[0]["meeting_name"]),
            "date": str(race.iloc[0]["date"]),
            "venue": str(race.iloc[0]["venue"]),
            "actual_pos": actual,
            "models": {
                "current_live": shared._model_record(baseline, actual),
                arm: shared._model_record(candidate, actual),
            },
        })
    return output


def _eligible(
    values: dict[str, Any], tail: dict[str, Any], folds: list[dict[str, Any]],
    volatility: dict[str, Any], arm: str,
) -> bool:
    paired = values["paired"]
    tail_paired = tail["paired"]
    return (
        paired["gold"]["delta"] >= 0
        and paired["good"]["delta"] >= 0
        and sum(item["primary_nonnegative"] for item in folds) >= 3
        and sum(
            paired[key]["delta"] > 0
            for key in ("top3_capture_at5", "competitive_recall_at5", "ndcg5")
        ) >= 2
        and tail_paired["missed_top3_outside5"]["delta"] <= 0.01
        and tail_paired["model_top5_finish8plus"]["delta"] <= 0.01
        and volatility[arm]["sd_top5_hits"]
        <= volatility["current_live"]["sd_top5_hits"] + 1e-12
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    df = _prepare(args.dataset)
    dates = sorted(df["date"].astype(str).unique())
    terminal_count = max(1, math.ceil(len(dates) * 0.15))
    dev_dates, terminal_dates = dates[:-terminal_count], dates[-terminal_count:]
    dev = df[df["date"].astype(str).isin(set(dev_dates))].copy()
    terminal = df[df["date"].astype(str).isin(set(terminal_dates))].copy()
    report: dict[str, Any] = {
        "schema": "hkjc-complete-strength-objective/v1",
        "dataset": {
            "rows": int(len(df)),
            "races": int(df["race_key"].nunique()),
            "meetings": int(df["meeting_name"].nunique()),
            "development_dates": [dev_dates[0], dev_dates[-1]],
            "terminal_dates": [terminal_dates[0], terminal_dates[-1]],
        },
        "target": "continuous_whole_field_finish_strength",
        "learner": {"type": "positive_ridge", "alpha": ALPHA},
        "features": list(STRENGTH_FEATURES),
        "leakage_audit": {
            "status": "PASS",
            "feature_source": "archived_pre_race_fields_only",
            "odds_used": False,
            "post_race_text_used": False,
            "result_use": "strictly_earlier_training_labels_and_post_score_evaluation_only",
        },
        "development_arms": {},
    }

    selected: tuple[float, str] | None = None
    cached: dict[bool, tuple[pd.DataFrame, list[dict[str, Any]]]] = {}
    for arm, config in ARMS.items():
        venue_specific = bool(config["venue_specific"])
        if venue_specific not in cached:
            cached[venue_specific] = _score_folds(dev, dev_dates, venue_specific)
        scored, fit_audit = cached[venue_specific]
        records = _records(scored, arm, float(config["share"]))
        values = shared._report(records, arm)
        tail = shared._tail_report(records, arm)
        volatility = shared._meeting_volatility(records, arm)
        folds = []
        for number, block in enumerate(shared._date_blocks(dev_dates), start=1):
            fold_records = [row for row in records if row["date"] in set(block)]
            fold_values = shared._report(fold_records, arm)
            paired = fold_values["paired"]
            folds.append({
                "fold": number,
                **fold_values,
                "primary_nonnegative": (
                    paired["gold"]["delta"] >= 0 and paired["good"]["delta"] >= 0
                ),
            })
        eligible = _eligible(values, tail, folds, volatility, arm)
        paired = values["paired"]
        objective = sum(
            paired[key]["delta"]
            for key in ("top3_capture_at5", "competitive_recall_at5", "ndcg5")
        )
        report["development_arms"][arm] = {
            "config": config,
            "metrics": values,
            "tail": tail,
            "meeting_volatility": volatility,
            "folds": folds,
            "fit_audit": fit_audit,
            "eligible": eligible,
            "selection_objective": round(float(objective), 9),
        }
        if eligible and (selected is None or objective > selected[0] + 1e-12):
            selected = (objective, arm)

    if selected is None:
        report["decision"] = {
            "verdict": "REJECT_DEV",
            "reason": "no_eligible_complete_strength_arm",
        }
    else:
        _, arm = selected
        config = ARMS[arm]
        dev_scored = cached[bool(config["venue_specific"])][0]
        terminal_prediction, terminal_fit = _predict(
            dev, terminal, bool(config["venue_specific"])
        )
        terminal_scored = terminal.copy()
        terminal_scored["strength_prediction"] = terminal_prediction
        terminal_scored["strength_rank"] = terminal_scored.groupby("race_key")[
            "strength_prediction"
        ].transform(_race_percentile)
        dev_records = _records(dev_scored, arm, float(config["share"]))
        terminal_records = _records(terminal_scored, arm, float(config["share"]))
        all_records = dev_records + terminal_records
        terminal_values = shared._report(terminal_records, arm)
        terminal_tail = shared._tail_report(terminal_records, arm)
        all_volatility = shared._meeting_volatility(all_records, arm)
        paired = terminal_values["paired"]
        terminal_pass = (
            paired["gold"]["delta"] >= 0
            and paired["good"]["delta"] >= 0
            and any(
                paired[key]["delta"] > 0
                for key in ("top3_capture_at5", "competitive_recall_at5", "ndcg5")
            )
            and terminal_tail["paired"]["missed_top3_outside5"]["delta"] <= 0
            and all_volatility[arm]["sd_top5_hits"]
            <= all_volatility["current_live"]["sd_top5_hits"] + 1e-12
        )
        stage4 = evaluate_stage4_candidate(all_records, arm, leakage_audit_passed=True)
        report["selected"] = {
            "arm": arm,
            "development": report["development_arms"][arm],
            "terminal": {
                "metrics": terminal_values,
                "tail": terminal_tail,
                "fit_audit": terminal_fit,
            },
            "all": {
                "metrics": shared._report(all_records, arm),
                "tail": shared._tail_report(all_records, arm),
                "meeting_volatility": all_volatility,
            },
            "venues": {
                venue: {
                    part: shared._report(
                        [row for row in records if row["venue"] == venue], arm
                    )
                    for part, records in (
                        ("development", dev_records),
                        ("terminal", terminal_records),
                    )
                }
                for venue in ("沙田", "跑馬地")
            },
            "stage4": stage4,
            "terminal_pass": terminal_pass,
        }
        promoted = terminal_pass and stage4["verdict"] != "REJECT"
        report["decision"] = {
            "verdict": "PROMOTE" if promoted else "REJECT",
            "reason": (
                "passed_locked_gate"
                if promoted
                else stage4.get("reason", "terminal_gate_failed")
            ),
        }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
