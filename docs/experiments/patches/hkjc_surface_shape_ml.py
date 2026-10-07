#!/usr/bin/env python3
"""Point-in-time diagnostic for HKJC race-shape and horse surface aptitude.

Research only.  The script never writes production scores.  It:

* rebuilds the current horse-level archive dataset;
* recovers the live race-shape subcomponents from each pre-race Logic file;
* derives strictly prior, distance-matched performance for Sha Tin turf,
  Happy Valley turf, and Sha Tin AWT;
* compares fixed feature families with expanding-meeting pairwise logistic
  ranking; and
* compares one pooled formula with separate Sha Tin / Happy Valley fits.

No odds, current-race result, incident text, or future result enters a feature.
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
from sklearn.linear_model import LogisticRegression


REPO = Path(__file__).resolve().parents[3]
REFLECTOR = REPO / ".agents/skills/hkjc_racing/hkjc_reflector/scripts"
AUTO = REPO / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts"
for path in (REFLECTOR, AUTO, REPO):
    sys.path.insert(0, str(path))

from hkjc_results_db import get_season_results_roots  # noqa: E402
from hkjc_racing_engine.engine_core import RacingEngine  # noqa: E402


OTHER_6 = [
    "matrix_stability",
    "matrix_sectional",
    "matrix_trainer_signal",
    "matrix_horse_health",
    "matrix_form_line",
    "matrix_class_advantage",
]
MIN_TRAIN_MEETINGS = 12
MIN_TRAIN_RACES = 110
PAIRWISE_C = 0.10


def _surface_key(venue: object, track: object) -> str:
    venue_text = str(venue or "")
    track_text = str(track or "").upper()
    if "泥" in track_text or "AWT" in track_text or "ALL WEATHER" in track_text:
        return "ST_AWT"
    if "跑馬地" in venue_text or "HAPPY" in venue_text.upper():
        return "HV_TURF"
    return "ST_TURF"


def _flatten(value: object) -> str:
    if isinstance(value, list):
        return " ".join(_flatten(item) for item in value)
    if isinstance(value, dict):
        return " ".join(_flatten(item) for item in value.values())
    return str(value or "")


def _race_meta(payload: dict) -> tuple[str, int | None]:
    text = _flatten(payload.get("sectional_times") or payload.get("cumulative_times") or "")
    is_awt = any(token in text.upper() for token in ("泥地", "全天候", "AWT", "ALL WEATHER"))
    surface = _surface_key(payload.get("venue"), "AWT" if is_awt else "Turf")
    match = re.search(r"(\d{3,4})\s*米", text)
    return surface, (int(match.group(1)) if match else None)


def _horse_id(value: object) -> str:
    match = re.search(r"\(([A-Z]\d{3})\)", str(value or ""), re.I)
    return match.group(1).upper() if match else ""


def _load_prior_runs() -> dict[str, list[dict]]:
    by_horse: dict[str, list[dict]] = defaultdict(list)
    seen: set[tuple] = set()
    for root in get_season_results_roots():
        for path in sorted(root.rglob("full_day_results.json")):
            try:
                day = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(day, dict):
                continue
            for race_no, race in day.items():
                if not isinstance(race, dict):
                    continue
                date = str(race.get("racedate") or path.parent.name)[:10]
                surface, distance = _race_meta(race)
                results = race.get("results") if isinstance(race.get("results"), list) else []
                valid = []
                for runner in results:
                    try:
                        pos = int(re.match(r"\d+", str(runner.get("pos") or "")).group())
                    except (AttributeError, ValueError):
                        continue
                    horse_id = _horse_id(runner.get("horse_name"))
                    if horse_id:
                        valid.append((horse_id, pos))
                field = len(valid)
                if field < 4 or distance is None:
                    continue
                for horse_id, pos in valid:
                    key = (date, str(race_no), horse_id)
                    if key in seen:
                        continue
                    seen.add(key)
                    # 1.0 = winner, 0.0 = last; every complete field centres 0.5.
                    perf = 1.0 - (pos - 1.0) / max(field - 1.0, 1.0)
                    by_horse[horse_id].append(
                        {"date": date, "surface": surface, "distance": distance, "perf": perf}
                    )
    for rows in by_horse.values():
        rows.sort(key=lambda row: row["date"])
    return by_horse


def _weighted_quality(rows: list[dict], target_date: str) -> tuple[float, float]:
    weighted = 0.0
    total = 0.0
    target_ts = pd.Timestamp(target_date)
    for row in rows:
        age = (target_ts - pd.Timestamp(row["date"])).days
        if age <= 0 or age > 730:
            continue
        weight = 2.0 ** (-age / 365.0)
        weighted += weight * float(row["perf"])
        total += weight
    # Beta-style shrinkage toward the all-field neutral performance of 0.5.
    return ((weighted + 2.0) / (total + 4.0), total) if total else (0.5, 0.0)


def _add_surface_features(df: pd.DataFrame, history: dict[str, list[dict]]) -> pd.DataFrame:
    out = df.copy()
    values = defaultdict(list)
    for row in out.itertuples(index=False):
        target_surface = _surface_key(row.venue, row.track)
        target_distance = int(float(row.distance_num))
        target = []
        other = []
        for prior in history.get(str(row.horse_id), []):
            if prior["date"] >= str(row.date):
                continue
            if abs(int(prior["distance"]) - target_distance) > 200:
                continue
            (target if prior["surface"] == target_surface else other).append(prior)
        target_q, target_n = _weighted_quality(target, str(row.date))
        other_q, other_n = _weighted_quality(other, str(row.date))
        values["surface_quality"].append(target_q - 0.5)
        # A specialization signal needs evidence on both sides.  One-sided
        # histories are neutral instead of being treated as proof of preference.
        reliability = min(target_n / (target_n + 3.0), other_n / (other_n + 3.0)) if target_n and other_n else 0.0
        values["surface_specialism"].append((target_q - other_q) * reliability)
        values["surface_target_eff_n"].append(target_n)
        values["surface_other_eff_n"].append(other_n)
        values["surface_key"].append(target_surface)
    for key, column in values.items():
        out[key] = column
    starts = pd.to_numeric(out["same_venue_distance_starts"], errors="coerce").fillna(0.0)
    places = sum(
        pd.to_numeric(out[f"same_venue_distance_{suffix}"], errors="coerce").fillna(0.0)
        for suffix in ("wins", "seconds", "thirds")
    )
    out["same_venue_distance_eb"] = (places + 2.0) / (starts + 8.0) - 0.25
    out.loc[starts <= 0, "same_venue_distance_eb"] = 0.0
    return out


def _add_shape_components(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    fit_map: dict[tuple[str, int, int], float] = {}
    trip_map: dict[tuple[str, int, int], float] = {}
    delta_map: dict[tuple[str, int, int], float] = {}
    delta_trip_map: dict[tuple[str, int, int], float] = {}
    delta_fit_map: dict[tuple[str, int, int], float] = {}
    for (meeting, race_no), _rows in out.groupby(["meeting", "race_number"], sort=False):
        logic_path = Path(str(meeting)) / f"Race_{int(race_no)}_Logic.json"
        try:
            logic = json.loads(logic_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        context = dict(logic.get("race_analysis") or {})
        context.setdefault("race_date", Path(str(meeting)).name[:10])
        horses = logic.get("horses") if isinstance(logic.get("horses"), dict) else {}
        for horse_no, horse in horses.items():
            if not isinstance(horse, dict):
                continue
            engine = RacingEngine(horse, context)
            try:
                fit = float(engine._draw_position_fit_score()[0])
                trip = float(engine._trip_consumption_score()[0])
                delta, items = engine._race_shape_context_delta()
            except Exception:
                continue
            key = (str(meeting), int(race_no), int(horse_no))
            fit_map[key] = fit
            trip_map[key] = trip
            delta_map[key] = float(delta)
            delta_trip_map[key] = sum(
                float(item.get("delta") or 0.0)
                for item in items
                if item.get("factor") == "近仗消耗"
            )
            delta_fit_map[key] = sum(
                float(item.get("delta") or 0.0)
                for item in items
                if item.get("factor") != "近仗消耗"
            )
    keys = list(zip(out["meeting"].astype(str), out["race_number"].astype(int), out["horse_number"].astype(int)))
    out["shape_fit"] = [fit_map.get(key, 60.0) for key in keys]
    out["shape_trip"] = [trip_map.get(key, 60.0) for key in keys]
    out["shape_delta"] = [delta_map.get(key, 0.0) for key in keys]
    out["shape_delta_trip"] = [delta_trip_map.get(key, 0.0) for key in keys]
    out["shape_delta_fit"] = [delta_fit_map.get(key, 0.0) for key in keys]
    out["shape_draw"] = pd.to_numeric(out["feat_draw_score"], errors="coerce").fillna(60.0)
    return out


def _race_rel(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    blocks = []
    for _, race in df.groupby("race_key", sort=False):
        block = race.copy()
        for column in columns:
            value = pd.to_numeric(block[column], errors="coerce").fillna(0.0)
            sd = float(value.std(ddof=0))
            block[column] = (value - float(value.mean())) / sd if sd > 1e-9 else 0.0
        blocks.append(block)
    return pd.concat(blocks, ignore_index=True)


def _pairwise(df: pd.DataFrame, columns: list[str]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    X: list[np.ndarray] = []
    y: list[int] = []
    weights: list[float] = []
    for _, race in df.groupby("race_key", sort=False):
        race = race.sort_values("finish_pos")
        matrix = race[columns].to_numpy(float)
        pos = race["finish_pos"].to_numpy(int)
        for i in range(len(race)):
            for j in range(i + 1, len(race)):
                if pos[i] == pos[j]:
                    continue
                diff = matrix[i] - matrix[j]
                weight = 2.0 if pos[i] == 1 else (1.5 if pos[i] <= 3 else 1.0)
                X.extend((diff, -diff))
                y.extend((1, 0))
                weights.extend((weight, weight))
    return np.asarray(X), np.asarray(y), np.asarray(weights)


def _fit(df: pd.DataFrame, columns: list[str]) -> LogisticRegression | None:
    X, y, weights = _pairwise(df, columns)
    if len(y) == 0:
        return None
    model = LogisticRegression(C=PAIRWISE_C, fit_intercept=False, max_iter=1500, solver="lbfgs")
    model.fit(X, y, sample_weight=weights)
    return model


def _race_flags(race: pd.DataFrame, score_column: str) -> dict[str, float]:
    ordered = race.sort_values([score_column, "horse_number"], ascending=[False, True])
    picks = ordered.head(5)
    top3 = set(race.loc[race.finish_pos <= 3, "horse_number"].astype(int))
    winner = set(race.loc[race.finish_pos == race.finish_pos.min(), "horse_number"].astype(int))
    order = picks.horse_number.astype(int).tolist()
    gains = [1.0 if horse in top3 else 0.0 for horse in order]
    dcg = sum(gain / math.log2(index + 2) for index, gain in enumerate(gains))
    ideal = sum(1.0 / math.log2(index + 2) for index in range(min(3, len(race))))
    return {
        "gold": float(top3.issubset(set(order[:4]))),
        "good": float(len(order) >= 2 and order[0] in top3 and order[1] in top3),
        "champion": float(bool(order) and order[0] in winner),
        "ndcg5": dcg / ideal if ideal else 0.0,
    }


def _summarize(flags: list[dict[str, float]]) -> dict[str, float]:
    if not flags:
        return {"races": 0}
    return {"races": len(flags), **{key: round(float(np.mean([row[key] for row in flags])), 6) for key in ("gold", "good", "champion", "ndcg5")}}


def _paired_delta(candidate: list[dict[str, float]], baseline: list[dict[str, float]]) -> dict:
    if len(candidate) != len(baseline) or not candidate:
        return {"races": 0}
    rng = np.random.default_rng(7)
    size = len(candidate)
    output = {"races": size}
    for metric in ("gold", "good", "champion", "ndcg5"):
        delta = np.asarray([c[metric] - b[metric] for c, b in zip(candidate, baseline)], dtype=float)
        draws = np.empty(2000, dtype=float)
        for index in range(2000):
            sample = rng.integers(0, size, size=size)
            draws[index] = float(delta[sample].mean())
        output[metric] = {
            "delta": round(float(delta.mean()), 6),
            "ci95": [round(float(np.quantile(draws, 0.025)), 6), round(float(np.quantile(draws, 0.975)), 6)],
        }
    return output


def _walk_forward(df: pd.DataFrame, feature_sets: dict[str, list[str]]) -> dict:
    all_columns = sorted({column for columns in feature_sets.values() for column in columns})
    prepared = _race_rel(df, all_columns)
    meetings = []
    for meeting, rows in prepared.groupby("meeting", sort=False):
        meetings.append((str(rows.iloc[0].date), str(meeting), rows))
    meetings.sort()
    history: list[pd.DataFrame] = []
    flags: dict[str, list[dict[str, float]]] = defaultdict(list)
    coefficients: dict[str, list[dict]] = defaultdict(list)
    venue_flags: dict[str, dict[str, list[dict[str, float]]]] = defaultdict(lambda: defaultdict(list))
    for index, (date, meeting, eval_rows) in enumerate(meetings):
        train = pd.concat(history, ignore_index=True) if history else pd.DataFrame()
        train_races = int(train.race_key.nunique()) if not train.empty else 0
        if index >= MIN_TRAIN_MEETINGS and train_races >= MIN_TRAIN_RACES:
            live = eval_rows.copy()
            live["_score"] = pd.to_numeric(live["current_live_recomputed_ability"], errors="coerce").fillna(0.0)
            for _, race in live.groupby("race_key", sort=False):
                row = _race_flags(race, "_score")
                flags["current_live"].append(row)
                venue_flags["current_live"][str(race.iloc[0].surface_key)].append(row)
            for name, columns in feature_sets.items():
                model = _fit(train, columns)
                if model is None:
                    continue
                scored = eval_rows.copy()
                scored["_score"] = model.predict_proba(scored[columns].to_numpy(float))[:, 1]
                coefficients[name].append({"date": date, **{column: float(weight) for column, weight in zip(columns, model.coef_[0])}})
                for _, race in scored.groupby("race_key", sort=False):
                    row = _race_flags(race, "_score")
                    flags[name].append(row)
                    venue_flags[name][str(race.iloc[0].surface_key)].append(row)
        history.append(eval_rows)
    comparisons = {}
    for candidate, baseline in (
        ("base6_draw", "base6"),
        ("base6_draw_fit", "base6_draw"),
        ("base6_draw_trip", "base6_draw"),
        ("base6_surface_quality", "base6"),
        ("base6_surface_specialism", "base6"),
        ("base6_same_venue_distance", "base6"),
        ("base6_shape_surface", "base6"),
        ("base6_shape_surface", "current_live"),
    ):
        comparisons[f"{candidate}__vs__{baseline}"] = _paired_delta(flags[candidate], flags[baseline])
    return {
        "overall": {name: _summarize(rows) for name, rows in flags.items()},
        "by_surface": {name: {surface: _summarize(rows) for surface, rows in surfaces.items()} for name, surfaces in venue_flags.items()},
        "coefficient_medians": {
            name: {column: round(float(np.median([row[column] for row in rows])), 6) for column in feature_sets[name]}
            for name, rows in coefficients.items() if rows
        },
        "coefficient_sign_stability": {
            name: {column: round(float(np.mean([row[column] > 0 for row in rows])), 4) for column in feature_sets[name]}
            for name, rows in coefficients.items() if rows
        },
        "folds": {name: len(rows) for name, rows in coefficients.items()},
        "paired_bootstrap": comparisons,
    }


def _separate_venue_test(df: pd.DataFrame, columns: list[str]) -> dict:
    turf = df[df.surface_key.isin(["ST_TURF", "HV_TURF"])].copy()
    prepared = _race_rel(turf, columns)
    meetings = []
    for meeting, rows in prepared.groupby("meeting", sort=False):
        meetings.append((str(rows.iloc[0].date), str(meeting), rows))
    meetings.sort()
    history: list[pd.DataFrame] = []
    pooled_flags: list[dict[str, float]] = []
    split_flags: list[dict[str, float]] = []
    split_by_surface: dict[str, list[dict[str, float]]] = defaultdict(list)
    coeffs: dict[str, list[np.ndarray]] = defaultdict(list)
    for index, (_date, _meeting, eval_rows) in enumerate(meetings):
        train = pd.concat(history, ignore_index=True) if history else pd.DataFrame()
        if index >= MIN_TRAIN_MEETINGS and int(train.race_key.nunique()) >= MIN_TRAIN_RACES:
            pooled = _fit(train, columns)
            surface = str(eval_rows.iloc[0].surface_key)
            venue_train = train[train.surface_key == surface]
            split = _fit(venue_train, columns) if venue_train.race_key.nunique() >= 45 else None
            if pooled is not None and split is not None:
                pooled_eval = eval_rows.copy()
                split_eval = eval_rows.copy()
                pooled_eval["_score"] = pooled.predict_proba(pooled_eval[columns].to_numpy(float))[:, 1]
                split_eval["_score"] = split.predict_proba(split_eval[columns].to_numpy(float))[:, 1]
                coeffs[f"{surface}_split"].append(split.coef_[0])
                coeffs["pooled"].append(pooled.coef_[0])
                for key, race in pooled_eval.groupby("race_key", sort=False):
                    pooled_flags.append(_race_flags(race, "_score"))
                    split_race = split_eval[split_eval.race_key == key]
                    row = _race_flags(split_race, "_score")
                    split_flags.append(row)
                    split_by_surface[surface].append(row)
        history.append(eval_rows)
    return {
        "pooled": _summarize(pooled_flags),
        "separate": _summarize(split_flags),
        "separate_vs_pooled": _paired_delta(split_flags, pooled_flags),
        "separate_by_surface": {key: _summarize(rows) for key, rows in split_by_surface.items()},
        "median_coefficients": {
            key: {column: round(float(value), 6) for column, value in zip(columns, np.median(np.vstack(rows), axis=0))}
            for key, rows in coeffs.items() if rows
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    df = pd.read_csv(args.dataset)
    df["race_key"] = df.meeting.astype(str) + "::" + df.race_number.astype(str)
    df = _add_shape_components(df)
    history = _load_prior_runs()
    df = _add_surface_features(df, history)

    feature_sets = {
        "base6": OTHER_6,
        "base6_draw": OTHER_6 + ["shape_draw"],
        "base6_draw_fit": OTHER_6 + ["shape_draw", "shape_fit"],
        "base6_draw_trip": OTHER_6 + ["shape_draw", "shape_trip"],
        "base6_shape_parts": OTHER_6 + ["shape_draw", "shape_fit", "shape_trip"],
        "base6_live_shape": OTHER_6 + ["matrix_race_shape"],
        "base6_surface_quality": OTHER_6 + ["surface_quality"],
        "base6_surface_specialism": OTHER_6 + ["surface_specialism"],
        "base6_same_venue_distance": OTHER_6 + ["same_venue_distance_eb"],
        "base6_shape_surface": OTHER_6 + ["shape_draw", "shape_fit", "shape_trip", "surface_quality", "surface_specialism"],
    }
    wf = _walk_forward(df, feature_sets)
    separate = _separate_venue_test(df, OTHER_6 + ["shape_draw", "shape_fit", "shape_trip", "surface_quality", "surface_specialism"])
    report = {
        "contract": {
            "rows": int(len(df)),
            "races": int(df.race_key.nunique()),
            "meetings": int(df.meeting.nunique()),
            "date_min": str(df.date.min()),
            "date_max": str(df.date.max()),
            "min_train_meetings": MIN_TRAIN_MEETINGS,
            "min_train_races": MIN_TRAIN_RACES,
            "pairwise_C": PAIRWISE_C,
            "surface_rule": "strict date<target; same horse ID; distance +/-200m; 730d max; 365d half-life; no odds",
        },
        "coverage": {
            "target_surface_history": round(float((df.surface_target_eff_n > 0).mean()), 6),
            "two_surface_history": round(float(((df.surface_target_eff_n > 0) & (df.surface_other_eff_n > 0)).mean()), 6),
            "same_venue_distance_nonzero": round(float((pd.to_numeric(df.same_venue_distance_starts, errors="coerce").fillna(0) > 0).mean()), 6),
            "surface_races": df.groupby("surface_key").race_key.nunique().astype(int).to_dict(),
        },
        "walk_forward": wf,
        "separate_venue_formula": separate,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
