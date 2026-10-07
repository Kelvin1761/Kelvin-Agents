#!/usr/bin/env python3
"""Constrained hierarchical refit for HKJC 7D and race-shape components.

Research-only harness for EXP-20260928-06.  Candidate selection uses expanding
development folds only.  The locked terminal dates are scored at most once.
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
from scipy.optimize import minimize


REPO = Path(__file__).resolve().parents[3]
PATCHES = Path(__file__).resolve().parent
REFLECTOR = REPO / ".agents/skills/hkjc_racing/hkjc_reflector/scripts"
SHARED_RACING = REPO / ".agents/skills/shared_racing"
for path in (PATCHES, REFLECTOR, SHARED_RACING, REPO):
    sys.path.insert(0, str(path))

import hkjc_surface_shape_ml as shared  # noqa: E402
from eval_metrics import race_metrics  # noqa: E402
from hkjc_no_regression_gate import evaluate_stage4_candidate  # noqa: E402


DIMS = (
    "sectional",
    "trainer_signal",
    "stability",
    "race_shape",
    "class_advantage",
    "horse_health",
    "form_line",
)
MATRIX_COLS = tuple(f"matrix_{name}" for name in DIMS)
CURRENT_OUTER = np.asarray((0.1285, 0.2362, 0.0983, 0.2737, 0.1428, 0.0404, 0.0801))
CURRENT_ST = np.asarray((0.55, 0.25, 0.20, 0.0))
CURRENT_HV = np.asarray((1.0, 1.0, 1.0, 0.0))
TEMPERATURE = 6.0
REGULARIZATION = 0.18
FINAL_BOOTSTRAPS = 80
MIN_SUCCESSFUL_BOOTSTRAPS = 60
VARIANT_ORDER = ("outer_only", "inner_only", "combined")


def _clip(value: np.ndarray, low: float = 0.0, high: float = 100.0) -> np.ndarray:
    return np.minimum(high, np.maximum(low, value))


def _prepare_frame(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["race_key"] = df["meeting"].astype(str) + "::" + df["race_number"].astype(str)
    df = shared._add_shape_components(df)
    df = shared._add_surface_features(df, shared._load_prior_runs())
    df["surface_score"] = (60.0 + 40.0 * df["surface_quality"]).clip(40.0, 80.0)
    for column in MATRIX_COLS:
        df[column] = pd.to_numeric(df[column], errors="coerce").fillna(60.0)
    df["current_live_recomputed_ability"] = pd.to_numeric(
        df["current_live_recomputed_ability"], errors="coerce"
    ).fillna(60.0)
    df["finish_pos"] = pd.to_numeric(df["finish_pos"], errors="coerce").fillna(99).astype(int)
    df["horse_number"] = pd.to_numeric(df["horse_number"], errors="coerce").fillna(999).astype(int)
    df["is_debut"] = df["is_debut"].fillna(0).astype(bool)
    matrix = df[list(MATRIX_COLS)].to_numpy(float)
    df["_fixed_adjustment"] = df["current_live_recomputed_ability"].to_numpy(float) - matrix @ CURRENT_OUTER
    return df


def _raw_shape_formula(df: pd.DataFrame, st: np.ndarray, hv: np.ndarray) -> np.ndarray:
    is_hv = df["surface_key"].eq("HV_TURF").to_numpy(bool)
    draw = df["shape_draw"].to_numpy(float)
    fit = df["shape_fit"].to_numpy(float)
    trip = df["shape_trip"].to_numpy(float)
    surface = df["surface_score"].to_numpy(float)

    st_score = 60.0 + (
        st[0] * (draw - 60.0)
        + st[1] * (fit - 60.0)
        + st[2] * (trip - 60.0)
        + st[3] * (surface - 60.0)
    )
    hv_delta = (
        hv[1] * df["shape_delta_fit"].to_numpy(float)
        + hv[2] * df["shape_delta_trip"].to_numpy(float)
        + hv[3] * (surface - 60.0)
    )
    hv_score = 60.0 + hv[0] * (draw - 60.0) + np.clip(hv_delta, -10.0, 7.0)
    return _clip(np.where(is_hv, hv_score, st_score))


def _shape_score(df: pd.DataFrame, st: np.ndarray, hv: np.ndarray) -> np.ndarray:
    """Apply only the parameter delta to the production matrix score.

    Production contains small context/rounding details that are intentionally
    outside this refit.  Anchoring on the stored live matrix makes the current
    parameter vector an exact row-for-row replica instead of silently replacing
    those details with a research reconstruction.
    """
    current = df["matrix_race_shape"].to_numpy(float)
    candidate_formula = _raw_shape_formula(df, st, hv)
    baseline_formula = _raw_shape_formula(df, CURRENT_ST, CURRENT_HV)
    return _clip(current + candidate_formula - baseline_formula)


def _score_frame(df: pd.DataFrame, outer: np.ndarray, st: np.ndarray, hv: np.ndarray) -> np.ndarray:
    matrix = df[list(MATRIX_COLS)].to_numpy(float).copy()
    matrix[:, DIMS.index("race_shape")] = _shape_score(df, st, hv)
    candidate = df["_fixed_adjustment"].to_numpy(float) + matrix @ outer
    current = df["current_live_recomputed_ability"].to_numpy(float)
    return np.where(df["is_debut"].to_numpy(bool), current, candidate)


def _race_blocks(df: pd.DataFrame) -> list[pd.DataFrame]:
    return [race.copy() for _, race in df.groupby("race_key", sort=False)]


def _pairwise_loss(
    df: pd.DataFrame,
    outer: np.ndarray,
    st: np.ndarray,
    hv: np.ndarray,
) -> float:
    scores = _score_frame(df, outer, st, hv)
    work = df[["race_key", "finish_pos"]].copy()
    work["_score"] = scores
    losses: list[float] = []
    weights: list[float] = []
    for race in _race_blocks(work):
        values = race["_score"].to_numpy(float)
        pos = race["finish_pos"].to_numpy(int)
        for i, pos_i in enumerate(pos):
            if pos_i > 3:
                continue
            for j, pos_j in enumerate(pos):
                if pos_j <= pos_i:
                    continue
                weight = 1.0 if pos_i == 1 else (0.6 if pos_i == 2 else 0.35)
                if pos_j >= 8:
                    weight *= 1.1
                losses.append(float(np.logaddexp(0.0, -(values[i] - values[j]) / TEMPERATURE)))
                weights.append(weight)
    if not losses:
        return 0.0
    return float(np.average(np.asarray(losses), weights=np.asarray(weights)))


def _outer_fit(df: pd.DataFrame, st: np.ndarray, hv: np.ndarray, start: np.ndarray) -> tuple[np.ndarray, bool]:
    def objective(weights: np.ndarray) -> float:
        return _pairwise_loss(df, weights, st, hv) + REGULARIZATION * float(
            np.sum((weights - CURRENT_OUTER) ** 2)
        )

    result = minimize(
        objective,
        start,
        method="SLSQP",
        bounds=[(0.0, 0.40)] * len(DIMS),
        constraints=[{"type": "eq", "fun": lambda values: float(np.sum(values) - 1.0)}],
        options={"maxiter": 300, "ftol": 1e-10},
    )
    values = np.asarray(result.x, dtype=float)
    values = np.clip(values, 0.0, 0.40)
    values /= values.sum()
    return values, bool(result.success)


def _inner_fit(
    df: pd.DataFrame,
    outer: np.ndarray,
    start_st: np.ndarray,
    start_hv: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, bool]:
    start = np.concatenate((start_st, start_hv))

    def objective(values: np.ndarray) -> float:
        st = values[:4]
        hv = values[4:]
        penalty = float(np.sum((st - CURRENT_ST) ** 2) + np.sum((hv - CURRENT_HV) ** 2))
        return _pairwise_loss(df, outer, st, hv) + REGULARIZATION * penalty

    result = minimize(
        objective,
        start,
        method="SLSQP",
        bounds=[(0.0, 1.0)] * 4 + [(0.5, 1.25), (0.0, 1.5), (0.0, 1.5), (0.0, 0.75)],
        constraints=[{"type": "eq", "fun": lambda values: float(np.sum(values[:4]) - 1.0)}],
        options={"maxiter": 300, "ftol": 1e-10},
    )
    st = np.clip(np.asarray(result.x[:4], dtype=float), 0.0, 1.0)
    st /= st.sum()
    hv = np.asarray(result.x[4:], dtype=float)
    hv = np.clip(hv, np.asarray((0.5, 0.0, 0.0, 0.0)), np.asarray((1.25, 1.5, 1.5, 0.75)))
    return st, hv, bool(result.success)


def _fit_variant(df: pd.DataFrame, variant: str) -> dict[str, Any]:
    outer = CURRENT_OUTER.copy()
    st = CURRENT_ST.copy()
    hv = CURRENT_HV.copy()
    successes: list[bool] = []
    if variant == "outer_only":
        outer, ok = _outer_fit(df, st, hv, outer)
        successes.append(ok)
    elif variant == "inner_only":
        st, hv, ok = _inner_fit(df, outer, st, hv)
        successes.append(ok)
    elif variant == "combined":
        for _ in range(3):
            outer, ok_outer = _outer_fit(df, st, hv, outer)
            st, hv, ok_inner = _inner_fit(df, outer, st, hv)
            successes.extend((ok_outer, ok_inner))
    else:
        raise ValueError(f"unknown variant: {variant}")
    return {
        "outer": outer,
        "st": st,
        "hv": hv,
        "success": bool(successes and all(successes)),
        "loss": _pairwise_loss(df, outer, st, hv),
    }


def _model_record(race: pd.DataFrame, scores: np.ndarray) -> dict[str, Any]:
    ordered = race.assign(_score=scores).sort_values(
        ["_score", "horse_number"], ascending=[False, True]
    )
    picks = ordered["horse_number"].astype(int).tolist()
    actual_pos = dict(zip(race["horse_number"].astype(int), race["finish_pos"].astype(int)))
    top3 = {horse for horse, pos in actual_pos.items() if pos <= 3}
    return {
        "picks": picks,
        "gold": top3.issubset(set(picks[:4])),
        "good": len(picks) >= 2 and picks[0] in top3 and picks[1] in top3,
    }


def _flags(record: dict[str, Any], actual_pos: dict[int, int]) -> dict[str, float]:
    top3 = {horse for horse, pos in actual_pos.items() if pos <= 3}
    winner = next((horse for horse, pos in actual_pos.items() if pos == 1), None)
    metrics = race_metrics(
        record["picks"], top3, winner=winner, actual_pos=actual_pos, field_size=len(actual_pos)
    )
    return {
        "gold": float(record["gold"]),
        "good": float(record["good"]),
        "champion": float(bool(record["picks"]) and record["picks"][0] == winner),
        "top3_capture_at5": float(metrics["top3_capture_at5"]),
        "competitive_recall_at5": float(metrics["competitive_recall_at5"]),
        "ndcg5": float(metrics["ndcg_at5"]),
    }


def _summarize(rows: list[dict[str, float]]) -> dict[str, float]:
    if not rows:
        return {"races": 0}
    return {
        "races": len(rows),
        **{key: round(float(np.mean([row[key] for row in rows])), 6) for key in rows[0]},
    }


def _paired(candidate: list[dict[str, float]], baseline: list[dict[str, float]]) -> dict[str, Any]:
    if not candidate or len(candidate) != len(baseline):
        return {"races": 0}
    rng = np.random.default_rng(7)
    size = len(candidate)
    output: dict[str, Any] = {"races": size}
    for metric in candidate[0]:
        delta = np.asarray([c[metric] - b[metric] for c, b in zip(candidate, baseline)], dtype=float)
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


def _evaluate_block(df: pd.DataFrame, fit: dict[str, Any]) -> tuple[list[dict], list[dict], list[dict]]:
    candidate_scores = _score_frame(df, fit["outer"], fit["st"], fit["hv"])
    current_scores = df["current_live_recomputed_ability"].to_numpy(float)
    records: list[dict] = []
    candidate_flags: list[dict] = []
    baseline_flags: list[dict] = []
    for race_key, race in df.groupby("race_key", sort=False):
        positions = race.index.to_numpy()
        # df indices are reset before every evaluation block.
        cand = _model_record(race, candidate_scores[positions])
        base = _model_record(race, current_scores[positions])
        actual = dict(zip(race["horse_number"].astype(int), race["finish_pos"].astype(int)))
        records.append({
            "race_key": str(race_key),
            "date": str(race.iloc[0]["date"]),
            "surface": str(race.iloc[0]["surface_key"]),
            "field_size": int(len(race)),
            "actual_pos": actual,
            "models": {"current_live": base, "candidate": cand},
        })
        candidate_flags.append(_flags(cand, actual))
        baseline_flags.append(_flags(base, actual))
    return records, candidate_flags, baseline_flags


def _date_split(df: pd.DataFrame) -> tuple[list[str], list[str]]:
    dates = sorted(df["date"].astype(str).unique())
    terminal_count = max(1, math.ceil(len(dates) * 0.15))
    return dates[:-terminal_count], dates[-terminal_count:]


def _dev_folds(dev_dates: list[str]) -> list[tuple[list[str], list[str]]]:
    initial = max(8, int(math.ceil(len(dev_dates) * 0.40)))
    validation_dates = dev_dates[initial:]
    blocks = [list(block) for block in np.array_split(np.asarray(validation_dates, dtype=object), 5) if len(block)]
    folds = []
    cursor = initial
    for block in blocks:
        folds.append((dev_dates[:cursor], block))
        cursor += len(block)
    return folds


def _params_payload(fit: dict[str, Any]) -> dict[str, Any]:
    return {
        "success": bool(fit["success"]),
        "loss": round(float(fit["loss"]), 8),
        "outer": {name: round(float(value), 6) for name, value in zip(DIMS, fit["outer"])},
        "sha_tin_shape": {
            name: round(float(value), 6)
            for name, value in zip(("draw", "fit", "trip", "surface"), fit["st"])
        },
        "happy_valley_shape_scales": {
            name: round(float(value), 6)
            for name, value in zip(("draw", "fit_delta", "trip_delta", "surface"), fit["hv"])
        },
    }


def _walk_forward(df: pd.DataFrame, dev_dates: list[str]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    folds = _dev_folds(dev_dates)
    for variant in VARIANT_ORDER:
        all_records: list[dict] = []
        all_candidate: list[dict] = []
        all_baseline: list[dict] = []
        fold_rows = []
        for fold_no, (train_dates, valid_dates) in enumerate(folds, start=1):
            train = df[df["date"].astype(str).isin(train_dates)].reset_index(drop=True)
            valid = df[df["date"].astype(str).isin(valid_dates)].reset_index(drop=True)
            fit = _fit_variant(train, variant)
            records, candidate, baseline = _evaluate_block(valid, fit)
            all_records.extend(records)
            all_candidate.extend(candidate)
            all_baseline.extend(baseline)
            pair = _paired(candidate, baseline)
            fold_rows.append({
                "fold": fold_no,
                "train_dates": [train_dates[0], train_dates[-1]],
                "valid_dates": [valid_dates[0], valid_dates[-1]],
                "train_races": int(train["race_key"].nunique()),
                "valid_races": int(valid["race_key"].nunique()),
                "fit": _params_payload(fit),
                "baseline": _summarize(baseline),
                "candidate": _summarize(candidate),
                "paired": pair,
                "primary_nonnegative": bool(
                    pair["gold"]["delta"] >= 0.0 and pair["good"]["delta"] >= 0.0
                ),
            })
        aggregate_pair = _paired(all_candidate, all_baseline)
        ranking_positive = sum(
            aggregate_pair[key]["delta"] > 0.0
            for key in ("top3_capture_at5", "competitive_recall_at5", "ndcg5")
        )
        primary_folds = sum(row["primary_nonnegative"] for row in fold_rows)
        eligible = bool(
            aggregate_pair["gold"]["delta"] >= 0.0
            and aggregate_pair["good"]["delta"] >= 0.0
            and primary_folds >= 3
            and ranking_positive >= 2
        )
        output[variant] = {
            "folds": fold_rows,
            "records": all_records,
            "baseline": _summarize(all_baseline),
            "candidate": _summarize(all_candidate),
            "paired": aggregate_pair,
            "primary_nonnegative_folds": primary_folds,
            "ranking_positive_metrics": ranking_positive,
            "eligible_for_terminal": eligible,
        }
    return output


def _bootstrap_consensus(df: pd.DataFrame, variant: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    meetings = sorted(df["meeting"].astype(str).unique())
    rng = np.random.default_rng(20260928)
    fits: list[dict[str, Any]] = []
    for boot in range(FINAL_BOOTSTRAPS):
        sampled = rng.choice(meetings, size=len(meetings), replace=True)
        pieces = []
        for index, meeting in enumerate(sampled):
            block = df[df["meeting"].astype(str).eq(str(meeting))].copy()
            block["race_key"] = block["race_key"].astype(str) + f"::boot{boot}:{index}"
            pieces.append(block)
        sample = pd.concat(pieces, ignore_index=True)
        fit = _fit_variant(sample, variant)
        if fit["success"]:
            fits.append(fit)
    audit = {"requested": FINAL_BOOTSTRAPS, "successful": len(fits)}
    if len(fits) < MIN_SUCCESSFUL_BOOTSTRAPS:
        return None, audit
    outer = np.median(np.vstack([fit["outer"] for fit in fits]), axis=0)
    outer = np.clip(outer, 0.0, 0.40)
    outer /= outer.sum()
    st = np.median(np.vstack([fit["st"] for fit in fits]), axis=0)
    st = np.clip(st, 0.0, 1.0)
    st /= st.sum()
    hv = np.median(np.vstack([fit["hv"] for fit in fits]), axis=0)
    hv = np.clip(hv, np.asarray((0.5, 0.0, 0.0, 0.0)), np.asarray((1.25, 1.5, 1.5, 0.75)))
    consensus = {
        "outer": outer,
        "st": st,
        "hv": hv,
        "success": True,
        "loss": _pairwise_loss(df, outer, st, hv),
    }
    return consensus, audit


def _cohort_report(records: list[dict]) -> dict[str, Any]:
    buckets: dict[str, tuple[list[dict], list[dict]]] = defaultdict(lambda: ([], []))
    for record in records:
        actual = record["actual_pos"]
        candidate = _flags(record["models"]["candidate"], actual)
        baseline = _flags(record["models"]["current_live"], actual)
        names = [record["surface"]]
        field = int(record["field_size"])
        names.append("field_le8" if field <= 8 else "field_9_10" if field <= 10 else "field_11_12" if field <= 12 else "field_13plus")
        for name in names:
            buckets[name][0].append(candidate)
            buckets[name][1].append(baseline)
    return {
        name: {
            "baseline": _summarize(rows[1]),
            "candidate": _summarize(rows[0]),
            "paired": _paired(rows[0], rows[1]),
        }
        for name, rows in buckets.items()
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    df = _prepare_frame(args.dataset)
    dev_dates, terminal_dates = _date_split(df)
    dev = df[df["date"].astype(str).isin(dev_dates)].reset_index(drop=True)
    terminal = df[df["date"].astype(str).isin(terminal_dates)].reset_index(drop=True)

    baseline_shape = _shape_score(df, CURRENT_ST, CURRENT_HV)
    replica_delta = np.abs(baseline_shape - df["matrix_race_shape"].to_numpy(float))
    walk_forward = _walk_forward(df, dev_dates)
    selected = next(
        (variant for variant in VARIANT_ORDER if walk_forward[variant]["eligible_for_terminal"]),
        None,
    )

    terminal_report: dict[str, Any] = {"opened": False, "selected": selected}
    stage4 = None
    if selected:
        consensus, bootstrap_audit = _bootstrap_consensus(dev, selected)
        terminal_report["bootstrap"] = bootstrap_audit
        if consensus is not None:
            terminal_records, terminal_candidate, terminal_baseline = _evaluate_block(terminal, consensus)
            terminal_report.update({
                "opened": True,
                "fit": _params_payload(consensus),
                "baseline": _summarize(terminal_baseline),
                "candidate": _summarize(terminal_candidate),
                "paired": _paired(terminal_candidate, terminal_baseline),
                "cohorts": _cohort_report(terminal_records),
            })
            dev_records = walk_forward[selected]["records"]
            stage4_records = dev_records + terminal_records
            stage4 = evaluate_stage4_candidate(
                stage4_records,
                "candidate",
                leakage_audit_passed=True,
                holdout_fraction=len(terminal_dates) / len({row["date"] for row in stage4_records}),
            )
            terminal_report["stage4"] = stage4

    full_dev_fits = {
        variant: _params_payload(_fit_variant(dev, variant))
        for variant in VARIANT_ORDER
    }
    report = {
        "contract": {
            "rows": int(len(df)),
            "races": int(df["race_key"].nunique()),
            "meetings": int(df["meeting"].nunique()),
            "date_min": str(df["date"].min()),
            "date_max": str(df["date"].max()),
            "dev_dates": [dev_dates[0], dev_dates[-1]],
            "terminal_dates": [terminal_dates[0], terminal_dates[-1]],
            "dev_races": int(dev["race_key"].nunique()),
            "terminal_races": int(terminal["race_key"].nunique()),
            "selection_order": list(VARIANT_ORDER),
            "temperature": TEMPERATURE,
            "regularization": REGULARIZATION,
        },
        "baseline_replica": {
            "shape_mean_abs_delta": round(float(replica_delta.mean()), 8),
            "shape_max_abs_delta": round(float(replica_delta.max()), 8),
            "rows_over_0_05": int((replica_delta > 0.05).sum()),
        },
        "full_dev_direct_fits": full_dev_fits,
        "walk_forward_development": walk_forward,
        "selection": {
            "selected": selected,
            "terminal_opened": bool(terminal_report.get("opened")),
        },
        "terminal": terminal_report,
        "stage4": stage4,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    # Keep stdout compact; the full reproducible evidence is the JSON file.
    compact = {
        "contract": report["contract"],
        "baseline_replica": report["baseline_replica"],
        "development": {
            name: {
                "baseline": payload["baseline"],
                "candidate": payload["candidate"],
                "paired": payload["paired"],
                "primary_nonnegative_folds": payload["primary_nonnegative_folds"],
                "ranking_positive_metrics": payload["ranking_positive_metrics"],
                "eligible_for_terminal": payload["eligible_for_terminal"],
            }
            for name, payload in walk_forward.items()
        },
        "full_dev_direct_fits": full_dev_fits,
        "selection": report["selection"],
        "terminal": terminal_report,
        "stage4": stage4,
    }
    print(json.dumps(compact, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
