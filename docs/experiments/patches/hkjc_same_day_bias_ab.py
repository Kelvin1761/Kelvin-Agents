#!/usr/bin/env python3
"""Strict point-in-time A/B for intraday HKJC track bias.

For target race N, only completed races < N from the same meeting and surface
are visible.  The script is research-only and never edits production Logic.
"""
from __future__ import annotations

import argparse
import json
import math
import re
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

import hkjc_surface_shape_ml as surface_ml  # noqa: E402
from eval_metrics import race_metrics  # noqa: E402
from hkjc_no_regression_gate import evaluate_stage4_candidate  # noqa: E402
from hkjc_results_db import get_season_results_roots  # noqa: E402


STANDARD_SHAPE_WEIGHT = 0.2737
DEBUT_SHAPE_WEIGHT = 0.20
MIN_PRIOR_SAME_SURFACE_RACES = 2


def _horse_id(value: object) -> str:
    match = re.search(r"\(([A-Z]\d{3})\)", str(value or ""), re.I)
    return match.group(1).upper() if match else ""


def _first_position(value: object) -> int | None:
    match = re.search(r"\d+", str(value or ""))
    return int(match.group()) if match else None


def _load_results() -> tuple[dict[str, dict], dict[str, list[dict]]]:
    days: dict[str, dict] = {}
    history: dict[str, list[dict]] = defaultdict(list)
    for root in get_season_results_roots():
        for path in sorted(root.rglob("full_day_results.json")):
            try:
                day = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(day, dict):
                continue
            date = path.parent.name[:10]
            days[date] = day
            for race in day.values():
                if not isinstance(race, dict):
                    continue
                surface, _distance = surface_ml._race_meta(race)
                rows = race.get("results") if isinstance(race.get("results"), list) else []
                field = len(rows)
                if field < 4:
                    continue
                for row in rows:
                    horse_id = _horse_id(row.get("horse_name"))
                    early = _first_position(row.get("running_positions"))
                    if not horse_id or early is None or not 1 <= early <= field:
                        continue
                    history[horse_id].append(
                        {
                            "date": str(race.get("racedate") or date)[:10],
                            "surface": surface,
                            "early_pct": (early - 1.0) / (field - 1.0),
                        }
                    )
    for rows in history.values():
        rows.sort(key=lambda item: item["date"], reverse=True)
    return days, history


def _prior_day_bias(day: dict, target_race: int, target_surface: str) -> dict:
    positions: list[float] = []
    draws: list[float] = []
    race_count = 0
    for race_no_text, race in day.items():
        try:
            race_no = int(race_no_text)
        except (TypeError, ValueError):
            continue
        if race_no >= target_race or not isinstance(race, dict):
            continue
        surface, _distance = surface_ml._race_meta(race)
        if surface != target_surface:
            continue
        results = race.get("results") if isinstance(race.get("results"), list) else []
        field = len(results)
        if field < 4:
            continue
        usable = 0
        for row in results:
            try:
                finish = int(re.match(r"\d+", str(row.get("pos") or "")).group())
            except (AttributeError, ValueError):
                continue
            if finish > 3:
                continue
            early = _first_position(row.get("running_positions"))
            try:
                draw = int(row.get("draw") or 0)
            except (TypeError, ValueError):
                draw = 0
            if early is not None and 1 <= early <= field:
                positions.append((early - 1.0) / (field - 1.0))
                usable += 1
            if 1 <= draw <= field:
                draws.append((draw - 1.0) / (field - 1.0))
        if usable:
            race_count += 1
    return {
        "races": race_count,
        "top3_position": float(np.mean(positions)) if positions else 0.5,
        "top3_draw": float(np.mean(draws)) if draws else 0.5,
    }


def _horse_typical(history: dict[str, list[dict]], horse_id: str, target_date: str) -> tuple[float, int]:
    rows = [row for row in history.get(horse_id, []) if row["date"] < target_date][:5]
    if not rows:
        return 0.5, 0
    return float(np.mean([row["early_pct"] for row in rows])), len(rows)


def _within_race_z(df: pd.DataFrame, column: str) -> pd.Series:
    output = pd.Series(0.0, index=df.index)
    for _key, race in df.groupby("race_key", sort=False):
        values = race[column].astype(float)
        sd = float(values.std(ddof=0))
        if sd > 1e-9:
            output.loc[race.index] = (values - float(values.mean())) / sd
    return output


def _add_features(df: pd.DataFrame, days: dict[str, dict], history: dict[str, list[dict]]) -> pd.DataFrame:
    out = df.copy()
    day_cache: dict[tuple[str, int, str], dict] = {}
    position_match = []
    draw_match = []
    prior_races = []
    typical_coverage = []
    for row in out.itertuples(index=False):
        date = str(row.date)
        surface = surface_ml._surface_key(row.venue, row.track)
        cache_key = (date, int(row.race_number), surface)
        if cache_key not in day_cache:
            day_cache[cache_key] = _prior_day_bias(days.get(date, {}), int(row.race_number), surface)
        bias = day_cache[cache_key]
        typical, starts = _horse_typical(history, str(row.horse_id), date)
        reliability = min(float(bias["races"]) / 4.0, 1.0) * min(starts / 3.0, 1.0)
        enabled = int(bias["races"]) >= MIN_PRIOR_SAME_SURFACE_RACES and starts > 0
        position_match.append(
            (0.5 - typical) * (0.5 - float(bias["top3_position"])) * reliability
            if enabled else 0.0
        )
        field = max(int(row.field_size), 2)
        try:
            draw_pct = (int(row.barrier) - 1.0) / (field - 1.0)
        except (TypeError, ValueError):
            draw_pct = 0.5
        draw_match.append(
            (0.25 - abs(draw_pct - float(bias["top3_draw"]))) * min(float(bias["races"]) / 4.0, 1.0)
            if int(bias["races"]) >= MIN_PRIOR_SAME_SURFACE_RACES else 0.0
        )
        prior_races.append(int(bias["races"]))
        typical_coverage.append(starts)
    out["same_day_position_match"] = position_match
    out["same_day_draw_match"] = draw_match
    out["same_day_prior_races"] = prior_races
    out["historical_position_starts"] = typical_coverage
    out["position_z"] = _within_race_z(out, "same_day_position_match")
    out["draw_z"] = _within_race_z(out, "same_day_draw_match")
    active_weight = np.where(out["is_debut"].astype(bool), DEBUT_SHAPE_WEIGHT, STANDARD_SHAPE_WEIGHT)
    out["score_current_live"] = out["current_live_recomputed_ability"].astype(float)
    adjustments = {
        "same_day_position": np.clip(4.0 * out["position_z"], -5.0, 5.0),
        "same_day_draw": np.clip(4.0 * out["draw_z"], -5.0, 5.0),
        "both": np.clip(2.0 * out["position_z"] + 2.0 * out["draw_z"], -5.0, 5.0),
    }
    for name, adjustment in adjustments.items():
        candidate_shape = np.clip(out["matrix_race_shape"].astype(float) + adjustment, 0.0, 100.0)
        out[f"score_{name}"] = (
            out["score_current_live"]
            + active_weight * (candidate_shape - out["matrix_race_shape"].astype(float))
        )
    return out


def _model(race: pd.DataFrame, score: str) -> dict:
    ordered = race.sort_values([score, "horse_number"], ascending=[False, True])
    picks = ordered["horse_number"].astype(int).tolist()
    actual = dict(zip(race["horse_number"].astype(int), race["finish_pos"].astype(int)))
    top3 = {horse for horse, pos in actual.items() if pos <= 3}
    return {
        "picks": picks,
        "gold": top3.issubset(set(picks[:4])),
        "good": len(picks) >= 2 and picks[0] in top3 and picks[1] in top3,
    }


def _flags(model: dict, actual: dict[int, int]) -> dict[str, float]:
    top3 = {horse for horse, pos in actual.items() if pos <= 3}
    winner = next((horse for horse, pos in actual.items() if pos == 1), None)
    metric = race_metrics(model["picks"], top3, winner=winner, actual_pos=actual, field_size=len(actual))
    return {
        "gold": float(model["gold"]),
        "good": float(model["good"]),
        "champion": float(bool(model["picks"]) and model["picks"][0] == winner),
        "top3_capture_at5": float(metric["top3_capture_at5"]),
        "competitive_recall_at5": float(metric["competitive_recall_at5"]),
        "ndcg5": float(metric["ndcg_at5"]),
    }


def _summary(rows: list[dict[str, float]]) -> dict:
    if not rows:
        return {"races": 0}
    return {"races": len(rows), **{key: round(float(np.mean([r[key] for r in rows])), 6) for key in rows[0]}}


def _paired(candidate: list[dict[str, float]], baseline: list[dict[str, float]]) -> dict:
    rng = np.random.default_rng(7)
    size = len(candidate)
    output: dict[str, object] = {"races": size}
    for key in candidate[0]:
        delta = np.asarray([c[key] - b[key] for c, b in zip(candidate, baseline)], dtype=float)
        draws = np.asarray([delta[rng.integers(0, size, size=size)].mean() for _ in range(2000)])
        output[key] = {
            "delta": round(float(delta.mean()), 6),
            "ci95": [round(float(np.quantile(draws, 0.025)), 6), round(float(np.quantile(draws, 0.975)), 6)],
        }
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    df = pd.read_csv(args.dataset)
    df["race_key"] = df["meeting"].astype(str) + "::" + df["race_number"].astype(str)
    df["surface_key"] = [surface_ml._surface_key(v, t) for v, t in zip(df["venue"], df["track"])]
    days, history = _load_results()
    df = _add_features(df, days, history)

    names = ("current_live", "same_day_position", "same_day_draw", "both")
    records = []
    grouped_flags = defaultdict(lambda: defaultdict(list))
    unique_dates = sorted(df["date"].astype(str).unique())
    terminal_dates = set(unique_dates[-max(1, math.ceil(len(unique_dates) * 0.15)):])
    for (_meeting, _race_no), race in df.groupby(["meeting", "race_number"], sort=False):
        date = str(race.iloc[0]["date"])
        surface = str(race.iloc[0]["surface_key"])
        actual = dict(zip(race["horse_number"].astype(int), race["finish_pos"].astype(int)))
        models = {name: _model(race, f"score_{name}") for name in names}
        records.append({"date": date, "actual_pos": actual, "models": models})
        split = "terminal" if date in terminal_dates else "development"
        band = "R1_4" if int(race.iloc[0]["race_number"]) <= 4 else "R5_plus"
        enabled = bool((race["same_day_prior_races"] >= MIN_PRIOR_SAME_SURFACE_RACES).any())
        for name, model in models.items():
            row = _flags(model, actual)
            for cohort in ("all", split, surface, band, "enabled" if enabled else "not_enabled"):
                grouped_flags[name][cohort].append(row)

    cohorts = ("all", "development", "terminal", "ST_TURF", "HV_TURF", "ST_AWT", "R1_4", "R5_plus", "enabled", "not_enabled")
    summaries = {name: {c: _summary(grouped_flags[name][c]) for c in cohorts} for name in names}
    paired = {
        name: {c: _paired(grouped_flags[name][c], grouped_flags["current_live"][c]) for c in cohorts if grouped_flags[name][c]}
        for name in names if name != "current_live"
    }
    stage4 = {
        name: evaluate_stage4_candidate(records, name, leakage_audit_passed=True)
        for name in names if name != "current_live"
    }
    report = {
        "contract": {
            "rows": int(len(df)),
            "races": int(df["race_key"].nunique()),
            "meetings": int(df["meeting"].nunique()),
            "min_prior_same_surface_races": MIN_PRIOR_SAME_SURFACE_RACES,
            "eligible_candidate": "same_day_position",
            "diagnostic_only": ["same_day_draw", "both"],
        },
        "coverage": {
            "runner_enabled": round(float((df["same_day_prior_races"] >= MIN_PRIOR_SAME_SURFACE_RACES).mean()), 6),
            "race_enabled": round(float(df.groupby("race_key")["same_day_prior_races"].max().ge(MIN_PRIOR_SAME_SURFACE_RACES).mean()), 6),
            "historical_position": round(float((df["historical_position_starts"] > 0).mean()), 6),
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
