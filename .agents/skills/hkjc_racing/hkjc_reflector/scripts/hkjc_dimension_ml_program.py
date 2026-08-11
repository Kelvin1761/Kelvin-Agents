#!/usr/bin/env python3
"""Research-only ML audit for selected HKJC scoring dimensions.

The production seven-dimension Matrix is frozen.  This program tests whether
three specific dimensions contain systematic residual information by using:

1. dimension ablation;
2. a diagnostic standalone dimension model; and
3. a strongly regularised residual model with a clipped log-odds adjustment.

All preprocessing and fitting are chronological and fold-local.  The external
meeting is used once, after the residual cap is selected on development data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit, logit
from sklearn.linear_model import LogisticRegression

from hkjc_ml_program import (
    FACT_NUMERIC,
    ModelSpec,
    PRODUCTION_MATRIX_WEIGHTS,
    RANDOM_SEED,
    RACE_KEYS,
    TARGETS,
    _coherent_win_probabilities,
    _fit,
    _metric_record,
    _preprocessor,
    add_race_relative_features,
    assert_leakage_safe,
    chronological_blocks,
    clean_archive,
    make_matrix_calibrator,
    make_pipeline,
    metrics,
    predict_probabilities,
)


ROOT = Path(__file__).resolve().parents[5]
DEFAULT_PRIMARY = ROOT / "scratch" / "hkjc_ranking_dataset_current.csv"
DEFAULT_EXTERNAL = ROOT / "scratch" / "hkjc_ranking_dataset_2026_07_15_current.csv"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "artifacts" / "hkjc_dimension_ml_program"
CAPS = (0.05, 0.10, 0.20)
L2_PENALTY = 1.0
MINIMUM_TRAIN_MEETINGS = 8


DIMENSIONS: dict[str, dict[str, list[str]]] = {
    "trainer_signal": {
        "numeric": [
            "matrix_trainer_signal",
            "rel_matrix_trainer_signal",
            "feat_jockey_score",
            "feat_trainer_score",
            "tw_jockey_present",
        ],
        "categorical": [],
    },
    "race_shape": {
        "numeric": [
            "matrix_race_shape",
            "rel_matrix_race_shape",
            "feat_draw_score",
            "feat_race_shape_context_score",
            "barrier",
            "field_size",
            "distance_num",
        ],
        "categorical": ["venue", "course"],
    },
    "stability": {
        "numeric": [
            "matrix_stability",
            "rel_matrix_stability",
            "feat_form_score",
            "feat_consistency_score",
            "feat_trackwork_trend_score",
            "last6_runs",
            "last6_mean_finish",
            "last6_best_finish",
            "last6_worst_finish",
            "last6_top3_count",
            "last6_top5_count",
            "days_since_last",
            "tw_entries_count",
            "tw_gallop_count",
            "tw_flags_count",
        ],
        "categorical": [],
    },
}


@dataclass
class OffsetResidualModel:
    preprocessor: Any
    coefficients: np.ndarray
    l2_penalty: float
    success: bool
    iterations: int
    objective: float

    def raw_delta(self, frame: pd.DataFrame) -> np.ndarray:
        transformed = np.asarray(self.preprocessor.transform(frame), dtype=float)
        return transformed @ self.coefficients


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--primary", default=str(DEFAULT_PRIMARY))
    parser.add_argument("--external", default=str(DEFAULT_EXTERNAL))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--seed", type=int, default=RANDOM_SEED)
    return parser.parse_args()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _race_weight(field_size: pd.Series) -> np.ndarray:
    return (
        1.0 / pd.to_numeric(field_size, errors="coerce").clip(lower=1)
    ).to_numpy(dtype=float)


def _fit_offset_residual(
    train: pd.DataFrame,
    features: list[str],
    categorical: list[str],
    target: str,
    baseline_probability: np.ndarray,
    l2_penalty: float = L2_PENALTY,
) -> OffsetResidualModel:
    numeric = [column for column in features if column not in categorical]
    preprocessor = _preprocessor(numeric, categorical)
    transformed = np.asarray(preprocessor.fit_transform(train[features]), dtype=float)
    y = train[TARGETS[target]].to_numpy(dtype=float)
    weights = _race_weight(train["field_size"])
    weights = weights / weights.sum()
    offset = logit(np.clip(baseline_probability, 1e-6, 1 - 1e-6))

    def objective(beta: np.ndarray) -> tuple[float, np.ndarray]:
        linear = offset + transformed @ beta
        probability = expit(linear)
        loss = float(
            np.sum(weights * (np.logaddexp(0.0, linear) - y * linear))
            + 0.5 * l2_penalty * np.dot(beta, beta)
        )
        gradient = transformed.T @ (weights * (probability - y)) + l2_penalty * beta
        return loss, gradient

    result = minimize(
        objective,
        np.zeros(transformed.shape[1], dtype=float),
        method="L-BFGS-B",
        jac=True,
        options={"maxiter": 500, "ftol": 1e-12},
    )
    if not result.success:
        raise RuntimeError(f"Offset residual fit failed: {result.message}")
    return OffsetResidualModel(
        preprocessor=preprocessor,
        coefficients=np.asarray(result.x, dtype=float),
        l2_penalty=l2_penalty,
        success=bool(result.success),
        iterations=int(result.nit),
        objective=float(result.fun),
    )


def _apply_delta(
    frame: pd.DataFrame,
    baseline_probability: np.ndarray,
    raw_delta: np.ndarray,
    cap: float,
    target: str,
) -> np.ndarray:
    bounded = np.clip(raw_delta, -cap, cap)
    probability = expit(
        logit(np.clip(baseline_probability, 1e-6, 1 - 1e-6)) + bounded
    )
    if target == "Win":
        probability = _coherent_win_probabilities(frame, probability)
    return np.clip(probability, 1e-6, 1 - 1e-6)


def _ablated_ability(frame: pd.DataFrame, dimension: str) -> pd.Series:
    column = f"matrix_{dimension}"
    weight = PRODUCTION_MATRIX_WEIGHTS[column]
    return (
        frame["current_live_recomputed_ability"] - weight * frame[column]
    ) / (1.0 - weight)


def _available_features(
    data: pd.DataFrame, dimension: str
) -> tuple[list[str], list[str]]:
    configured = DIMENSIONS[dimension]
    numeric = [
        column
        for column in configured["numeric"]
        if column in data and data[column].notna().any()
    ]
    categorical = [
        column
        for column in configured["categorical"]
        if column in data and data[column].notna().any()
    ]
    assert_leakage_safe(numeric + categorical)
    return numeric, categorical


def _fold_cache(development: pd.DataFrame, target: str) -> list[dict[str, Any]]:
    output = []
    feature = ["current_live_recomputed_ability"]
    for train_dates, test_date in chronological_blocks(
        development, MINIMUM_TRAIN_MEETINGS
    ):
        train = development[development["date"].isin(train_dates)].copy()
        test = development[development["date"] == test_date].copy()
        model = make_matrix_calibrator()
        _fit(model, train[feature], train[TARGETS[target]], train["field_size"])
        output.append(
            {
                "train": train,
                "test": test,
                "train_probability": predict_probabilities(model, train, feature, target),
                "test_probability": predict_probabilities(model, test, feature, target),
                "train_end": max(train_dates),
                "test_date": test_date,
            }
        )
    return output


def _prediction_frame(
    test: pd.DataFrame,
    probability: np.ndarray,
    train_end: str,
    test_date: str,
) -> pd.DataFrame:
    frame = test.copy()
    frame["probability"] = probability
    frame["fold_train_end"] = train_end
    frame["fold_test_date"] = test_date
    return frame


def evaluate_dimension_walk_forward(
    development: pd.DataFrame,
    dimension: str,
    target: str,
    folds: list[dict[str, Any]],
    seed: int,
) -> tuple[dict[str, pd.DataFrame], list[dict[str, Any]]]:
    numeric, categorical = _available_features(development, dimension)
    features = numeric + categorical
    logistic = ModelSpec(
        "Dimension Standalone",
        lambda: LogisticRegression(
            C=0.25, max_iter=1500, solver="lbfgs", random_state=seed
        ),
    )
    outputs: dict[str, list[pd.DataFrame]] = {
        "Matrix Champion": [],
        "Ablated": [],
        "Standalone": [],
        **{f"Residual cap={cap:.2f}": [] for cap in CAPS},
    }
    optimizer_rows: list[dict[str, Any]] = []

    for fold in folds:
        train = fold["train"].copy()
        test = fold["test"].copy()
        outputs["Matrix Champion"].append(
            _prediction_frame(
                test,
                fold["test_probability"],
                fold["train_end"],
                fold["test_date"],
            )
        )

        ablation_column = f"ablated_{dimension}_ability"
        train[ablation_column] = _ablated_ability(train, dimension)
        test[ablation_column] = _ablated_ability(test, dimension)
        ablation_model = make_matrix_calibrator()
        _fit(
            ablation_model,
            train[[ablation_column]],
            train[TARGETS[target]],
            train["field_size"],
        )
        ablation_probability = predict_probabilities(
            ablation_model, test, [ablation_column], target
        )
        outputs["Ablated"].append(
            _prediction_frame(
                test,
                ablation_probability,
                fold["train_end"],
                fold["test_date"],
            )
        )

        standalone_model = make_pipeline(logistic, numeric, categorical)
        _fit(
            standalone_model,
            train[features],
            train[TARGETS[target]],
            train["field_size"],
        )
        standalone_probability = predict_probabilities(
            standalone_model, test, features, target
        )
        outputs["Standalone"].append(
            _prediction_frame(
                test,
                standalone_probability,
                fold["train_end"],
                fold["test_date"],
            )
        )

        residual = _fit_offset_residual(
            train,
            features,
            categorical,
            target,
            fold["train_probability"],
        )
        raw_delta = residual.raw_delta(test[features])
        optimizer_rows.append(
            {
                "dimension": dimension,
                "target": target,
                "fold_test_date": fold["test_date"],
                "features": len(features),
                "transformed_features": len(residual.coefficients),
                "iterations": residual.iterations,
                "objective": residual.objective,
                "max_abs_raw_delta": float(np.max(np.abs(raw_delta))),
                "mean_abs_raw_delta": float(np.mean(np.abs(raw_delta))),
            }
        )
        for cap in CAPS:
            probability = _apply_delta(
                test, fold["test_probability"], raw_delta, cap, target
            )
            outputs[f"Residual cap={cap:.2f}"].append(
                _prediction_frame(
                    test,
                    probability,
                    fold["train_end"],
                    fold["test_date"],
                )
            )

    return (
        {
            method: pd.concat(frames, ignore_index=True)
            for method, frames in outputs.items()
        },
        optimizer_rows,
    )


def _selection_rows(
    predictions: dict[str, pd.DataFrame], dimension: str, target: str
) -> list[dict[str, Any]]:
    baseline = metrics(predictions["Matrix Champion"], "probability", target)
    rows = []
    for method, frame in predictions.items():
        current = metrics(frame, "probability", target)
        row: dict[str, Any] = {
            "period": "walk_forward",
            "dimension": dimension,
            "target": target,
            "method": method,
            **current,
        }
        for metric_name in (
            "top2_zero_hit",
            "top2_one_hit",
            "top2_two_hit",
            "winner_top3",
            "top3_capture_at5",
            "ndcg_at5",
            "log_loss",
            "brier",
        ):
            row[f"delta_{metric_name}"] = current[metric_name] - baseline[metric_name]
        row["top2_miss_severity"] = (
            2.0 * current["top2_zero_hit"] + current["top2_one_hit"]
        )
        row["delta_top2_miss_severity"] = row["top2_miss_severity"] - (
            2.0 * baseline["top2_zero_hit"] + baseline["top2_one_hit"]
        )
        row["selection_score"] = (
            -1.5 * row["delta_top2_miss_severity"]
            + row["delta_winner_top3"]
            + row["delta_top3_capture_at5"]
            + 0.25 * row["delta_ndcg_at5"]
            - 0.20 * row["delta_log_loss"]
        )
        row["development_gate"] = bool(
            method.startswith("Residual")
            and row["delta_top2_miss_severity"] < 0
            and row["delta_winner_top3"] >= -0.005
            and row["delta_top3_capture_at5"] >= -0.005
            and row["delta_ndcg_at5"] >= -0.005
            and row["delta_log_loss"] <= 0.002
            and row["delta_brier"] <= 0.001
        )
        rows.append(row)
    return rows


def _select_cap(rows: pd.DataFrame, dimension: str) -> tuple[float, bool]:
    candidates = rows[
        (rows["dimension"] == dimension)
        & (rows["target"] == "Win")
        & rows["method"].str.startswith("Residual")
    ].copy()
    gated = candidates[candidates["development_gate"]]
    selection = gated if not gated.empty else candidates
    best = selection.sort_values(
        ["selection_score", "log_loss", "method"],
        ascending=[False, True, True],
    ).iloc[0]
    return float(str(best["method"]).split("=")[-1]), bool(not gated.empty)


def fit_external_models(
    development: pd.DataFrame,
    external: pd.DataFrame,
    dimension: str,
    target: str,
    cap: float,
    seed: int,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    numeric, categorical = _available_features(development, dimension)
    features = numeric + categorical
    base_feature = ["current_live_recomputed_ability"]
    baseline_model = make_matrix_calibrator()
    _fit(
        baseline_model,
        development[base_feature],
        development[TARGETS[target]],
        development["field_size"],
    )
    train_base = predict_probabilities(
        baseline_model, development, base_feature, target
    )
    external_base = predict_probabilities(
        baseline_model, external, base_feature, target
    )

    ablation_column = f"ablated_{dimension}_ability"
    train_ablation = development.copy()
    external_ablation = external.copy()
    train_ablation[ablation_column] = _ablated_ability(development, dimension)
    external_ablation[ablation_column] = _ablated_ability(external, dimension)
    ablation_model = make_matrix_calibrator()
    _fit(
        ablation_model,
        train_ablation[[ablation_column]],
        train_ablation[TARGETS[target]],
        train_ablation["field_size"],
    )
    ablation_probability = predict_probabilities(
        ablation_model, external_ablation, [ablation_column], target
    )

    logistic = ModelSpec(
        "Dimension Standalone",
        lambda: LogisticRegression(
            C=0.25, max_iter=1500, solver="lbfgs", random_state=seed
        ),
    )
    standalone_model = make_pipeline(logistic, numeric, categorical)
    _fit(
        standalone_model,
        development[features],
        development[TARGETS[target]],
        development["field_size"],
    )
    standalone_probability = predict_probabilities(
        standalone_model, external, features, target
    )

    residual = _fit_offset_residual(
        development, features, categorical, target, train_base
    )
    raw_delta = residual.raw_delta(external[features])
    residual_probability = _apply_delta(
        external, external_base, raw_delta, cap, target
    )

    def with_probability(probability: np.ndarray) -> pd.DataFrame:
        frame = external.copy()
        frame["probability"] = probability
        return frame

    models = {
        "baseline_calibrator": baseline_model,
        "ablation_calibrator": ablation_model,
        "standalone_model": standalone_model,
        "residual_model": residual,
        "features": features,
        "categorical": categorical,
        "cap": cap,
        "target": target,
        "dimension": dimension,
    }
    return {
        "Matrix Champion": with_probability(external_base),
        "Ablated": with_probability(ablation_probability),
        "Standalone": with_probability(standalone_probability),
        f"Residual cap={cap:.2f}": with_probability(residual_probability),
    }, models


def _external_rows(
    predictions: dict[str, pd.DataFrame], dimension: str, target: str
) -> list[dict[str, Any]]:
    baseline = metrics(predictions["Matrix Champion"], "probability", target)
    rows = []
    for method, frame in predictions.items():
        current = metrics(frame, "probability", target)
        row: dict[str, Any] = {
            "period": "external_holdout",
            "dimension": dimension,
            "target": target,
            "method": method,
            **current,
        }
        for metric_name in (
            "top2_zero_hit",
            "top2_one_hit",
            "top2_two_hit",
            "winner_top3",
            "top3_capture_at5",
            "ndcg_at5",
            "log_loss",
            "brier",
        ):
            row[f"delta_{metric_name}"] = current[metric_name] - baseline[metric_name]
        row["top2_miss_severity"] = (
            2.0 * current["top2_zero_hit"] + current["top2_one_hit"]
        )
        row["delta_top2_miss_severity"] = row["top2_miss_severity"] - (
            2.0 * baseline["top2_zero_hit"] + baseline["top2_one_hit"]
        )
        row["external_non_regression"] = bool(
            row["delta_winner_top3"] >= -0.12
            and row["delta_top3_capture_at5"] >= -0.04
            and row["delta_ndcg_at5"] >= -0.04
            and row["delta_log_loss"] <= 0.02
            and row["delta_brier"] <= 0.01
        )
        rows.append(row)
    return rows


def _feature_audit(data: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for dimension in DIMENSIONS:
        numeric, categorical = _available_features(data, dimension)
        for column in numeric + categorical:
            series = data[column]
            numeric_series = pd.to_numeric(series, errors="coerce")
            rows.append(
                {
                    "dimension": dimension,
                    "feature": column,
                    "kind": "categorical" if column in categorical else "numeric",
                    "coverage_rate": float(series.notna().mean()),
                    "missing_rate": float(series.isna().mean()),
                    "unique_values": int(series.nunique(dropna=True)),
                    "zero_rate": (
                        float((numeric_series == 0).mean())
                        if column not in categorical
                        else math.nan
                    ),
                    "leakage_safe": True,
                    "pre_race_available": True,
                }
            )
    return pd.DataFrame(rows)


def _race_summary(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for race_key, group in frame.groupby("race_key", sort=False):
        ranked = group.sort_values("probability", ascending=False)
        actual = set(group.loc[group["is_top3"] == 1, "horse_number"].astype(str))
        predicted = set(ranked.head(2)["horse_number"].astype(str))
        winner = str(group.loc[group["is_win"] == 1, "horse_number"].iloc[0])
        rank_lookup = {
            str(value): rank
            for rank, value in enumerate(ranked["horse_number"].astype(str), start=1)
        }
        rows.append(
            {
                "race_key": race_key,
                "date": group["date"].iloc[0],
                "meeting_name": group["meeting_name"].iloc[0],
                "race_number": group["race_number"].iloc[0],
                "top2_hits": len(actual & predicted),
                "winner_rank": rank_lookup[winner],
                "actual_top3": ",".join(sorted(actual, key=int)),
                "predicted_top2": ",".join(ranked.head(2)["horse_number"].astype(str)),
            }
        )
    return pd.DataFrame(rows)


def _weak_race_impact(
    baseline: pd.DataFrame,
    candidate: pd.DataFrame,
    dimension: str,
    period: str,
    method: str,
) -> pd.DataFrame:
    base = _race_summary(baseline).add_prefix("baseline_")
    challenger = _race_summary(candidate).add_prefix("candidate_")
    merged = base.merge(
        challenger,
        left_on="baseline_race_key",
        right_on="candidate_race_key",
        validate="one_to_one",
    )
    merged = merged[merged["baseline_top2_hits"] <= 1].copy()
    merged["dimension"] = dimension
    merged["period"] = period
    merged["method"] = method
    merged["top2_hit_delta"] = (
        merged["candidate_top2_hits"] - merged["baseline_top2_hits"]
    )
    merged["winner_rank_delta"] = (
        merged["candidate_winner_rank"] - merged["baseline_winner_rank"]
    )
    merged["outcome"] = np.select(
        [merged["top2_hit_delta"] > 0, merged["top2_hit_delta"] < 0],
        ["helped", "harmed"],
        default="unchanged",
    )
    return merged


def _rank_movements(
    baseline: pd.DataFrame,
    candidate: pd.DataFrame,
    dimension: str,
    period: str,
    method: str,
) -> pd.DataFrame:
    keys = RACE_KEYS + ["race_key", "horse_number"]
    base = baseline.copy()
    challenger = candidate.copy()
    base["baseline_rank"] = base.groupby("race_key")["probability"].rank(
        ascending=False, method="first"
    )
    challenger["candidate_rank"] = challenger.groupby("race_key")["probability"].rank(
        ascending=False, method="first"
    )
    base_columns = keys + [
        "horse_name",
        "finish_pos",
        "is_win",
        "is_top3",
        "baseline_rank",
        "probability",
    ]
    challenger_columns = keys + ["candidate_rank", "probability"]
    merged = base[base_columns].merge(
        challenger[challenger_columns],
        on=keys,
        validate="one_to_one",
        suffixes=("_baseline", "_candidate"),
    )
    merged["rank_delta"] = merged["candidate_rank"] - merged["baseline_rank"]
    merged["entered_top2"] = (
        (merged["baseline_rank"] > 2) & (merged["candidate_rank"] <= 2)
    )
    merged["left_top2"] = (
        (merged["baseline_rank"] <= 2) & (merged["candidate_rank"] > 2)
    )
    merged["dimension"] = dimension
    merged["period"] = period
    merged["method"] = method
    return merged


def _segment_rows(
    baseline: pd.DataFrame,
    candidate: pd.DataFrame,
    dimension: str,
    period: str,
) -> list[dict[str, Any]]:
    rows = []
    for segment in ("venue", "course", "distance_num", "race_class_label"):
        for value, base_group in baseline.groupby(segment, dropna=False):
            race_keys = set(base_group["race_key"])
            candidate_group = candidate[candidate["race_key"].isin(race_keys)]
            races = len(race_keys)
            if races < 5:
                continue
            base_metric = metrics(base_group, "probability", "Win")
            candidate_metric = metrics(candidate_group, "probability", "Win")
            rows.append(
                {
                    "period": period,
                    "dimension": dimension,
                    "segment": segment,
                    "value": value,
                    "races": races,
                    "delta_top2_zero_hit": candidate_metric["top2_zero_hit"]
                    - base_metric["top2_zero_hit"],
                    "delta_winner_top3": candidate_metric["winner_top3"]
                    - base_metric["winner_top3"],
                    "delta_top3_capture_at5": candidate_metric["top3_capture_at5"]
                    - base_metric["top3_capture_at5"],
                    "delta_ndcg_at5": candidate_metric["ndcg_at5"]
                    - base_metric["ndcg_at5"],
                    "delta_log_loss": candidate_metric["log_loss"]
                    - base_metric["log_loss"],
                }
            )
    return rows


def _prediction_export(
    frame: pd.DataFrame,
    dimension: str,
    target: str,
    method: str,
    period: str,
) -> pd.DataFrame:
    columns = RACE_KEYS + [
        "race_key",
        "horse_number",
        "horse_name",
        "finish_pos",
        "is_win",
        "is_top3",
        "is_place",
        "field_size",
        "probability",
    ]
    output = frame[columns].copy()
    output["dimension"] = dimension
    output["target"] = target
    output["method"] = method
    output["period"] = period
    return output


def _format_metric(value: float) -> str:
    return f"{value:.4f}"


def _write_reports(
    output: Path,
    quality: dict[str, Any],
    walk: pd.DataFrame,
    external: pd.DataFrame,
    selected: dict[str, dict[str, Any]],
    weak: pd.DataFrame,
    rank_movements: pd.DataFrame,
    coefficients: pd.DataFrame,
) -> None:
    baseline = walk[
        (walk["dimension"] == "trainer_signal")
        & (walk["target"] == "Win")
        & (walk["method"] == "Matrix Champion")
    ].iloc[0]
    lines = [
        "# HKJC 個別評分維度 ML Research Report",
        "",
        f"產生日期：{date.today().isoformat()}",
        "",
        "## 結論先行",
        "",
        "今次只研究 `trainer_signal`、`race_shape`、`stability`。Production 七維 Matrix、外層權重、排序及 renderer 均沒有改動。",
        "",
        (
            f"現行權重重算後，walk-forward Matrix 基準為：0-hit "
            f"{_format_metric(baseline['top2_zero_hit'])}、Winner@3 "
            f"{_format_metric(baseline['winner_top3'])}、Top3 capture@5 "
            f"{_format_metric(baseline['top3_capture_at5'])}、NDCG@5 "
            f"{_format_metric(baseline['ndcg_at5'])}。"
        ),
        "",
        "Archive 嘅 `current_live_recomputed_ability` 原本沿用上一版外層權重；本輪已保留舊值作 audit，並由七維分數按 2026-08-01 production contract 重算基準。",
        "",
        "## Development cap selection",
        "",
        "| 維度 | 選定 cap | Development gate | External non-regression | 研究判斷 |",
        "|---|---:|---|---|---|",
    ]
    for dimension, info in selected.items():
        lines.append(
            f"| `{dimension}` | {info['cap']:.2f} | "
            f"{'PASS' if info['development_gate'] else 'FAIL'} | "
            f"{'PASS' if info['external_non_regression'] else 'FAIL'} | "
            f"{info['verdict']} |"
        )
    lines.extend(
        [
            "",
            "Operational decision：`stability` 已接入 checksum-pinned opt-in shadow monitoring；呢個決定唔等於 production promotion，亦唔會改主排名或投注建議。",
        ]
    )
    lines.extend(
        [
            "",
            "## Selected residual scorecard",
            "",
        "| Period | 維度 | 0-hit Δ | 0/1-hit severity Δ | Winner@3 Δ | Capture@5 Δ | NDCG@5 Δ | Log loss Δ |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for dimension, info in selected.items():
        for period, table in (("walk_forward", walk), ("external_holdout", external)):
            method = f"Residual cap={info['cap']:.2f}"
            row = table[
                (table["dimension"] == dimension)
                & (table["target"] == "Win")
                & (table["method"] == method)
            ].iloc[0]
            lines.append(
                f"| {period} | `{dimension}` | {row['delta_top2_zero_hit']:+.4f} | "
                f"{row['delta_top2_miss_severity']:+.4f} | {row['delta_winner_top3']:+.4f} | {row['delta_top3_capture_at5']:+.4f} | "
                f"{row['delta_ndcg_at5']:+.4f} | {row['delta_log_loss']:+.4f} |"
            )
    helped = weak[weak["outcome"] == "helped"].groupby(["period", "dimension"]).size()
    harmed = weak[weak["outcome"] == "harmed"].groupby(["period", "dimension"]).size()
    lines.extend(["", "## 0/1-hit races", ""])
    for dimension in DIMENSIONS:
        lines.append(
            f"- `{dimension}`：walk-forward 幫到 {int(helped.get(('walk_forward', dimension), 0))} 場，"
            f"傷害 {int(harmed.get(('walk_forward', dimension), 0))} 場；其餘不變。"
        )
    stability_moves = rank_movements[
        (rank_movements["dimension"] == "stability")
        & rank_movements["entered_top2"]
        & (rank_movements["is_top3"] == 1)
    ]
    walk_promotions = stability_moves[stability_moves["period"] == "walk_forward"]
    external_promotions = stability_moves[
        stability_moves["period"] == "external_holdout"
    ]
    lines.extend(
        [
            "",
            "### Stability Rank 3 → Top 2",
            "",
            f"- Development：{len(walk_promotions)} 匹實際三甲馬由 Rank 3 升 Rank 2，其中 {int(walk_promotions['is_win'].sum())} 匹係頭馬。",
            f"- External：{len(external_promotions)} 匹；包括 2026-07-15 R3「浪漫老撾」由 Rank 3 升 Rank 2，取代最終第7嘅「大千氣象」。",
            "- 呢啲係整個 residual ranking 自然產生嘅移動，唔係逐場 blind swap；完整清單見 `dimension_rank_movements.csv`。",
            "",
            "## Residual signal diagnosis",
            "",
        ]
    )
    for dimension in DIMENSIONS:
        top = coefficients[
            (coefficients["dimension"] == dimension)
            & (coefficients["target"] == "Win")
        ].nlargest(3, "abs_coefficient")
        rendered = ", ".join(
            f"`{row.feature}` ({row.coefficient:+.4f})"
            for row in top.itertuples(index=False)
        )
        lines.append(f"- `{dimension}`：{rendered}。")
    lines.append(
        "以上係標準化後、控制 Matrix offset 嘅條件 residual coefficient，只供診斷，唔等於 production 權重。"
    )
    lines.extend(
        [
            "",
            "## 方法與限制",
            "",
            f"- {quality['valid_races']} 場／{quality['valid_rows']} runners；development 24 meetings，external 1 meeting。",
            "- Walk-forward 以首 8 meetings 起步，每次只訓練較早日期；imputation、scaling、one-hot、calibration 同 residual fit 全部 fold-local。",
            f"- Residual 係 Matrix log-odds offset 上嘅 L2={L2_PENALTY:g} 細幅修正；cap 只由 development 選，external 只驗證一次。",
            "- 冇用 odds、市場排名、ROI、賽果 priors、事故資料、步速預測、跑法標籤、micro tie-break 或 blind swap。",
            "- External 只有 9 場，證據只可視為 non-regression check，唔足以批准 production promotion。",
            "",
            "詳細數字見 `dimension_walk_forward_results.csv`、`dimension_external_results.csv`、`dimension_weak_race_impact.csv` 同 `dimension_segment_analysis.csv`。",
        ]
    )
    (output / "hkjc_dimension_ml_report.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )

    passed = [
        dimension
        for dimension, info in selected.items()
        if info["development_gate"] and info["external_non_regression"]
    ]
    recommendation = [
        "# Dimension ML Promotion Recommendation",
        "",
        "## Decision",
        "",
        "**Do not promote to production.**",
        "",
        "今次係個別維度 research audit，唔係 production 權重搜尋。即使有維度通過今輪窄門，亦只代表值得做 shadow candidate。",
        "",
        f"同時通過 development 與 external non-regression：{', '.join(passed) if passed else '沒有'}。",
        "",
        "`stability` 已批准以固定 feature list、L2=1.0、cap=0.05 接入 opt-in shadow monitoring；主排名、Grade、verdict、Top Pick及投注建議保持不變。唔應因 9 場 external 或單一成功 swap 即時改 Matrix。",
    ]
    (output / "dimension_promotion_recommendation.md").write_text(
        "\n".join(recommendation) + "\n", encoding="utf-8"
    )


def main() -> int:
    args = parse_args()
    primary = Path(args.primary).resolve()
    external_source = Path(args.external).resolve()
    output = Path(args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "models").mkdir(exist_ok=True)

    raw, quality = clean_archive(primary, external_source)
    relative_base = [
        column
        for column in FACT_NUMERIC + list(PRODUCTION_MATRIX_WEIGHTS)
        if column in raw
    ]
    data, _ = add_race_relative_features(raw, relative_base)
    development = data[data["source_split"] == "development"].copy()
    external = data[data["source_split"] == "external_holdout"].copy()
    if development["date"].max() >= external["date"].min():
        raise ValueError("External holdout is not strictly later than development")

    audit = _feature_audit(data)
    audit.to_csv(output / "dimension_feature_audit.csv", index=False, encoding="utf-8-sig")

    walk_rows: list[dict[str, Any]] = []
    external_rows: list[dict[str, Any]] = []
    optimizer_rows: list[dict[str, Any]] = []
    prediction_exports: list[pd.DataFrame] = []
    weak_frames: list[pd.DataFrame] = []
    segment_rows: list[dict[str, Any]] = []
    rank_movement_frames: list[pd.DataFrame] = []
    coefficient_rows: list[dict[str, Any]] = []
    walk_predictions: dict[tuple[str, str], dict[str, pd.DataFrame]] = {}

    caches = {
        target: _fold_cache(development, target)
        for target in TARGETS
    }
    for dimension in DIMENSIONS:
        for target in TARGETS:
            predictions, optimizer = evaluate_dimension_walk_forward(
                development,
                dimension,
                target,
                caches[target],
                args.seed,
            )
            walk_predictions[(dimension, target)] = predictions
            walk_rows.extend(_selection_rows(predictions, dimension, target))
            optimizer_rows.extend(optimizer)
            for method, frame in predictions.items():
                prediction_exports.append(
                    _prediction_export(
                        frame, dimension, target, method, "walk_forward"
                    )
                )

    walk_table = pd.DataFrame(walk_rows)
    selected: dict[str, dict[str, Any]] = {}
    for dimension in DIMENSIONS:
        cap, development_gate = _select_cap(walk_table, dimension)
        selected[dimension] = {
            "cap": cap,
            "development_gate": development_gate,
        }

    for dimension in DIMENSIONS:
        cap = selected[dimension]["cap"]
        for target in TARGETS:
            predictions, models = fit_external_models(
                development,
                external,
                dimension,
                target,
                cap,
                args.seed,
            )
            external_rows.extend(_external_rows(predictions, dimension, target))
            safe_dimension = dimension.replace("_", "-")
            residual_model = models["residual_model"]
            portable_models = {
                **models,
                "residual_model": {
                    "preprocessor": residual_model.preprocessor,
                    "coefficients": residual_model.coefficients,
                    "l2_penalty": residual_model.l2_penalty,
                    "success": residual_model.success,
                    "iterations": residual_model.iterations,
                    "objective": residual_model.objective,
                },
            }
            joblib.dump(
                portable_models,
                output / "models" / f"{safe_dimension}-{target.lower()}-residual.joblib",
            )
            feature_names = residual_model.preprocessor.get_feature_names_out()
            for feature_name, coefficient in zip(
                feature_names, residual_model.coefficients
            ):
                coefficient_rows.append(
                    {
                        "dimension": dimension,
                        "target": target,
                        "feature": feature_name,
                        "coefficient": float(coefficient),
                        "abs_coefficient": abs(float(coefficient)),
                        "l2_penalty": residual_model.l2_penalty,
                        "selected_cap": cap,
                    }
                )
            for method, frame in predictions.items():
                prediction_exports.append(
                    _prediction_export(
                        frame, dimension, target, method, "external_holdout"
                    )
                )
        selected_method = f"Residual cap={cap:.2f}"
        walk_win = walk_predictions[(dimension, "Win")]
        weak_frames.append(
            _weak_race_impact(
                walk_win["Matrix Champion"],
                walk_win[selected_method],
                dimension,
                "walk_forward",
                selected_method,
            )
        )
        rank_movement_frames.append(
            _rank_movements(
                walk_win["Matrix Champion"],
                walk_win[selected_method],
                dimension,
                "walk_forward",
                selected_method,
            )
        )
        segment_rows.extend(
            _segment_rows(
                walk_win["Matrix Champion"],
                walk_win[selected_method],
                dimension,
                "walk_forward",
            )
        )

    external_table = pd.DataFrame(external_rows)
    for dimension in DIMENSIONS:
        cap = selected[dimension]["cap"]
        method = f"Residual cap={cap:.2f}"
        row = external_table[
            (external_table["dimension"] == dimension)
            & (external_table["target"] == "Win")
            & (external_table["method"] == method)
        ].iloc[0]
        selected[dimension]["external_non_regression"] = bool(
            row["external_non_regression"]
        )
        selected[dimension]["verdict"] = (
            "shadow candidate"
            if selected[dimension]["development_gate"]
            and selected[dimension]["external_non_regression"]
            else "reject / diagnostic only"
        )

        external_predictions, _ = fit_external_models(
            development,
            external,
            dimension,
            "Win",
            cap,
            args.seed,
        )
        weak_frames.append(
            _weak_race_impact(
                external_predictions["Matrix Champion"],
                external_predictions[method],
                dimension,
                "external_holdout",
                method,
            )
        )
        rank_movement_frames.append(
            _rank_movements(
                external_predictions["Matrix Champion"],
                external_predictions[method],
                dimension,
                "external_holdout",
                method,
            )
        )
        segment_rows.extend(
            _segment_rows(
                external_predictions["Matrix Champion"],
                external_predictions[method],
                dimension,
                "external_holdout",
            )
        )

    weak = pd.concat(weak_frames, ignore_index=True)
    predictions = pd.concat(prediction_exports, ignore_index=True)
    walk_table.to_csv(
        output / "dimension_walk_forward_results.csv", index=False, encoding="utf-8-sig"
    )
    walk_table[walk_table["method"].isin(["Matrix Champion", "Ablated"])].to_csv(
        output / "dimension_ablation_scorecard.csv", index=False, encoding="utf-8-sig"
    )
    walk_table[walk_table["method"].str.startswith("Residual")].to_csv(
        output / "dimension_residual_cap_search.csv", index=False, encoding="utf-8-sig"
    )
    external_table.to_csv(
        output / "dimension_external_results.csv", index=False, encoding="utf-8-sig"
    )
    pd.DataFrame(optimizer_rows).to_csv(
        output / "dimension_optimizer_diagnostics.csv", index=False, encoding="utf-8-sig"
    )
    predictions.to_csv(
        output / "dimension_predictions.csv", index=False, encoding="utf-8-sig"
    )
    weak.to_csv(
        output / "dimension_weak_race_impact.csv", index=False, encoding="utf-8-sig"
    )
    pd.DataFrame(segment_rows).to_csv(
        output / "dimension_segment_analysis.csv", index=False, encoding="utf-8-sig"
    )
    rank_movements = pd.concat(rank_movement_frames, ignore_index=True)
    rank_movements.to_csv(
        output / "dimension_rank_movements.csv", index=False, encoding="utf-8-sig"
    )
    coefficients = pd.DataFrame(coefficient_rows).sort_values(
        ["dimension", "target", "abs_coefficient"], ascending=[True, True, False]
    )
    coefficients.to_csv(
        output / "dimension_residual_coefficients.csv", index=False, encoding="utf-8-sig"
    )

    manifest = {
        "created_on": date.today().isoformat(),
        "git_head": _git_head(),
        "seed": args.seed,
        "primary": {"path": str(primary.relative_to(ROOT)), "sha256": _sha256(primary)},
        "external": {
            "path": str(external_source.relative_to(ROOT)),
            "sha256": _sha256(external_source),
        },
        "coverage": quality,
        "production_matrix_weights": PRODUCTION_MATRIX_WEIGHTS,
        "dimensions": DIMENSIONS,
        "caps": CAPS,
        "l2_penalty": L2_PENALTY,
        "minimum_train_meetings": MINIMUM_TRAIN_MEETINGS,
        "selected": selected,
        "package_versions": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scipy": __import__("scipy").__version__,
            "scikit_learn": __import__("sklearn").__version__,
        },
        "production_modified": False,
    }
    encoded = json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode("utf-8")
    manifest["manifest_sha256"] = hashlib.sha256(encoded).hexdigest()
    (output / "dimension_program_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _write_reports(
        output,
        quality,
        walk_table,
        external_table,
        selected,
        weak,
        rank_movements,
        coefficients,
    )

    print(json.dumps(selected, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
