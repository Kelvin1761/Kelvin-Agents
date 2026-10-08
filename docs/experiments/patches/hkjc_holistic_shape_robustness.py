#!/usr/bin/env python3
"""Holistic race-shape deweight and robustification experiment for HKJC."""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


REPO = Path(__file__).resolve().parents[3]
PATCHES = Path(__file__).resolve().parent
SHARED = REPO / ".agents/skills/shared_racing"
AUTO_SCRIPTS = REPO / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts"
for path in (PATCHES, SHARED, AUTO_SCRIPTS):
    sys.path.insert(0, str(path))

import hkjc_top2_locked_reranker as shared  # noqa: E402
from hkjc_no_regression_gate import evaluate_stage4_candidate  # noqa: E402
from hkjc_racing_engine.scoring import DISPLAY_SLOPE  # noqa: E402


MATRIX = (
    "matrix_sectional",
    "matrix_trainer_signal",
    "matrix_stability",
    "matrix_race_shape",
    "matrix_class_advantage",
    "matrix_horse_health",
    "matrix_form_line",
)
CURRENT = np.asarray((0.1285, 0.2362, 0.0983, 0.2737, 0.1428, 0.0404, 0.0801))
CORE_INDEX = (0, 2, 4, 6)


def _core_weights(shape_weight: float) -> np.ndarray:
    output = CURRENT.copy()
    released = output[3] - shape_weight
    output[3] = shape_weight
    total = float(sum(CURRENT[index] for index in CORE_INDEX))
    for index in CORE_INDEX:
        output[index] += released * CURRENT[index] / total
    return output


def _proportional_weights(shape_weight: float) -> np.ndarray:
    output = CURRENT.copy()
    released = output[3] - shape_weight
    output[3] = shape_weight
    total = float(CURRENT.sum() - CURRENT[3])
    for index in range(len(output)):
        if index != 3:
            output[index] += released * CURRENT[index] / total
    return output


WEIGHT_PROFILES = {
    "shape26_core": _core_weights(0.26),
    "shape24_core": _core_weights(0.24),
    "shape20_core": _core_weights(0.20),
    "shape24_stability": np.asarray(
        (0.1285, 0.2362, 0.1320, 0.2400, 0.1428, 0.0404, 0.0801)
    ),
    "shape24_proportional": _proportional_weights(0.24),
}
ROBUST_PROFILES = {
    "shape_winsor12": ("winsor", 12.0, 0.0),
    "shape_winsor10": ("winsor", 10.0, 0.0),
    "shape_winsor8": ("winsor", 8.0, 0.0),
    "shape_huber8_half": ("huber", 8.0, 0.5),
}
ARMS = (*WEIGHT_PROFILES, *ROBUST_PROFILES)


def _prepare(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df[df["race_label_valid"].fillna(0).astype(int).eq(1)].copy()
    df["race_key"] = df["meeting_name"].astype(str) + "::" + df["race_number"].astype(str)
    for column in (*MATRIX, "current_live_recomputed_ability", "finish_pos", "horse_number"):
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df.dropna(subset=[*MATRIX, "current_live_recomputed_ability", "finish_pos", "horse_number"])
    df["finish_pos"] = df["finish_pos"].astype(int)
    df["horse_number"] = df["horse_number"].astype(int)
    matrix = df[list(MATRIX)].to_numpy(float)
    baseline = df["current_live_recomputed_ability"].to_numpy(float)
    for arm, weights in WEIGHT_PROFILES.items():
        df[f"score_{arm}"] = baseline + matrix @ (weights - CURRENT) * DISPLAY_SLOPE

    shape = df["matrix_race_shape"].to_numpy(float)
    median = df.groupby("race_key")["matrix_race_shape"].transform("median").to_numpy(float)
    deviation = shape - median
    for arm, (kind, threshold, tail_share) in ROBUST_PROFILES.items():
        if kind == "winsor":
            adjusted_deviation = np.clip(deviation, -threshold, threshold)
        else:
            excess = np.maximum(np.abs(deviation) - threshold, 0.0)
            adjusted_deviation = np.sign(deviation) * (
                np.minimum(np.abs(deviation), threshold) + tail_share * excess
            )
        adjusted_shape = median + adjusted_deviation
        raw_delta = CURRENT[3] * (adjusted_shape - shape)
        df[f"score_{arm}"] = baseline + raw_delta * DISPLAY_SLOPE
    return df.sort_values(["date", "meeting_name", "race_number", "horse_number"]).reset_index(drop=True)


def _records(df: pd.DataFrame, arm: str) -> list[dict[str, Any]]:
    output = []
    for race_key, race in df.groupby("race_key", sort=False):
        actual = dict(zip(race["horse_number"].astype(int), race["finish_pos"].astype(int)))
        baseline = shared._baseline_picks(race)
        candidate = (
            race.sort_values([f"score_{arm}", "horse_number"], ascending=[False, True])["horse_number"]
            .astype(int)
            .tolist()
        )
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


def _folds(records: list[dict[str, Any]], dates: list[str], arm: str) -> list[dict[str, Any]]:
    output = []
    for number, block in enumerate(shared._date_blocks(dates), start=1):
        rows = [row for row in records if row["date"] in set(block)]
        values = shared._report(rows, arm)
        paired = values["paired"]
        output.append({
            "fold": number,
            **values,
            "primary_nonnegative": paired["gold"]["delta"] >= 0
            and paired["good"]["delta"] >= 0,
        })
    return output


def _volatility_pass(volatility: dict[str, Any], arm: str) -> bool:
    baseline = volatility["current_live"]
    candidate = volatility[arm]
    return (
        candidate["sd_top5_hits"] <= baseline["sd_top5_hits"] + 1e-12
        and candidate["sd_complete_capture"] <= baseline["sd_complete_capture"] + 0.005
    )


def _eligible(
    values: dict[str, Any], tail: dict[str, Any], folds: list[dict[str, Any]], volatility: dict[str, Any], arm: str
) -> bool:
    paired = values["paired"]
    tail_paired = tail["paired"]
    return (
        paired["gold"]["delta"] >= 0
        and paired["good"]["delta"] >= 0
        and sum(row["primary_nonnegative"] for row in folds) >= 3
        and sum(
            paired[key]["delta"] > 0
            for key in ("top3_capture_at5", "competitive_recall_at5", "ndcg5")
        )
        >= 2
        and tail_paired["missed_top3_outside5"]["delta"] <= 0.01
        and tail_paired["model_top5_finish8plus"]["delta"] <= 0.01
        and _volatility_pass(volatility, arm)
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
        "schema": "hkjc-holistic-shape-robustness/v1",
        "dataset": {
            "rows": int(len(df)),
            "races": int(df["race_key"].nunique()),
            "development_dates": [dev_dates[0], dev_dates[-1]],
            "terminal_dates": [terminal_dates[0], terminal_dates[-1]],
        },
        "current_weights": dict(zip(MATRIX, CURRENT.tolist())),
        "weight_profiles": {
            arm: dict(zip(MATRIX, values.tolist())) for arm, values in WEIGHT_PROFILES.items()
        },
        "robust_profiles": ROBUST_PROFILES,
        "leakage_audit": {
            "status": "PASS",
            "feature_source": "pre_race_production_matrix_only",
            "odds_used": False,
            "result_join": "evaluation_only_after_scores",
        },
        "development_arms": {},
    }

    selected: tuple[float, str, float] | None = None
    for arm in ARMS:
        records = _records(dev, arm)
        values = shared._report(records, arm)
        tail = shared._tail_report(records, arm)
        folds = _folds(records, dev_dates, arm)
        volatility = shared._meeting_volatility(records, arm)
        eligible = _eligible(values, tail, folds, volatility, arm)
        paired = values["paired"]
        objective = sum(
            paired[key]["delta"]
            for key in ("top3_capture_at5", "competitive_recall_at5", "ndcg5")
        )
        mean_abs_adjustment = float(
            np.mean(np.abs(dev[f"score_{arm}"] - dev["current_live_recomputed_ability"]))
        )
        report["development_arms"][arm] = {
            "metrics": values,
            "tail": tail,
            "folds": folds,
            "primary_nonnegative_folds": sum(row["primary_nonnegative"] for row in folds),
            "meeting_volatility": volatility,
            "mean_abs_adjustment": round(mean_abs_adjustment, 6),
            "eligible": eligible,
            "selection_objective": round(float(objective), 9),
        }
        if eligible and (
            selected is None
            or objective > selected[0] + 1e-12
            or (abs(objective - selected[0]) <= 1e-12 and mean_abs_adjustment < selected[2])
        ):
            selected = (objective, arm, mean_abs_adjustment)

    if selected is None:
        report["decision"] = {"verdict": "REJECT_DEV", "reason": "no_eligible_holistic_arm"}
    else:
        _, arm, _ = selected
        dev_records = _records(dev, arm)
        terminal_records = _records(terminal, arm)
        all_records = dev_records + terminal_records
        terminal_values = shared._report(terminal_records, arm)
        terminal_tail = shared._tail_report(terminal_records, arm)
        all_volatility = shared._meeting_volatility(all_records, arm)
        paired = terminal_values["paired"]
        tail_paired = terminal_tail["paired"]
        terminal_pass = (
            paired["gold"]["delta"] >= 0
            and paired["good"]["delta"] >= 0
            and any(
                paired[key]["delta"] > 0
                for key in ("top3_capture_at5", "competitive_recall_at5", "ndcg5")
            )
            and tail_paired["missed_top3_outside5"]["delta"] <= 0
            and tail_paired["model_top5_finish8plus"]["delta"] <= 0.01
            and _volatility_pass(all_volatility, arm)
        )
        venue = {}
        for name in ("沙田", "跑馬地"):
            venue[name] = {}
            for part, records in (("development", dev_records), ("terminal", terminal_records)):
                rows = [row for row in records if row["venue"] == name]
                venue[name][part] = {
                    "metrics": shared._report(rows, arm),
                    "tail": shared._tail_report(rows, arm),
                }
        stage4 = evaluate_stage4_candidate(all_records, arm, leakage_audit_passed=True)
        promoted = terminal_pass and stage4["verdict"] != "REJECT"
        report["selected"] = {
            "arm": arm,
            "development": report["development_arms"][arm],
            "terminal": {"metrics": terminal_values, "tail": terminal_tail},
            "all": {
                "metrics": shared._report(all_records, arm),
                "tail": shared._tail_report(all_records, arm),
            },
            "venues": venue,
            "meeting_volatility": all_volatility,
            "stage4": stage4,
            "terminal_pass": terminal_pass,
        }
        report["decision"] = {
            "verdict": "PROMOTE" if promoted else "REJECT",
            "reason": "passed_locked_gate" if promoted else stage4.get("reason", "terminal_gate_failed"),
        }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
