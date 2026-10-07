#!/usr/bin/env python3
"""Frozen deterministic A/B for HKJC race-shape v2.

The candidate definitions and decision rules are pre-registered in
EXP-20260928-02.  This script does not edit or call the production scorer.
"""
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
from eval_metrics import race_metrics  # noqa: E402
from hkjc_no_regression_gate import evaluate_stage4_candidate  # noqa: E402


STANDARD_SHAPE_WEIGHT = 0.2737
DEBUT_SHAPE_WEIGHT = 0.20


def _clip(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def _candidate_shapes(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["surface_score"] = (60.0 + 40.0 * out["surface_quality"]).clip(40.0, 80.0)
    is_hv = out["surface_key"].eq("HV_TURF")

    st_no_trip = 0.55 * out["shape_draw"] + 0.25 * out["shape_fit"] + 0.20 * 60.0
    st_surface_trip = (
        0.55 * out["shape_draw"]
        + 0.25 * out["shape_fit"]
        + 0.20 * out["surface_score"]
    )
    st_draw_only = 0.55 * out["shape_draw"] + 0.45 * 60.0
    st_draw_surface = 0.55 * out["shape_draw"] + 0.45 * out["surface_score"]

    hv_fit_delta = out["shape_delta_fit"].clip(-10.0, 7.0)
    hv_surface_trip_delta = (
        out["shape_delta_fit"] + 0.20 * (out["surface_score"] - 60.0)
    ).clip(-10.0, 7.0)
    hv_draw_surface_delta = (0.45 * (out["surface_score"] - 60.0)).clip(-10.0, 7.0)

    out["shape_no_trip"] = np.where(
        is_hv,
        (out["shape_draw"] + hv_fit_delta).clip(0.0, 100.0),
        st_no_trip.clip(0.0, 100.0),
    )
    out["shape_surface_replaces_trip"] = np.where(
        is_hv,
        (out["shape_draw"] + hv_surface_trip_delta).clip(0.0, 100.0),
        st_surface_trip.clip(0.0, 100.0),
    )
    out["shape_draw_only"] = np.where(
        is_hv,
        out["shape_draw"].clip(0.0, 100.0),
        st_draw_only.clip(0.0, 100.0),
    )
    out["shape_draw_surface"] = np.where(
        is_hv,
        (out["shape_draw"] + hv_draw_surface_delta).clip(0.0, 100.0),
        st_draw_surface.clip(0.0, 100.0),
    )
    active_weight = np.where(out["is_debut"].astype(bool), DEBUT_SHAPE_WEIGHT, STANDARD_SHAPE_WEIGHT)
    for name in ("no_trip", "surface_replaces_trip", "draw_only", "draw_surface"):
        out[f"score_{name}"] = (
            out["current_live_recomputed_ability"]
            + active_weight * (out[f"shape_{name}"] - out["matrix_race_shape"])
        )
    out["score_current_live"] = out["current_live_recomputed_ability"]
    return out


def _model_record(race: pd.DataFrame, score_column: str) -> dict:
    ordered = race.sort_values([score_column, "horse_number"], ascending=[False, True])
    picks = ordered["horse_number"].astype(int).tolist()
    actual_pos = dict(zip(race["horse_number"].astype(int), race["finish_pos"].astype(int)))
    top3 = {horse for horse, pos in actual_pos.items() if pos <= 3}
    return {
        "picks": picks,
        "gold": top3.issubset(set(picks[:4])),
        "good": len(picks) >= 2 and picks[0] in top3 and picks[1] in top3,
    }


def _ranking_flags(record: dict, actual_pos: dict[int, int]) -> dict[str, float]:
    top3 = {horse for horse, pos in actual_pos.items() if pos <= 3}
    winner = next((horse for horse, pos in actual_pos.items() if pos == 1), None)
    metrics = race_metrics(
        record["picks"],
        top3,
        winner=winner,
        actual_pos=actual_pos,
        field_size=len(actual_pos),
    )
    return {
        "gold": float(record["gold"]),
        "good": float(record["good"]),
        "champion": float(bool(record["picks"]) and record["picks"][0] == winner),
        "top3_capture_at5": float(metrics["top3_capture_at5"]),
        "competitive_recall_at5": float(metrics["competitive_recall_at5"]),
        "ndcg5": float(metrics["ndcg_at5"]),
    }


def _summary(rows: list[dict[str, float]]) -> dict[str, float]:
    if not rows:
        return {"races": 0}
    return {
        "races": len(rows),
        **{
            key: round(float(np.mean([row[key] for row in rows])), 6)
            for key in rows[0]
        },
    }


def _paired(candidate: list[dict[str, float]], baseline: list[dict[str, float]]) -> dict:
    rng = np.random.default_rng(7)
    size = len(candidate)
    output: dict[str, object] = {"races": size}
    for metric in candidate[0]:
        delta = np.asarray([c[metric] - b[metric] for c, b in zip(candidate, baseline)])
        draws = np.asarray([
            delta[rng.integers(0, size, size=size)].mean()
            for _ in range(2000)
        ])
        output[metric] = {
            "delta": round(float(delta.mean()), 6),
            "ci95": [
                round(float(np.quantile(draws, 0.025)), 6),
                round(float(np.quantile(draws, 0.975)), 6),
            ],
        }
    return output


def _records(df: pd.DataFrame) -> tuple[list[dict], dict[str, dict[str, list[dict[str, float]]]]]:
    records = []
    flags = defaultdict(lambda: defaultdict(list))
    model_names = ("current_live", "no_trip", "surface_replaces_trip", "draw_only", "draw_surface")
    unique_dates = sorted(df["date"].astype(str).unique())
    terminal_count = max(1, math.ceil(len(unique_dates) * 0.15))
    terminal_dates = set(unique_dates[-terminal_count:])
    for (_meeting, _race_no), race in df.groupby(["meeting", "race_number"], sort=False):
        date = str(race.iloc[0]["date"])
        surface = str(race.iloc[0]["surface_key"])
        actual_pos = dict(zip(race["horse_number"].astype(int), race["finish_pos"].astype(int)))
        models = {name: _model_record(race, f"score_{name}") for name in model_names}
        records.append({"date": date, "actual_pos": actual_pos, "models": models})
        split = "terminal" if date in terminal_dates else "development"
        for name, model in models.items():
            row = _ranking_flags(model, actual_pos)
            flags[name]["all"].append(row)
            flags[name][split].append(row)
            flags[name][surface].append(row)
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
    df = _candidate_shapes(df)
    records, flags = _records(df)

    model_names = ("current_live", "no_trip", "surface_replaces_trip", "draw_only", "draw_surface")
    cohorts = ("all", "development", "terminal", "ST_TURF", "HV_TURF", "ST_AWT")
    summaries = {
        name: {cohort: _summary(flags[name][cohort]) for cohort in cohorts}
        for name in model_names
    }
    paired = {
        name: {
            cohort: _paired(flags[name][cohort], flags["current_live"][cohort])
            for cohort in cohorts if flags[name][cohort]
        }
        for name in model_names if name != "current_live"
    }
    stage4 = {
        name: evaluate_stage4_candidate(
            records,
            name,
            leakage_audit_passed=True,
        )
        for name in model_names if name != "current_live"
    }
    report = {
        "contract": {
            "rows": int(len(df)),
            "races": int(df["race_key"].nunique()),
            "meetings": int(df["meeting"].nunique()),
            "date_min": str(df["date"].min()),
            "date_max": str(df["date"].max()),
            "eligible_candidate": "surface_replaces_trip",
            "diagnostic_only": ["no_trip", "draw_only", "draw_surface"],
            "surface_rule": "strict PIT; same surface; distance +/-200m; 730d; half-life 365d; 4 neutral pseudo-runs",
            "outer_shape_weight": {"standard": STANDARD_SHAPE_WEIGHT, "debut": DEBUT_SHAPE_WEIGHT},
        },
        "surface_score_coverage": {
            "any_prior": round(float((df["surface_target_eff_n"] > 0).mean()), 6),
            "neutral": round(float((df["surface_target_eff_n"] <= 0).mean()), 6),
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
