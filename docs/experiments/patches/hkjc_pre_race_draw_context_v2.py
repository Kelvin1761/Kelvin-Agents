#!/usr/bin/env python3
"""Locked PIT tests for rail-aware draw context and strength/context architecture."""
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
sys.path.insert(0, str(PATCHES))

import hkjc_hierarchical_refit as base  # noqa: E402


SHRINK_RUNNERS = 60.0
MIN_RUNNERS = 100
MIN_RACES = 20
DRAW_CAP = 4.0
SHAPE_WEIGHT = 0.2737
ARCH_VARIANTS = ("core60_uncapped", "production_share_cap4", "core60_cap4")
CORE_DIMS = ("sectional", "stability", "class_advantage", "form_line")
CONTEXT_DIMS = ("trainer_signal", "race_shape", "horse_health")


def _draw_group(value: object) -> str:
    draw = int(float(value)) if pd.notna(value) else 0
    return "inner" if 0 < draw <= 4 else "middle" if draw <= 8 else "outer"


def _distance_band(value: object) -> str:
    distance = int(float(value)) if pd.notna(value) else 0
    return "sprint" if distance <= 1200 else "middle" if distance <= 1650 else "route"


def _rail_rows(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["Date"] = df["Date"].astype(str)
    df = df[df["Track"].astype(str).eq("Turf")].copy()
    df["draw_group"] = df["Draw"].map(_draw_group)
    df["distance_band"] = df["Distance"].map(_distance_band)
    df["expected"] = np.minimum(3, pd.to_numeric(df["FieldSize"], errors="coerce")) / pd.to_numeric(
        df["FieldSize"], errors="coerce"
    ).clip(lower=1)
    df["residual"] = pd.to_numeric(df["Place"], errors="coerce").fillna(0) - df["expected"]
    df["race_id"] = df["Date"] + "|" + df["Venue"].astype(str) + "|" + df["RaceNo"].astype(str)
    return df


def _effect(history: pd.DataFrame, venue: str, rail: str, band: str, group: str) -> tuple[float, bool, int, int]:
    cell = history[
        history["Venue"].astype(str).eq(venue)
        & history["Rail"].astype(str).eq(rail)
        & history["distance_band"].eq(band)
        & history["draw_group"].eq(group)
    ]
    parent = history[
        history["Venue"].astype(str).eq(venue)
        & history["distance_band"].eq(band)
        & history["draw_group"].eq(group)
    ]
    n = len(cell)
    races = cell["race_id"].nunique()
    stable = n >= MIN_RUNNERS and races >= MIN_RACES and len(parent) >= MIN_RUNNERS
    if not stable:
        return 0.0, False, n, races
    cell_excess = float(cell["residual"].sum()) / (n + SHRINK_RUNNERS)
    parent_excess = float(parent["residual"].sum()) / (len(parent) + SHRINK_RUNNERS)
    return float(np.clip(100.0 * (cell_excess - parent_excess), -DRAW_CAP, DRAW_CAP)), True, n, races


def _draw_scores(df: pd.DataFrame, rail: pd.DataFrame) -> tuple[np.ndarray, list[dict]]:
    adjustments = np.zeros(len(df), dtype=float)
    audit: list[dict] = []
    cache: dict[tuple[str, str, str, str, str], tuple[float, bool, int, int]] = {}
    for pos, row in enumerate(df.itertuples(index=False)):
        if str(row.track) != "Turf" or bool(row.is_debut):
            continue
        key = (str(row.date), str(row.venue), str(row.course), _distance_band(row.distance_num), _draw_group(row.barrier))
        if key not in cache:
            cutoff, venue, course, band, group = key
            cache[key] = _effect(rail[rail["Date"] < cutoff], venue, course, band, group)
        adjustment, stable, runners, races = cache[key]
        adjustments[pos] = adjustment
        audit.append({"key": list(key), "adjustment": adjustment, "stable": stable, "runners": runners, "races": races})
    is_hv = df["surface_key"].eq("HV_TURF").to_numpy(bool)
    shape_delta = adjustments * np.where(is_hv, 1.0, 0.55)
    scores = df["current_live_recomputed_ability"].to_numpy(float) + SHAPE_WEIGHT * shape_delta
    return scores, audit


def _architecture_scores(df: pd.DataFrame, variant: str) -> np.ndarray:
    weights = dict(zip(base.DIMS, base.CURRENT_OUTER))
    core_total = sum(weights[name] for name in CORE_DIMS)
    context_total = sum(weights[name] for name in CONTEXT_DIMS)
    core = sum(df[f"matrix_{name}"].to_numpy(float) * weights[name] for name in CORE_DIMS) / core_total
    context = sum(df[f"matrix_{name}"].to_numpy(float) * weights[name] for name in CONTEXT_DIMS) / context_total
    if variant == "core60_uncapped":
        matrix = 0.60 * core + 0.40 * context
    elif variant == "production_share_cap4":
        matrix = core + np.clip(context_total * (context - core), -4.0, 4.0)
    elif variant == "core60_cap4":
        matrix = core + np.clip(0.40 * (context - core), -4.0, 4.0)
    else:
        raise ValueError(variant)
    scores = df["_fixed_adjustment"].to_numpy(float) + matrix
    return np.where(df["is_debut"].to_numpy(bool), df["current_live_recomputed_ability"], scores)


def _evaluate(df: pd.DataFrame, scores: np.ndarray) -> tuple[list[dict], list[dict], list[dict]]:
    records, candidate, baseline = [], [], []
    score_series = pd.Series(scores, index=df.index)
    for race_key, race in df.groupby("race_key", sort=False):
        cand = base._model_record(race, score_series.loc[race.index].to_numpy(float))
        live = base._model_record(race, race["current_live_recomputed_ability"].to_numpy(float))
        actual = dict(zip(race["horse_number"].astype(int), race["finish_pos"].astype(int)))
        candidate.append(base._flags(cand, actual))
        baseline.append(base._flags(live, actual))
        records.append({"race_key": race_key, "date": str(race.iloc[0]["date"]), "surface": str(race.iloc[0]["surface_key"]), "field_size": len(race), "actual_pos": actual, "models": {"current_live": live, "candidate": cand}})
    return records, candidate, baseline


def _result(candidate: list[dict], baseline: list[dict]) -> dict:
    paired = base._paired(candidate, baseline)
    return {"baseline": base._summarize(baseline), "candidate": base._summarize(candidate), "paired": paired}


def _eligible(fold_pairs: list[dict], aggregate: dict) -> bool:
    primary_folds = sum(p["gold"]["delta"] >= 0 and p["good"]["delta"] >= 0 for p in fold_pairs)
    ranking_positive = sum(aggregate[k]["delta"] > 0 for k in ("top3_capture_at5", "competitive_recall_at5", "ndcg5"))
    return bool(aggregate["gold"]["delta"] >= 0 and aggregate["good"]["delta"] >= 0 and primary_folds >= 3 and ranking_positive >= 2)


def _run_candidate(df: pd.DataFrame, dev_dates: list[str], score_fn) -> dict:
    all_c, all_b, folds = [], [], []
    for fold_no, (_, valid_dates) in enumerate(base._dev_folds(dev_dates), 1):
        valid = df[df["date"].astype(str).isin(valid_dates)].copy()
        _, cand, live = _evaluate(valid, score_fn(valid))
        pair = base._paired(cand, live)
        folds.append({"fold": fold_no, "dates": [valid_dates[0], valid_dates[-1]], **_result(cand, live)})
        all_c.extend(cand); all_b.extend(live)
    aggregate = _result(all_c, all_b)
    aggregate["eligible_for_terminal"] = _eligible([f["paired"] for f in folds], aggregate["paired"])
    aggregate["primary_nonnegative_folds"] = sum(f["paired"]["gold"]["delta"] >= 0 and f["paired"]["good"]["delta"] >= 0 for f in folds)
    aggregate["folds"] = folds
    return aggregate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--rail-dataset", required=True)
    parser.add_argument("--experiment", choices=("draw", "architecture"), required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    df = base._prepare_frame(args.dataset)
    rail = _rail_rows(args.rail_dataset)
    dev_dates, terminal_dates = base._date_split(df)
    terminal = df[df["date"].astype(str).isin(terminal_dates)].copy()
    report = {"contract": {"rows": len(df), "races": df["race_key"].nunique(), "meetings": df["meeting"].nunique(), "date_min": str(df["date"].min()), "date_max": str(df["date"].max()), "dev_dates": [dev_dates[0], dev_dates[-1]], "terminal_dates": [terminal_dates[0], terminal_dates[-1]], "terminal_races": terminal["race_key"].nunique()}}
    if args.experiment == "draw":
        score_fn = lambda frame: _draw_scores(frame, rail)[0]
        dev = _run_candidate(df, dev_dates, score_fn)
        selected = "rail_relative_cap4" if dev["eligible_for_terminal"] else None
        report.update({"candidate": {"pit": True, "shrink_runners": SHRINK_RUNNERS, "min_runners": MIN_RUNNERS, "min_races": MIN_RACES, "draw_cap": DRAW_CAP}, "development": dev, "selection": selected})
        if selected:
            scores, audit = _draw_scores(terminal, rail)
            records, cand, live = _evaluate(terminal, scores)
            report["terminal"] = {"opened": True, **_result(cand, live), "cohorts": base._cohort_report(records), "active_runner_rows": sum(item["stable"] for item in audit), "adjustment": {"mean_abs": float(np.mean(np.abs(scores-terminal["current_live_recomputed_ability"].to_numpy(float)))), "max_abs": float(np.max(np.abs(scores-terminal["current_live_recomputed_ability"].to_numpy(float))))}}
        else:
            report["terminal"] = {"opened": False}
    else:
        development = {name: _run_candidate(df, dev_dates, lambda frame, name=name: _architecture_scores(frame, name)) for name in ARCH_VARIANTS}
        selected = next((name for name in ARCH_VARIANTS if development[name]["eligible_for_terminal"]), None)
        report.update({"candidate_order": list(ARCH_VARIANTS), "development": development, "selection": selected})
        if selected:
            scores = _architecture_scores(terminal, selected)
            records, cand, live = _evaluate(terminal, scores)
            report["terminal"] = {"opened": True, **_result(cand, live), "cohorts": base._cohort_report(records), "adjustment": {"mean_abs": float(np.mean(np.abs(scores-terminal["current_live_recomputed_ability"].to_numpy(float)))), "max_abs": float(np.max(np.abs(scores-terminal["current_live_recomputed_ability"].to_numpy(float))))}}
        else:
            report["terminal"] = {"opened": False}
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    compact = {"contract": report["contract"], "selection": report["selection"], "development": {k: {x: v[x] for x in ("baseline", "candidate", "paired", "eligible_for_terminal", "primary_nonnegative_folds")} for k, v in report["development"].items()} if args.experiment == "architecture" else {x: report["development"][x] for x in ("baseline", "candidate", "paired", "eligible_for_terminal", "primary_nonnegative_folds")}, "terminal": report["terminal"]}
    print(json.dumps(compact, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
