#!/usr/bin/env python3
"""
train_hkjc_ranking_model.py — first horse-level HKJC ranking model research pipeline.

This script is research-only and does not touch mainline scoring.

Approach:
1. Build or load a horse-level dataset from archived HKJC meetings.
2. Train a pairwise logistic ranking model with walk-forward evaluation.
3. Compare multiple feature sets against the current live HKJC baseline.
"""

from __future__ import annotations

import argparse
import json
import math
import warnings
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from pandas.errors import PerformanceWarning

from build_hkjc_ranking_dataset import DEFAULT_OUTPUT as DEFAULT_DATASET_OUTPUT
from build_hkjc_ranking_dataset import build_rows
from review_auto_weighting import default_meeting_roots, default_results_roots, evaluate_pick_order, summarize_model_races


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_REPORT = SCRIPT_DIR.parent / "artifacts" / "hkjc_ranking_model_report.json"

DEFAULT_MIN_TRAIN_MEETINGS = 8
DEFAULT_MIN_TRAIN_RACES = 48
DEFAULT_MAXITER = 180
DEFAULT_REG_GRID = (0.35, 0.75, 1.5)
OBJECTIVE_PROFILES = {
    "balanced": {"winner_bonus": 1.2, "top3_bonus": 0.6, "top4_bonus": 0.2, "tail_bonus": 0.2, "gap_scale": 0.12},
    "winner_focus": {"winner_bonus": 1.8, "top3_bonus": 0.45, "top4_bonus": 0.1, "tail_bonus": 0.15, "gap_scale": 0.16},
    "coverage_focus": {"winner_bonus": 1.0, "top3_bonus": 0.85, "top4_bonus": 0.35, "tail_bonus": 0.25, "gap_scale": 0.1},
}

warnings.simplefilter("ignore", PerformanceWarning)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a horse-level HKJC ranking model with walk-forward testing")
    parser.add_argument("--meeting-root", action="append", default=[], help="Root folder to scan for HKJC meetings")
    parser.add_argument("--results-root", action="append", default=[], help="Root folder containing HKJC results")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET_OUTPUT), help="Horse-level dataset CSV path")
    parser.add_argument("--report-output", default=str(DEFAULT_REPORT), help="Output JSON report path")
    parser.add_argument("--rebuild-dataset", action="store_true", help="Rebuild dataset from archive even if CSV exists")
    parser.add_argument("--feature-set", action="append", default=[], help="Only run specific feature set(s)")
    parser.add_argument("--min-train-meetings", type=int, default=DEFAULT_MIN_TRAIN_MEETINGS)
    parser.add_argument("--min-train-races", type=int, default=DEFAULT_MIN_TRAIN_RACES)
    parser.add_argument("--maxiter", type=int, default=DEFAULT_MAXITER)
    parser.add_argument("--json", action="store_true", help="Print JSON report")
    return parser.parse_args()


def _safe_float(value: object, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        if math.isnan(float(value)):
            return default
        return float(value)
    text = str(value).strip()
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def _feature_sets(df: pd.DataFrame) -> dict[str, list[str]]:
    feature_cols = sorted(column for column in df.columns if column.startswith("feat_"))
    matrix_cols = sorted(column for column in df.columns if column.startswith("matrix_"))
    forensic_cols = sorted(
        column
        for column in df.columns
        if column.startswith(("raw_", "flag_", "tw_", "season_", "same_distance_", "same_venue_distance_"))
    )
    card_cols = sorted(column for column in df.columns if column.startswith("card_"))
    prior_cols = sorted(column for column in df.columns if column.startswith("prior_"))
    raw_cols = [
        "barrier",
        "weight_carried",
        "weight",
        "days_since_last",
        "base_rating",
        "final_rating",
        "starts",
        "wins",
        "hk_starts",
        "last6_mean_finish",
        "last6_top3_count",
        "last6_top5_count",
        "is_debut",
        "is_import",
    ]
    stack_cols = [
        "current_live_ability",
        "current_live_rank_score",
        "current_live_recomputed_ability",
    ]
    interaction_cols = [
        "venue_is_hv",
        "venue_is_st",
        "is_sprint",
        "is_middle",
        "int_hv_draw",
        "int_hv_race_shape",
        "int_middle_race_shape",
        "int_sprint_speed",
        "int_distance_speed",
        "int_class_weight",
        "int_st_class_advantage",
        "int_formline_class",
        "int_quick_return_trackwork",
        "int_prior_combo_signal",
        "int_prior_horse_course_fit",
        "int_prior_draw_hv",
        "int_prior_rest_sharp",
        "int_rating_change_class",
    ]
    valid_raw = [column for column in raw_cols if column in df.columns]
    valid_stack = [column for column in stack_cols if column in df.columns]
    valid_forensic = [column for column in forensic_cols if column in df.columns]
    valid_card = [column for column in card_cols if column in df.columns]
    valid_prior = [column for column in prior_cols if column in df.columns]
    valid_interaction = [column for column in interaction_cols if column in df.columns]
    return {
        "engine_only": feature_cols + matrix_cols,
        "engine_context": feature_cols + matrix_cols + valid_raw,
        "engine_facts_trends": feature_cols + matrix_cols + valid_raw + valid_forensic,
        "engine_context_stack": feature_cols + matrix_cols + valid_raw + valid_stack + valid_interaction,
        "engine_priors": feature_cols + matrix_cols + valid_raw + valid_card + valid_prior,
        "engine_full_research": feature_cols + matrix_cols + valid_raw + valid_forensic + valid_card + valid_prior + valid_stack + valid_interaction,
    }


def _load_or_build_dataset(args: argparse.Namespace) -> pd.DataFrame:
    dataset_path = Path(args.dataset)
    if dataset_path.exists() and not args.rebuild_dataset:
        return pd.read_csv(dataset_path, encoding="utf-8-sig")

    meeting_roots = [Path(path) for path in args.meeting_root] or default_meeting_roots()
    results_roots = [Path(path) for path in args.results_root] or default_results_roots()
    df, _coverage = build_rows(meeting_roots, results_roots)
    dataset_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(dataset_path, index=False, encoding="utf-8-sig")
    return df


def _prepare_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    prepared = df.copy()
    prepared["date"] = prepared["date"].astype(str)
    prepared["meeting"] = prepared["meeting"].astype(str)
    prepared["meeting_name"] = prepared["meeting_name"].astype(str)
    prepared["race_key"] = prepared["meeting"] + "::" + prepared["race_number"].astype(str)
    prepared["distance_num"] = pd.to_numeric(prepared.get("distance_num"), errors="coerce")
    prepared["venue_is_hv"] = (prepared["venue"] == "跑馬地").astype(float)
    prepared["venue_is_st"] = (prepared["venue"] == "沙田").astype(float)
    prepared["is_sprint"] = prepared["distance_num"].fillna(0).isin([1000, 1200]).astype(float)
    prepared["is_middle"] = prepared["distance_num"].fillna(0).isin([1600, 1650, 1800]).astype(float)

    if "matrix_race_shape" in prepared.columns:
        prepared["int_hv_race_shape"] = prepared["matrix_race_shape"] * prepared["venue_is_hv"]
        prepared["int_middle_race_shape"] = prepared["matrix_race_shape"] * prepared["is_middle"]
    if "feat_speed_score" in prepared.columns:
        prepared["int_hv_speed"] = prepared["feat_speed_score"] * prepared["venue_is_hv"]
        prepared["int_sprint_speed"] = prepared["feat_speed_score"] * prepared["is_sprint"]
        prepared["int_distance_speed"] = prepared["feat_speed_score"] * prepared["distance_num"].fillna(0.0) / 1000.0
    if "matrix_class_advantage" in prepared.columns:
        prepared["int_st_class_advantage"] = prepared["matrix_class_advantage"] * prepared["venue_is_st"]
    if "barrier" in prepared.columns:
        prepared["int_hv_draw"] = pd.to_numeric(prepared["barrier"], errors="coerce").fillna(0.0) * prepared["venue_is_hv"]
    if "race_class_num" in prepared.columns and "weight_carried" in prepared.columns:
        prepared["int_class_weight"] = (
            pd.to_numeric(prepared["race_class_num"], errors="coerce").fillna(0.0)
            * pd.to_numeric(prepared["weight_carried"], errors="coerce").fillna(0.0)
            / 100.0
        )
    if "raw_formline_higher_win_count" in prepared.columns and "race_class_num" in prepared.columns:
        prepared["int_formline_class"] = (
            pd.to_numeric(prepared["raw_formline_higher_win_count"], errors="coerce").fillna(0.0)
            * pd.to_numeric(prepared["race_class_num"], errors="coerce").fillna(0.0)
        )
    if "days_since_last" in prepared.columns and "tw_entries_count" in prepared.columns:
        prepared["int_quick_return_trackwork"] = (
            1.0 / (1.0 + pd.to_numeric(prepared["days_since_last"], errors="coerce").fillna(999.0))
        ) * pd.to_numeric(prepared["tw_entries_count"], errors="coerce").fillna(0.0)
    if "prior_combo_place_rate" in prepared.columns and "matrix_trainer_signal" in prepared.columns:
        prepared["int_prior_combo_signal"] = (
            pd.to_numeric(prepared["prior_combo_place_rate"], errors="coerce").fillna(0.0)
            * pd.to_numeric(prepared["matrix_trainer_signal"], errors="coerce").fillna(0.0)
            / 100.0
        )
    if "prior_horse_cd_place_rate" in prepared.columns and "matrix_stability" in prepared.columns:
        prepared["int_prior_horse_course_fit"] = (
            pd.to_numeric(prepared["prior_horse_cd_place_rate"], errors="coerce").fillna(0.0)
            * pd.to_numeric(prepared["matrix_stability"], errors="coerce").fillna(0.0)
            / 100.0
        )
    if "prior_draw_class_place_edge" in prepared.columns:
        prepared["int_prior_draw_hv"] = (
            pd.to_numeric(prepared["prior_draw_class_place_edge"], errors="coerce").fillna(0.0)
            * prepared["venue_is_hv"]
        )
    if "prior_rest_bucket_place_rate" in prepared.columns and "days_since_last" in prepared.columns:
        prepared["int_prior_rest_sharp"] = (
            pd.to_numeric(prepared["prior_rest_bucket_place_rate"], errors="coerce").fillna(0.0)
            / (1.0 + pd.to_numeric(prepared["days_since_last"], errors="coerce").fillna(999.0) / 14.0)
        )
    if "card_rating_change" in prepared.columns and "race_class_num" in prepared.columns:
        prepared["int_rating_change_class"] = (
            pd.to_numeric(prepared["card_rating_change"], errors="coerce").fillna(0.0)
            * pd.to_numeric(prepared["race_class_num"], errors="coerce").fillna(0.0)
        )

    return prepared


def _race_standardize(race_df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    frame = race_df.copy()
    derived: dict[str, pd.Series] = {}
    for column in columns:
        values = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
        mean = float(values.mean())
        std = float(values.std(ddof=0))
        if std < 1e-8:
            derived[f"{column}__race_rel"] = pd.Series(np.zeros(len(frame)), index=frame.index)
        else:
            derived[f"{column}__race_rel"] = (values - mean) / std
    if derived:
        frame = pd.concat([frame, pd.DataFrame(derived)], axis=1)
    return frame


def _materialize_feature_frame(df: pd.DataFrame, base_columns: list[str]) -> tuple[pd.DataFrame, list[str]]:
    numeric = df.copy()
    for column in base_columns:
        numeric[column] = pd.to_numeric(numeric[column], errors="coerce").fillna(0.0)

    per_race_frames = []
    for _race_key, race_df in numeric.groupby("race_key", sort=False):
        per_race_frames.append(_race_standardize(race_df, base_columns))
    merged = pd.concat(per_race_frames, ignore_index=True)

    derived_columns = []
    for column in base_columns:
        derived_columns.append(column)
        race_rel = f"{column}__race_rel"
        if race_rel in merged.columns:
            derived_columns.append(race_rel)
    return merged, derived_columns


def _make_pairwise_arrays(
    df: pd.DataFrame,
    feature_columns: list[str],
    profile: dict[str, float],
) -> tuple[np.ndarray, np.ndarray]:
    rows: list[np.ndarray] = []
    weights: list[float] = []
    for _race_key, race_df in df.groupby("race_key", sort=False):
        race_df = race_df.sort_values("finish_pos")
        matrix = race_df[feature_columns].to_numpy(dtype=float)
        positions = race_df["finish_pos"].to_numpy(dtype=int)
        for i in range(len(race_df)):
            for j in range(i + 1, len(race_df)):
                diff = matrix[i] - matrix[j]
                pos_i = int(positions[i])
                pos_j = int(positions[j])
                gap = max(pos_j - pos_i, 1)
                weight = 1.0 + min(gap, 6) * profile.get("gap_scale", 0.0)
                if pos_i == 1:
                    weight += profile.get("winner_bonus", 0.0)
                elif pos_i <= 3:
                    weight += profile.get("top3_bonus", 0.0)
                elif pos_i <= 4:
                    weight += profile.get("top4_bonus", 0.0)
                if pos_j >= 8:
                    weight += profile.get("tail_bonus", 0.0)
                rows.append(diff)
                weights.append(weight)
    if not rows:
        return np.zeros((0, len(feature_columns))), np.zeros((0,))
    return np.vstack(rows), np.array(weights, dtype=float)


def _fit_pairwise_model(
    train_df: pd.DataFrame,
    feature_columns: list[str],
    regularization: float,
    maxiter: int,
    profile: dict[str, float],
) -> np.ndarray | None:
    X, sample_weight = _make_pairwise_arrays(train_df, feature_columns, profile)
    if X.size == 0:
        return None

    y = np.ones(X.shape[0], dtype=float)

    def objective(params: np.ndarray) -> float:
        logits = X @ params
        losses = np.logaddexp(0.0, -y * logits)
        weighted_loss = float(np.sum(losses * sample_weight) / max(len(losses), 1))
        penalty = float(regularization * np.sum(params ** 2))
        return weighted_loss + penalty

    initial = np.zeros(X.shape[1], dtype=float)
    result = minimize(objective, initial, method="L-BFGS-B", options={"maxiter": maxiter})
    if not result.success and result.x is None:
        return None
    return np.array(result.x, dtype=float)


def _score_races(eval_df: pd.DataFrame, feature_columns: list[str], weights: np.ndarray) -> dict[str, Any]:
    model_races = []
    for _race_key, race_df in eval_df.groupby("race_key", sort=False):
        features = race_df[feature_columns].to_numpy(dtype=float)
        ability = features @ weights
        race_df = race_df.copy()
        race_df["model_score"] = ability
        race_df = race_df.sort_values(["model_score", "horse_number"], ascending=[False, True])
        picks = race_df["horse_number"].astype(int).tolist()[:4]
        actual_pos = {
            int(row.horse_number): int(row.finish_pos)
            for row in race_df.itertuples()
        }
        model_races.append(evaluate_pick_order(picks, actual_pos))
    return summarize_model_races(model_races)


def _current_live_summary(eval_df: pd.DataFrame) -> dict[str, Any]:
    model_races = []
    for _race_key, race_df in eval_df.groupby("race_key", sort=False):
        race_df = race_df.copy()
        race_df["current_live_recomputed_ability"] = pd.to_numeric(
            race_df["current_live_recomputed_ability"], errors="coerce"
        ).fillna(0.0)
        race_df = race_df.sort_values(
            ["current_live_recomputed_ability", "horse_number"],
            ascending=[False, True],
        )
        picks = race_df["horse_number"].astype(int).tolist()[:4]
        actual_pos = {
            int(row.horse_number): int(row.finish_pos)
            for row in race_df.itertuples()
        }
        model_races.append(evaluate_pick_order(picks, actual_pos))
    return summarize_model_races(model_races)


def _combine_summaries(items: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [item for item in items if item]
    if not valid:
        return {}
    total_races = sum(int(item.get("races", 0)) for item in valid)
    if total_races <= 0:
        return {}
    return {
        "races": total_races,
        "gold": sum(int(item.get("gold", 0)) for item in valid),
        "good": sum(int(item.get("good", 0)) for item in valid),
        "min_threshold": sum(int(item.get("min_threshold", 0)) for item in valid),
        "single": sum(int(item.get("single", 0)) for item in valid),
        "champion": sum(int(item.get("champion", 0)) for item in valid),
        "top3_has_champion": sum(int(item.get("top3_has_champion", 0)) for item in valid),
        "order_issue": sum(int(item.get("order_issue", 0)) for item in valid),
        "avg_winner_rank": round(sum(float(item.get("avg_winner_rank", 0.0)) * int(item.get("races", 0)) for item in valid) / total_races, 3),
        "mrr": round(sum(float(item.get("mrr", 0.0)) * int(item.get("races", 0)) for item in valid) / total_races, 4),
        "avg_pick1_finish": round(sum(float(item.get("avg_pick1_finish", 0.0)) * int(item.get("races", 0)) for item in valid) / total_races, 3),
        "avg_top4_hits": round(sum(float(item.get("avg_top4_hits", 0.0)) * int(item.get("races", 0)) for item in valid) / total_races, 3),
    }


def _summary_sort_key(summary: dict[str, Any]) -> tuple[Any, ...]:
    return (
        summary.get("champion", 0),
        summary.get("gold", 0),
        summary.get("min_threshold", 0),
        summary.get("mrr", 0.0),
        -summary.get("avg_pick1_finish", 99.0),
    )


def _walk_forward(
    df: pd.DataFrame,
    base_columns: list[str],
    min_train_meetings: int,
    min_train_races: int,
    maxiter: int,
) -> dict[str, Any]:
    materialized, feature_columns = _materialize_feature_frame(df, base_columns)
    meetings = []
    for meeting, meeting_df in materialized.groupby("meeting", sort=False):
        first = meeting_df.iloc[0]
        meetings.append((meeting, str(first["date"]), str(first["meeting_name"]), meeting_df))
    meetings.sort(key=lambda item: (item[1], item[2], item[0]))

    history_frames: list[pd.DataFrame] = []
    fold_candidates: list[dict[str, Any]] = []
    evaluated_by_candidate: dict[str, list[dict[str, Any]]] = defaultdict(list)
    candidate_meta: dict[str, dict[str, Any]] = {}

    for meeting_idx, (meeting, date, meeting_name, meeting_df) in enumerate(meetings):
        history = pd.concat(history_frames, ignore_index=True) if history_frames else pd.DataFrame()
        train_races = history["race_key"].nunique() if not history.empty else 0
        if meeting_idx < min_train_meetings or train_races < min_train_races:
            history_frames.append(meeting_df)
            continue

        current_live = _current_live_summary(meeting_df)
        fold_row = {
            "meeting": meeting,
            "meeting_name": meeting_name,
            "date": date,
            "train_races": int(train_races),
            "eval_races": int(meeting_df["race_key"].nunique()),
            "current_live": current_live,
            "candidate_summaries": {},
        }
        for profile_name, profile in OBJECTIVE_PROFILES.items():
            for regularization in DEFAULT_REG_GRID:
                weights = _fit_pairwise_model(
                    history,
                    feature_columns,
                    regularization=regularization,
                    maxiter=maxiter,
                    profile=profile,
                )
                if weights is None:
                    continue
                summary = _score_races(meeting_df, feature_columns, weights)
                candidate_key = f"{profile_name}__reg_{regularization}"
                candidate_meta[candidate_key] = {
                    "profile": profile_name,
                    "regularization": regularization,
                }
                evaluated_by_candidate[candidate_key].append(summary)
                fold_row["candidate_summaries"][candidate_key] = summary

        if fold_row["candidate_summaries"]:
            fold_candidates.append(fold_row)

        history_frames.append(meeting_df)

    candidate_summaries = {
        candidate_key: _combine_summaries(items)
        for candidate_key, items in evaluated_by_candidate.items()
    }
    best_candidate_key = None
    if candidate_summaries:
        best_candidate_key = max(candidate_summaries, key=lambda key: _summary_sort_key(candidate_summaries[key]))
    selected_fold_rows = []
    for row in fold_candidates:
        selected_summary = row["candidate_summaries"].get(best_candidate_key) if best_candidate_key else None
        if not selected_summary:
            continue
        selected_fold_rows.append(
            {
                "meeting": row["meeting"],
                "meeting_name": row["meeting_name"],
                "date": row["date"],
                "train_races": row["train_races"],
                "eval_races": row["eval_races"],
                "current_live": row["current_live"],
                "selected_model": selected_summary,
            }
        )

    return {
        "folds": len(selected_fold_rows),
        "feature_columns": feature_columns,
        "fold_rows": selected_fold_rows,
        "best_candidate": (
            {
                "key": best_candidate_key,
                **candidate_meta.get(best_candidate_key, {}),
                "summary": candidate_summaries.get(best_candidate_key, {}),
            }
            if best_candidate_key
            else {}
        ),
        "candidate_summaries": candidate_summaries,
    }


def _feature_importance(
    train_df: pd.DataFrame,
    base_columns: list[str],
    maxiter: int,
    regularization: float,
    profile_name: str,
) -> list[dict[str, Any]]:
    materialized, feature_columns = _materialize_feature_frame(train_df, base_columns)
    weights = _fit_pairwise_model(
        materialized,
        feature_columns,
        regularization=regularization,
        maxiter=maxiter,
        profile=OBJECTIVE_PROFILES[profile_name],
    )
    if weights is None:
        return []
    rows = []
    for feature, weight in zip(feature_columns, weights):
        rows.append({"feature": feature, "weight": round(float(weight), 6), "abs_weight": round(abs(float(weight)), 6)})
    rows.sort(key=lambda row: row["abs_weight"], reverse=True)
    return rows[:25]


def run_training(args: argparse.Namespace) -> dict[str, Any]:
    df = _prepare_dataframe(_load_or_build_dataset(args))
    feature_sets = _feature_sets(df)
    selected_feature_sets = feature_sets
    if args.feature_set:
        selected_feature_sets = {name: feature_sets[name] for name in args.feature_set if name in feature_sets}

    results = {}
    for name, columns in selected_feature_sets.items():
        results[name] = _walk_forward(
            df,
            base_columns=columns,
            min_train_meetings=args.min_train_meetings,
            min_train_races=args.min_train_races,
            maxiter=args.maxiter,
        )

    heldout_current_live = []
    if results:
        first_key = next(iter(results))
        for row in results[first_key]["fold_rows"]:
            heldout_current_live.append(row["current_live"])

    leaderboard = []
    for name, payload in results.items():
        best_candidate = payload.get("best_candidate") or {}
        summary = best_candidate.get("summary", {})
        leaderboard.append(
            {
                "model": name,
                "profile": best_candidate.get("profile"),
                "regularization": best_candidate.get("regularization"),
                "summary": summary,
                "score_tuple": _summary_sort_key(summary),
            }
        )
    leaderboard.sort(key=lambda row: row["score_tuple"], reverse=True)

    best_model_name = leaderboard[0]["model"] if leaderboard else None
    best_feature_importance = []
    if best_model_name:
        best_row = next(row for row in leaderboard if row["model"] == best_model_name)
        best_feature_importance = _feature_importance(
            df,
            selected_feature_sets[best_model_name],
            args.maxiter,
            regularization=float(best_row["regularization"]),
            profile_name=str(best_row["profile"]),
        )

    return {
        "dataset_rows": int(len(df)),
        "dataset_path": str(Path(args.dataset)),
        "feature_sets": {name: len(columns) for name, columns in selected_feature_sets.items()},
        "current_live_heldout_summary": _combine_summaries(heldout_current_live),
        "models": results,
        "leaderboard": leaderboard,
        "best_model_name": best_model_name,
        "best_model_top_weights": best_feature_importance,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# HKJC Ranking Model Test",
        "",
        f"- Dataset rows: {report['dataset_rows']}",
        f"- Dataset path: `{report['dataset_path']}`",
        f"- Held-out current_live: `{json.dumps(report['current_live_heldout_summary'], ensure_ascii=False, sort_keys=True)}`",
        "",
        "## Leaderboard",
        "",
        "| Model | Profile | Reg | Races | Gold | Good | Min | Single | Champion | Top3 Champ | MRR | Avg Pick1 Finish | Avg Top4 Hits |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in report["leaderboard"]:
        stats = row["summary"]
        lines.append(
            f"| {row['model']} | {row.get('profile', '-') or '-'} | {row.get('regularization', '-')} | "
            f"{stats.get('races', 0)} | {stats.get('gold', 0)} | {stats.get('good', 0)} | "
            f"{stats.get('min_threshold', 0)} | {stats.get('single', 0)} | {stats.get('champion', 0)} | "
            f"{stats.get('top3_has_champion', 0)} | {stats.get('mrr', '-')} | "
            f"{stats.get('avg_pick1_finish', '-')} | {stats.get('avg_top4_hits', '-')} |"
        )

    if report["best_model_top_weights"]:
        lines.extend(
            [
                "",
                f"## Top Weights: {report['best_model_name']}",
                "",
                "| Feature | Weight |",
                "| --- | ---: |",
            ]
        )
        for row in report["best_model_top_weights"]:
            lines.append(f"| {row['feature']} | {row['weight']} |")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    report = run_training(args)
    report_path = Path(args.report_output)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
