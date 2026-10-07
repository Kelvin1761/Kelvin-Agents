#!/usr/bin/env python3
"""Pre-registered Sha Tin turf race-shape shrinkage ablation."""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd


REPO = Path(__file__).resolve().parents[3]
PATCHES = Path(__file__).resolve().parent
REFLECTOR = REPO / ".agents/skills/hkjc_racing/hkjc_reflector/scripts"
SHARED_RACING = REPO / ".agents/skills/shared_racing"
for path in (PATCHES, REFLECTOR, SHARED_RACING, REPO):
    sys.path.insert(0, str(path))

import hkjc_surface_shape_ml as shared  # noqa: E402
import hkjc_race_shape_v2_ab as metrics  # noqa: E402
from hkjc_no_regression_gate import evaluate_stage4_candidate  # noqa: E402


STANDARD_SHAPE_WEIGHT = 0.2737
MODEL_NAMES = ("current_live", "trip_half", "fit_half", "both_half", "draw70")


def _candidate_scores(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    eligible = out["surface_key"].eq("ST_TURF") & ~out["is_debut"].astype(bool)
    neutral = 60.0
    candidates = {
        "trip_half": 0.55 * out["shape_draw"] + 0.25 * out["shape_fit"] + 0.10 * out["shape_trip"] + 0.10 * neutral,
        "fit_half": 0.55 * out["shape_draw"] + 0.125 * out["shape_fit"] + 0.20 * out["shape_trip"] + 0.125 * neutral,
        "both_half": 0.55 * out["shape_draw"] + 0.125 * out["shape_fit"] + 0.10 * out["shape_trip"] + 0.225 * neutral,
        "draw70": 0.70 * out["shape_draw"] + 0.15 * out["shape_fit"] + 0.15 * out["shape_trip"],
    }
    out["score_current_live"] = out["current_live_recomputed_ability"]
    for name, shape in candidates.items():
        candidate_shape = np.where(eligible, shape.clip(0.0, 100.0), out["matrix_race_shape"])
        out[f"shape_{name}"] = candidate_shape
        out[f"score_{name}"] = (
            out["current_live_recomputed_ability"]
            + STANDARD_SHAPE_WEIGHT * (candidate_shape - out["matrix_race_shape"])
        )
    return out


def _distance_bucket(value: object) -> str:
    distance = float(value or 0)
    if distance <= 1200:
        return "distance_1000_1200"
    if distance <= 1600:
        return "distance_1400_1600"
    return "distance_1650_plus"


def _field_bucket(value: object) -> str:
    size = int(float(value or 0))
    if size <= 10:
        return "field_le10"
    if size <= 12:
        return "field_11_12"
    return "field_13_plus"


def _records(df: pd.DataFrame):
    records = []
    flags = defaultdict(lambda: defaultdict(list))
    dates = sorted(df["date"].astype(str).unique())
    terminal_count = max(1, math.ceil(len(dates) * 0.15))
    terminal_dates = set(dates[-terminal_count:])
    for (_meeting, _race_no), race in df.groupby(["meeting", "race_number"], sort=False):
        first = race.iloc[0]
        date = str(first["date"])
        surface = str(first["surface_key"])
        split = "terminal" if date in terminal_dates else "development"
        actual_pos = dict(zip(race["horse_number"].astype(int), race["finish_pos"].astype(int)))
        models = {name: metrics._model_record(race, f"score_{name}") for name in MODEL_NAMES}
        records.append({"date": date, "actual_pos": actual_pos, "models": models})
        cohorts = ["all", split, surface]
        if surface == "ST_TURF":
            cohorts.extend([
                f"ST_TURF_{split}",
                f"date_{date}",
                _distance_bucket(first["distance_num"]),
                _field_bucket(first["field_size"]),
                f"course_{str(first.get('course') or 'unknown').strip() or 'unknown'}",
            ])
        for name, model in models.items():
            row = metrics._ranking_flags(model, actual_pos)
            for cohort in cohorts:
                flags[name][cohort].append(row)
    return records, flags


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    df = pd.read_csv(args.dataset)
    df["race_key"] = df["meeting"].astype(str) + "::" + df["race_number"].astype(str)
    df = shared._add_shape_components(df)
    df = shared._add_surface_features(df, shared._load_prior_runs())
    df = _candidate_scores(df)
    records, flags = _records(df)
    cohorts = sorted(flags["current_live"])
    summaries = {
        name: {cohort: metrics._summary(flags[name][cohort]) for cohort in cohorts}
        for name in MODEL_NAMES
    }
    paired = {
        name: {
            cohort: metrics._paired(flags[name][cohort], flags["current_live"][cohort])
            for cohort in cohorts if flags[name][cohort]
        }
        for name in MODEL_NAMES if name != "current_live"
    }
    stage4 = {
        name: evaluate_stage4_candidate(records, name, leakage_audit_passed=True)
        for name in MODEL_NAMES if name != "current_live"
    }
    report = {
        "contract": {
            "eligible_candidate": "trip_half",
            "diagnostic_only": ["fit_half", "both_half", "draw70"],
            "scope": "ST_TURF standard runners only; HV/ST_AWT/debut exact no-op",
            "rows": int(len(df)),
            "races": int(df["race_key"].nunique()),
            "meetings": int(df["meeting"].nunique()),
            "date_min": str(df["date"].min()),
            "date_max": str(df["date"].max()),
        },
        "summaries": summaries,
        "paired_vs_current_live": paired,
        "stage4": stage4,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
