#!/usr/bin/env python3
"""Matrix-anchored learning-to-rank research for HKJC Wong Choi.

The frozen seven-dimension Matrix remains the production anchor.  A conservative
LambdaRank model learns whole-field competitiveness from genuinely pre-race
signals, then contributes only a bounded share of the within-race ranking.  All
model fitting and probability calibration are chronological and fold-local.
The final 2026-07-15 block is opened only after the development candidate is
selected.  This script never edits production scoring or ranking code.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import warnings
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from hkjc_ml_program import (
    FACT_CATEGORICAL,
    FACT_NUMERIC,
    MATRIX_FEATURES,
    RANDOM_SEED,
    RACE_KEYS,
    _coherent_win_probabilities,
    _fit,
    _preprocessor,
    add_race_relative_features,
    assert_leakage_safe,
    chronological_blocks,
    clean_archive,
    fit_matrix_and_predict,
    matrix_walk_forward,
    metrics,
)


ROOT = Path(__file__).resolve().parents[5]
DEFAULT_PRIMARY = ROOT / "scratch" / "hkjc_ranking_dataset_current.csv"
DEFAULT_EXTERNAL = ROOT / "scratch" / "hkjc_ranking_dataset_2026_07_15_current.csv"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "artifacts" / "hkjc_full_rank_ml_program"
MINIMUM_TRAIN_MEETINGS = 8
HYBRID_MATRIX_WEIGHTS = (0.70, 0.80, 0.90)
MODEL_VERSION = "HKJC_MATRIX_ANCHORED_LAMBDARANK_V1"
USER_APPROVED_PRODUCTION_PROMOTION = True

COMPONENT_FEATURES = [
    "feat_form_score",
    "feat_speed_score",
    "feat_class_score",
    "feat_jockey_score",
    "feat_trainer_score",
    "feat_draw_score",
    "feat_distance_score",
    "feat_track_going_score",
    "feat_weight_score",
    "feat_consistency_score",
    "feat_risk_score",
    "feat_confidence_score",
    "feat_formline_strength_score",
    "feat_margin_trend_score",
    "feat_same_distance_signal_score",
    "feat_trackwork_trend_score",
    "feat_race_shape_context_score",
]

EXTRA_RAW_FEATURES = [
    "barrier",
    "season_starts",
    "season_wins",
    "season_seconds",
    "season_thirds",
    "card_has_claim",
    "card_gear_tt",
    "card_gear_cp",
    "card_gear_blinkers",
    "tw_confidence_high",
    "tw_confidence_low",
    "tw_mode_barrier_trial",
]

FORBIDDEN_FRAGMENTS = (
    "finish_pos",
    "is_win",
    "is_place",
    "is_top",
    "result",
    "incident",
    "interference",
    "injury",
    "dividend",
    "odds",
    "market",
    "roi",
)


@dataclass
class RankModel:
    preprocessor: Any
    ranker: Any
    numeric: list[str]
    categorical: list[str]

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        features = self.numeric + self.categorical
        transformed = np.asarray(self.preprocessor.transform(frame[features]))
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="X does not have valid feature names, but LGBMRanker was fitted with feature names",
                category=UserWarning,
            )
            return np.asarray(self.ranker.predict(transformed), dtype=float)


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


def _manifest_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return path.name


def competitiveness_relevance(finish_pos: pd.Series) -> np.ndarray:
    """Graded relevance: winner 4, second 3, third 2, fourth/fifth 1."""
    finish = pd.to_numeric(finish_pos, errors="coerce").fillna(999).to_numpy()
    return np.select(
        [finish == 1, finish == 2, finish == 3, finish <= 5],
        [4, 3, 2, 1],
        default=0,
    ).astype(int)


def assert_full_rank_feature_safe(features: list[str]) -> None:
    assert_leakage_safe(features)
    violations = [
        feature
        for feature in features
        if any(fragment in feature.lower() for fragment in FORBIDDEN_FRAGMENTS)
    ]
    if violations:
        raise ValueError(f"Post-race/leakage features selected: {sorted(violations)}")


def prepare_data(primary: Path, external: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    raw, quality = clean_archive(primary, external)
    configured_numeric = list(dict.fromkeys(MATRIX_FEATURES + COMPONENT_FEATURES + FACT_NUMERIC + EXTRA_RAW_FEATURES))
    available = [
        column
        for column in configured_numeric
        if column in raw and pd.to_numeric(raw[column], errors="coerce").notna().any()
    ]
    for column in available:
        raw[column] = pd.to_numeric(raw[column], errors="coerce")
    enriched, _ = add_race_relative_features(raw, available)
    return enriched, quality


def feature_scopes(data: pd.DataFrame) -> dict[str, tuple[list[str], list[str]]]:
    matrix = [column for column in MATRIX_FEATURES if column in data and data[column].notna().any()]
    components = [column for column in COMPONENT_FEATURES if column in data and data[column].notna().any()]
    raw = [
        column
        for column in list(dict.fromkeys(FACT_NUMERIC + EXTRA_RAW_FEATURES))
        if column in data and data[column].notna().any()
    ]
    categorical = [column for column in FACT_CATEGORICAL if column in data]

    def with_relative(columns: list[str]) -> list[str]:
        relative = [f"rel_{column}" for column in columns if f"rel_{column}" in data]
        return list(dict.fromkeys(columns + relative))

    scopes = {
        "matrix_7d": (with_relative(matrix), []),
        "matrix_plus_components": (with_relative(matrix + components), []),
        "matrix_plus_components_raw": (with_relative(matrix + components + raw), categorical),
    }
    for numeric, cats in scopes.values():
        assert_full_rank_feature_safe(numeric + cats)
    return scopes


def feature_audit(data: pd.DataFrame, scopes: dict[str, tuple[list[str], list[str]]]) -> pd.DataFrame:
    rows = []
    for scope, (numeric, categorical) in scopes.items():
        for feature in numeric + categorical:
            values = data[feature]
            rows.append(
                {
                    "scope": scope,
                    "feature": feature,
                    "kind": "categorical" if feature in categorical else "numeric",
                    "coverage_rate": float(values.notna().mean()),
                    "missing_rate": float(values.isna().mean()),
                    "unique_values": int(values.nunique(dropna=True)),
                    "allowed_pre_race": True,
                }
            )
    return pd.DataFrame(rows).drop_duplicates(["scope", "feature"])


def _sort_for_groups(frame: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    ordered = frame.sort_values(RACE_KEYS + ["horse_number"], kind="stable").copy()
    group = ordered.groupby("race_key", sort=False).size().to_numpy(dtype=int)
    if int(group.sum()) != len(ordered):
        raise AssertionError("Ranking groups do not cover every training row")
    return ordered, group


def fit_ranker(
    train: pd.DataFrame,
    numeric: list[str],
    categorical: list[str],
    seed: int,
) -> RankModel:
    try:
        from lightgbm import LGBMRanker
    except Exception as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError(f"LightGBM ranking runtime unavailable: {exc}") from exc

    features = numeric + categorical
    assert_full_rank_feature_safe(features)
    ordered, groups = _sort_for_groups(train)
    preprocessor = _preprocessor(numeric, categorical)
    transformed = np.asarray(preprocessor.fit_transform(ordered[features]))
    relevance = competitiveness_relevance(ordered["finish_pos"])
    sample_weight = 1.0 / ordered["field_size"].clip(lower=1).to_numpy(dtype=float)
    ranker = LGBMRanker(
        objective="lambdarank",
        metric="ndcg",
        label_gain=(0, 1, 3, 7, 15),
        n_estimators=100,
        learning_rate=0.03,
        num_leaves=7,
        max_depth=3,
        min_child_samples=40,
        subsample=0.80,
        colsample_bytree=0.75,
        reg_alpha=1.0,
        reg_lambda=5.0,
        random_state=seed,
        n_jobs=1,
        verbosity=-1,
    )
    ranker.fit(transformed, relevance, group=groups, sample_weight=sample_weight)
    return RankModel(preprocessor, ranker, numeric, categorical)


def within_race_percentile(frame: pd.DataFrame, values: np.ndarray | pd.Series) -> np.ndarray:
    series = pd.Series(np.asarray(values, dtype=float), index=frame.index)
    return series.groupby(frame["race_key"]).rank(method="average", pct=True).to_numpy()


def hybrid_rank_score(
    frame: pd.DataFrame,
    ml_score: np.ndarray,
    matrix_weight: float,
) -> np.ndarray:
    if not 0.0 <= matrix_weight <= 1.0:
        raise ValueError("matrix_weight must be between zero and one")
    matrix_percentile = within_race_percentile(
        frame, frame["current_live_recomputed_ability"].to_numpy(dtype=float)
    )
    ml_percentile = within_race_percentile(frame, ml_score)
    # The tiny continuous Matrix term resolves equal percentile blends without
    # creating a horse-specific or outcome-aware tie-break rule.
    matrix_raw = frame["current_live_recomputed_ability"].to_numpy(dtype=float)
    return (
        matrix_weight * matrix_percentile
        + (1.0 - matrix_weight) * ml_percentile
        + 1e-10 * matrix_raw
    )


def make_rank_calibrator() -> Pipeline:
    return Pipeline(
        [
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("model", LogisticRegression(C=1.0, max_iter=1000, random_state=RANDOM_SEED)),
        ]
    )


def calibrate_scores(
    train: pd.DataFrame,
    train_score: np.ndarray,
    test: pd.DataFrame,
    test_score: np.ndarray,
) -> tuple[Any, np.ndarray]:
    calibrator = make_rank_calibrator()
    feature = pd.DataFrame({"rank_score": train_score}, index=train.index)
    _fit(calibrator, feature, train["is_win"], train["field_size"])
    test_feature = pd.DataFrame({"rank_score": test_score}, index=test.index)
    probability = calibrator.predict_proba(test_feature)[:, 1]
    return calibrator, _coherent_win_probabilities(test, probability)


def _prediction_frame(
    test: pd.DataFrame,
    probability: np.ndarray,
    ml_score: np.ndarray,
    combined_score: np.ndarray,
    scope: str,
    matrix_weight: float,
    train_end: str,
    test_date: str,
) -> pd.DataFrame:
    output = test.copy()
    output["probability"] = probability
    output["ml_rank_score"] = ml_score
    output["hybrid_rank_score"] = combined_score
    output["feature_scope"] = scope
    output["matrix_weight"] = matrix_weight
    output["fold_train_end"] = train_end
    output["fold_test_date"] = test_date
    return output


def walk_forward_candidates(
    development: pd.DataFrame,
    scopes: dict[str, tuple[list[str], list[str]]],
    seed: int,
) -> dict[tuple[str, float], pd.DataFrame]:
    output: dict[tuple[str, float], list[pd.DataFrame]] = {
        (scope, weight): [] for scope in scopes for weight in HYBRID_MATRIX_WEIGHTS
    }
    for train_dates, test_date in chronological_blocks(development, MINIMUM_TRAIN_MEETINGS):
        train = development[development["date"].isin(train_dates)].copy()
        test = development[development["date"] == test_date].copy()
        for scope, (numeric, categorical) in scopes.items():
            model = fit_ranker(train, numeric, categorical, seed)
            train_ml = model.predict(train)
            test_ml = model.predict(test)
            for weight in HYBRID_MATRIX_WEIGHTS:
                train_score = hybrid_rank_score(train, train_ml, weight)
                test_score = hybrid_rank_score(test, test_ml, weight)
                _, probability = calibrate_scores(train, train_score, test, test_score)
                output[(scope, weight)].append(
                    _prediction_frame(
                        test,
                        probability,
                        test_ml,
                        test_score,
                        scope,
                        weight,
                        max(train_dates),
                        test_date,
                    )
                )
    return {key: pd.concat(frames, ignore_index=True) for key, frames in output.items()}


def _rank_lookup(group: pd.DataFrame, score: str) -> dict[str, int]:
    ordered = group.sort_values(
        [score, "current_live_recomputed_ability", "horse_number"],
        ascending=[False, False, True],
        kind="stable",
    )
    return {
        str(horse): rank
        for rank, horse in enumerate(ordered["horse_number"].astype(str), start=1)
    }


def _competitive_ndcg_at5(group: pd.DataFrame, score: str) -> float:
    ordered = group.sort_values(score, ascending=False).head(5)
    relevance = competitiveness_relevance(ordered["finish_pos"])
    ideal = np.sort(competitiveness_relevance(group["finish_pos"]))[::-1][:5]
    discounts = 1.0 / np.log2(np.arange(2, len(relevance) + 2))
    denominator = float(np.sum(ideal * discounts[: len(ideal)]))
    return float(np.sum(relevance * discounts) / denominator) if denominator else 0.0


def extended_metrics(frame: pd.DataFrame, score: str = "probability") -> dict[str, float]:
    result = metrics(frame, score, "Win")
    rows = []
    for _, group in frame.groupby("race_key", sort=False):
        lookup = _rank_lookup(group, score)
        actual_top3 = group.loc[group["finish_pos"] <= 3, "horse_number"].astype(str).tolist()
        actual_top5 = group.loc[group["finish_pos"] <= 5, "horse_number"].astype(str).tolist()
        ranked = group.sort_values(score, ascending=False)
        predicted_top4 = set(ranked.head(4)["horse_number"].astype(str))
        predicted_top5 = set(ranked.head(5)["horse_number"].astype(str))
        predicted_top2 = set(ranked.head(2)["horse_number"].astype(str))
        rows.append(
            {
                "top3_capture_at4": len(set(actual_top3) & predicted_top4) / len(actual_top3),
                "top5_capture_at5": len(set(actual_top5) & predicted_top5) / len(actual_top5),
                "actual_top3_average_rank": float(np.mean([lookup[horse] for horse in actual_top3])),
                "mean_top2_hits": float(len(set(actual_top3) & predicted_top2)),
                "competitive_ndcg_at5": _competitive_ndcg_at5(group, score),
            }
        )
    extra = pd.DataFrame(rows).mean(numeric_only=True).to_dict()
    result.update({key: float(value) for key, value in extra.items()})
    result["top2_zero_or_one_hit"] = result["top2_zero_hit"] + result["top2_one_hit"]
    return result


def _selection_score(row: dict[str, Any]) -> float:
    return float(
        1.50 * row["top3_capture_at5"]
        + 1.00 * row["competitive_ndcg_at5"]
        + 0.75 * row["winner_top3"]
        + 0.40 * row["winner_top2"]
        + 0.30 * row["top5_capture_at5"]
        - 0.75 * row["top2_zero_hit"]
        - 0.20 * row["top2_one_hit"]
        - 0.20 * row["log_loss"]
    )


def _development_gate(candidate: dict[str, Any], baseline: dict[str, Any]) -> tuple[bool, int]:
    non_regression = (
        candidate["top3_capture_at5"] >= baseline["top3_capture_at5"] - 0.005
        and candidate["competitive_ndcg_at5"] >= baseline["competitive_ndcg_at5"] - 0.005
        and candidate["winner_top3"] >= baseline["winner_top3"] - 0.010
        and candidate["top2_zero_hit"] <= baseline["top2_zero_hit"] + 0.005
        and candidate["log_loss"] <= baseline["log_loss"] + 0.010
    )
    improvements = sum(
        [
            candidate["top2_zero_hit"] <= baseline["top2_zero_hit"] - 0.005,
            candidate["top3_capture_at5"] >= baseline["top3_capture_at5"] + 0.005,
            candidate["competitive_ndcg_at5"] >= baseline["competitive_ndcg_at5"] + 0.005,
            candidate["winner_top3"] >= baseline["winner_top3"] + 0.005,
            candidate["winner_top2"] >= baseline["winner_top2"] + 0.005,
            candidate["actual_top3_average_rank"] <= baseline["actual_top3_average_rank"] - 0.03,
        ]
    )
    return bool(non_regression and improvements >= 2), int(improvements)


def candidate_scorecard(
    baseline: pd.DataFrame,
    candidates: dict[tuple[str, float], pd.DataFrame],
) -> pd.DataFrame:
    baseline_metrics = extended_metrics(baseline)
    rows = [
        {
            "model": "Matrix Champion",
            "feature_scope": "frozen_matrix",
            "matrix_weight": 1.0,
            "development_gate": True,
            "improvement_dimensions": 0,
            "selection_score": _selection_score(baseline_metrics),
            **baseline_metrics,
        }
    ]
    for (scope, weight), predictions in candidates.items():
        record = extended_metrics(predictions)
        gate, improvements = _development_gate(record, baseline_metrics)
        rows.append(
            {
                "model": MODEL_VERSION,
                "feature_scope": scope,
                "matrix_weight": weight,
                "development_gate": gate,
                "improvement_dimensions": improvements,
                "selection_score": _selection_score(record),
                **record,
            }
        )
    return pd.DataFrame(rows)


def select_candidate(scorecard: pd.DataFrame) -> tuple[str, float, bool]:
    challengers = scorecard[scorecard["model"] == MODEL_VERSION].copy()
    passed = challengers[challengers["development_gate"]]
    pool = passed if not passed.empty else challengers
    chosen = pool.sort_values(
        ["selection_score", "matrix_weight", "feature_scope"],
        ascending=[False, False, True],
    ).iloc[0]
    return str(chosen["feature_scope"]), float(chosen["matrix_weight"]), bool(chosen["development_gate"])


def fit_final_candidate(
    development: pd.DataFrame,
    external: pd.DataFrame,
    numeric: list[str],
    categorical: list[str],
    matrix_weight: float,
    seed: int,
) -> tuple[dict[str, Any], pd.DataFrame]:
    rank_model = fit_ranker(development, numeric, categorical, seed)
    train_ml = rank_model.predict(development)
    external_ml = rank_model.predict(external)
    train_score = hybrid_rank_score(development, train_ml, matrix_weight)
    external_score = hybrid_rank_score(external, external_ml, matrix_weight)
    calibrator, probability = calibrate_scores(
        development, train_score, external, external_score
    )
    predictions = _prediction_frame(
        external,
        probability,
        external_ml,
        external_score,
        "selected",
        matrix_weight,
        str(development["date"].max()),
        str(external["date"].min()),
    )
    bundle = {
        "version": MODEL_VERSION,
        # Persist only library-native objects.  Serialising RankModel while this
        # file runs as a script would bind it to ``__main__`` and break reload
        # from a separate process.
        "preprocessor": rank_model.preprocessor,
        "ranker": rank_model.ranker,
        "calibrator": calibrator,
        "numeric_features": numeric,
        "categorical_features": categorical,
        "matrix_weight": matrix_weight,
        "training_date_max": str(development["date"].max()),
        "seed": seed,
    }
    return bundle, predictions


def _external_gate(candidate: dict[str, Any], baseline: dict[str, Any]) -> bool:
    return bool(
        candidate["top2_zero_hit"] <= baseline["top2_zero_hit"]
        and candidate["top3_capture_at5"] >= baseline["top3_capture_at5"]
        and candidate["competitive_ndcg_at5"] >= baseline["competitive_ndcg_at5"] - 0.005
        and candidate["winner_top3"] >= baseline["winner_top3"]
        and candidate["log_loss"] <= baseline["log_loss"] + 0.015
    )


def comparison_rows(
    baseline: pd.DataFrame,
    candidate: pd.DataFrame,
    period: str,
    development_gate: bool,
) -> pd.DataFrame:
    base = extended_metrics(baseline)
    challenger = extended_metrics(candidate)
    external_gate = _external_gate(challenger, base) if period == "external_holdout" else math.nan
    return pd.DataFrame(
        [
            {"period": period, "model": "Matrix Champion", "development_gate": True, "external_gate": True, **base},
            {"period": period, "model": MODEL_VERSION, "development_gate": development_gate, "external_gate": external_gate, **challenger},
        ]
    )


def rank_movements(
    baseline: pd.DataFrame,
    candidate: pd.DataFrame,
    period: str,
) -> pd.DataFrame:
    keys = RACE_KEYS + ["horse_number"]
    columns = keys + ["race_key", "horse_name", "finish_pos", "is_win", "is_top3", "current_live_recomputed_ability", "probability"]
    left = baseline[columns].copy()
    right = candidate[keys + ["race_key", "probability", "ml_rank_score", "hybrid_rank_score"]].copy()
    left["matrix_rank"] = left.groupby("race_key")["probability"].rank(ascending=False, method="first").astype(int)
    right["hybrid_rank"] = right.groupby("race_key")["probability"].rank(ascending=False, method="first").astype(int)
    right = right.drop(columns="race_key")
    output = left.merge(right, on=keys, validate="one_to_one", suffixes=("_matrix", "_hybrid"))
    output["rank_change"] = output["matrix_rank"] - output["hybrid_rank"]
    output["entered_top2"] = (output["matrix_rank"] > 2) & (output["hybrid_rank"] <= 2)
    output["left_top2"] = (output["matrix_rank"] <= 2) & (output["hybrid_rank"] > 2)
    output["rank3_placegetter_entered_top2"] = (
        (output["matrix_rank"] == 3) & (output["hybrid_rank"] <= 2) & (output["finish_pos"] <= 3)
    )
    output["period"] = period
    return output.sort_values(["date", "race_number", "hybrid_rank"])


def _horse_list(group: pd.DataFrame, score: str, limit: int) -> str:
    ordered = group.sort_values(score, ascending=False).head(limit)
    return " | ".join(f"{row.horse_number}:{row.horse_name}" for row in ordered.itertuples())


def _dimension_profile(row: pd.Series) -> str:
    signals = []
    for column in MATRIX_FEATURES:
        relative = f"rel_{column}"
        if relative in row.index and pd.notna(row[relative]):
            signals.append((column.removeprefix("matrix_"), float(row[relative])))
    signals.sort(key=lambda item: abs(item[1]), reverse=True)
    return ", ".join(f"{name}={value:+.2f}σ" for name, value in signals[:3])


def _profile_horses(group: pd.DataFrame, horse_numbers: set[str]) -> str:
    selected = group[group["horse_number"].astype(str).isin(horse_numbers)]
    return " | ".join(
        f"{row['horse_number']}:{row['horse_name']}[{_dimension_profile(row)}]"
        for _, row in selected.iterrows()
    )


def weak_race_review(
    baseline: pd.DataFrame,
    candidate: pd.DataFrame,
    period: str,
) -> pd.DataFrame:
    candidate_by_race = {key: group for key, group in candidate.groupby("race_key", sort=False)}
    rows = []
    for race_key, matrix_group in baseline.groupby("race_key", sort=False):
        hybrid_group = candidate_by_race[race_key]
        matrix_ranked = matrix_group.sort_values("probability", ascending=False)
        hybrid_ranked = hybrid_group.sort_values("probability", ascending=False)
        actual_top3 = set(matrix_group.loc[matrix_group["finish_pos"] <= 3, "horse_number"].astype(str))
        matrix_top2 = set(matrix_ranked.head(2)["horse_number"].astype(str))
        hybrid_top2 = set(hybrid_ranked.head(2)["horse_number"].astype(str))
        matrix_top5 = set(matrix_ranked.head(5)["horse_number"].astype(str))
        hybrid_top5 = set(hybrid_ranked.head(5)["horse_number"].astype(str))
        promoted = hybrid_top2 - matrix_top2
        displaced = matrix_top2 - hybrid_top2
        matrix_hits = len(actual_top3 & matrix_top2)
        if matrix_hits > 1:
            continue
        hybrid_hits = len(actual_top3 & hybrid_top2)
        matrix_capture5 = len(actual_top3 & matrix_top5)
        hybrid_capture5 = len(actual_top3 & hybrid_top5)
        missed = matrix_group[matrix_group["finish_pos"] <= 3].copy()
        matrix_lookup = _rank_lookup(matrix_group, "probability")
        hybrid_lookup = _rank_lookup(hybrid_group, "probability")
        missed_text = " | ".join(
            f"{row.horse_number}:{row.horse_name}(結果{int(row.finish_pos)},M{matrix_lookup[str(row.horse_number)]},H{hybrid_lookup[str(row.horse_number)]})"
            for row in missed.itertuples()
            if matrix_lookup[str(row.horse_number)] > 2
        )
        rows.append(
            {
                "period": period,
                "date": matrix_group["date"].iloc[0],
                "meeting_name": matrix_group["meeting_name"].iloc[0],
                "race_number": int(matrix_group["race_number"].iloc[0]),
                "race_key": race_key,
                "venue": matrix_group["venue"].iloc[0],
                "course": matrix_group["course"].iloc[0],
                "distance_num": matrix_group["distance_num"].iloc[0],
                "race_class_label": matrix_group["race_class_label"].iloc[0],
                "field_size": matrix_group["field_size"].iloc[0],
                "matrix_top2_hits": matrix_hits,
                "hybrid_top2_hits": hybrid_hits,
                "top2_hit_delta": hybrid_hits - matrix_hits,
                "matrix_top5_capture_count": matrix_capture5,
                "hybrid_top5_capture_count": hybrid_capture5,
                "top5_capture_delta": hybrid_capture5 - matrix_capture5,
                "matrix_top2": _horse_list(matrix_group, "probability", 2),
                "hybrid_top2": _horse_list(hybrid_group, "probability", 2),
                "actual_top3": " | ".join(
                    f"{row.horse_number}:{row.horse_name}"
                    for row in matrix_group.sort_values("finish_pos").head(3).itertuples()
                ),
                "matrix_missed_top3_with_rank_change": missed_text,
                "promoted_signal_profile": _profile_horses(hybrid_group, promoted),
                "displaced_signal_profile": _profile_horses(matrix_group, displaced),
                "matrix_top2_nonfinishers": _profile_horses(
                    matrix_group, matrix_top2 - actual_top3
                ),
                "classification": (
                    "improved" if (hybrid_hits, hybrid_capture5) > (matrix_hits, matrix_capture5)
                    else "harmed" if (hybrid_hits, hybrid_capture5) < (matrix_hits, matrix_capture5)
                    else "unchanged"
                ),
            }
        )
    return pd.DataFrame(rows)


def weak_pattern_summary(weak: pd.DataFrame) -> pd.DataFrame:
    if weak.empty:
        return pd.DataFrame()
    frame = weak.copy()
    frame["distance_bucket"] = pd.cut(
        frame["distance_num"],
        bins=[0, 1200, 1650, 3200],
        labels=["sprint<=1200", "mile-ish 1201-1650", "staying>1650"],
        include_lowest=True,
    ).astype(str)
    rows = []
    for dimension in ("classification", "venue", "course", "distance_bucket", "race_class_label"):
        for (period, value), group in frame.groupby(["period", dimension], dropna=False):
            rows.append(
                {
                    "period": period,
                    "segment_dimension": dimension,
                    "segment_value": str(value),
                    "weak_races": int(len(group)),
                    "mean_top2_hit_delta": float(group["top2_hit_delta"].mean()),
                    "mean_top5_capture_delta": float(group["top5_capture_delta"].mean()),
                    "improved_races": int((group["classification"] == "improved").sum()),
                    "harmed_races": int((group["classification"] == "harmed").sum()),
                }
            )
    return pd.DataFrame(rows)


def feature_importance(bundle: dict[str, Any]) -> pd.DataFrame:
    preprocessor = bundle.get("preprocessor")
    ranker = bundle.get("ranker")
    if preprocessor is None or ranker is None:
        rank_model: RankModel = bundle["rank_model"]
        preprocessor = rank_model.preprocessor
        ranker = rank_model.ranker
    names = preprocessor.get_feature_names_out()
    gain = ranker.booster_.feature_importance(importance_type="gain")
    split = ranker.booster_.feature_importance(importance_type="split")
    length = min(len(names), len(gain), len(split))
    output = pd.DataFrame(
        {"feature": names[:length], "gain": gain[:length], "split": split[:length]}
    )
    total = float(output["gain"].sum())
    output["gain_share"] = output["gain"] / total if total else 0.0
    return output.sort_values(["gain", "split"], ascending=False)


def portable_rank_model(bundle: dict[str, Any], source_joblib_sha256: str) -> dict[str, Any]:
    """Export the selected ranker for dependency-free production inference."""
    preprocessor = bundle["preprocessor"]
    numeric_pipeline = preprocessor.named_transformers_["num"]
    imputer = numeric_pipeline.named_steps["impute"]
    scaler = numeric_pipeline.named_steps["scale"]
    booster = bundle["ranker"].booster_.dump_model()
    if len(imputer.indicator_.features_):
        raise RuntimeError("Portable ranker does not support active missing indicators")
    if any(tree.get("num_cat", 0) for tree in booster["tree_info"]):
        raise RuntimeError("Portable ranker does not support categorical tree splits")
    return {
        "schema_version": "HKJC_PORTABLE_LGBM_RANKER_V1",
        "model_version": bundle["version"],
        "source_joblib_sha256": source_joblib_sha256,
        "features": list(bundle["numeric_features"]),
        "imputer_medians": np.asarray(imputer.statistics_, dtype=float).tolist(),
        "scaler_mean": np.asarray(scaler.mean_, dtype=float).tolist(),
        "scaler_scale": np.asarray(scaler.scale_, dtype=float).tolist(),
        "objective": booster.get("objective"),
        "average_output": bool(booster.get("average_output")),
        "trees": [tree["tree_structure"] for tree in booster["tree_info"]],
    }


def prediction_export(frame: pd.DataFrame) -> pd.DataFrame:
    """Keep ledgers compact while retaining every ranking audit field."""
    configured = RACE_KEYS + [
        "race_key",
        "venue",
        "course",
        "distance_num",
        "race_class_label",
        "field_size",
        "horse_number",
        "horse_name",
        "finish_pos",
        "is_win",
        "is_top3",
        "is_place",
        "current_live_recomputed_ability",
        *MATRIX_FEATURES,
        "probability",
        "ml_rank_score",
        "hybrid_rank_score",
        "feature_scope",
        "matrix_weight",
        "fold_train_end",
        "fold_test_date",
    ]
    columns = list(dict.fromkeys(column for column in configured if column in frame))
    return frame[columns].copy()


def all_scope_feature_importance(
    development: pd.DataFrame,
    scopes: dict[str, tuple[list[str], list[str]]],
    seed: int,
) -> pd.DataFrame:
    frames = []
    for scope, (numeric, categorical) in scopes.items():
        model = fit_ranker(development, numeric, categorical, seed)
        table = feature_importance({"rank_model": model})
        table.insert(0, "feature_scope", scope)
        frames.append(table)
    return pd.concat(frames, ignore_index=True)


def _fmt(value: Any) -> str:
    if isinstance(value, (float, np.floating)):
        return "—" if math.isnan(float(value)) else f"{float(value):.4f}"
    return str(value)


def write_report(
    output: Path,
    scorecard: pd.DataFrame,
    comparison: pd.DataFrame,
    weak: pd.DataFrame,
    movements: pd.DataFrame,
    scope: str,
    matrix_weight: float,
    development_gate: bool,
    external_gate: bool,
) -> None:
    dev_rows = comparison[comparison["period"] == "walk_forward"].set_index("model")
    ext_rows = comparison[comparison["period"] == "external_holdout"].set_index("model")
    keys = [
        "top2_zero_hit", "top2_one_hit", "winner_top2", "winner_top3",
        "top3_capture_at5", "top5_capture_at5", "competitive_ndcg_at5",
        "actual_top3_average_rank", "log_loss", "brier",
    ]
    lines = [
        "# HKJC Matrix-Anchored Full Ranking ML",
        "",
        f"- Model: `{MODEL_VERSION}`",
        f"- Selected feature scope: `{scope}`",
        f"- Matrix / ML ranking share: `{matrix_weight:.0%}` / `{1-matrix_weight:.0%}`",
        f"- Development gate: `{'PASS' if development_gate else 'FAIL'}`",
        f"- External 2026-07-15 gate: `{'PASS' if external_gate else 'FAIL'}`",
        "- Production Matrix ability / Grade: unchanged",
        f"- Production hybrid ranking promoted by user: `{'YES' if USER_APPROVED_PRODUCTION_PROMOTION else 'NO'}`",
        "",
        "## Outcome",
        "",
    ]
    if USER_APPROVED_PRODUCTION_PROMOTION and development_gate:
        lines.append(
            "用戶審視樣本量後批准將 70/30 hybrid 用作正式全場排序：161 場 walk-forward 改善優先於九場 external 入面少捕捉一匹 Top 3 馬；external limitation 仍完整保留，Matrix ability / Grade 不變。"
        )
    elif development_gate and external_gate:
        lines.append("個候選同時通過 development 同 external gate，可以考慮下一步做獨立 opt-in shadow；未獲准直接取代 Matrix。")
    elif development_gate:
        lines.append("候選喺 development 有系統改善，但 external 未能確認穩定性；保留 research-only，唔推入 production。")
    else:
        lines.append("全場 ranking ML 未能通過 development 非退步門檻；Matrix 繼續做唯一 production 排名。")
    raw_rows = scorecard[
        (scorecard["model"] == MODEL_VERSION)
        & (scorecard["feature_scope"] == "matrix_plus_components_raw")
    ]
    if not raw_rows.empty:
        best_raw = raw_rows.sort_values("selection_score", ascending=False).iloc[0]
        lines.extend(
            [
                "",
                "### Raw-signal challenger",
                "",
                f"最佳 7D＋component＋raw 候選用 {float(best_raw['matrix_weight']):.0%} Matrix anchor："
                f"0-hit={float(best_raw['top2_zero_hit']):.4f}、Winner Top2={float(best_raw['winner_top2']):.4f}、"
                f"Top3 capture@5={float(best_raw['top3_capture_at5']):.4f}、Winner Top3={float(best_raw['winner_top3']):.4f}。"
                f"Development gate=`{'PASS' if bool(best_raw['development_gate']) else 'FAIL'}`，所以無用 external 結果補救或重新選模。",
            ]
        )
    lines.extend(["", "## Exact scorecard", "", "| Metric | WF Matrix | WF Hybrid | External Matrix | External Hybrid |", "|---|---:|---:|---:|---:|"])
    for key in keys:
        lines.append(
            f"| {key} | {_fmt(dev_rows.loc['Matrix Champion', key])} | {_fmt(dev_rows.loc[MODEL_VERSION, key])} | "
            f"{_fmt(ext_rows.loc['Matrix Champion', key])} | {_fmt(ext_rows.loc[MODEL_VERSION, key])} |"
        )
    weak_dev = weak[weak["period"] == "walk_forward"]
    lines.extend(
        [
            "",
            "## Weak-race impact",
            "",
            f"- Baseline 0/1-hit weak races reviewed: {len(weak_dev)}",
            f"- Improved: {int((weak_dev['classification'] == 'improved').sum()) if len(weak_dev) else 0}",
            f"- Harmed: {int((weak_dev['classification'] == 'harmed').sum()) if len(weak_dev) else 0}",
            f"- Rank 3 placegetter moved into Top 2: {int(movements['rank3_placegetter_entered_top2'].sum())}",
            "",
            "## Interpretation",
            "",
            "LambdaRank 以頭五名 graded relevance 學整體競爭力；blend 係全場一致規則，唔係逐場 micro tie-break 或 blind swap。Feature scope 同 blend 權重只由 development walk-forward 選擇，external meeting 無參與選模。極冷門／意外事件無可靠 point-in-time 標籤，因此本輪無用賽後理由刪除任何場次，避免主觀 hindsight exclusion。",
            "",
            "詳細檔案：`development_candidate_scorecard.csv`、`final_comparison.csv`、`weak_race_review.csv`、`rank_movements.csv`、`feature_importance.csv`。",
            "",
        ]
    )
    (output / "full_rank_ml_report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    primary = Path(args.primary).resolve()
    external_path = Path(args.external).resolve()
    output = Path(args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "models").mkdir(exist_ok=True)

    data, quality = prepare_data(primary, external_path)
    development = data[data["source_split"] == "development"].copy()
    external = data[data["source_split"] == "external_holdout"].copy()
    if development["date"].max() >= external["date"].min():
        raise ValueError("External holdout must be strictly later than development")
    scopes = feature_scopes(data)
    feature_audit(data, scopes).to_csv(output / "feature_audit.csv", index=False, encoding="utf-8-sig")

    matrix_oof = matrix_walk_forward(development, "Win", MINIMUM_TRAIN_MEETINGS)
    candidates = walk_forward_candidates(development, scopes, args.seed)
    scorecard = candidate_scorecard(matrix_oof, candidates)
    scorecard.to_csv(output / "development_candidate_scorecard.csv", index=False, encoding="utf-8-sig")
    selected_scope, matrix_weight, development_gate = select_candidate(scorecard)
    selected_oof = candidates[(selected_scope, matrix_weight)]

    numeric, categorical = scopes[selected_scope]
    bundle, external_candidate = fit_final_candidate(
        development, external, numeric, categorical, matrix_weight, args.seed
    )
    _, external_matrix = fit_matrix_and_predict(development, external, "Win")
    comparison = pd.concat(
        [
            comparison_rows(matrix_oof, selected_oof, "walk_forward", development_gate),
            comparison_rows(external_matrix, external_candidate, "external_holdout", development_gate),
        ],
        ignore_index=True,
    )
    comparison.to_csv(output / "final_comparison.csv", index=False, encoding="utf-8-sig")
    external_gate = bool(
        comparison.loc[
            (comparison["period"] == "external_holdout") & (comparison["model"] == MODEL_VERSION),
            "external_gate",
        ].iloc[0]
    )

    oof_moves = rank_movements(matrix_oof, selected_oof, "walk_forward")
    external_moves = rank_movements(external_matrix, external_candidate, "external_holdout")
    movements = pd.concat([oof_moves, external_moves], ignore_index=True)
    movements.to_csv(output / "rank_movements.csv", index=False, encoding="utf-8-sig")
    movements[movements["rank3_placegetter_entered_top2"]].to_csv(
        output / "rank3_placegetter_to_top2.csv", index=False, encoding="utf-8-sig"
    )
    weak = pd.concat(
        [
            weak_race_review(matrix_oof, selected_oof, "walk_forward"),
            weak_race_review(external_matrix, external_candidate, "external_holdout"),
        ],
        ignore_index=True,
    )
    weak.to_csv(output / "weak_race_review.csv", index=False, encoding="utf-8-sig")
    weak_pattern_summary(weak).to_csv(
        output / "weak_race_pattern_summary.csv", index=False, encoding="utf-8-sig"
    )
    prediction_export(selected_oof).to_csv(
        output / "walk_forward_predictions.csv", index=False, encoding="utf-8-sig"
    )
    prediction_export(external_candidate).to_csv(
        output / "external_predictions.csv", index=False, encoding="utf-8-sig"
    )
    importance = feature_importance(bundle)
    importance.to_csv(output / "feature_importance.csv", index=False, encoding="utf-8-sig")
    all_scope_feature_importance(development, scopes, args.seed).to_csv(
        output / "scope_feature_importance.csv", index=False, encoding="utf-8-sig"
    )

    model_path = output / "models" / "matrix_anchored_lambdarank.joblib"
    joblib.dump(bundle, model_path)
    model_sha256 = _sha256(model_path)
    portable_path = output / "models" / "matrix_anchored_lambdarank_portable.json"
    portable_path.write_text(
        json.dumps(
            portable_rank_model(bundle, model_sha256),
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    manifest = {
        "created_on": date.today().isoformat(),
        "git_head": _git_head(),
        "version": MODEL_VERSION,
        "seed": args.seed,
        "primary": {"path": _manifest_path(primary), "sha256": _sha256(primary)},
        "external": {"path": _manifest_path(external_path), "sha256": _sha256(external_path)},
        "coverage": quality,
        "split": {
            "development_dates": sorted(development["date"].unique().tolist()),
            "external_dates": sorted(external["date"].unique().tolist()),
            "minimum_train_meetings": MINIMUM_TRAIN_MEETINGS,
        },
        "selection": {
            "feature_scope": selected_scope,
            "matrix_weight": matrix_weight,
            "development_gate": development_gate,
            "external_gate": external_gate,
            "production_promoted": USER_APPROVED_PRODUCTION_PROMOTION,
            "promotion_basis": (
                "user_approved_after_sample_size_review; ranking_only; "
                "matrix_ability_and_grade_unchanged"
                if USER_APPROVED_PRODUCTION_PROMOTION
                else "not_promoted"
            ),
        },
        "features": {"numeric": numeric, "categorical": categorical},
        "model": {"path": _manifest_path(model_path), "sha256": model_sha256},
        "portable_model": {
            "path": _manifest_path(portable_path),
            "sha256": _sha256(portable_path),
            "dependency_free_inference": True,
        },
        "external_not_used_for_selection": True,
    }
    manifest_payload = json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode("utf-8")
    manifest["manifest_sha256"] = hashlib.sha256(manifest_payload).hexdigest()
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    write_report(
        output,
        scorecard,
        comparison,
        weak,
        movements,
        selected_scope,
        matrix_weight,
        development_gate,
        external_gate,
    )
    print(json.dumps(manifest["selection"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
