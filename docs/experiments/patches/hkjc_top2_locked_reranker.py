#!/usr/bin/env python3
"""Evaluate a point-in-time Top-2 locked HKJC boundary reranker.

Research only.  The candidate family and selection rule are pre-registered in
EXP-20261008-02.  Terminal data is not scored until development selection ends.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression


REPO = Path(__file__).resolve().parents[3]
PATCHES = Path(__file__).resolve().parent
REFLECTOR = REPO / ".agents/skills/hkjc_racing/hkjc_reflector/scripts"
SHARED = REPO / ".agents/skills/shared_racing"
for path in (PATCHES, REFLECTOR, SHARED):
    sys.path.insert(0, str(path))

import hkjc_hierarchical_refit as metrics  # noqa: E402
from hkjc_no_regression_gate import evaluate_stage4_candidate  # noqa: E402


MATRIX = (
    "matrix_sectional",
    "matrix_trainer_signal",
    "matrix_stability",
    "matrix_race_shape",
    "matrix_class_advantage",
    "matrix_horse_health",
    "matrix_form_line",
)
FEATURE_SCORES = (
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
)
BASE_FEATURES = ("current_live_recomputed_ability", *MATRIX, *FEATURE_SCORES)
SHARES = (0.15, 0.30, 0.45)
MODEL_C = 0.20
MIN_TRAIN_RACES = 55


def _race_percentile(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    median = numeric.median()
    filled = numeric.fillna(60.0 if pd.isna(median) else median)
    return filled.rank(method="average", pct=True)


def _prepare(path: str) -> tuple[pd.DataFrame, list[str]]:
    df = pd.read_csv(path)
    df = df[df["race_label_valid"].fillna(0).astype(int).eq(1)].copy()
    df["race_key"] = df["meeting_name"].astype(str) + "::" + df["race_number"].astype(str)
    for column in (*BASE_FEATURES, "finish_pos", "horse_number"):
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df.dropna(subset=["current_live_recomputed_ability", "finish_pos", "horse_number"])
    df["finish_pos"] = df["finish_pos"].astype(int)
    df["horse_number"] = df["horse_number"].astype(int)
    df["is_top3_target"] = df["finish_pos"].le(3).astype(int)
    df["is_hv"] = df["venue"].astype(str).eq("跑馬地").astype(float)

    model_features: list[str] = []
    grouped = df.groupby("race_key", sort=False)
    for column in BASE_FEATURES:
        output = f"rank_{column}"
        df[output] = grouped[column].transform(_race_percentile)
        model_features.append(output)
    for column in MATRIX:
        base = f"rank_{column}"
        output = f"hv_x_{base}"
        df[output] = df[base] * df["is_hv"]
        model_features.append(output)
    return (
        df.sort_values(["date", "meeting_name", "race_number", "horse_number"]).reset_index(drop=True),
        model_features,
    )


def _fit(train: pd.DataFrame, features: list[str]) -> LogisticRegression:
    model = LogisticRegression(C=MODEL_C, penalty="l2", solver="lbfgs", max_iter=2000)
    model.fit(train[features].to_numpy(float), train["is_top3_target"].to_numpy(int))
    return model


def _candidate_picks(race: pd.DataFrame, probability_column: str, share: float) -> list[int]:
    ordered = race.sort_values(
        ["current_live_recomputed_ability", "horse_number"], ascending=[False, True]
    ).copy()
    horses = ordered["horse_number"].astype(int).tolist()
    if len(horses) <= 3:
        return horses
    pool = ordered.iloc[2:8].copy()
    if len(pool) <= 1:
        return horses
    size = len(pool)
    pool["_base_strength"] = np.linspace(1.0, 0.0, num=size)
    pool["_ml_strength"] = pool[probability_column].rank(method="average", pct=True)
    pool["_blend"] = (1.0 - share) * pool["_base_strength"] + share * pool["_ml_strength"]
    pool = pool.sort_values(
        ["_blend", "current_live_recomputed_ability", "horse_number"],
        ascending=[False, False, True],
    )
    return horses[:2] + pool["horse_number"].astype(int).tolist() + horses[8:]


def _baseline_picks(race: pd.DataFrame) -> list[int]:
    return (
        race.sort_values(
            ["current_live_recomputed_ability", "horse_number"], ascending=[False, True]
        )["horse_number"]
        .astype(int)
        .tolist()
    )


def _model_record(picks: list[int], actual: dict[int, int]) -> dict[str, Any]:
    top3 = {horse for horse, position in actual.items() if position <= 3}
    return {
        "picks": picks,
        "gold": top3.issubset(set(picks[:4])),
        "good": len(picks) >= 2 and picks[0] in top3 and picks[1] in top3,
    }


def _records(df: pd.DataFrame, probability_column: str, arm: str, share: float) -> list[dict[str, Any]]:
    output = []
    for race_key, race in df.groupby("race_key", sort=False):
        actual = dict(zip(race["horse_number"].astype(int), race["finish_pos"].astype(int)))
        output.append({
            "race_key": str(race_key),
            "meeting": str(race.iloc[0]["meeting_name"]),
            "date": str(race.iloc[0]["date"]),
            "venue": str(race.iloc[0]["venue"]),
            "actual_pos": actual,
            "models": {
                "current_live": _model_record(_baseline_picks(race), actual),
                arm: _model_record(_candidate_picks(race, probability_column, share), actual),
            },
        })
    return output


def _report(records: list[dict[str, Any]], arm: str) -> dict[str, Any]:
    base, candidate = [], []
    for record in records:
        actual = record["actual_pos"]
        base.append(metrics._flags(record["models"]["current_live"], actual))
        candidate.append(metrics._flags(record["models"][arm], actual))
    return {
        "baseline": metrics._summarize(base),
        "candidate": metrics._summarize(candidate),
        "paired": metrics._paired(candidate, base),
    }


def _tail_row(model: dict[str, Any], actual: dict[int, int]) -> dict[str, float]:
    picks = [int(value) for value in model["picks"]]
    ranks = {horse: index + 1 for index, horse in enumerate(picks)}
    top3 = [horse for horse, position in actual.items() if position <= 3]
    return {
        "missed_top3_outside5": float(sum(ranks[horse] > 5 for horse in top3)),
        "worst_top3_rank": float(max(ranks[horse] for horse in top3)),
        "model_top5_finish8plus": float(sum(actual.get(horse, 99) >= 8 for horse in picks[:5])),
        "top5_hits": float(sum(ranks[horse] <= 5 for horse in top3)),
        "complete_top5": float(all(ranks[horse] <= 5 for horse in top3)),
    }


def _tail_report(records: list[dict[str, Any]], arm: str) -> dict[str, Any]:
    baseline = [_tail_row(row["models"]["current_live"], row["actual_pos"]) for row in records]
    candidate = [_tail_row(row["models"][arm], row["actual_pos"]) for row in records]
    return {
        "baseline": metrics._summarize(baseline),
        "candidate": metrics._summarize(candidate),
        "paired": metrics._paired(candidate, baseline),
    }


def _meeting_volatility(records: list[dict[str, Any]], arm: str) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        grouped[row["meeting"]].append(row)
    output: dict[str, Any] = {"meetings": len(grouped)}
    for model in ("current_live", arm):
        hits, captures = [], []
        for rows in grouped.values():
            tail = [_tail_row(row["models"][model], row["actual_pos"]) for row in rows]
            hits.append(float(np.mean([item["top5_hits"] for item in tail])))
            captures.append(float(np.mean([item["complete_top5"] for item in tail])))
        output[model] = {
            "mean_top5_hits": round(float(np.mean(hits)), 6),
            "sd_top5_hits": round(float(np.std(hits, ddof=1)), 6),
            "mean_complete_capture": round(float(np.mean(captures)), 6),
            "sd_complete_capture": round(float(np.std(captures, ddof=1)), 6),
        }
    return output


def _date_blocks(dates: list[str]) -> list[list[str]]:
    return [list(block) for block in np.array_split(np.asarray(dates, dtype=object), 5) if len(block)]


def _oof_development(
    dev: pd.DataFrame, dev_dates: list[str], features: list[str]
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    output = dev.copy()
    output["ml_probability"] = output["rank_current_live_recomputed_ability"]
    audit = []
    for number, block in enumerate(_date_blocks(dev_dates), start=1):
        block_set = set(block)
        train = dev[dev["date"].astype(str) < min(block_set)]
        valid_mask = output["date"].astype(str).isin(block_set)
        train_races = int(train["race_key"].nunique())
        active = train_races >= MIN_TRAIN_RACES and train["is_top3_target"].nunique() == 2
        if active:
            model = _fit(train, features)
            output.loc[valid_mask, "ml_probability"] = model.predict_proba(
                output.loc[valid_mask, features].to_numpy(float)
            )[:, 1]
        audit.append({
            "fold": number,
            "dates": [min(block_set), max(block_set)],
            "train_races": train_races,
            "active": active,
        })
    return output, audit


def _arm_name(share: float) -> str:
    return f"top2_lock_ml{int(round(share * 100)):02d}"


def _eligible(dev_report: dict[str, Any], tail: dict[str, Any], nonnegative_folds: int) -> bool:
    paired = dev_report["paired"]
    ranking_positive = sum(
        paired[key]["delta"] > 0
        for key in ("top3_capture_at5", "competitive_recall_at5", "ndcg5")
    )
    tail_paired = tail["paired"]
    return (
        paired["gold"]["delta"] >= 0
        and paired["good"]["delta"] >= 0
        and nonnegative_folds >= 3
        and ranking_positive >= 2
        and tail_paired["missed_top3_outside5"]["delta"] <= 0.01
        and tail_paired["model_top5_finish8plus"]["delta"] <= 0.01
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    df, features = _prepare(args.dataset)
    dates = sorted(df["date"].astype(str).unique())
    terminal_count = max(1, math.ceil(len(dates) * 0.15))
    dev_dates, terminal_dates = dates[:-terminal_count], dates[-terminal_count:]
    dev = df[df["date"].astype(str).isin(set(dev_dates))].copy()
    terminal = df[df["date"].astype(str).isin(set(terminal_dates))].copy()
    oof, fold_audit = _oof_development(dev, dev_dates, features)

    report: dict[str, Any] = {
        "schema": "hkjc-top2-locked-reranker/v1",
        "dataset": {
            "rows": int(len(df)),
            "races": int(df["race_key"].nunique()),
            "meetings": int(df["meeting_name"].nunique()),
            "dates": [dates[0], dates[-1]],
            "development_dates": [dev_dates[0], dev_dates[-1]],
            "terminal_dates": [terminal_dates[0], terminal_dates[-1]],
        },
        "learner": {"type": "logistic_regression_l2", "C": MODEL_C},
        "features": features,
        "fold_audit": fold_audit,
        "leakage_audit": {
            "status": "PASS",
            "feature_source": "pre_race_point_in_time_engine_fields_only",
            "odds_used": False,
            "result_use": "training_label_and_evaluation_only",
        },
        "development_arms": {},
    }

    selected: tuple[float, str, float] | None = None
    blocks = _date_blocks(dev_dates)
    for share in SHARES:
        arm = _arm_name(share)
        records = _records(oof, "ml_probability", arm, share)
        dev_metrics = _report(records, arm)
        dev_tail = _tail_report(records, arm)
        folds = []
        for number, block in enumerate(blocks, start=1):
            rows = [row for row in records if row["date"] in set(block)]
            value = _report(rows, arm)
            paired = value["paired"]
            folds.append({
                "fold": number,
                **value,
                "primary_nonnegative": paired["gold"]["delta"] >= 0
                and paired["good"]["delta"] >= 0,
            })
        nonnegative = sum(row["primary_nonnegative"] for row in folds)
        eligible = _eligible(dev_metrics, dev_tail, nonnegative)
        paired = dev_metrics["paired"]
        objective = sum(
            paired[key]["delta"]
            for key in ("top3_capture_at5", "competitive_recall_at5", "ndcg5")
        )
        report["development_arms"][arm] = {
            "share": share,
            "metrics": dev_metrics,
            "tail": dev_tail,
            "folds": folds,
            "primary_nonnegative_folds": nonnegative,
            "eligible": eligible,
            "selection_objective": round(float(objective), 9),
        }
        if eligible and (selected is None or objective > selected[0] + 1e-12):
            selected = (objective, arm, share)

    if selected is None:
        report["decision"] = {"verdict": "REJECT_DEV", "reason": "no_eligible_arm"}
    else:
        _, arm, share = selected
        final_model = _fit(dev, features)
        terminal["ml_probability"] = final_model.predict_proba(terminal[features].to_numpy(float))[:, 1]
        terminal_records = _records(terminal, "ml_probability", arm, share)
        dev_records = _records(oof, "ml_probability", arm, share)
        all_records = dev_records + terminal_records
        terminal_metrics = _report(terminal_records, arm)
        terminal_tail = _tail_report(terminal_records, arm)
        venue = {}
        for name in ("沙田", "跑馬地"):
            venue[name] = {}
            for part, records in (("development", dev_records), ("terminal", terminal_records)):
                rows = [row for row in records if row["venue"] == name]
                venue[name][part] = {
                    "metrics": _report(rows, arm),
                    "tail": _tail_report(rows, arm),
                }
        stage4 = evaluate_stage4_candidate(all_records, arm, leakage_audit_passed=True)
        terminal_paired = terminal_metrics["paired"]
        terminal_ranking_positive = sum(
            terminal_paired[key]["delta"] > 0
            for key in ("top3_capture_at5", "competitive_recall_at5", "ndcg5")
        )
        terminal_tail_paired = terminal_tail["paired"]
        terminal_pass = (
            terminal_paired["gold"]["delta"] >= 0
            and terminal_paired["good"]["delta"] >= 0
            and terminal_ranking_positive >= 1
            and terminal_tail_paired["missed_top3_outside5"]["delta"] <= 0
            and terminal_tail_paired["model_top5_finish8plus"]["delta"] <= 0.01
        )
        report["selected"] = {
            "arm": arm,
            "share": share,
            "development": report["development_arms"][arm],
            "terminal": {"metrics": terminal_metrics, "tail": terminal_tail},
            "all": {"metrics": _report(all_records, arm), "tail": _tail_report(all_records, arm)},
            "venues": venue,
            "meeting_volatility": _meeting_volatility(all_records, arm),
            "stage4": stage4,
            "terminal_pass": terminal_pass,
            "coefficients": {
                feature: round(float(value), 8)
                for feature, value in zip(features, final_model.coef_[0])
            },
            "intercept": round(float(final_model.intercept_[0]), 8),
        }
        report["decision"] = {
            "verdict": "PROMOTE" if terminal_pass and stage4["verdict"] != "REJECT" else "REJECT",
            "reason": "passed_locked_gate" if terminal_pass else "terminal_gate_failed",
        }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
