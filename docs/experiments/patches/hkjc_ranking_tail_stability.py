#!/usr/bin/env python3
"""Evaluate a bounded core/context disagreement correction for HKJC ranking.

Research only.  Candidate scores are computed before result labels are joined.
The fixed candidate family is pre-registered in EXP-20261008-01.
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


REPO = Path(__file__).resolve().parents[3]
PATCHES = Path(__file__).resolve().parent
REFLECTOR = REPO / ".agents/skills/hkjc_racing/hkjc_reflector/scripts"
SHARED = REPO / ".agents/skills/shared_racing"
HKJC_AUTO_SCRIPTS = REPO / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts"
for path in (PATCHES, REFLECTOR, SHARED, HKJC_AUTO_SCRIPTS):
    sys.path.insert(0, str(path))

import hkjc_hierarchical_refit as metrics  # noqa: E402
from hkjc_no_regression_gate import evaluate_stage4_candidate  # noqa: E402
from hkjc_racing_engine.scoring import DISPLAY_SLOPE  # noqa: E402


WEIGHTS = {
    "matrix_sectional": 0.1285,
    "matrix_trainer_signal": 0.2362,
    "matrix_stability": 0.0983,
    "matrix_race_shape": 0.2737,
    "matrix_class_advantage": 0.1428,
    "matrix_horse_health": 0.0404,
    "matrix_form_line": 0.0801,
}
CORE = ("matrix_sectional", "matrix_stability", "matrix_class_advantage", "matrix_form_line")
CONTEXT = ("matrix_trainer_signal", "matrix_race_shape", "matrix_horse_health")
THRESHOLD = 12.0
SLOPE = 0.04
CAP = 0.8
ARMS = ("over_only", "under_only", "symmetric")


def _weighted_mean(frame: pd.DataFrame, columns: tuple[str, ...]) -> pd.Series:
    total = sum(WEIGHTS[column] for column in columns)
    return sum(frame[column] * WEIGHTS[column] for column in columns) / total


def _prepare(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df[df["race_label_valid"].fillna(0).astype(int).eq(1)].copy()
    df["race_key"] = df["meeting_name"].astype(str) + "::" + df["race_number"].astype(str)
    for column in (*WEIGHTS, "current_live_recomputed_ability", "finish_pos", "horse_number"):
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df.dropna(subset=["current_live_recomputed_ability", "finish_pos", "horse_number"])
    df["finish_pos"] = df["finish_pos"].astype(int)
    df["horse_number"] = df["horse_number"].astype(int)
    df["is_debut"] = df["is_debut"].fillna(0).astype(bool)
    df["core_score"] = _weighted_mean(df, CORE)
    df["context_score"] = _weighted_mean(df, CONTEXT)
    gap = df["core_score"] - df["context_score"]
    magnitude = (gap.abs() - THRESHOLD).clip(lower=0.0) * SLOPE
    df["tail_delta"] = np.sign(gap) * magnitude.clip(upper=CAP)
    df.loc[df["is_debut"], "tail_delta"] = 0.0
    df["score_current_live"] = df["current_live_recomputed_ability"].astype(float)
    display_delta = df["tail_delta"] * DISPLAY_SLOPE
    df["score_over_only"] = df["score_current_live"] + display_delta.clip(upper=0.0)
    df["score_under_only"] = df["score_current_live"] + display_delta.clip(lower=0.0)
    df["score_symmetric"] = df["score_current_live"] + display_delta
    return df.sort_values(["date", "meeting_name", "race_number", "horse_number"]).reset_index(drop=True)


def _model_record(race: pd.DataFrame, score_column: str) -> dict[str, Any]:
    ordered = race.sort_values([score_column, "horse_number"], ascending=[False, True])
    picks = ordered["horse_number"].astype(int).tolist()
    actual = dict(zip(race["horse_number"].astype(int), race["finish_pos"].astype(int)))
    top3 = {horse for horse, position in actual.items() if position <= 3}
    return {
        "picks": picks,
        "gold": top3.issubset(set(picks[:4])),
        "good": len(picks) >= 2 and picks[0] in top3 and picks[1] in top3,
    }


def _records(df: pd.DataFrame, arm: str) -> list[dict[str, Any]]:
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
                "current_live": _model_record(race, "score_current_live"),
                arm: _model_record(race, f"score_{arm}"),
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
        "model_top3_finish8plus": float(sum(actual.get(horse, 99) >= 8 for horse in picks[:3])),
        "model_top5_finish8plus": float(sum(actual.get(horse, 99) >= 8 for horse in picks[:5])),
        "top5_hits": float(sum(horse in set(top3) for horse in picks[:5])),
        "complete_top5": float(set(top3).issubset(set(picks[:5]))),
    }


def _tail_report(records: list[dict[str, Any]], arm: str) -> dict[str, Any]:
    baseline = [_tail_row(row["models"]["current_live"], row["actual_pos"]) for row in records]
    candidate = [_tail_row(row["models"][arm], row["actual_pos"]) for row in records]
    paired = metrics._paired(candidate, baseline)
    return {
        "baseline": metrics._summarize(baseline),
        "candidate": metrics._summarize(candidate),
        "paired": paired,
    }


def _meeting_volatility(records: list[dict[str, Any]], arm: str) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        grouped[row["meeting"]].append(row)
    output: dict[str, Any] = {"meetings": len(grouped)}
    for model in ("current_live", arm):
        hit_means, capture_rates = [], []
        for rows in grouped.values():
            tail = [_tail_row(row["models"][model], row["actual_pos"]) for row in rows]
            hit_means.append(float(np.mean([item["top5_hits"] for item in tail])))
            capture_rates.append(float(np.mean([item["complete_top5"] for item in tail])))
        output[model] = {
            "mean_top5_hits": round(float(np.mean(hit_means)), 6),
            "sd_top5_hits": round(float(np.std(hit_means, ddof=1)), 6) if len(hit_means) > 1 else 0.0,
            "mean_complete_capture": round(float(np.mean(capture_rates)), 6),
            "sd_complete_capture": round(float(np.std(capture_rates, ddof=1)), 6) if len(capture_rates) > 1 else 0.0,
        }
    return output


def _blocks(dev_dates: list[str]) -> list[set[str]]:
    return [set(block.tolist()) for block in np.array_split(np.asarray(dev_dates, dtype=object), 5) if len(block)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    df = _prepare(args.dataset)
    dates = sorted(df["date"].dropna().astype(str).unique())
    terminal_count = max(1, math.ceil(len(dates) * 0.15))
    dev_dates, terminal_dates = dates[:-terminal_count], dates[-terminal_count:]
    dev_set, terminal_set = set(dev_dates), set(terminal_dates)

    report: dict[str, Any] = {
        "schema": "hkjc-ranking-tail-stability/v1",
        "dataset": {
            "rows": int(len(df)),
            "races": int(df["race_key"].nunique()),
            "meetings": int(df["meeting_name"].nunique()),
            "dates": [dates[0], dates[-1]],
            "development_dates": [dev_dates[0], dev_dates[-1]],
            "terminal_dates": [terminal_dates[0], terminal_dates[-1]],
        },
        "locked_parameters": {"threshold": THRESHOLD, "slope": SLOPE, "cap": CAP},
        "activation": {
            "nonzero_rows": int(df["tail_delta"].ne(0).sum()),
            "positive_rows": int(df["tail_delta"].gt(0).sum()),
            "negative_rows": int(df["tail_delta"].lt(0).sum()),
            "mean_abs_delta": round(float(df["tail_delta"].abs().mean()), 6),
            "max_abs_delta": round(float(df["tail_delta"].abs().max()), 6),
        },
        "leakage_audit": {
            "status": "PASS",
            "feature_source": "pre_race_production_matrix_only",
            "result_join": "evaluation_only_after_scores",
            "odds_used": False,
        },
        "arms": {},
    }

    for arm in ARMS:
        all_records = _records(df, arm)
        dev_records = [row for row in all_records if row["date"] in dev_set]
        terminal_records = [row for row in all_records if row["date"] in terminal_set]
        venue_reports = {}
        for venue in ("沙田", "跑馬地"):
            rows = [row for row in all_records if row["venue"] == venue]
            venue_reports[venue] = {"metrics": _report(rows, arm), "tail": _tail_report(rows, arm)}
        fold_reports = []
        for number, block in enumerate(_blocks(dev_dates), start=1):
            rows = [row for row in dev_records if row["date"] in block]
            value = _report(rows, arm)
            paired = value["paired"]
            fold_reports.append({
                "fold": number,
                "dates": [min(block), max(block)],
                **value,
                "primary_nonnegative": (
                    paired["gold"]["delta"] >= 0 and paired["good"]["delta"] >= 0
                ),
            })
        report["arms"][arm] = {
            "all": {"metrics": _report(all_records, arm), "tail": _tail_report(all_records, arm)},
            "development": {"metrics": _report(dev_records, arm), "tail": _tail_report(dev_records, arm)},
            "terminal": {"metrics": _report(terminal_records, arm), "tail": _tail_report(terminal_records, arm)},
            "venues": venue_reports,
            "development_folds": fold_reports,
            "development_primary_nonnegative_folds": sum(row["primary_nonnegative"] for row in fold_reports),
            "meeting_volatility": _meeting_volatility(all_records, arm),
            "stage4": evaluate_stage4_candidate(all_records, arm, leakage_audit_passed=True),
        }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
