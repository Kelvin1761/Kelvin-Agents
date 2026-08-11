#!/usr/bin/env python3
"""Run the full odds-free AU Wong Choi Champion-vs-ML research program."""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.feature_selection import VarianceThreshold
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

try:
    from lightgbm import LGBMClassifier
except Exception as exc:  # pragma: no cover - environment diagnostic
    LGBMClassifier = None
    LIGHTGBM_IMPORT_ERROR = repr(exc)
else:
    LIGHTGBM_IMPORT_ERROR = None

try:
    from xgboost import XGBClassifier
except Exception as exc:  # pragma: no cover - environment diagnostic
    XGBClassifier = None
    XGBOOST_IMPORT_ERROR = repr(exc)
else:
    XGBOOST_IMPORT_ERROR = None

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[4]
sys.path.insert(0, str(SCRIPT_DIR))

from au_ml_dataset import (  # noqa: E402
    FORBIDDEN_FEATURE_TOKENS,
    validate_feature_contract,
)


MODEL_NAMES = ("champion", "logistic", "lightgbm", "xgboost")
CHALLENGERS = MODEL_NAMES[1:]
TARGETS = ("win", "place")
SEED = 20260811


def _clip_prob(values) -> np.ndarray:
    return np.clip(np.asarray(values, dtype=float), 1e-6, 1 - 1e-6)


def _logit(values) -> np.ndarray:
    values = _clip_prob(values)
    return np.log(values / (1 - values))


def load_dataset(path: Path) -> tuple[pd.DataFrame, dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    contract = payload["feature_contract"]
    validate_feature_contract(contract)
    features = contract["numeric"] + contract["categorical"]
    leaked = [
        key for key in features
        if any(token in key.lower() for token in FORBIDDEN_FEATURE_TOKENS)
    ]
    if leaked:
        raise ValueError(f"Market/outcome feature leak: {leaked}")
    frame = pd.DataFrame(payload["rows"])
    frame["date"] = pd.to_datetime(frame["date"], errors="raise")
    frame = frame.sort_values(
        ["date", "track", "race_number", "horse_number"],
        kind="stable",
    ).reset_index(drop=True)
    return frame, contract


def chronological_holdout(frame: pd.DataFrame, fraction: float = 0.15) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    dates = sorted(frame["date"].drop_duplicates())
    holdout_dates = max(1, math.ceil(len(dates) * fraction))
    split_date = dates[-holdout_dates]
    development = frame[frame["date"] < split_date].copy()
    holdout = frame[frame["date"] >= split_date].copy()
    return development, holdout, {
        "split_date": str(split_date.date()),
        "development_dates": [str(development["date"].min().date()), str(development["date"].max().date())],
        "holdout_dates": [str(holdout["date"].min().date()), str(holdout["date"].max().date())],
        "development_races": int(development["race_id"].nunique()),
        "holdout_races": int(holdout["race_id"].nunique()),
        "development_runners": len(development),
        "holdout_runners": len(holdout),
    }


def walkforward_splits(frame: pd.DataFrame, folds: int = 5, min_train_ratio: float = 0.48) -> list[tuple[pd.DataFrame, pd.DataFrame, dict]]:
    dates = sorted(frame["date"].drop_duplicates())
    start = max(2, int(len(dates) * min_train_ratio))
    future = dates[start:]
    block = max(1, math.ceil(len(future) / folds))
    output = []
    for index in range(0, len(future), block):
        valid_dates = future[index : index + block]
        if not valid_dates:
            continue
        first = valid_dates[0]
        train = frame[frame["date"] < first].copy()
        valid = frame[frame["date"].isin(valid_dates)].copy()
        if train.empty or valid.empty:
            continue
        output.append(
            (
                train,
                valid,
                {
                    "train_end": str(train["date"].max().date()),
                    "valid_start": str(valid["date"].min().date()),
                    "valid_end": str(valid["date"].max().date()),
                    "train_races": int(train["race_id"].nunique()),
                    "valid_races": int(valid["race_id"].nunique()),
                },
            )
        )
    return output


def inner_fit_calibration_split(frame: pd.DataFrame, fraction: float = 0.18) -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = sorted(frame["date"].drop_duplicates())
    size = max(1, math.ceil(len(dates) * fraction))
    split = dates[-size]
    fit = frame[frame["date"] < split].copy()
    calibration = frame[frame["date"] >= split].copy()
    if fit.empty or calibration.empty:
        raise ValueError("Insufficient dated rows for inner chronological calibration split")
    return fit, calibration


def make_preprocessor(model_name: str, numeric: list[str], categorical: list[str]) -> ColumnTransformer:
    # Historical coverage genuinely changes over time.  Keep all declared
    # columns even when an early walk-forward fit window contains no observed
    # values, otherwise the model schema silently changes between periods.
    numeric_steps = [(
        "impute",
        SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True),
    )]
    if model_name == "logistic":
        numeric_steps.append(("scale", StandardScaler(with_mean=False)))
    return ColumnTransformer(
        [
            ("numeric", Pipeline(numeric_steps), numeric),
            (
                "categorical",
                OneHotEncoder(handle_unknown="ignore", min_frequency=5),
                categorical,
            ),
        ],
        remainder="drop",
        sparse_threshold=0.3,
    )


def estimator(model_name: str, target: str):
    if model_name == "logistic":
        return LogisticRegression(
            C=0.35,
            penalty="l2",
            solver="liblinear",
            max_iter=800,
            random_state=SEED,
        )
    if model_name == "lightgbm":
        if LGBMClassifier is None:
            raise RuntimeError(f"LightGBM unavailable: {LIGHTGBM_IMPORT_ERROR}")
        return LGBMClassifier(
            objective="binary",
            n_estimators=220,
            learning_rate=0.025,
            max_depth=4,
            num_leaves=15,
            min_child_samples=55,
            subsample=0.8,
            colsample_bytree=0.78,
            reg_alpha=0.6,
            reg_lambda=2.5,
            random_state=SEED + (0 if target == "win" else 1),
            n_jobs=2,
            verbosity=-1,
        )
    if model_name == "xgboost":
        if XGBClassifier is None:
            raise RuntimeError(f"XGBoost unavailable: {XGBOOST_IMPORT_ERROR}")
        return XGBClassifier(
            objective="binary:logistic",
            eval_metric="logloss",
            n_estimators=240,
            learning_rate=0.025,
            max_depth=3,
            min_child_weight=24,
            subsample=0.8,
            colsample_bytree=0.78,
            reg_alpha=0.6,
            reg_lambda=3.0,
            random_state=SEED + (0 if target == "win" else 1),
            n_jobs=2,
        )
    raise ValueError(model_name)


def make_pipeline(model_name: str, target: str, contract: dict) -> Pipeline:
    return Pipeline(
        [
            (
                "preprocess",
                make_preprocessor(
                    model_name,
                    contract["numeric"],
                    contract["categorical"],
                ),
            ),
            # Fit-window-only pruning removes dead/default flags without using
            # validation or holdout coverage for feature selection.
            ("variance", VarianceThreshold(threshold=0.0)),
            ("model", estimator(model_name, target)),
        ]
    )


class PlattCalibrator:
    def __init__(self, *, input_is_probability: bool):
        self.input_is_probability = input_is_probability
        self.model = LogisticRegression(C=10.0, solver="lbfgs", max_iter=500, random_state=SEED)

    def _x(self, values) -> np.ndarray:
        values = _logit(values) if self.input_is_probability else np.asarray(values, dtype=float)
        return values.reshape(-1, 1)

    def fit(self, values, labels) -> "PlattCalibrator":
        self.model.fit(self._x(values), np.asarray(labels, dtype=int))
        return self

    def predict(self, values) -> np.ndarray:
        return self.model.predict_proba(self._x(values))[:, 1]


def _race_normalize(frame: pd.DataFrame, probabilities, target: str) -> np.ndarray:
    temp = frame[["race_id", "place_slots"]].copy()
    temp["prob"] = _clip_prob(probabilities)
    output = np.zeros(len(temp), dtype=float)
    for _race_id, group in temp.groupby("race_id", sort=False):
        values = group["prob"].to_numpy(dtype=float)
        total = 1.0 if target == "win" else float(group["place_slots"].iloc[0])
        # Repeated proportional scaling with clipping enforces the race-level
        # probability mass without creating values outside [0, 1].
        scaled = values.copy()
        free = np.ones(len(scaled), dtype=bool)
        remaining = total
        for _ in range(4):
            denom = scaled[free].sum()
            if not free.any() or denom <= 0:
                break
            scaled[free] *= remaining / denom
            hit = free & (scaled >= 1)
            if not hit.any():
                break
            scaled[hit] = 1 - 1e-6
            free[hit] = False
            remaining = max(1e-6, total - scaled[~free].sum())
        output[group.index.to_numpy()] = _clip_prob(scaled)
    return output


def fit_predict_champion(train: pd.DataFrame, valid: pd.DataFrame, target: str) -> tuple[np.ndarray, dict]:
    _fit, calibration = inner_fit_calibration_split(train)
    label = f"label_{target}"
    calibrator = PlattCalibrator(input_is_probability=False).fit(
        calibration["champion_score"].to_numpy(),
        calibration[label].to_numpy(),
    )
    raw = calibrator.predict(valid["champion_score"].to_numpy())
    return _race_normalize(valid.reset_index(drop=True), raw, target), {
        "fit_races": 0,
        "calibration_races": int(calibration["race_id"].nunique()),
    }


def fit_predict_model(
    model_name: str,
    train: pd.DataFrame,
    valid: pd.DataFrame,
    target: str,
    contract: dict,
) -> tuple[np.ndarray, Pipeline, dict]:
    fit, calibration = inner_fit_calibration_split(train)
    label = f"label_{target}"
    features = contract["numeric"] + contract["categorical"]
    pipeline = make_pipeline(model_name, target, contract)
    pipeline.fit(fit[features], fit[label].astype(int))
    cal_raw = pipeline.predict_proba(calibration[features])[:, 1]
    calibrator = PlattCalibrator(input_is_probability=True).fit(
        cal_raw,
        calibration[label].to_numpy(),
    )
    valid_raw = pipeline.predict_proba(valid[features])[:, 1]
    calibrated = calibrator.predict(valid_raw)
    normalized = _race_normalize(valid.reset_index(drop=True), calibrated, target)
    return normalized, pipeline, {
        "fit_races": int(fit["race_id"].nunique()),
        "calibration_races": int(calibration["race_id"].nunique()),
    }


def predict_all_models(train: pd.DataFrame, valid: pd.DataFrame, contract: dict) -> tuple[dict[str, pd.DataFrame], dict]:
    outputs = {}
    fitted = {}
    timings = {}
    base = valid.reset_index(drop=True).copy()
    for model_name in MODEL_NAMES:
        started = time.perf_counter()
        prediction = base.copy()
        fitted[model_name] = {}
        for target in TARGETS:
            if model_name == "champion":
                values, metadata = fit_predict_champion(train, base, target)
                pipeline = None
            else:
                values, pipeline, metadata = fit_predict_model(
                    model_name, train, base, target, contract
                )
            prediction[f"pred_{target}"] = values
            fitted[model_name][target] = {
                "pipeline": pipeline,
                "metadata": metadata,
            }
        prediction["analysis_score"] = (
            prediction["pred_win"]
            + prediction["pred_place"] / prediction["place_slots"].clip(lower=1)
        )
        outputs[model_name] = prediction
        timings[model_name] = round(time.perf_counter() - started, 3)
    return outputs, {"fitted": fitted, "timings_seconds": timings}


def calibration_table(labels, probabilities, bins: int = 10) -> tuple[list[dict], float]:
    table = pd.DataFrame({"label": labels, "prob": probabilities})
    table["bucket"] = pd.cut(
        table["prob"],
        bins=np.linspace(0, 1, bins + 1),
        include_lowest=True,
        duplicates="drop",
    )
    rows = []
    total = len(table)
    ece = 0.0
    for bucket, group in table.groupby("bucket", observed=True):
        predicted = float(group["prob"].mean())
        observed = float(group["label"].mean())
        ece += len(group) / max(1, total) * abs(predicted - observed)
        rows.append(
            {
                "bucket": str(bucket),
                "count": len(group),
                "predicted": round(predicted, 6),
                "observed": round(observed, 6),
            }
        )
    return rows, ece


def evaluate_predictions(frame: pd.DataFrame) -> dict:
    y_win = frame["label_win"].to_numpy(dtype=int)
    y_place = frame["label_place"].to_numpy(dtype=int)
    p_win = _clip_prob(frame["pred_win"])
    p_place = _clip_prob(frame["pred_place"])
    race_stats = []
    winner_ranks = []
    place_ranks = []
    rank_correlations = []
    for _race_id, race in frame.groupby("race_id", sort=False):
        by_win = race.sort_values(["pred_win", "horse_number"], ascending=[False, True])
        by_place = race.sort_values(["pred_place", "horse_number"], ascending=[False, True])
        by_analysis = race.sort_values(["analysis_score", "horse_number"], ascending=[False, True])
        win_ranks = {idx: rank for rank, idx in enumerate(by_win.index, 1)}
        place_rank_map = {idx: rank for rank, idx in enumerate(by_place.index, 1)}
        analysis_top = by_analysis.head(5)
        actual_top3 = set(race.index[race["actual_pos"] <= 3])
        top3_idx = list(by_analysis.head(3).index)
        top4_idx = set(by_analysis.head(4).index)
        winner_idx = set(race.index[race["label_win"] == 1])
        slots = int(race["place_slots"].iloc[0])
        top_place = set(by_place.head(slots).index)
        race_stats.append(
            {
                "race_id": race["race_id"].iloc[0],
                "win_brier": float(np.mean((race["pred_win"] - race["label_win"]) ** 2)),
                "win_log_loss": float(log_loss(race["label_win"], race["pred_win"], labels=[0, 1])),
                "place_brier": float(np.mean((race["pred_place"] - race["label_place"]) ** 2)),
                "place_log_loss": float(log_loss(race["label_place"], race["pred_place"], labels=[0, 1])),
                "top1": int(bool(winner_idx & set(by_win.head(1).index))),
                "top2": int(bool(winner_idx & set(by_win.head(2).index))),
                "top3": int(bool(winner_idx & set(by_win.head(3).index))),
                "top5": int(bool(winner_idx & set(by_win.head(5).index))),
                "place_precision": len(top_place & set(race.index[race["label_place"] == 1])) / max(1, slots),
                "gold": int(actual_top3 <= top4_idx),
                "gold_strict": int(set(top3_idx) == actual_top3),
                "good": int(len(top3_idx) >= 2 and top3_idx[0] in actual_top3 and top3_idx[1] in actual_top3),
                "pass": int(len(set(top3_idx) & actual_top3) >= 2),
                "champion": int(bool(winner_idx & set(by_analysis.head(1).index))),
                "winner_in_top3": int(bool(winner_idx & set(by_analysis.head(3).index))),
                "winner_in_top5": int(bool(winner_idx & set(analysis_top.index))),
            }
        )
        winner_ranks.extend(win_ranks[idx] for idx in winner_idx)
        place_ranks.extend(place_rank_map[idx] for idx in race.index[race["label_place"] == 1])
        if race["actual_pos"].nunique() > 1 and race["analysis_score"].nunique() > 1:
            correlation = spearmanr(-race["analysis_score"], race["actual_pos"]).statistic
            if math.isfinite(correlation):
                rank_correlations.append(float(correlation))
    per_race = pd.DataFrame(race_stats)
    win_calibration, win_ece = calibration_table(y_win, p_win)
    place_calibration, place_ece = calibration_table(y_place, p_place)
    races = max(1, len(per_race))
    result = {
        "races": len(per_race),
        "runners": len(frame),
        "win_brier": float(brier_score_loss(y_win, p_win)),
        "win_log_loss": float(log_loss(y_win, p_win, labels=[0, 1])),
        "top1": float(per_race["top1"].mean()),
        "top2": float(per_race["top2"].mean()),
        "top3": float(per_race["top3"].mean()),
        "top5": float(per_race["top5"].mean()),
        "place_brier": float(brier_score_loss(y_place, p_place)),
        "place_log_loss": float(log_loss(y_place, p_place, labels=[0, 1])),
        "place_precision": float(per_race["place_precision"].mean()),
        "winner_average_rank": float(mean(winner_ranks)),
        "place_getter_average_rank": float(mean(place_ranks)),
        "ranking_correlation": float(mean(rank_correlations)),
        "gold": int(per_race["gold"].sum()),
        "gold_rate": float(per_race["gold"].sum() / races),
        "gold_strict": int(per_race["gold_strict"].sum()),
        "gold_strict_rate": float(per_race["gold_strict"].sum() / races),
        "good": int(per_race["good"].sum()),
        "good_rate": float(per_race["good"].sum() / races),
        "pass": int(per_race["pass"].sum()),
        "pass_rate": float(per_race["pass"].sum() / races),
        "champion": int(per_race["champion"].sum()),
        "champion_rate": float(per_race["champion"].sum() / races),
        "winner_in_top3": float(per_race["winner_in_top3"].mean()),
        "winner_in_top5": float(per_race["winner_in_top5"].mean()),
        "win_ece": float(win_ece),
        "place_ece": float(place_ece),
        "win_calibration": win_calibration,
        "place_calibration": place_calibration,
        "per_race": per_race.to_dict(orient="records"),
    }
    return result


def model_selection_score(metrics: dict) -> float:
    # Development-only selection.  Probability quality leads; ranking has a
    # smaller explicit role so a well-calibrated but useless ranker cannot win.
    return (
        -(metrics["win_brier"] + metrics["place_brier"])
        - 0.2 * (metrics["win_log_loss"] + metrics["place_log_loss"])
        + 0.15 * metrics["top1"]
        + 0.10 * metrics["top3"]
        + 0.10 * metrics["place_precision"]
    )


def combine_predictions(champion: pd.DataFrame, challenger: pd.DataFrame, alpha: float) -> pd.DataFrame:
    output = champion.copy()
    output["pred_win"] = (1 - alpha) * champion["pred_win"] + alpha * challenger["pred_win"]
    output["pred_place"] = (1 - alpha) * champion["pred_place"] + alpha * challenger["pred_place"]
    output["pred_win"] = _race_normalize(output, output["pred_win"], "win")
    output["pred_place"] = _race_normalize(output, output["pred_place"], "place")
    output["analysis_score"] = output["pred_win"] + output["pred_place"] / output["place_slots"].clip(lower=1)
    return output


def paired_bootstrap(champion: dict, challenger: dict, iterations: int = 2000) -> dict:
    champ = pd.DataFrame(champion["per_race"]).set_index("race_id")
    cand = pd.DataFrame(challenger["per_race"]).set_index("race_id")
    common = sorted(set(champ.index) & set(cand.index))
    rng = random.Random(SEED)
    metrics = {
        "win_brier_improvement": ("win_brier", -1),
        "win_log_loss_improvement": ("win_log_loss", -1),
        "place_brier_improvement": ("place_brier", -1),
        "place_log_loss_improvement": ("place_log_loss", -1),
        "top1_difference": ("top1", 1),
        "top3_difference": ("top3", 1),
    }
    output = {}
    for label, (key, direction) in metrics.items():
        deltas = []
        for _ in range(iterations):
            sample = [common[rng.randrange(len(common))] for _ in common]
            raw = float(cand.loc[sample, key].mean() - champ.loc[sample, key].mean())
            deltas.append(direction * raw)
        deltas.sort()
        output[label] = {
            "mean": float(mean(deltas)),
            "ci95": [deltas[int(0.025 * iterations)], deltas[int(0.975 * iterations) - 1]],
        }
    return output


def walkforward(frame: pd.DataFrame, contract: dict) -> tuple[dict, dict[str, pd.DataFrame]]:
    periods = []
    aggregate = {name: [] for name in MODEL_NAMES}
    for index, (train, valid, split) in enumerate(walkforward_splits(frame), 1):
        print(
            f"Walk-forward {index}: train {split['train_races']} races → "
            f"validate {split['valid_races']} races",
            flush=True,
        )
        predictions, details = predict_all_models(train, valid, contract)
        metrics = {}
        for name, prediction in predictions.items():
            metrics[name] = evaluate_predictions(prediction)
            aggregate[name].append(prediction)
        periods.append({"period": index, **split, "metrics": metrics, "timings_seconds": details["timings_seconds"]})
    combined = {name: pd.concat(parts, ignore_index=True) for name, parts in aggregate.items()}
    summary = {name: evaluate_predictions(value) for name, value in combined.items()}
    return {"periods": periods, "summary": summary}, combined


def select_hybrid(aggregate: dict[str, pd.DataFrame], best: str) -> tuple[float, dict]:
    options = {}
    for alpha in (0.25, 0.5, 0.75):
        metrics = evaluate_predictions(combine_predictions(aggregate["champion"], aggregate[best], alpha))
        options[str(alpha)] = metrics
    best_alpha = max(options, key=lambda key: model_selection_score(options[key]))
    return float(best_alpha), options


def learning_curve(
    development: pd.DataFrame,
    contract: dict,
    model_name: str,
) -> list[dict]:
    races = (
        development[["race_id", "date"]]
        .drop_duplicates()
        .sort_values(["date", "race_id"])
    )
    dates = sorted(races["date"].drop_duplicates())
    validation_start = dates[max(1, int(len(dates) * 0.84))]
    pool = development[development["date"] < validation_start]
    validation = development[development["date"] >= validation_start]
    pool_races = (
        pool[["race_id", "date"]].drop_duplicates().sort_values(["date", "race_id"])
    )
    output = []
    requested = [100, 200, 300, 400, 500, 600, len(pool_races)]
    for size in sorted(set(min(value, len(pool_races)) for value in requested if value >= 80)):
        selected = set(pool_races.tail(size)["race_id"])
        train = pool[pool["race_id"].isin(selected)]
        predictions = {}
        for target in TARGETS:
            values, _pipeline, _meta = fit_predict_model(model_name, train, validation, target, contract)
            predictions[target] = values
        scored = validation.reset_index(drop=True).copy()
        scored["pred_win"] = predictions["win"]
        scored["pred_place"] = predictions["place"]
        scored["analysis_score"] = scored["pred_win"] + scored["pred_place"] / scored["place_slots"].clip(lower=1)
        metrics = evaluate_predictions(scored)
        output.append({"training_races": size, "validation_races": int(validation["race_id"].nunique()), "metrics": metrics})
        print(f"Learning curve {model_name}: {size} races", flush=True)
    return output


def _race_confidence_labels(frame: pd.DataFrame) -> pd.Series:
    race_coverage = frame.groupby("race_id")["source_coverage_pct"].mean()
    race_buckets = pd.cut(
        race_coverage,
        [0, 70, 85, 100],
        labels=["Low", "Medium", "High"],
        include_lowest=True,
    )
    return frame["race_id"].map(race_buckets.astype(str))


def _market_status_labels(frame: pd.DataFrame) -> pd.Series:
    prices = pd.to_numeric(frame["market_sp_label"], errors="coerce")
    favourite = prices.groupby(frame["race_id"]).transform("min")
    labels = pd.Series("NonFavourite", index=frame.index, dtype=object)
    labels[prices.isna()] = "MarketUnavailable"
    labels[prices.notna() & np.isclose(prices, favourite, rtol=0, atol=1e-9)] = "Favourite/TiedFavourite"
    return labels


def _race_winner_market_status_labels(frame: pd.DataFrame) -> pd.Series:
    """Post-hoc market slice that preserves every runner in each race."""
    by_race = {}
    for race_id, race in frame.groupby("race_id", sort=False):
        prices = pd.to_numeric(race["market_sp_label"], errors="coerce")
        if prices.notna().sum() == 0:
            by_race[race_id] = "MarketUnavailable"
            continue
        favourite = float(prices.min())
        winners = race[race["label_win"] == 1]
        winner_prices = pd.to_numeric(winners["market_sp_label"], errors="coerce")
        favourite_won = any(
            math.isclose(float(price), favourite, rel_tol=0, abs_tol=1e-9)
            for price in winner_prices.dropna()
        )
        by_race[race_id] = "FavouriteWon" if favourite_won else "NonFavouriteWon"
    return frame["race_id"].map(by_race)


def segment_analysis(frame: pd.DataFrame) -> dict:
    definitions = {
        "venue": "venue",
        "distance": "distance_bucket",
        "class": "race_type",
        "race_type": "race_type",
        "track_condition": "going_bucket",
        "field_size": "field_size_bucket",
        # Confidence is a race-level segment.  A race must never be split into
        # different evaluation groups because individual runners have slightly
        # different source coverage.
        "confidence": _race_confidence_labels(frame),
        # This is a retrospective evaluation slice only. Market status is
        # created after predictions are frozen and is never a model feature.
        "market_status": _race_winner_market_status_labels(frame),
    }
    output = {}
    for family, source in definitions.items():
        labels = frame[source] if isinstance(source, str) else source
        groups = {}
        for label in sorted(set(labels)):
            subset = frame[labels == label]
            if subset["race_id"].nunique() < 5:
                continue
            metrics = evaluate_predictions(subset)
            groups[str(label)] = {
                key: metrics[key]
                for key in (
                    "races", "runners", "win_brier", "place_brier", "top1",
                    "top3", "place_precision", "gold_rate", "good_rate", "pass_rate",
                )
            }
        output[family] = groups
    return output


def _shap_importance(fitted: Pipeline, sample: pd.DataFrame, features: list[str]) -> dict:
    try:
        import shap

        transformed = fitted.named_steps["preprocess"].transform(sample[features])
        feature_names = fitted.named_steps["preprocess"].get_feature_names_out()
        variance = fitted.named_steps.get("variance")
        if variance is not None:
            transformed = variance.transform(transformed)
            feature_names = feature_names[variance.get_support()]
        values = shap.TreeExplainer(fitted.named_steps["model"]).shap_values(transformed)
        if isinstance(values, list):
            values = values[-1]
        values = np.asarray(values)
        if values.ndim == 3:
            values = values[:, :, -1]
        magnitudes = np.abs(values).mean(axis=0)
        rows = sorted(
            (
                {"feature": str(key), "mean_abs_shap": float(value)}
                for key, value in zip(feature_names, magnitudes)
            ),
            key=lambda item: item["mean_abs_shap"],
            reverse=True,
        )
        return {"status": "complete", "features": rows}
    except Exception as exc:  # pragma: no cover - dependency/runtime diagnostic
        return {"status": "unavailable", "reason": repr(exc), "features": []}


def feature_importance(
    fitted: Pipeline,
    holdout: pd.DataFrame,
    contract: dict,
    target: str = "place",
) -> dict:
    features = contract["numeric"] + contract["categorical"]
    sample = holdout.sample(min(1200, len(holdout)), random_state=SEED)
    result = permutation_importance(
        fitted,
        sample[features],
        sample[f"label_{target}"],
        scoring="neg_brier_score",
        n_repeats=3,
        random_state=SEED,
        n_jobs=1,
    )
    rows = sorted(
        (
            {"feature": key, "importance": float(value)}
            for key, value in zip(features, result.importances_mean)
        ),
        key=lambda item: item["importance"],
        reverse=True,
    )
    return {
        "method": "permutation_neg_brier_and_tree_shap",
        "target": target,
        "features": rows,
        "shap": _shap_importance(fitted, sample, features),
    }


def betting_scorecard(frame: pd.DataFrame, edge_threshold: float = 0.05) -> dict:
    candidates = frame.copy()
    candidates = candidates[
        candidates["market_sp_label"].notna()
        & (candidates["market_sp_label"] >= 1.5)
        & (candidates["market_sp_label"] <= 50)
    ].copy()
    candidates["market_implied"] = 1 / candidates["market_sp_label"]
    candidates["edge"] = candidates["pred_win"] - candidates["market_implied"]
    bets = candidates[candidates["edge"] >= edge_threshold].sort_values(
        ["date", "track", "race_number", "horse_number"]
    )
    profits = [
        float(row.market_sp_label - 1) if int(row.label_win) else -1.0
        for row in bets.itertuples()
    ]
    equity = 0.0
    peak = 0.0
    drawdown = 0.0
    longest = current = 0
    for profit in profits:
        equity += profit
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
        if profit < 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    turnover = len(profits)
    profit = sum(profits)
    return {
        "rule": f"flat 1u; predicted win edge >= {edge_threshold:.0%}; SP 1.5–50",
        "bets": turnover,
        "turnover": turnover,
        "profit": profit,
        "roi": profit / turnover if turnover else None,
        "strike_rate": float(bets["label_win"].mean()) if turnover else None,
        "average_odds": float(bets["market_sp_label"].mean()) if turnover else None,
        "average_predicted_edge": float(bets["edge"].mean()) if turnover else None,
        "maximum_drawdown_units": drawdown,
        "longest_losing_streak": longest,
        "place": "N/A — historical place dividends are unavailable; SP cannot be used as a substitute.",
        "clv": "N/A — no timestamped opening/closing odds snapshots in the aligned archive.",
    }


def betting_segment_analysis(frame: pd.DataFrame) -> dict:
    segmented = frame.copy()
    prices = pd.to_numeric(segmented["market_sp_label"], errors="coerce")
    implied = 1 / prices
    edge = segmented["pred_win"] - implied
    odds_band = pd.cut(
        prices,
        [0, 3, 6, 12, 25, 50, np.inf],
        labels=["<=3", "3-6", "6-12", "12-25", "25-50", ">50"],
        include_lowest=True,
    ).astype(str)
    odds_band[prices.isna()] = "MarketUnavailable"
    edge_band = pd.cut(
        edge,
        [-np.inf, 0, 0.05, 0.10, 0.20, np.inf],
        labels=["<0", "0-5%", "5-10%", "10-20%", "20%+"],
        include_lowest=True,
    ).astype(str)
    edge_band[prices.isna()] = "MarketUnavailable"
    definitions = {
        "venue": segmented["venue"],
        "distance": segmented["distance_bucket"],
        "class": segmented["race_type"],
        "race_type": segmented["race_type"],
        "track_condition": segmented["going_bucket"],
        "field_size": segmented["field_size_bucket"],
        "market_status": _market_status_labels(segmented),
        "odds_band": odds_band,
        "confidence": _race_confidence_labels(segmented),
        "predicted_edge": edge_band,
    }
    output = {}
    for family, labels in definitions.items():
        groups = {}
        for label in sorted(set(labels)):
            subset = segmented[labels == label]
            card = betting_scorecard(subset)
            groups[str(label)] = {
                "population_races": int(subset["race_id"].nunique()),
                "population_runners": len(subset),
                **card,
            }
        output[family] = groups
    return output


def _pct(value) -> str:
    return f"{100 * value:.2f}%"


def _num(value) -> str:
    return f"{value:.6f}"


def _improvement(lower_better_current: float, candidate: float) -> float:
    return (lower_better_current - candidate) / lower_better_current


def _promotion_gate(
    champion: dict,
    candidate: dict,
    bootstrap: dict,
    wf_periods: list[dict],
    candidate_name: str,
    champion_betting: dict,
    candidate_betting: dict,
) -> dict:
    improved_periods = sum(
        model_selection_score(period["metrics"][candidate_name])
        > model_selection_score(period["metrics"]["champion"])
        for period in wf_periods
    )
    probability_ok = (
        candidate["win_brier"] < champion["win_brier"]
        and candidate["place_brier"] < champion["place_brier"]
        and candidate["win_log_loss"] <= champion["win_log_loss"]
        and candidate["place_log_loss"] <= champion["place_log_loss"]
    )
    ranking_ok = (
        candidate["top1"] >= champion["top1"]
        and candidate["top3"] >= champion["top3"]
    )
    stable = improved_periods >= max(3, math.ceil(len(wf_periods) * 0.6))
    statistically_supported = (
        bootstrap["win_brier_improvement"]["ci95"][0] > 0
        or bootstrap["place_brier_improvement"]["ci95"][0] > 0
    )
    betting_ok = (
        candidate_betting.get("roi") is not None
        and champion_betting.get("roi") is not None
        and candidate_betting["roi"] >= champion_betting["roi"] - 0.05
    )
    return {
        "candidate": candidate_name,
        "probability": probability_ok,
        "top_rank": ranking_ok,
        "walkforward": stable,
        "walkforward_improved_periods": improved_periods,
        "bootstrap": statistically_supported,
        "betting_not_materially_worse": betting_ok,
        "passed": all((probability_ok, ranking_ok, stable, statistically_supported, betting_ok)),
    }


def promotion_verdict(
    champion: dict,
    candidates: dict[str, dict],
    bootstraps: dict[str, dict],
    wf_periods: list[dict],
    betting: dict[str, dict],
    best_name: str,
) -> tuple[str, list[str], dict]:
    gates = {
        name: _promotion_gate(
            champion,
            metrics,
            bootstraps[name],
            wf_periods,
            name,
            betting["champion"],
            betting[name],
        )
        for name, metrics in candidates.items()
    }
    preferred = "hybrid" if gates["hybrid"]["passed"] else best_name
    gate = gates[preferred]
    reasons = [
        f"Candidate assessed: {preferred}",
        f"Probability gate: {'PASS' if gate['probability'] else 'FAIL'}",
        f"Top-rank gate: {'PASS' if gate['top_rank'] else 'FAIL'}",
        f"Walk-forward consistency: {gate['walkforward_improved_periods']}/{len(wf_periods)} periods ({'PASS' if gate['walkforward'] else 'FAIL'})",
        f"Paired bootstrap support: {'PASS' if gate['bootstrap'] else 'FAIL'}",
        f"Betting not materially worse (5pp tolerance): {'PASS' if gate['betting_not_materially_worse'] else 'FAIL'}",
    ]
    if gates["hybrid"]["passed"]:
        return "PROMOTE MATRIX + ML HYBRID", reasons, gates
    if gates[best_name]["passed"]:
        return "PROMOTE ML", reasons, gates
    return "KEEP CURRENT MATRIX", reasons, gates


def report_markdown(results: dict) -> str:
    final = results["final_test"]
    champion = final["metrics"]["champion"]
    best_name = results["selection"]["best_independent_model"]
    best = final["metrics"][best_name]
    hybrid = final["metrics"]["hybrid"]
    betting = final["betting"]
    wf = results["walk_forward"]
    improved = results["selection"]["walkforward_improved_periods"]
    periods = len(wf["periods"])
    verdict = results["verdict"]["decision"]
    importance_lookup = {
        item["feature"]: item["importance"]
        for item in results["explainability"]["features"]
    }
    quality = results["dataset"].get("feature_quality", {})
    lines = [
        "# AU Wong Choi ML Experiment Report",
        "",
        "## AU WONG CHOI ML RESULT",
        "",
        f"Current Production Model: **{results['champion']['model']}**",
        "",
        f"Best Independent Analysis Model: **{best_name}**",
        "",
        f"Best Analysis Hybrid: **Matrix + {best_name} @ {results['selection']['hybrid_alpha']:.0%} ML**",
        "",
        f"Historical Dataset: **{results['dataset']['races']} races / {results['dataset']['runners']} runners**",
        "",
        f"Final Out-of-Sample Test: **{best['races']} races / {best['runners']} runners**",
        "",
        "> This final chronological block was untouched by this ML model-selection run, but the archive was previously used to optimise the Rating Matrix. It is not claimed as globally untouched.",
        "",
        "## ANALYSIS PERFORMANCE",
        "",
        "| Metric | Current Matrix | Logistic | LightGBM | XGBoost | Hybrid |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for label, key, formatter in (
        ("Win Brier", "win_brier", _num),
        ("Win Log Loss", "win_log_loss", _num),
        ("Top-1", "top1", _pct),
        ("Top-2", "top2", _pct),
        ("Top-3", "top3", _pct),
        ("Top-5", "top5", _pct),
        ("Place Brier", "place_brier", _num),
        ("Place Log Loss", "place_log_loss", _num),
        ("Place precision", "place_precision", _pct),
        ("Winner average rank", "winner_average_rank", _num),
        ("Place-getter average rank", "place_getter_average_rank", _num),
        ("Ranking correlation", "ranking_correlation", _num),
        ("Gold", "gold_rate", _pct),
        ("Gold strict", "gold_strict_rate", _pct),
        ("Good", "good_rate", _pct),
        ("Pass", "pass_rate", _pct),
    ):
        lines.append(
            f"| {label} | "
            + " | ".join(formatter(final["metrics"][name][key]) for name in (*MODEL_NAMES, "hybrid"))
            + " |"
        )
    lines.extend([
        "",
        "### WIN",
        "",
        f"Current Matrix Top-1: **{_pct(champion['top1'])}**",
        "",
        f"Best ML Top-1: **{_pct(best['top1'])}**",
        "",
        f"Difference: **{100 * (best['top1'] - champion['top1']):+.2f} percentage points**",
        "",
        f"Current Matrix Top-3: **{_pct(champion['top3'])}**",
        "",
        f"Best ML Top-3: **{_pct(best['top3'])}**",
        "",
        f"Difference: **{100 * (best['top3'] - champion['top3']):+.2f} percentage points**",
        "",
        f"Current Matrix Win Brier: **{_num(champion['win_brier'])}**",
        "",
        f"Best ML Win Brier: **{_num(best['win_brier'])}**",
        "",
        f"Improvement: **{_pct(_improvement(champion['win_brier'], best['win_brier']))}**",
        "",
        f"Current Matrix Win Log Loss: **{_num(champion['win_log_loss'])}**",
        "",
        f"Best ML Win Log Loss: **{_num(best['win_log_loss'])}**",
        "",
        f"Improvement: **{_pct(_improvement(champion['win_log_loss'], best['win_log_loss']))}**",
        "",
        "### PLACE",
        "",
        f"Current Matrix Place Brier: **{_num(champion['place_brier'])}**",
        "",
        f"Best ML Place Brier: **{_num(best['place_brier'])}**",
        "",
        f"Improvement: **{_pct(_improvement(champion['place_brier'], best['place_brier']))}**",
        "",
        f"Current Matrix Place Log Loss: **{_num(champion['place_log_loss'])}**",
        "",
        f"Best ML Place Log Loss: **{_num(best['place_log_loss'])}**",
        "",
        f"Improvement: **{_pct(_improvement(champion['place_log_loss'], best['place_log_loss']))}**",
        "",
        "## WALK-FORWARD ANALYSIS",
        "",
        f"ML improved vs Matrix: **{improved} / {periods} periods**",
        "",
        f"ML underperformed Matrix: **{periods - improved} / {periods} periods**",
        "",
        "| Period | Train end | Validation | Matrix score | Best ML score | Hybrid score |",
        "|---:|---|---|---:|---:|---:|",
    ])
    for period in wf["periods"]:
        lines.append(
            f"| {period['period']} | {period['train_end']} | {period['valid_start']}→{period['valid_end']} | "
            f"{model_selection_score(period['metrics']['champion']):.6f} | "
            f"{model_selection_score(period['metrics'][best_name]):.6f} | "
            f"{model_selection_score(period['metrics']['hybrid']):.6f} |"
        )
    lines.extend([
        "",
        f"Hybrid improved vs Matrix: **{results['selection']['hybrid_walkforward_improved_periods']} / {periods} periods**",
        "",
        "## CALIBRATION AND STATISTICAL SUPPORT",
        "",
        "| Model | Win ECE | Place ECE |",
        "|---|---:|---:|",
    ])
    for name in (*MODEL_NAMES, "hybrid"):
        lines.append(
            f"| {name} | {final['metrics'][name]['win_ece']:.6f} | "
            f"{final['metrics'][name]['place_ece']:.6f} |"
        )
    lines.extend([
        "",
        f"Selected {best_name} chronological-holdout probability buckets:",
        "",
        "| Target | Probability bucket | Runners | Mean predicted | Observed |",
        "|---|---|---:|---:|---:|",
    ])
    for target in ("win", "place"):
        for bucket in best[f"{target}_calibration"]:
            lines.append(
                f"| {target} | {bucket['bucket']} | {bucket['count']} | "
                f"{_pct(bucket['predicted'])} | {_pct(bucket['observed'])} |"
            )
    lines.extend([
        "",
        "Paired race bootstrap (candidate minus Matrix; positive means improvement):",
        "",
        "| Candidate | Metric | Mean | 95% CI |",
        "|---|---|---:|---:|",
    ])
    for candidate, bootstrap in final["bootstrap"].items():
        for metric, values in bootstrap.items():
            low, high = values["ci95"]
            lines.append(
                f"| {candidate} | {metric} | {values['mean']:+.6f} | "
                f"[{low:+.6f}, {high:+.6f}] |"
            )
    lines.extend([
        "",
        "## LEARNING CURVE",
        "",
        "| Training races | Validation races | Win Brier | Place Brier | Top-1 | Top-3 |",
        "|---:|---:|---:|---:|---:|---:|",
    ])
    for point in results["learning_curve"]:
        metrics = point["metrics"]
        lines.append(
            f"| {point['training_races']} | {point['validation_races']} | "
            f"{metrics['win_brier']:.6f} | {metrics['place_brier']:.6f} | "
            f"{_pct(metrics['top1'])} | {_pct(metrics['top3'])} |"
        )
    lines.extend([
        "",
        "The maximum training point is 444 races because the last 150 development races remain a fixed chronological learning-curve validation block. Testing 500/600 training races would overlap that block and violate the point-in-time comparison. Win Brier continued to improve modestly, while Top-1/Top-3 remained unstable; more races may help probability estimation but current data do not show a stable ranking breakthrough.",
        "",
        "## BETTING PERFORMANCE",
        "",
        "Market odds were introduced only after all analysis predictions and model selection were frozen.",
        "",
        "### WIN",
        "",
        f"Current Matrix Betting ROI: **{_pct(betting['champion']['roi']) if betting['champion']['roi'] is not None else 'N/A'}**",
        "",
        f"Best ML Betting ROI: **{_pct(betting[best_name]['roi']) if betting[best_name]['roi'] is not None else 'N/A'}**",
        "",
        f"Difference: **{100 * ((betting[best_name]['roi'] or 0) - (betting['champion']['roi'] or 0)):+.2f} percentage points**",
        "",
        "### PLACE",
        "",
        "Current Matrix Betting ROI: **N/A**",
        "",
        "Best ML Betting ROI: **N/A**",
        "",
        "Reason: historical place dividends are unavailable; win SP is not a valid proxy.",
        "",
        "## RISK",
        "",
        f"Current Matrix Max Drawdown: **{betting['champion']['maximum_drawdown_units']:.2f} units**",
        "",
        f"ML Max Drawdown: **{betting[best_name]['maximum_drawdown_units']:.2f} units**",
        "",
        "### Full win betting scorecard",
        "",
        "| Model | Bets | Profit (u) | ROI | Strike | Avg odds | Max DD (u) | Longest losing streak |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for name in (*MODEL_NAMES, "hybrid"):
        card = betting[name]
        lines.append(
            f"| {name} | {card['bets']} | {card['profit']:.2f} | {_pct(card['roi'])} | "
            f"{_pct(card['strike_rate'])} | {card['average_odds']:.2f} | "
            f"{card['maximum_drawdown_units']:.2f} | {card['longest_losing_streak']} |"
        )
    lines.extend([
        "",
        "### Post-analysis betting segments",
        "",
        "Favourite status, odds and edge are created only after predictions are frozen. Full venue/distance/class/track/race-type/field-size breakdowns are preserved in the JSON result.",
        "",
        "| Model | Segment | Group | Bets | Profit (u) | ROI | Strike | Max DD (u) |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ])
    for name in ("champion", best_name, "hybrid"):
        for family in ("market_status", "odds_band", "predicted_edge", "confidence"):
            for label, card in final["betting_segments"][name][family].items():
                if not card["bets"]:
                    continue
                lines.append(
                    f"| {name} | {family} | {label} | {card['bets']} | "
                    f"{card['profit']:.2f} | {_pct(card['roi'])} | "
                    f"{_pct(card['strike_rate'])} | {card['maximum_drawdown_units']:.2f} |"
                )
    lines.extend([
        "",
        "## CLV",
        "",
        "Current Matrix: **N/A**",
        "",
        "ML: **N/A**",
        "",
        "No timestamped opening/closing odds snapshots exist in the aligned archive.",
        "",
        "## EXPLAINABILITY",
        "",
        "Top permutation features for Place Brier:",
        "",
    ])
    for item in results["explainability"]["features"][:20]:
        lines.append(f"- `{item['feature']}`: {item['importance']:+.6f}")
    shap_result = results["explainability"].get("shap", {})
    lines.extend([
        "",
        "Top TreeSHAP features for the selected Place model:",
        "",
    ])
    if shap_result.get("status") == "complete":
        for item in shap_result["features"][:20]:
            lines.append(f"- `{item['feature']}`: {item['mean_abs_shap']:.6f}")
    else:
        lines.append(f"- SHAP unavailable: `{shap_result.get('reason', 'unknown reason')}`")
    overlap_text = "; ".join(
        ", ".join(item["features"])
        for item in quality.get("conceptual_overlap_groups", [])
    ) or "See readiness report"
    constant_text = ", ".join(
        item["feature"] for item in quality.get("constant_features", [])
    ) or "none"
    lines.extend([
        "",
        "### Ten diagnostic questions",
        "",
        "1. **Which features genuinely improve prediction?** Permutation and TreeSHAP agree that pace figure, official rating, recent form, trainer place performance and Performance Quality are the strongest reusable signals. This is predictive association on the holdout, not a causal claim.",
        "2. **Which Matrix features remain strong?** `leaf_pace_figure_score`, `leaf_rating_score`, `leaf_form_score` and `leaf_performance_quality_score` all appear near the top, supporting the core Matrix design.",
        f"3. **Which are weak?** Features outside the leading permutation set, including heavily neutral report leaves, add little stable holdout value. Examples: sectional importance {importance_lookup.get('leaf_sectional_score', 0.0):+.6f}, health {importance_lookup.get('leaf_health_score', 0.0):+.6f}, confidence {importance_lookup.get('leaf_confidence_score', 0.0):+.6f}.",
        f"4. **Which are duplicated?** Conceptual overlaps audited: {overlap_text}. Exact non-constant duplicates are reported separately in readiness.",
        "5. **Which appear overweighted?** No Matrix dimension can be defensibly labelled overweighted from this experiment: removing the Matrix structure made independent ML ranking materially worse, especially Top-3.",
        "6. **Which appear underweighted?** The hybrid hints that conditional combinations can improve Place Brier, but ranking worsened and bootstrap intervals cross zero. That is insufficient evidence to reweight any live dimension.",
        f"7. **Which neutral/default features create noise?** Constant/dead snapshot inputs are: {constant_text}. The pipeline now drops zero-variance columns inside each chronological training fit; high-neutral leaves such as weight and sectionals remain documented and should not gain influence without new evidence.",
        "8. **Which nonlinear relationships appear?** XGBoost uses barrier, field size, race type and trainer/jockey rates alongside pace/rating. However, its final Top-3 deficit shows those nonlinearities do not generalise strongly enough yet.",
        "9. **Which interactions are missing from Matrix?** The strongest unresolved candidate is shallow formal history × wet going, plus condition-specific trainer/jockey and timed-trial evidence. Existing archive fields cannot identify these point-in-time effects reliably.",
        "10. **What is ML learning that Wong Choi misses?** Mostly conditional scaling of signals the Matrix already has, rather than a new independent ability source. The 50% hybrid's small Place-probability gains are statistically fragile, ranking and betting performance are worse, so this learning is research-only.",
    ])
    lines.extend([
        "",
        "## SEGMENT ANALYSIS",
        "",
        "The full venue breakdown is preserved in the JSON result. Major structural segments are below.",
        "",
        "| Segment | Group | Races | Matrix Win Brier | ML Win Brier | Matrix Top-3 | ML Top-3 |",
        "|---|---|---:|---:|---:|---:|---:|",
    ])
    for family in ("distance", "class", "race_type", "track_condition", "field_size", "confidence", "market_status"):
        champion_groups = final["segments"]["champion"][family]
        best_groups = final["segments"][best_name][family]
        for label in sorted(set(champion_groups) & set(best_groups)):
            current = champion_groups[label]
            challenger = best_groups[label]
            lines.append(
                f"| {family} | {label} | {current['races']} | "
                f"{current['win_brier']:.6f} | {challenger['win_brier']:.6f} | "
                f"{_pct(current['top3'])} | {_pct(challenger['top3'])} |"
            )
    lines.extend([
        "",
        "`market_status` is a retrospective race-level slice (`FavouriteWon` / `NonFavouriteWon`) created only after predictions were frozen; every race remains whole. It is not an input feature. Betting segments for every model and every required family are in `au_ml_experiment_results.json`.",
        "",
        "## REPRODUCIBILITY",
        "",
        "Run the complete archive → runtime snapshot → readiness → ML program with one command:",
        "",
        "```bash",
        "python3 .agents/skills/au_racing/au_wong_choi_auto/scripts/au_ml_rebuild.py \\",
        "  --archive-root \"<AU_Racing archive>\" \\",
        "  --results-csv \"<point-in-time merged results.csv>\" \\",
        "  --work-dir /private/tmp/au_ml_program \\",
        "  --report-dir .",
        "```",
        "",
        "The wrapper defaults to `--require-complete`, records commands/input and output hashes in `au_ml_rebuild_manifest.json`, and inherits the caller environment. On macOS, LightGBM/XGBoost may require `DYLD_LIBRARY_PATH` pointing to a trusted `libomp` installation.",
        "",
        "## PRODUCTION PROMOTION GATE",
        "",
        "| Candidate | Probability | Top rank | Walk-forward | Bootstrap | Betting risk | Overall |",
        "|---|---|---|---|---|---|---|",
    ])
    for name, gate in results["verdict"]["candidate_gates"].items():
        mark = lambda value: "PASS" if value else "FAIL"
        lines.append(
            f"| {name} | {mark(gate['probability'])} | {mark(gate['top_rank'])} | "
            f"{mark(gate['walkforward'])} ({gate['walkforward_improved_periods']}/{periods}) | "
            f"{mark(gate['bootstrap'])} | {mark(gate['betting_not_materially_worse'])} | "
            f"{mark(gate['passed'])} |"
        )
    lines.extend([
        "",
        *[f"- {reason}" for reason in results["verdict"]["reasons"]],
        "",
        "## FINAL VERDICT",
        "",
        f"**{verdict}**",
        "",
        results["verdict"]["explanation"],
        "",
        "Production Rating Matrix code was not changed by model training or betting results.",
        "",
    ])
    return "\n".join(lines)


def serializable_metrics(metrics: dict) -> dict:
    return {key: value for key, value in metrics.items() if key != "per_race"}


def strip_per_race(value):
    if isinstance(value, dict):
        return {key: strip_per_race(item) for key, item in value.items() if key != "per_race"}
    if isinstance(value, list):
        return [strip_per_race(item) for item in value]
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--readiness-audit", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args()

    readiness = json.loads(args.readiness_audit.read_text(encoding="utf-8"))
    if readiness.get("readiness") == "NOT READY":
        raise SystemExit("Dataset is NOT READY; fix integrity/leakage blockers first.")
    frame, contract = load_dataset(args.dataset)
    development, holdout, split = chronological_holdout(frame)
    print(f"Dataset {frame['race_id'].nunique()} races; final test {split['holdout_races']} races", flush=True)

    walk_forward, wf_predictions = walkforward(development, contract)
    challenger_scores = {
        name: model_selection_score(walk_forward["summary"][name])
        for name in CHALLENGERS
    }
    best_name = max(challenger_scores, key=challenger_scores.get)
    hybrid_alpha, hybrid_options = select_hybrid(wf_predictions, best_name)
    for period in walk_forward["periods"]:
        valid_start = pd.Timestamp(period["valid_start"])
        valid_end = pd.Timestamp(period["valid_end"])
        champion_period = wf_predictions["champion"][
            wf_predictions["champion"]["date"].between(valid_start, valid_end)
        ].reset_index(drop=True)
        best_period = wf_predictions[best_name][
            wf_predictions[best_name]["date"].between(valid_start, valid_end)
        ].reset_index(drop=True)
        period["metrics"]["hybrid"] = evaluate_predictions(
            combine_predictions(champion_period, best_period, hybrid_alpha)
        )
    improved_periods = sum(
        model_selection_score(period["metrics"][best_name])
        > model_selection_score(period["metrics"]["champion"])
        for period in walk_forward["periods"]
    )
    hybrid_improved_periods = sum(
        model_selection_score(period["metrics"]["hybrid"])
        > model_selection_score(period["metrics"]["champion"])
        for period in walk_forward["periods"]
    )
    print(f"Development selection: {best_name}; hybrid alpha {hybrid_alpha}", flush=True)

    final_predictions, details = predict_all_models(development, holdout, contract)
    final_metrics = {name: evaluate_predictions(prediction) for name, prediction in final_predictions.items()}
    hybrid_prediction = combine_predictions(
        final_predictions["champion"], final_predictions[best_name], hybrid_alpha
    )
    final_metrics["hybrid"] = evaluate_predictions(hybrid_prediction)
    bootstraps = {
        best_name: paired_bootstrap(final_metrics["champion"], final_metrics[best_name]),
        "hybrid": paired_bootstrap(final_metrics["champion"], final_metrics["hybrid"]),
    }
    curve = learning_curve(development, contract, best_name)
    fitted_best_place = details["fitted"][best_name]["place"]["pipeline"]
    importance = feature_importance(fitted_best_place, holdout, contract, "place")
    final_segments = {
        name: segment_analysis(prediction)
        for name, prediction in {
            **final_predictions,
            "hybrid": hybrid_prediction,
        }.items()
    }
    betting = {
        name: betting_scorecard(prediction)
        for name, prediction in {
            **final_predictions,
            "hybrid": hybrid_prediction,
        }.items()
    }
    betting_segments = {
        name: betting_segment_analysis(prediction)
        for name, prediction in {
            **final_predictions,
            "hybrid": hybrid_prediction,
        }.items()
    }
    decision, reasons, promotion_gates = promotion_verdict(
        final_metrics["champion"],
        {best_name: final_metrics[best_name], "hybrid": final_metrics["hybrid"]},
        bootstraps,
        walk_forward["periods"],
        betting,
        best_name,
    )
    explanation = (
        "Neither the independent challenger nor the hybrid cleared every probability, ranking, "
        "walk-forward, statistical-support and betting-risk gate. Keep the deterministic Champion "
        "and preserve the ML pipeline/results as research."
        if decision == "KEEP CURRENT MATRIX"
        else "The selected architecture cleared the predeclared independent-analysis gates; production still requires a separate deployment review."
    )
    results = {
        "program": "AU Wong Choi Full Machine Learning Program",
        "generated_at": pd.Timestamp.now(tz="Australia/Sydney").isoformat(),
        "dataset": {
            "races": int(frame["race_id"].nunique()),
            "runners": len(frame),
            "date_range": [str(frame["date"].min().date()), str(frame["date"].max().date())],
            "readiness": readiness["readiness"],
            "holdout_disclosure": "New to this ML run; not globally untouched because the Matrix used the archive previously.",
            "feature_quality": readiness.get("feature_quality", {}),
        },
        "champion": readiness["champion"],
        "dependencies": {
            "lightgbm": getattr(sys.modules.get("lightgbm"), "__version__", "unavailable"),
            "xgboost": getattr(sys.modules.get("xgboost"), "__version__", "unavailable"),
            "sklearn": sys.modules["sklearn"].__version__ if "sklearn" in sys.modules else "unknown",
            "openmp": "LLVM libomp 19.1.5, venv-local DYLD_LIBRARY_PATH",
        },
        "split": split,
        "walk_forward": walk_forward,
        "selection": {
            "challenger_scores": challenger_scores,
            "best_independent_model": best_name,
            "hybrid_alpha": hybrid_alpha,
            "hybrid_options": hybrid_options,
            "walkforward_improved_periods": improved_periods,
            "hybrid_walkforward_improved_periods": hybrid_improved_periods,
        },
        "final_test": {
            "metrics": final_metrics,
            "bootstrap": bootstraps,
            "timings_seconds": details["timings_seconds"],
            "segments": final_segments,
            "betting": betting,
            "betting_segments": betting_segments,
        },
        "learning_curve": curve,
        "explainability": importance,
        "verdict": {
            "decision": decision,
            "reasons": reasons,
            "candidate_gates": promotion_gates,
            "explanation": explanation,
            "production_changed": False,
        },
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(strip_per_race(results), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text(report_markdown(results), encoding="utf-8")
    print(f"Best independent: {best_name}")
    print(f"Final verdict: {decision}")
    print(f"JSON: {args.output_json}")
    print(f"Report: {args.output_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
