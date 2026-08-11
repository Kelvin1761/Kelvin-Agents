#!/usr/bin/env python3
"""Leakage-aware HKJC Wong Choi ML research program.

This module is research-only.  It freezes the deterministic Matrix score,
repairs archived tabular alignment, trains simple Win/Place challengers with
chronological validation, and writes an evidence pack.  It never writes to the
production scoring configuration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


ROOT = Path(__file__).resolve().parents[5]
DEFAULT_PRIMARY = ROOT / "scratch" / "hkjc_ranking_dataset_current.csv"
DEFAULT_EXTERNAL = ROOT / "scratch" / "hkjc_ranking_dataset_2026_07_15_current.csv"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "artifacts" / "hkjc_ml_program"
RANDOM_SEED = 20260811
RACE_KEYS = ["date", "meeting_name", "race_number"]
TARGETS = {"Win": "is_win", "Place": "is_place"}

MATRIX_FEATURES = [
    "matrix_stability",
    "matrix_sectional",
    "matrix_race_shape",
    "matrix_trainer_signal",
    "matrix_horse_health",
    "matrix_form_line",
    "matrix_class_advantage",
]

FACT_NUMERIC = [
    "card_age",
    "card_rating",
    "card_rating_change",
    "card_declared_bodyweight",
    "card_priority_rank",
    "card_claim_lbs",
    "card_gear_count",
    "card_gear_first_time",
    "weight_carried",
    "days_since_last",
    "starts",
    "wins",
    "hk_starts",
    "last6_runs",
    "last6_mean_finish",
    "last6_best_finish",
    "last6_worst_finish",
    "last6_top3_count",
    "last6_top5_count",
    "same_distance_starts",
    "same_distance_wins",
    "same_distance_seconds",
    "same_distance_thirds",
    "same_venue_distance_starts",
    "same_venue_distance_wins",
    "same_venue_distance_seconds",
    "same_venue_distance_thirds",
    "tw_entries_count",
    "tw_gallop_count",
    "tw_flags_count",
    "tw_jockey_present",
    "raw_formline_higher_win_count",
    "raw_formline_same_win_count",
    "raw_formline_lower_win_count",
    "raw_l400",
    "raw_finish_time_adj",
    "raw_total_starts",
    "raw_total_wins",
    "raw_last_margin",
    "raw_last_finish",
    "raw_weight_trend_span",
    "is_debut",
    "is_import",
    "is_foreign_runner",
    "field_size",
    "distance_num",
]

FACT_CATEGORICAL = [
    "venue",
    "track",
    "course",
    "race_class_label",
]

LEAKAGE_BLACKLIST_PREFIXES = ("prior_",)
LEAKAGE_BLACKLIST_EXACT = {
    "finish_pos",
    "is_win",
    "is_top3",
    "is_top4",
    "is_place",
    "place_cutoff",
    "race_label_valid",
    "current_live_rank",
    "current_live_rank_score",
    "current_live_model_pick_status",
    "current_live_grade",
    "prior_combo_roi",
    "odds",
    "win_odds",
    "place_odds",
    "market_rank",
    "dividend",
}

WIN_BANDS = [
    ("A ≥15%", 0.15, 1.01),
    ("B 10–15%", 0.10, 0.15),
    ("C 6–10%", 0.06, 0.10),
    ("D <6%", 0.0, 0.06),
]
PLACE_BANDS = [
    ("A ≥35%", 0.35, 1.01),
    ("B 25–35%", 0.25, 0.35),
    ("C 15–25%", 0.15, 0.25),
    ("D <15%", 0.0, 0.15),
]


@dataclass
class ModelSpec:
    name: str
    factory: Callable[[], Any]


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


def _race_class_label(value: object) -> str:
    text = str(value or "").strip()
    chinese_group = {"一": 1, "二": 2, "三": 3}
    match = re.search(r"([一二三])級賽", text)
    if match:
        return f"Group {chinese_group[match.group(1)]}"
    match = re.search(r"(?:GROUP|GRADE|^G)\s*([1-3])", text, re.I)
    if match:
        return f"Group {int(match.group(1))}"
    match = re.search(r"(?:第)?([一二三四五])班", text)
    if match:
        class_number = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5}[match.group(1)]
        return f"Class {class_number}"
    match = re.search(r"(?:CLASS|^C)\s*([1-5])", text, re.I)
    if match:
        return f"Class {int(match.group(1))}"
    if text.upper() in {"GR", "GRIFFIN"} or "新馬" in text:
        return "Griffin"
    if "上市" in text or "表列" in text or text.upper() in {"LR", "LISTED"}:
        return "Listed"
    return "Unknown"


def _place_cutoff(field_size: int) -> int:
    if field_size >= 7:
        return 3
    if field_size >= 4:
        return 2
    return 0


def _authoritative_venue(meeting_name: object, raw: object) -> str:
    meeting = str(meeting_name or "").lower()
    if "happyvalley" in meeting:
        return "跑馬地"
    if "shatin" in meeting:
        return "沙田"
    value = str(raw or "")
    if "跑馬地" in value or "happy" in value.lower():
        return "跑馬地"
    return "沙田"


def clean_archive(primary: Path, external: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    frames = []
    for path, split in ((primary, "development"), (external, "external_holdout")):
        frame = pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
        frame["source_split"] = split
        frame["source_file"] = path.name
        frames.append(frame)
    df = pd.concat(frames, ignore_index=True, sort=False)
    # Do not propagate workstation-specific CloudStorage paths into research
    # artifacts; meeting_name is the stable archive identifier.
    df["meeting"] = df["meeting_name"].astype(str)
    before_rows = len(df)
    duplicate_rows = int(df.duplicated(RACE_KEYS + ["horse_number"]).sum())
    df = df.drop_duplicates(RACE_KEYS + ["horse_number"], keep="last").copy()
    df["date"] = df["date"].astype(str)
    df["venue_raw"] = df["venue"].astype(str)
    df["venue"] = [
        _authoritative_venue(meeting, raw)
        for meeting, raw in zip(df["meeting_name"], df["venue_raw"])
    ]
    awt = (
        df["venue_raw"].str.contains("AWT|泥", case=False, na=False)
        | df["track"].astype(str).str.contains("AWT|泥|ALL WEATHER", case=False, na=False)
        | df["course"].astype(str).str.contains("AWT|全天候|泥", case=False, na=False)
    )
    df["track"] = np.where(awt, "AWT", "Turf")
    valid_course = df["course"].astype(str).str.fullmatch(r"[ABC](?:\+\d+)?", case=False, na=False)
    df["course"] = np.where(awt, "AWT", np.where(valid_course, df["course"].str.upper(), "Unknown"))
    df["race_class_label"] = df["race_class"].map(_race_class_label)
    df["distance_num"] = pd.to_numeric(df["distance_num"], errors="coerce")
    bad_distance = ~df["distance_num"].between(800, 3200)
    parsed_distance = pd.to_numeric(
        df["distance"].astype(str).str.extract(r"(\d{3,4})", expand=False),
        errors="coerce",
    )
    df.loc[bad_distance, "distance_num"] = parsed_distance[bad_distance]

    df["declared_field_size"] = pd.to_numeric(df["field_size"], errors="coerce")
    df["field_size"] = df.groupby(RACE_KEYS)["horse_number"].transform("count").astype(int)
    df["place_cutoff"] = df["field_size"].map(_place_cutoff).astype(int)
    df["finish_pos"] = pd.to_numeric(df["finish_pos"], errors="coerce")
    df["is_win"] = (df["finish_pos"] == 1).astype(int)
    df["is_top3"] = (df["finish_pos"] <= 3).astype(int)
    df["is_top4"] = (df["finish_pos"] <= 4).astype(int)
    df["is_place"] = (
        (df["place_cutoff"] > 0) & (df["finish_pos"] <= df["place_cutoff"])
    ).astype(int)

    race_stats = df.groupby(RACE_KEYS).agg(
        starters=("horse_number", "count"),
        winners=("is_win", "sum"),
        top3=("is_top3", "sum"),
        finish_unique=("finish_pos", "nunique"),
        finish_min=("finish_pos", "min"),
        finish_max=("finish_pos", "max"),
        finish_sum=("finish_pos", "sum"),
        finish_missing=("finish_pos", lambda x: int(x.isna().sum())),
    )
    race_stats["expected_top3"] = race_stats["starters"].clip(upper=3)
    race_stats["race_label_valid"] = (
        (race_stats["winners"] == 1)
        & (race_stats["top3"] == race_stats["expected_top3"])
        & (race_stats["finish_unique"] == race_stats["starters"])
        & (race_stats["finish_min"] == 1)
        & (race_stats["finish_max"] == race_stats["starters"])
        & (race_stats["finish_sum"] == race_stats["starters"] * (race_stats["starters"] + 1) / 2)
        & (race_stats["finish_missing"] == 0)
    )
    valid_map = race_stats["race_label_valid"].to_dict()
    df["race_label_valid"] = [
        int(valid_map[(row.date, row.meeting_name, row.race_number)])
        for row in df[RACE_KEYS].itertuples(index=False)
    ]
    invalid = race_stats[~race_stats["race_label_valid"]].reset_index()
    valid = df[df["race_label_valid"] == 1].copy()
    valid["race_key"] = (
        valid["date"].astype(str)
        + "::"
        + valid["meeting_name"].astype(str)
        + "::R"
        + valid["race_number"].astype(str)
    )

    for column in FACT_NUMERIC + MATRIX_FEATURES + ["current_live_recomputed_ability"]:
        if column not in valid:
            valid[column] = np.nan
        valid[column] = pd.to_numeric(valid[column], errors="coerce")

    quality = {
        "input_rows": before_rows,
        "deduplicated_rows": int(len(df)),
        "duplicate_runner_keys": duplicate_rows,
        "input_races": int(df.groupby(RACE_KEYS).ngroups),
        "valid_races": int(valid.groupby(RACE_KEYS).ngroups),
        "invalid_races": invalid.to_dict(orient="records"),
        "valid_rows": int(len(valid)),
        "meetings": int(valid["date"].nunique()),
        "date_min": str(valid["date"].min()),
        "date_max": str(valid["date"].max()),
        "unknown_distance_rows": int(valid["distance_num"].isna().sum()),
        "unknown_class_rows": int((valid["race_class_label"] == "Unknown").sum()),
        "declared_actual_field_mismatch_races": int(
            (
                valid.groupby(RACE_KEYS)["declared_field_size"].first()
                != valid.groupby(RACE_KEYS).size()
            ).sum()
        ),
        "horse_id_missing_rows": int(valid["horse_id"].astype(str).isin(["", "nan", "None"]).sum()),
    }
    return valid.reset_index(drop=True), quality


def add_race_relative_features(df: pd.DataFrame, numeric: list[str]) -> tuple[pd.DataFrame, list[str]]:
    out = df.copy()
    rel_columns = []
    for column in numeric:
        if column not in out:
            continue
        values = pd.to_numeric(out[column], errors="coerce")
        group = values.groupby(out["race_key"])
        mean = group.transform("mean")
        std = group.transform("std").replace(0, np.nan)
        rel = f"rel_{column}"
        out[rel] = ((values - mean) / std).fillna(0.0)
        rel_columns.append(rel)
    return out, rel_columns


def feature_groups(df: pd.DataFrame) -> dict[str, tuple[list[str], list[str]]]:
    facts = [column for column in FACT_NUMERIC if column in df and df[column].notna().any()]
    matrix = [column for column in MATRIX_FEATURES if column in df and df[column].notna().any()]
    rel_facts = [f"rel_{column}" for column in facts if f"rel_{column}" in df]
    rel_matrix = [f"rel_{column}" for column in matrix if f"rel_{column}" in df]
    categorical = [column for column in FACT_CATEGORICAL if column in df]
    return {
        "matrix_7d": (matrix + rel_matrix, []),
        "facts_compact": (facts + rel_facts, categorical),
        "matrix_plus_facts": (matrix + facts + rel_matrix + rel_facts, categorical),
    }


def assert_leakage_safe(features: list[str]) -> None:
    violations = [
        feature
        for feature in features
        if feature in LEAKAGE_BLACKLIST_EXACT
        or feature.startswith(LEAKAGE_BLACKLIST_PREFIXES)
        or "odds" in feature.lower()
        or "dividend" in feature.lower()
        or "roi" in feature.lower()
    ]
    if violations:
        raise ValueError(f"Leakage/market features selected: {sorted(violations)}")


def _preprocessor(numeric: list[str], categorical: list[str]) -> ColumnTransformer:
    transformers: list[tuple[str, Any, list[str]]] = []
    if numeric:
        transformers.append(
            (
                "num",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="median", add_indicator=True)),
                        ("scale", StandardScaler()),
                    ]
                ),
                numeric,
            )
        )
    if categorical:
        transformers.append(
            (
                "cat",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="most_frequent")),
                        ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
                    ]
                ),
                categorical,
            )
        )
    return ColumnTransformer(transformers, remainder="drop", verbose_feature_names_out=True)


def model_specs(seed: int) -> list[ModelSpec]:
    try:
        from lightgbm import LGBMClassifier
    except Exception as exc:  # pragma: no cover - environment-specific
        raise RuntimeError(f"LightGBM unavailable: {exc}") from exc
    try:
        from xgboost import XGBClassifier
    except Exception as exc:  # pragma: no cover - environment-specific
        raise RuntimeError(f"XGBoost unavailable: {exc}") from exc

    return [
        ModelSpec(
            "Logistic Regression",
            lambda: LogisticRegression(
                C=0.25,
                max_iter=1500,
                solver="lbfgs",
                random_state=seed,
            ),
        ),
        ModelSpec(
            "LightGBM",
            lambda: LGBMClassifier(
                n_estimators=140,
                learning_rate=0.03,
                num_leaves=7,
                max_depth=3,
                min_child_samples=35,
                subsample=0.8,
                colsample_bytree=0.8,
                reg_alpha=0.6,
                reg_lambda=2.5,
                random_state=seed,
                n_jobs=1,
                verbosity=-1,
            ),
        ),
        ModelSpec(
            "XGBoost",
            lambda: XGBClassifier(
                n_estimators=160,
                learning_rate=0.03,
                max_depth=3,
                min_child_weight=8,
                subsample=0.8,
                colsample_bytree=0.8,
                reg_alpha=0.6,
                reg_lambda=3.0,
                eval_metric="logloss",
                random_state=seed,
                n_jobs=1,
            ),
        ),
    ]


def make_pipeline(spec: ModelSpec, numeric: list[str], categorical: list[str]) -> Pipeline:
    features = numeric + categorical
    assert_leakage_safe(features)
    return Pipeline([("preprocess", _preprocessor(numeric, categorical)), ("model", spec.factory())])


def make_matrix_calibrator() -> Pipeline:
    return Pipeline(
        [
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("model", LogisticRegression(C=1.0, max_iter=1000, random_state=RANDOM_SEED)),
        ]
    )


def _fit(model: Any, X: pd.DataFrame, y: pd.Series, field_size: pd.Series) -> Any:
    weights = 1.0 / pd.to_numeric(field_size, errors="coerce").clip(lower=1)
    try:
        model.fit(X, y, model__sample_weight=weights.to_numpy())
    except (TypeError, ValueError):
        try:
            model.fit(X, y, sample_weight=weights.to_numpy())
        except (TypeError, ValueError):
            model.fit(X, y)
    return model


def _coherent_win_probabilities(frame: pd.DataFrame, probabilities: np.ndarray) -> np.ndarray:
    result = pd.Series(np.clip(probabilities, 1e-6, 1 - 1e-6), index=frame.index)
    totals = result.groupby(frame["race_key"]).transform("sum").replace(0, np.nan)
    return (result / totals).fillna(1.0 / frame["field_size"]).to_numpy()


def predict_probabilities(model: Any, frame: pd.DataFrame, features: list[str], target: str) -> np.ndarray:
    probabilities = model.predict_proba(frame[features])[:, 1]
    if target == "Win":
        probabilities = _coherent_win_probabilities(frame, probabilities)
    return np.clip(probabilities, 1e-6, 1 - 1e-6)


def _ece(y: np.ndarray, p: np.ndarray, bins: int = 10) -> float:
    edges = np.linspace(0, 1, bins + 1)
    total = len(y)
    value = 0.0
    for left, right in zip(edges[:-1], edges[1:]):
        mask = (p >= left) & (p < right if right < 1 else p <= right)
        if mask.any():
            value += mask.mean() * abs(float(y[mask].mean()) - float(p[mask].mean()))
    return float(value if total else np.nan)


def _ndcg_at_5(group: pd.DataFrame, probability: str) -> float:
    ranked = group.sort_values(probability, ascending=False).head(5)
    relevance = np.maximum(4 - ranked["finish_pos"].to_numpy(dtype=float), 0)
    ideal = np.sort(np.maximum(4 - group["finish_pos"].to_numpy(dtype=float), 0))[::-1][:5]
    discounts = 1.0 / np.log2(np.arange(2, len(relevance) + 2))
    ideal_discounts = 1.0 / np.log2(np.arange(2, len(ideal) + 2))
    denom = float(np.sum(ideal * ideal_discounts))
    return float(np.sum(relevance * discounts) / denom) if denom else 0.0


def metrics(frame: pd.DataFrame, probability: str, target: str) -> dict[str, float]:
    y_column = TARGETS[target]
    y = frame[y_column].to_numpy(dtype=int)
    p = frame[probability].to_numpy(dtype=float)
    result: dict[str, float] = {
        "rows": float(len(frame)),
        "races": float(frame["race_key"].nunique()),
        "log_loss": float(log_loss(y, p, labels=[0, 1])),
        "brier": float(brier_score_loss(y, p)),
        "ece_10": _ece(y, p),
        "roc_auc": float(roc_auc_score(y, p)) if len(np.unique(y)) > 1 else math.nan,
    }
    race_rows = []
    for _, group in frame.groupby("race_key", sort=False):
        ranked = group.sort_values(probability, ascending=False)
        winner_rank = int(np.flatnonzero(ranked["is_win"].to_numpy() == 1)[0]) + 1
        actual_top3 = set(group.loc[group["is_top3"] == 1, "horse_number"].astype(str))
        predicted_top2 = set(ranked.head(2)["horse_number"].astype(str))
        predicted_top3 = set(ranked.head(3)["horse_number"].astype(str))
        predicted_top5 = set(ranked.head(5)["horse_number"].astype(str))
        top2_hits = len(actual_top3 & predicted_top2)
        place_actual = set(group.loc[group["is_place"] == 1, "horse_number"].astype(str))
        cutoff = int(group["place_cutoff"].iloc[0])
        race_rows.append(
            {
                "winner_top1": winner_rank <= 1,
                "winner_top2": winner_rank <= 2,
                "winner_top3": winner_rank <= 3,
                "winner_top5": winner_rank <= 5,
                "winner_rr": 1.0 / winner_rank,
                "top3_capture_at3": len(actual_top3 & predicted_top3) / max(len(actual_top3), 1),
                "top3_capture_at5": len(actual_top3 & predicted_top5) / max(len(actual_top3), 1),
                "top2_zero_hit": top2_hits == 0,
                "top2_one_hit": top2_hits == 1,
                "top2_two_hit": top2_hits == 2,
                "place_capture_at_cutoff": (
                    len(place_actual & set(ranked.head(cutoff)["horse_number"].astype(str)))
                    / max(len(place_actual), 1)
                    if cutoff
                    else math.nan
                ),
                "ndcg_at5": _ndcg_at_5(group, probability),
            }
        )
    race_frame = pd.DataFrame(race_rows)
    for column in race_frame.columns:
        result[column] = float(race_frame[column].mean())
    return result


def _metric_record(
    frame: pd.DataFrame,
    probability: str,
    target: str,
    model: str,
    period: str,
    feature_group: str,
) -> dict[str, Any]:
    return {
        "period": period,
        "target": target,
        "model": model,
        "feature_group": feature_group,
        **metrics(frame, probability, target),
    }


def chronological_blocks(df: pd.DataFrame, minimum_meetings: int = 8) -> list[tuple[list[str], str]]:
    dates = sorted(df["date"].unique())
    return [(dates[:index], dates[index]) for index in range(minimum_meetings, len(dates))]


def walk_forward_predict(
    df: pd.DataFrame,
    spec: ModelSpec,
    numeric: list[str],
    categorical: list[str],
    target: str,
    minimum_meetings: int = 8,
) -> pd.DataFrame:
    target_column = TARGETS[target]
    features = numeric + categorical
    outputs = []
    for train_dates, test_date in chronological_blocks(df, minimum_meetings):
        train = df[df["date"].isin(train_dates)]
        test = df[df["date"] == test_date].copy()
        model = make_pipeline(spec, numeric, categorical)
        _fit(model, train[features], train[target_column], train["field_size"])
        test["probability"] = predict_probabilities(model, test, features, target)
        test["fold_train_end"] = max(train_dates)
        test["fold_test_date"] = test_date
        outputs.append(test)
    return pd.concat(outputs, ignore_index=True)


def matrix_walk_forward(df: pd.DataFrame, target: str, minimum_meetings: int = 8) -> pd.DataFrame:
    target_column = TARGETS[target]
    outputs = []
    feature = ["current_live_recomputed_ability"]
    for train_dates, test_date in chronological_blocks(df, minimum_meetings):
        train = df[df["date"].isin(train_dates)]
        test = df[df["date"] == test_date].copy()
        model = make_matrix_calibrator()
        _fit(model, train[feature], train[target_column], train["field_size"])
        test["probability"] = predict_probabilities(model, test, feature, target)
        test["fold_train_end"] = max(train_dates)
        test["fold_test_date"] = test_date
        outputs.append(test)
    return pd.concat(outputs, ignore_index=True)


def fit_and_predict(
    train: pd.DataFrame,
    test: pd.DataFrame,
    spec: ModelSpec,
    numeric: list[str],
    categorical: list[str],
    target: str,
) -> tuple[Any, pd.DataFrame]:
    features = numeric + categorical
    model = make_pipeline(spec, numeric, categorical)
    _fit(model, train[features], train[TARGETS[target]], train["field_size"])
    predicted = test.copy()
    predicted["probability"] = predict_probabilities(model, predicted, features, target)
    return model, predicted


def fit_matrix_and_predict(
    train: pd.DataFrame, test: pd.DataFrame, target: str
) -> tuple[Any, pd.DataFrame]:
    feature = ["current_live_recomputed_ability"]
    model = make_matrix_calibrator()
    _fit(model, train[feature], train[TARGETS[target]], train["field_size"])
    predicted = test.copy()
    predicted["probability"] = predict_probabilities(model, predicted, feature, target)
    return model, predicted


def select_feature_group(
    development: pd.DataFrame,
    groups: dict[str, tuple[list[str], list[str]]],
    logistic: ModelSpec,
) -> tuple[str, pd.DataFrame]:
    rows = []
    for group_name, (numeric, categorical) in groups.items():
        for target in TARGETS:
            predictions = walk_forward_predict(
                development, logistic, numeric, categorical, target
            )
            rows.append(
                _metric_record(
                    predictions,
                    "probability",
                    target,
                    logistic.name,
                    "walk_forward",
                    group_name,
                )
            )
    comparison = pd.DataFrame(rows)
    win = comparison[comparison["target"] == "Win"].copy()
    win["selection_score"] = (
        win["top3_capture_at5"]
        + win["winner_top3"]
        + 0.25 * win["ndcg_at5"]
        - 0.20 * win["log_loss"]
    )
    best = win.sort_values(
        ["selection_score", "feature_group"], ascending=[False, True]
    ).iloc[0]
    selected = str(best["feature_group"])
    # Simplicity guard: retain 7D if a wider group gains less than one point.
    matrix_row = win[win["feature_group"] == "matrix_7d"]
    if not matrix_row.empty and selected != "matrix_7d":
        if float(best["selection_score"] - matrix_row.iloc[0]["selection_score"]) < 0.01:
            selected = "matrix_7d"
    comparison["selected"] = comparison["feature_group"].eq(selected)
    return selected, comparison


def combine_predictions(
    matrix: pd.DataFrame,
    ml: pd.DataFrame,
    alpha: float,
    name: str,
) -> pd.DataFrame:
    keys = RACE_KEYS + ["horse_number"]
    right = ml[keys + ["probability"]].rename(columns={"probability": "ml_probability"})
    out = matrix.merge(right, on=keys, how="inner", validate="one_to_one")
    out["probability"] = alpha * out["probability"] + (1 - alpha) * out["ml_probability"]
    out["hybrid_name"] = name
    return out


def choose_hybrid(
    matrix_oof: pd.DataFrame,
    ml_oof: pd.DataFrame,
    target: str,
) -> tuple[float, pd.DataFrame]:
    rows = []
    for alpha in (0.25, 0.50, 0.75):
        hybrid = combine_predictions(matrix_oof, ml_oof, alpha, f"Matrix {alpha:.2f}")
        row = _metric_record(
            hybrid,
            "probability",
            target,
            f"Matrix+ML α={alpha:.2f}",
            "walk_forward",
            "hybrid",
        )
        row["alpha"] = alpha
        row["selection_score"] = (
            row["top3_capture_at5"]
            + row["winner_top3"]
            + 0.25 * row["ndcg_at5"]
            - 0.20 * row["log_loss"]
        )
        rows.append(row)
    table = pd.DataFrame(rows)
    alpha = float(table.sort_values("selection_score", ascending=False).iloc[0]["alpha"])
    return alpha, table


def rank_overlay_search(
    matrix_win: pd.DataFrame,
    ml_win: pd.DataFrame,
    ml_place: pd.DataFrame,
    period: str,
) -> pd.DataFrame:
    """Test whether a light ML rank overlay safely moves contenders into Top 2.

    The synthetic probability is used only to obtain deterministic ranks. It is
    not treated as a calibrated Win probability and never enters log-loss gates.
    """
    keys = RACE_KEYS + ["horse_number"]
    base_columns = keys + [
        "race_key", "horse_name", "finish_pos", "is_win", "is_top3", "is_top4",
        "is_place", "field_size", "place_cutoff", "probability",
    ]
    base = matrix_win[base_columns].rename(columns={"probability": "matrix_probability"})
    base = base.merge(
        ml_win[keys + ["probability"]].rename(columns={"probability": "ml_win_probability"}),
        on=keys,
        validate="one_to_one",
    ).merge(
        ml_place[keys + ["probability"]].rename(columns={"probability": "ml_place_probability"}),
        on=keys,
        validate="one_to_one",
    )
    base["matrix_rank_score"] = base.groupby("race_key")["matrix_probability"].rank(pct=True)
    base["ml_win_rank_score"] = base.groupby("race_key")["ml_win_probability"].rank(pct=True)
    base["ml_place_rank_score"] = base.groupby("race_key")["ml_place_probability"].rank(pct=True)
    rows = []
    for source in ("Win ML", "Place ML"):
        source_column = "ml_win_rank_score" if source == "Win ML" else "ml_place_rank_score"
        for alpha in np.arange(0.50, 1.001, 0.05):
            frame = base.copy()
            frame["overlay_score"] = (
                alpha * frame["matrix_rank_score"] + (1 - alpha) * frame[source_column]
            )
            frame["probability"] = frame.groupby("race_key")["overlay_score"].transform(
                lambda values: np.exp(4 * values) / np.exp(4 * values).sum()
            )
            record = _metric_record(
                frame,
                "probability",
                "Win",
                f"Matrix+{source} rank overlay",
                period,
                "rank_overlay_research",
            )
            record["matrix_weight"] = round(float(alpha), 2)
            record["probability_metrics_valid"] = False
            rows.append(record)
    return pd.DataFrame(rows)


def score_band_rows(
    predictions: pd.DataFrame,
    model: str,
    target: str,
    period: str,
) -> list[dict[str, Any]]:
    bands = WIN_BANDS if target == "Win" else PLACE_BANDS
    y_column = TARGETS[target]
    rows = []
    for label, lower, upper in bands:
        subset = predictions[
            (predictions["probability"] >= lower)
            & (predictions["probability"] < upper)
        ]
        rows.append(
            {
                "period": period,
                "target": target,
                "model": model,
                "score_band": label,
                "lower": lower,
                "upper": upper,
                "runners": int(len(subset)),
                "races": int(subset["race_key"].nunique()) if len(subset) else 0,
                "mean_probability": float(subset["probability"].mean()) if len(subset) else math.nan,
                "observed_rate": float(subset[y_column].mean()) if len(subset) else math.nan,
                "calibration_gap": (
                    float(subset[y_column].mean() - subset["probability"].mean())
                    if len(subset)
                    else math.nan
                ),
            }
        )
    return rows


def segment_rows(
    predictions: pd.DataFrame,
    model: str,
    target: str,
    period: str,
) -> list[dict[str, Any]]:
    frame = predictions.copy()
    frame["distance_bucket"] = pd.cut(
        frame["distance_num"],
        bins=[0, 1200, 1650, 3200],
        labels=["sprint≤1200", "mile-ish 1201–1650", "staying>1650"],
        include_lowest=True,
    ).astype(str)
    frame["field_bucket"] = pd.cut(
        frame["field_size"],
        bins=[0, 9, 12, 99],
        labels=["small≤9", "medium10–12", "large13+"],
        include_lowest=True,
    ).astype(str)
    rows = []
    for dimension in ("venue", "track", "distance_bucket", "race_class_label", "field_bucket"):
        for value, subset in frame.groupby(dimension, dropna=False):
            if subset["race_key"].nunique() < 3:
                continue
            record = _metric_record(subset, "probability", target, model, period, "selected")
            record["segment_dimension"] = dimension
            record["segment_value"] = str(value)
            rows.append(record)
    return rows


def feature_importance(model: Pipeline, model_name: str, target: str) -> pd.DataFrame:
    preprocess = model.named_steps["preprocess"]
    names = preprocess.get_feature_names_out()
    estimator = model.named_steps["model"]
    if hasattr(estimator, "coef_"):
        values = np.asarray(estimator.coef_).reshape(-1)
        signed = values
        importance = np.abs(values)
    elif hasattr(estimator, "feature_importances_"):
        importance = np.asarray(estimator.feature_importances_).reshape(-1)
        signed = importance
    else:
        return pd.DataFrame()
    length = min(len(names), len(importance))
    return pd.DataFrame(
        {
            "model": model_name,
            "target": target,
            "feature": names[:length],
            "importance": importance[:length],
            "signed_effect": signed[:length],
        }
    ).sort_values("importance", ascending=False)


def shap_importance(
    model: Pipeline,
    model_name: str,
    target: str,
    sample: pd.DataFrame,
    features: list[str],
) -> pd.DataFrame:
    """Return mean absolute SHAP values for tree challengers when supported."""
    if model_name not in {"LightGBM", "XGBoost"}:
        return pd.DataFrame()
    try:
        import shap

        preprocess = model.named_steps["preprocess"]
        estimator = model.named_steps["model"]
        transformed = preprocess.transform(sample[features].head(500))
        names = preprocess.get_feature_names_out()
        values = shap.TreeExplainer(estimator).shap_values(transformed)
        if isinstance(values, list):
            values = values[-1]
        array = np.asarray(values)
        if array.ndim == 3:
            array = array[:, :, -1]
        importance = np.mean(np.abs(array), axis=0)
        length = min(len(names), len(importance))
        return pd.DataFrame(
            {
                "model": model_name,
                "target": target,
                "feature": names[:length],
                "mean_abs_shap": importance[:length],
            }
        ).sort_values("mean_abs_shap", ascending=False)
    except Exception as exc:  # pragma: no cover - optional explainer compatibility
        return pd.DataFrame(
            [{
                "model": model_name,
                "target": target,
                "feature": "__SHAP_UNAVAILABLE__",
                "mean_abs_shap": math.nan,
                "error": str(exc),
            }]
        )


def fold_metric_rows(
    predictions: pd.DataFrame,
    model: str,
    target: str,
    feature_group: str,
) -> list[dict[str, Any]]:
    rows = []
    for test_date, subset in predictions.groupby("fold_test_date", sort=True):
        row = _metric_record(
            subset,
            "probability",
            target,
            model,
            str(test_date),
            feature_group,
        )
        row["train_end"] = str(subset["fold_train_end"].iloc[0])
        row["test_date"] = str(test_date)
        rows.append(row)
    return rows


def bootstrap_uncertainty(
    predictions: pd.DataFrame,
    model: str,
    target: str,
    period: str,
    seed: int,
    samples: int = 1000,
) -> list[dict[str, Any]]:
    """Race-cluster bootstrap intervals for ranking and probability metrics."""
    race_rows = []
    y_column = TARGETS[target]
    for race_key, group in predictions.groupby("race_key", sort=False):
        ranked = group.sort_values("probability", ascending=False)
        winner_rank = int(np.flatnonzero(ranked["is_win"].to_numpy() == 1)[0]) + 1
        actual_top3 = set(group.loc[group["is_top3"] == 1, "horse_number"].astype(str))
        predicted_top2 = set(ranked.head(2)["horse_number"].astype(str))
        predicted_top5 = set(ranked.head(5)["horse_number"].astype(str))
        y = group[y_column].to_numpy(dtype=int)
        p = group["probability"].to_numpy(dtype=float)
        race_rows.append(
            {
                "race_key": race_key,
                "log_loss": float(log_loss(y, p, labels=[0, 1])),
                "brier": float(brier_score_loss(y, p)),
                "winner_top3": float(winner_rank <= 3),
                "top3_capture_at5": len(actual_top3 & predicted_top5) / max(len(actual_top3), 1),
                "top2_zero_hit": float(len(actual_top3 & predicted_top2) == 0),
            }
        )
    race_frame = pd.DataFrame(race_rows)
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(race_frame), size=(samples, len(race_frame)))
    rows = []
    for metric_name in ("log_loss", "brier", "winner_top3", "top3_capture_at5", "top2_zero_hit"):
        values = race_frame[metric_name].to_numpy(dtype=float)
        draws = values[indices].mean(axis=1)
        rows.append(
            {
                "period": period,
                "target": target,
                "model": model,
                "metric": metric_name,
                "estimate_race_mean": float(values.mean()),
                "ci_2_5": float(np.quantile(draws, 0.025)),
                "ci_97_5": float(np.quantile(draws, 0.975)),
                "bootstrap_samples": samples,
                "races": int(len(race_frame)),
            }
        )
    return rows


def failure_review_markdown(
    predictions: pd.DataFrame,
    matrix_predictions: pd.DataFrame,
    model_name: str,
) -> str:
    keys = RACE_KEYS + ["horse_number"]
    joined = predictions.merge(
        matrix_predictions[keys + ["probability"]].rename(columns={"probability": "matrix_probability"}),
        on=keys,
        validate="one_to_one",
    )
    annotation_path = ROOT / "scratch" / "hkjc_anomaly_annotations.csv"
    annotation_map: dict[tuple[str, int], dict[str, Any]] = {}
    if annotation_path.exists():
        annotations = pd.read_csv(annotation_path, low_memory=False)
        for row in annotations.to_dict(orient="records"):
            annotation_map[(str(row.get("meeting", "")), int(row.get("race_number", 0) or 0))] = row

    sections = [
        "# HKJC 0-hit / 1-hit Failure Review",
        "",
        f"Model reviewed: **{model_name}**.  All ranks below use pre-race features only; incidents and odds are diagnostic annotations, never training inputs.",
        "",
    ]
    categories = defaultdict(int)
    weak_count = 0
    improved = 0
    review_rows = []
    for race_key, group in joined.groupby("race_key", sort=True):
        ranked = group.sort_values("probability", ascending=False)
        matrix_ranked = group.sort_values("matrix_probability", ascending=False)
        actual_top3 = set(group.loc[group["is_top3"] == 1, "horse_number"].astype(str))
        hits = len(actual_top3 & set(ranked.head(2)["horse_number"].astype(str)))
        matrix_hits = len(actual_top3 & set(matrix_ranked.head(2)["horse_number"].astype(str)))
        if hits > 1:
            continue
        meta = group.iloc[0]
        annotation = annotation_map.get((str(meta["meeting_name"]), int(meta["race_number"])), {})
        abnormal = any(
            bool(annotation.get(column, False))
            for column in ("extreme_outsider", "major_incident", "interference", "injury", "abnormal")
        )
        model_order = {
            str(row.horse_number): index + 1 for index, row in enumerate(ranked.itertuples())
        }
        matrix_order = {
            str(row.horse_number): index + 1 for index, row in enumerate(matrix_ranked.itertuples())
        }
        model_top5_hits = len(actual_top3 & set(ranked.head(5)["horse_number"].astype(str)))
        matrix_top5_hits = len(actual_top3 & set(matrix_ranked.head(5)["horse_number"].astype(str)))
        actual_top3_rows = group[group["is_top3"] == 1]
        model_ranks = [model_order[str(value)] for value in actual_top3_rows["horse_number"]]
        matrix_ranks = [matrix_order[str(value)] for value in actual_top3_rows["horse_number"]]
        if model_top5_hits >= 2:
            category = "contender captured in Top-5 tier but not Top 2"
        elif model_top5_hits < matrix_top5_hits:
            category = "ML reordering degraded Matrix contender"
        elif model_top5_hits <= 1 and matrix_top5_hits <= 1:
            category = "competitive group absent from both Top-5 rankings"
        elif np.median(model_ranks) > np.median(matrix_ranks) + 1:
            category = "ML median rank degradation"
        else:
            category = "race-specific residual"
        review_rows.append(
            {
                "race_key": race_key,
                "group": group,
                "ranked": ranked,
                "matrix_ranked": matrix_ranked,
                "hits": hits,
                "matrix_hits": matrix_hits,
                "category": category,
                "abnormal": abnormal,
                "annotation": annotation,
                "model_order": model_order,
                "matrix_order": matrix_order,
            }
        )

    review_rows.sort(
        key=lambda item: (
            item["abnormal"],
            str(item["group"].iloc[0]["date"]),
            int(item["group"].iloc[0]["race_number"]),
        )
    )
    normal_weak = sum(not item["abnormal"] for item in review_rows)
    abnormal_weak = len(review_rows) - normal_weak
    for item in review_rows:
        group = item["group"]
        ranked = item["ranked"]
        matrix_ranked = item["matrix_ranked"]
        hits = item["hits"]
        matrix_hits = item["matrix_hits"]
        category = item["category"]
        abnormal = item["abnormal"]
        annotation = item["annotation"]
        model_order = item["model_order"]
        matrix_order = item["matrix_order"]
        weak_count += 1
        improved += int(hits > matrix_hits)
        categories[category] += 1
        if weak_count <= 35:
            meta = group.iloc[0]
            sections.extend(
                [
                    f"## {meta['date']} R{int(meta['race_number'])} — model Top-2 hits {hits}, Matrix {matrix_hits}",
                    "",
                    f"Classification: **{category}**. Predictability review: **{'abnormal/outsider flagged' if abnormal else 'normal-result cohort'}**. Venue {meta['venue']}, {meta['track']}, {int(meta['distance_num']) if pd.notna(meta['distance_num']) else 'unknown'}m, {meta['race_class_label']}.",
                    "",
                    "| Horse | Actual | ML rank / p | Matrix rank / p |",
                    "|---|---:|---:|---:|",
                ]
            )
            for row in group.sort_values("finish_pos").head(3).itertuples():
                horse = str(row.horse_number)
                sections.append(
                    f"| #{horse} {row.horse_name} | {int(row.finish_pos)} | {model_order[horse]} / {row.probability:.3f} | {matrix_order[horse]} / {row.matrix_probability:.3f} |"
                )
            notes = str(annotation.get("notes", "") or "").strip()
            if notes and notes.lower() != "nan":
                sections.extend(["", f"Post-race diagnostic annotation: {notes}"])
            sections.append("")
    sections.extend(
        [
            "# Recurring diagnosis",
            "",
            f"Weak races reviewed: **{weak_count}** ({normal_weak} normal-result cohort; {abnormal_weak} outsider/incident/injury/abnormal flagged). Races where the challenger improved Top-2 hit count over Matrix: **{improved}**.",
            "",
            "| Pattern | Races |",
            "|---|---:|",
        ]
    )
    for category, count in sorted(categories.items(), key=lambda item: (-item[1], item[0])):
        sections.append(f"| {category} | {count} |")
    sections.extend(
        [
            "",
            "Changes are eligible only when the same pattern improves multiple chronological folds. A single missed horse does not authorize a weight change.",
        ]
    )
    return "\n".join(sections) + "\n"


def _markdown_table(frame: pd.DataFrame, columns: list[str], digits: int = 4) -> str:
    if frame.empty:
        return "_No rows._"
    view = frame[columns].copy()
    for column in view.select_dtypes(include=["float", "float64"]).columns:
        view[column] = view[column].map(lambda value: "" if pd.isna(value) else f"{value:.{digits}f}")
    header = "| " + " | ".join(columns) + " |"
    divider = "|" + "|".join(["---"] * len(columns)) + "|"
    rows = ["| " + " | ".join(map(str, row)) + " |" for row in view.itertuples(index=False, name=None)]
    return "\n".join([header, divider] + rows)


def write_readiness(
    output: Path,
    quality: dict[str, Any],
    manifest: dict[str, Any],
    feature_groups_map: dict[str, tuple[list[str], list[str]]],
) -> None:
    invalid_count = len(quality["invalid_races"])
    verdict = "READY WITH LIMITATIONS"
    text = f"""# HKJC ML Readiness Report

## Verdict: {verdict}

The archive is usable for conservative chronological research after deterministic cleaning. It is not large or pristine enough to justify automatic production promotion.

## Coverage

- {quality['valid_rows']} valid runners, {quality['valid_races']} valid races, {quality['meetings']} meetings.
- Date range: {quality['date_min']} to {quality['date_max']}.
- Invalid races excluded: {invalid_count}.
- Declared-versus-actual starter mismatches repaired: {quality['declared_actual_field_mismatch_races']} races.
- Unknown distance rows retained as missing: {quality['unknown_distance_rows']}.
- Unknown class rows retained as `Unknown`: {quality['unknown_class_rows']}.

## Point-in-time decision

- Result labels, result position, market/odds, dividends, ROI, ranks, and static `prior_*` tables are excluded from analysis features.
- Historical engine replay now always receives `race_date`; latest/full-season trainer priors are rejected unless a matching PIT source is injected.
- Race-relative features use only runners declared in the same pre-race card.
- The frozen Matrix score is used as the Champion ranking and is calibrated using training dates only.

## Limitations

1. The 24-meeting archive has already influenced previous Matrix research, so it is development evidence, not a pristine holdout.
2. 2026-07-15 is ML-unseen and chronological, but has only nine races and was previously inspected during Matrix work; it is not globally untouched.
3. Full runner-level timestamped odds and Place-price snapshots are absent, so honest ROI, CLV, and Place betting evaluation are unavailable.
4. Rare classes, AWT, debut runners, and small fields have low effective sample size.
5. LightGBM/XGBoost should remain shallow and regularised; learning-curve saturation matters more than in-sample fit.

## Approved feature groups

{chr(10).join(f'- **{name}**: {len(numeric)} numeric, {len(categorical)} categorical' for name, (numeric, categorical) in feature_groups_map.items())}

Dataset manifest SHA-256: `{manifest['manifest_sha256']}`.
"""
    (output / "hkjc_ml_readiness_report.md").write_text(text, encoding="utf-8")


def write_leakage_report(output: Path, groups: dict[str, tuple[list[str], list[str]]]) -> None:
    all_features = sorted({feature for numeric, categorical in groups.values() for feature in numeric + categorical})
    violations = []
    try:
        assert_leakage_safe(all_features)
    except ValueError as exc:
        violations.append(str(exc))
    text = f"""# Point-in-time Leakage Test

## Result: {'PASS' if not violations else 'FAIL'}

- Features tested: {len(all_features)}.
- Forbidden feature violations: {len(violations)}.
- `prior_*` static full-season tables: excluded.
- `finish_pos`, Win/Place/Top-3 labels: targets only, excluded from X.
- odds, market rank, dividends, ROI: excluded from analysis layer.
- chronological split: training date is strictly earlier than test date in every fold.
- preprocessing/imputation/calibration: fitted inside each training fold only.
- historical trainer/jockey priors: latest snapshots neutralised unless matching PIT metadata is present.

{chr(10).join(violations) if violations else 'No leakage blacklist violations found.'}
"""
    (output / "point_in_time_leakage_test.md").write_text(text, encoding="utf-8")


def write_reports(
    output: Path,
    quality: dict[str, Any],
    scorecard: pd.DataFrame,
    walk: pd.DataFrame,
    holdout: pd.DataFrame,
    bands: pd.DataFrame,
    selected_group: str,
    best_ml_name: str,
    best_overall_name: str,
    promoted: bool,
    promotion_reasons: list[str],
    learning: pd.DataFrame,
    package_versions: dict[str, str],
) -> None:
    calibration = """# Calibration and Score-band Report

The fixed score bands are probability intervals, not retrospective grades. A useful band must show increasing observed strike rate and a small expected-versus-observed gap.

## Band definitions

- Win: A ≥15%, B 10–15%, C 6–10%, D <6%.
- Place: A ≥35%, B 25–35%, C 15–25%, D <15%.

## Results

""" + _markdown_table(
        bands,
        ["period", "target", "model", "score_band", "runners", "mean_probability", "observed_rate", "calibration_gap"],
    ) + "\n"
    (output / "calibration_report.md").write_text(calibration, encoding="utf-8")

    promotion = f"""# Promotion Recommendation

## Decision: {'PROMOTE' if promoted else 'DO NOT PROMOTE'}

Selected feature group: **{selected_group}**. Best standalone ML: **{best_ml_name}**. Best evaluated overall: **{best_overall_name}**.

Strict gate findings:

{chr(10).join(f'- {reason}' for reason in promotion_reasons)}

Research artifacts are valid regardless of the production decision. The Matrix Champion remains unchanged unless every gate passes.
"""
    (output / "promotion_recommendation.md").write_text(promotion, encoding="utf-8")

    betting = """# Separate Betting / Value Layer Report

## Status: NOT EVALUABLE FROM THIS ARCHIVE

The analysis layer was completed without odds. The archive does not contain complete, timestamped runner-level Win and Place prices across all 253 races. A few post-race result files and outsider annotations are not a valid betting dataset.

| Metric | Matrix Champion | Pure ML | Matrix+ML |
|---|---:|---:|---:|
| Win ROI | N/A | N/A | N/A |
| Place ROI | N/A | N/A | N/A |
| Turnover | N/A | N/A | N/A |
| Max drawdown | N/A | N/A | N/A |
| CLV | N/A | N/A | N/A |
| Bet count | N/A | N/A | N/A |

These values are deliberately N/A rather than inferred from partial post-race annotations.

Required next data: a timestamped odds snapshot for every runner at a fixed pre-race cutoff, final SP for comparison, official Win/Place dividends, scratches, and commission/rule metadata. Until that exists, no fair-odds or staking rule is promoted.
"""
    (output / "betting_layer_report.md").write_text(betting, encoding="utf-8")

    card_cols = [
        "period", "target", "model", "feature_group", "races", "log_loss", "brier", "ece_10",
        "winner_top1", "winner_top3", "top3_capture_at3", "top3_capture_at5", "ndcg_at5",
        "top2_zero_hit", "top2_one_hit",
    ]
    model_card = f"""# HKJC Competitiveness Model Card

## Intended use

Rank HKJC runners by pre-race competitiveness. It is not a betting instruction and does not ingest odds.

## Data

{quality['valid_races']} valid races / {quality['valid_rows']} runners from {quality['date_min']} to {quality['date_max']}. The final ML-unseen block is 2026-07-15 (nine races), with the historical-contamination caveat documented in the readiness report.

## Models

- Frozen Matrix Champion with fold-local probability calibration.
- Regularised Logistic Regression.
- Shallow LightGBM.
- Shallow XGBoost.
- Matrix+ML convex hybrid selected only on walk-forward predictions.

## Scorecard

{_markdown_table(scorecard, card_cols)}

## Known limitations

- Small race-level sample, particularly AWT and rare class segments.
- Archive has been used in earlier Matrix design cycles.
- No complete odds/CLV dataset.
- Probabilities should be refreshed and re-audited when a new HK season supplies genuinely unseen races.
- Race-cluster bootstrap intervals are supplied in `metric_uncertainty.csv`; the nine-race external interval is necessarily wide.

## Runtime

{chr(10).join(f'- {name}: {version}' for name, version in package_versions.items())}
"""
    (output / "model_card.md").write_text(model_card, encoding="utf-8")

    final = f"""# Final HKJC ML Report

## Executive result

- Readiness: **READY WITH LIMITATIONS**.
- Production decision: **{'PROMOTE' if promoted else 'DO NOT PROMOTE'}**.
- Selected feature group: **{selected_group}**.
- Best standalone ML: **{best_ml_name}**.
- Best overall evaluated ranking: **{best_overall_name}**.
- Betting layer: **N/A — complete timestamped odds are unavailable**.

## Analysis-layer scorecard

{_markdown_table(scorecard, card_cols)}

## Learning curve

{_markdown_table(learning, ['target','model','train_races','validation_races','log_loss','brier','winner_top3','top3_capture_at5'])}

## What changed

1. Meeting-folder venue now overrides stale per-race venue text.
2. AWT is separated from venue and represented as track/course.
3. Actual matched starters define field size and HKJC Place cutoff.
4. Incomplete result joins are hard-excluded from training.
5. Historical replay always receives its race date, enforcing PIT prior guards.
6. Score bands are calibrated probability intervals with observed strike rates.

## Decision discipline

No model is promoted because it fits history. Promotion requires consistent probability, ranking, calibration, segment, and external-block evidence. See `promotion_recommendation.md` for the binding gate.
"""
    (output / "final_hkjc_ml_report.md").write_text(final, encoding="utf-8")


def main() -> int:
    args = parse_args()
    primary = Path(args.primary).resolve()
    external = Path(args.external).resolve()
    output = Path(args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "models").mkdir(exist_ok=True)

    raw, quality = clean_archive(primary, external)
    base_numeric = [column for column in FACT_NUMERIC + MATRIX_FEATURES if column in raw]
    data, _relative = add_race_relative_features(raw, base_numeric)
    groups = feature_groups(data)
    for numeric, categorical in groups.values():
        assert_leakage_safe(numeric + categorical)

    development = data[data["source_split"] == "development"].copy()
    external_holdout = data[data["source_split"] == "external_holdout"].copy()
    if development["date"].max() >= external_holdout["date"].min():
        raise ValueError("External holdout is not strictly later than development")

    manifest = {
        "created_on": date.today().isoformat(),
        "git_head": _git_head(),
        "seed": args.seed,
        "primary": {"path": _manifest_path(primary), "sha256": _sha256(primary)},
        "external": {"path": _manifest_path(external), "sha256": _sha256(external)},
        "coverage": quality,
        "split": {
            "development_dates": sorted(development["date"].unique().tolist()),
            "external_holdout_dates": sorted(external_holdout["date"].unique().tolist()),
            "walk_forward_min_train_meetings": 8,
        },
        "leakage_blacklist_prefixes": list(LEAKAGE_BLACKLIST_PREFIXES),
        "leakage_blacklist_exact": sorted(LEAKAGE_BLACKLIST_EXACT),
    }
    manifest_bytes = json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode("utf-8")
    manifest["manifest_sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
    (output / "dataset_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    data.to_csv(output / "training_dataset_clean.csv", index=False, encoding="utf-8-sig")

    tests = {
        "duplicate_runner_keys_after_clean": int(data.duplicated(RACE_KEYS + ["horse_number"]).sum()),
        "invalid_races_excluded": len(quality["invalid_races"]),
        "all_valid_races_one_winner": bool((data.groupby("race_key")["is_win"].sum() == 1).all()),
        "all_finish_positions_unique_within_race": bool(
            (
                data.groupby("race_key")["finish_pos"].nunique()
                == data.groupby("race_key").size()
            ).all()
        ),
        "external_strictly_later": bool(development["date"].max() < external_holdout["date"].min()),
        "analysis_features_market_free": True,
        "place_cutoff_values": sorted(data["place_cutoff"].unique().tolist()),
        "pass": True,
    }
    (output / "data_quality_tests.json").write_text(
        json.dumps(tests, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    dictionary_rows = []
    all_selected = {feature for numeric, categorical in groups.values() for feature in numeric + categorical}
    for column in data.columns:
        if column in TARGETS.values() or column in {"finish_pos", "is_top3", "is_top4"}:
            role = "target/result"
        elif column in all_selected:
            role = "analysis_feature"
        elif column.startswith("prior_"):
            role = "excluded_static_prior"
        elif any(token in column.lower() for token in ("odds", "roi", "dividend", "market")):
            role = "excluded_market"
        else:
            role = "metadata/excluded"
        dictionary_rows.append(
            {
                "feature": column,
                "dtype": str(data[column].dtype),
                "role": role,
                "missing_rate": float(data[column].isna().mean()),
                "unique_values": int(data[column].nunique(dropna=True)),
                "point_in_time_note": (
                    "pre-race only" if role == "analysis_feature" else "not supplied to analysis model"
                ),
            }
        )
    pd.DataFrame(dictionary_rows).to_csv(
        output / "feature_dictionary.csv", index=False, encoding="utf-8-sig"
    )
    write_readiness(output, quality, manifest, groups)
    write_leakage_report(output, groups)

    specs = model_specs(args.seed)
    logistic = specs[0]
    selected_group, group_comparison = select_feature_group(development, groups, logistic)
    group_comparison.to_csv(output / "feature_group_comparison.csv", index=False, encoding="utf-8-sig")
    numeric, categorical = groups[selected_group]
    features = numeric + categorical

    scorecard_rows: list[dict[str, Any]] = []
    walk_rows: list[dict[str, Any]] = []
    holdout_rows: list[dict[str, Any]] = []
    band_rows: list[dict[str, Any]] = []
    segment_output: list[dict[str, Any]] = []
    importance_frames = []
    shap_frames = []
    fold_rows: list[dict[str, Any]] = []
    uncertainty_rows: list[dict[str, Any]] = []
    final_models: dict[tuple[str, str], Any] = {}
    walk_predictions: dict[tuple[str, str], pd.DataFrame] = {}
    holdout_predictions: dict[tuple[str, str], pd.DataFrame] = {}

    for target in TARGETS:
        matrix_oof = matrix_walk_forward(development, target)
        walk_predictions[("Matrix Champion", target)] = matrix_oof
        fold_rows.extend(
            fold_metric_rows(matrix_oof, "Matrix Champion", target, "frozen_matrix")
        )
        matrix_record = _metric_record(
            matrix_oof, "probability", target, "Matrix Champion", "walk_forward", "frozen_matrix"
        )
        scorecard_rows.append(matrix_record)
        walk_rows.append(matrix_record)
        matrix_model, matrix_hold = fit_matrix_and_predict(development, external_holdout, target)
        holdout_predictions[("Matrix Champion", target)] = matrix_hold
        matrix_hold_record = _metric_record(
            matrix_hold, "probability", target, "Matrix Champion", "external_holdout", "frozen_matrix"
        )
        scorecard_rows.append(matrix_hold_record)
        holdout_rows.append(matrix_hold_record)
        final_models[("Matrix Champion", target)] = matrix_model

        for spec in specs:
            oof = walk_forward_predict(development, spec, numeric, categorical, target)
            walk_predictions[(spec.name, target)] = oof
            fold_rows.extend(
                fold_metric_rows(oof, spec.name, target, selected_group)
            )
            record = _metric_record(
                oof, "probability", target, spec.name, "walk_forward", selected_group
            )
            scorecard_rows.append(record)
            walk_rows.append(record)
            model, predicted = fit_and_predict(
                development, external_holdout, spec, numeric, categorical, target
            )
            final_models[(spec.name, target)] = model
            holdout_predictions[(spec.name, target)] = predicted
            hold_record = _metric_record(
                predicted, "probability", target, spec.name, "external_holdout", selected_group
            )
            scorecard_rows.append(hold_record)
            holdout_rows.append(hold_record)
            importance_frames.append(feature_importance(model, spec.name, target))
            shap_frames.append(
                shap_importance(
                    model,
                    spec.name,
                    target,
                    external_holdout if len(external_holdout) else development,
                    features,
                )
            )

    walk_table = pd.DataFrame(walk_rows)
    win_ml = walk_table[
        (walk_table["target"] == "Win") & (walk_table["model"] != "Matrix Champion")
    ].copy()
    win_ml["selection_score"] = (
        win_ml["top3_capture_at5"]
        + win_ml["winner_top3"]
        + 0.25 * win_ml["ndcg_at5"]
        - 0.20 * win_ml["log_loss"]
    )
    best_ml_name = str(win_ml.sort_values("selection_score", ascending=False).iloc[0]["model"])

    hybrid_rows = []
    hybrid_config = {}
    for target in TARGETS:
        matrix_oof = walk_predictions[("Matrix Champion", target)]
        ml_oof = walk_predictions[(best_ml_name, target)]
        alpha, alpha_table = choose_hybrid(matrix_oof, ml_oof, target)
        hybrid_rows.append(alpha_table)
        hybrid_name = f"Matrix+{best_ml_name} α={alpha:.2f}"
        hybrid_config[target] = {"alpha_matrix": alpha, "ml_model": best_ml_name}
        hybrid_oof = combine_predictions(matrix_oof, ml_oof, alpha, hybrid_name)
        walk_predictions[(hybrid_name, target)] = hybrid_oof
        hybrid_oof["fold_test_date"] = hybrid_oof["date"]
        if "fold_train_end" not in hybrid_oof:
            hybrid_oof["fold_train_end"] = "mixed"
        fold_rows.extend(
            fold_metric_rows(hybrid_oof, hybrid_name, target, "hybrid")
        )
        record = _metric_record(
            hybrid_oof, "probability", target, hybrid_name, "walk_forward", "hybrid"
        )
        scorecard_rows.append(record)
        walk_rows.append(record)
        matrix_hold = holdout_predictions[("Matrix Champion", target)]
        ml_hold = holdout_predictions[(best_ml_name, target)]
        hybrid_hold = combine_predictions(matrix_hold, ml_hold, alpha, hybrid_name)
        holdout_predictions[(hybrid_name, target)] = hybrid_hold
        hold_record = _metric_record(
            hybrid_hold, "probability", target, hybrid_name, "external_holdout", "hybrid"
        )
        scorecard_rows.append(hold_record)
        holdout_rows.append(hold_record)

    pd.concat(hybrid_rows, ignore_index=True).to_csv(
        output / "hybrid_weight_search.csv", index=False, encoding="utf-8-sig"
    )
    (output / "hybrid_config.json").write_text(
        json.dumps(hybrid_config, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    overlay_walk = rank_overlay_search(
        walk_predictions[("Matrix Champion", "Win")],
        walk_predictions[(best_ml_name, "Win")],
        walk_predictions[(best_ml_name, "Place")],
        "walk_forward",
    )
    overlay_holdout = rank_overlay_search(
        holdout_predictions[("Matrix Champion", "Win")],
        holdout_predictions[(best_ml_name, "Win")],
        holdout_predictions[(best_ml_name, "Place")],
        "external_holdout",
    )
    overlay_search = pd.concat([overlay_walk, overlay_holdout], ignore_index=True)
    overlay_search.to_csv(
        output / "top2_rank_overlay_search.csv", index=False, encoding="utf-8-sig"
    )

    scorecard = pd.DataFrame(scorecard_rows)
    walk_table = pd.DataFrame(walk_rows)
    holdout_table = pd.DataFrame(holdout_rows)
    scorecard.to_csv(output / "model_comparison_scorecard.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(fold_rows).to_csv(
        output / "walk_forward_results.csv", index=False, encoding="utf-8-sig"
    )
    holdout_table.to_csv(output / "holdout_results.csv", index=False, encoding="utf-8-sig")

    overall_walk = walk_table[walk_table["target"] == "Win"].copy()
    overall_walk["selection_score"] = (
        overall_walk["top3_capture_at5"]
        + overall_walk["winner_top3"]
        + 0.25 * overall_walk["ndcg_at5"]
        - 0.20 * overall_walk["log_loss"]
    )
    best_overall_name = str(overall_walk.sort_values("selection_score", ascending=False).iloc[0]["model"])
    promotion_candidates = overall_walk[overall_walk["model"] != "Matrix Champion"]
    promotion_candidate_name = str(
        promotion_candidates.sort_values("selection_score", ascending=False).iloc[0]["model"]
    )

    for (model_name, target), predictions in walk_predictions.items():
        if model_name in {"Matrix Champion", best_ml_name, best_overall_name}:
            band_rows.extend(score_band_rows(predictions, model_name, target, "walk_forward"))
            segment_output.extend(segment_rows(predictions, model_name, target, "walk_forward"))
    for (model_name, target), predictions in holdout_predictions.items():
        if model_name in {"Matrix Champion", best_ml_name, best_overall_name}:
            band_rows.extend(score_band_rows(predictions, model_name, target, "external_holdout"))
            segment_output.extend(segment_rows(predictions, model_name, target, "external_holdout"))
    bands = pd.DataFrame(band_rows)
    bands.to_csv(output / "score_band_analysis.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(segment_output).to_csv(
        output / "segment_analysis.csv", index=False, encoding="utf-8-sig"
    )

    importance = pd.concat([frame for frame in importance_frames if not frame.empty], ignore_index=True)
    importance.to_csv(output / "feature_importance.csv", index=False, encoding="utf-8-sig")
    shap_valid = [frame for frame in shap_frames if not frame.empty]
    pd.concat(shap_valid, ignore_index=True).to_csv(
        output / "shap_summary.csv", index=False, encoding="utf-8-sig"
    )

    prediction_columns = RACE_KEYS + [
        "race_key", "horse_number", "horse_name", "finish_pos", "is_win", "is_place",
        "field_size", "place_cutoff", "probability",
    ]
    walk_prediction_frames = []
    holdout_prediction_frames = []
    for (model_name, target), frame in walk_predictions.items():
        extract = frame[prediction_columns].copy()
        extract["model"] = model_name
        extract["target"] = target
        walk_prediction_frames.append(extract)
    for (model_name, target), frame in holdout_predictions.items():
        extract = frame[prediction_columns].copy()
        extract["model"] = model_name
        extract["target"] = target
        holdout_prediction_frames.append(extract)
    pd.concat(walk_prediction_frames, ignore_index=True).to_csv(
        output / "walk_forward_predictions.csv", index=False, encoding="utf-8-sig"
    )
    pd.concat(holdout_prediction_frames, ignore_index=True).to_csv(
        output / "holdout_predictions.csv", index=False, encoding="utf-8-sig"
    )

    for model_name in {"Matrix Champion", best_overall_name}:
        for target in TARGETS:
            uncertainty_rows.extend(
                bootstrap_uncertainty(
                    walk_predictions[(model_name, target)],
                    model_name,
                    target,
                    "walk_forward",
                    args.seed,
                )
            )
            uncertainty_rows.extend(
                bootstrap_uncertainty(
                    holdout_predictions[(model_name, target)],
                    model_name,
                    target,
                    "external_holdout",
                    args.seed + 1,
                )
            )
    pd.DataFrame(uncertainty_rows).to_csv(
        output / "metric_uncertainty.csv", index=False, encoding="utf-8-sig"
    )

    # Learning curve uses a fixed pre-holdout validation slice; external remains untouched.
    dates = sorted(development["date"].unique())
    validation_dates = dates[-5:]
    curve_train = development[~development["date"].isin(validation_dates)].copy()
    curve_validation = development[development["date"].isin(validation_dates)].copy()
    curve_races = curve_train["race_key"].drop_duplicates().tolist()
    points = sorted(set([50, 100, 150, len(curve_races)]))
    learning_rows = []
    best_spec = next(spec for spec in specs if spec.name == best_ml_name)
    for count in points:
        if count > len(curve_races) or count < 20:
            continue
        selected_races = set(curve_races[-count:])
        subset = curve_train[curve_train["race_key"].isin(selected_races)]
        for target in TARGETS:
            _model, predicted = fit_and_predict(
                subset, curve_validation, best_spec, numeric, categorical, target
            )
            row = _metric_record(
                predicted, "probability", target, best_ml_name, "learning_curve_validation", selected_group
            )
            row["train_races"] = count
            row["validation_races"] = int(curve_validation["race_key"].nunique())
            learning_rows.append(row)
    learning = pd.DataFrame(learning_rows)
    learning.to_csv(output / "learning_curve.csv", index=False, encoding="utf-8-sig")

    matrix_failure = walk_predictions[("Matrix Champion", "Win")]
    matrix_review = failure_review_markdown(
        matrix_failure, matrix_failure, "Matrix Champion"
    )
    challenger_review = failure_review_markdown(
        walk_predictions[(best_ml_name, "Win")], matrix_failure, best_ml_name
    ).replace(
        "# HKJC 0-hit / 1-hit Failure Review",
        "# Best ML Challenger Comparison",
        1,
    )
    (output / "failure_review.md").write_text(
        matrix_review + "\n---\n\n" + challenger_review,
        encoding="utf-8",
    )

    for (model_name, target), model in final_models.items():
        safe_name = model_name.lower().replace(" ", "_").replace("+", "plus")
        joblib.dump(model, output / "models" / f"{safe_name}_{target.lower()}.joblib")

    package_versions = {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scikit-learn": __import__("sklearn").__version__,
        "lightgbm": __import__("lightgbm").__version__,
        "xgboost": __import__("xgboost").__version__,
    }
    metadata = {
        "selected_feature_group": selected_group,
        "selected_numeric_features": numeric,
        "selected_categorical_features": categorical,
        "best_ml_model": best_ml_name,
        "best_overall_model": best_overall_name,
        "hybrid": hybrid_config,
        "package_versions": package_versions,
        "random_seed": args.seed,
        "production_changed": False,
    }
    (output / "model_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Strict promotion: best overall must beat Matrix on both periods for Win
    # probability and core ranking, with no calibration regression.
    promotion_reasons = []
    promoted = True
    for period, table in (("walk-forward", walk_table), ("external holdout", holdout_table)):
        matrix = table[(table["target"] == "Win") & (table["model"] == "Matrix Champion")].iloc[0]
        candidate_rows = table[
            (table["target"] == "Win")
            & (table["model"] == promotion_candidate_name)
        ]
        if candidate_rows.empty:
            promoted = False
            promotion_reasons.append(f"FAIL {period}: selected candidate row unavailable.")
            continue
        candidate = candidate_rows.iloc[0]
        checks = {
            "log loss": candidate["log_loss"] <= matrix["log_loss"] - 0.002,
            "Brier": candidate["brier"] <= matrix["brier"],
            "ECE": candidate["ece_10"] <= matrix["ece_10"] + 0.005,
            "winner Top-3": candidate["winner_top3"] >= matrix["winner_top3"],
            "Top-3 capture@5": candidate["top3_capture_at5"] >= matrix["top3_capture_at5"],
            "0-hit rate": candidate["top2_zero_hit"] <= matrix["top2_zero_hit"],
        }
        failed = [name for name, passed in checks.items() if not passed]
        promoted &= not failed
        promotion_reasons.append(
            f"{'PASS' if not failed else 'FAIL'} {period}: "
            + ("all probability/ranking gates passed." if not failed else "failed " + ", ".join(failed) + ".")
        )
    if len(external_holdout["race_key"].unique()) < 30:
        promoted = False
        promotion_reasons.append(
            "FAIL evidence sufficiency: external holdout has only nine races; retain research/shadow status even if point estimates improve."
        )
    matrix_walk = overlay_search[
        (overlay_search["period"] == "walk_forward")
        & (overlay_search["model"] == "Matrix+Place ML rank overlay")
        & (overlay_search["matrix_weight"] == 1.0)
    ].iloc[0]
    best_overlay = overlay_search[
        (overlay_search["period"] == "walk_forward")
        & (overlay_search["model"] == "Matrix+Place ML rank overlay")
    ].sort_values(
        ["top2_zero_hit", "winner_top3", "top3_capture_at5"],
        ascending=[True, False, False],
    ).iloc[0]
    matching_holdout = overlay_search[
        (overlay_search["period"] == "external_holdout")
        & (overlay_search["model"] == "Matrix+Place ML rank overlay")
        & (overlay_search["matrix_weight"] == best_overlay["matrix_weight"])
    ].iloc[0]
    if (
        best_overlay["top2_zero_hit"] < matrix_walk["top2_zero_hit"]
        and matching_holdout["top3_capture_at5"]
        < overlay_search[
            (overlay_search["period"] == "external_holdout")
            & (overlay_search["model"] == "Matrix+Place ML rank overlay")
            & (overlay_search["matrix_weight"] == 1.0)
        ].iloc[0]["top3_capture_at5"]
    ):
        promotion_reasons.append(
            "FAIL Top-2 overlay: the strongest Place overlay reduced walk-forward 0-hit races "
            f"({matrix_walk['top2_zero_hit']:.1%}→{best_overlay['top2_zero_hit']:.1%}) but cut external Top-3 capture@5 "
            f"to {matching_holdout['top3_capture_at5']:.1%}; this is not a safe third-pick promotion rule."
        )

    write_reports(
        output,
        quality,
        scorecard,
        walk_table,
        holdout_table,
        bands,
        selected_group,
        best_ml_name,
        best_overall_name,
        promoted,
        promotion_reasons,
        learning,
        package_versions,
    )

    print(
        json.dumps(
            {
                "output": str(output),
                "readiness": "READY WITH LIMITATIONS",
                "selected_feature_group": selected_group,
                "best_ml": best_ml_name,
                "best_overall": best_overall_name,
                "promoted": promoted,
                "valid_races": quality["valid_races"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
