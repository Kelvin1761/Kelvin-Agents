#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import minimize


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_reflector" / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from train_hkjc_7d_ml_weights import (  # noqa: E402
    CURRENT_MATRIX_FORMULAS,
    CURRENT_MATRIX_WEIGHTS,
    DEBUT_MATRIX_WEIGHTS,
    DEFAULT_PAIRWISE_LOSS_SHARE,
    DEFAULT_TEMPERATURE,
    DEFAULT_WINNER_LOSS_SHARE,
    SECTION_COMPONENTS,
    SECTIONS,
    TOP4_RELEVANCE,
    _softmax,
    build_dataset,
    default_meeting_roots,
    default_results_roots,
)
from review_auto_weighting import evaluate_pick_order, summarize_model_races  # noqa: E402


DEFAULT_MIN_TRAIN_RACES = 48
DEFAULT_MIN_TRAIN_MEETINGS = 8
DEFAULT_REGULARIZATION = 0.08
DEFAULT_MAXITER = 180


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Walk-forward ML test for HKJC 7D score magnitude calibration")
    parser.add_argument("--json", action="store_true", help="Emit JSON only")
    parser.add_argument("--maxiter", type=int, default=DEFAULT_MAXITER)
    parser.add_argument("--min-train-races", type=int, default=DEFAULT_MIN_TRAIN_RACES)
    parser.add_argument("--min-train-meetings", type=int, default=DEFAULT_MIN_TRAIN_MEETINGS)
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument("--winner-loss-share", type=float, default=DEFAULT_WINNER_LOSS_SHARE)
    parser.add_argument("--pairwise-loss-share", type=float, default=DEFAULT_PAIRWISE_LOSS_SHARE)
    parser.add_argument("--regularization", type=float, default=DEFAULT_REGULARIZATION)
    return parser.parse_args()


def _current_inner_weights() -> dict[str, np.ndarray]:
    return {
        section: np.array([weight for _feature, weight in CURRENT_MATRIX_FORMULAS[section]], dtype=float)
        for section in SECTIONS
    }


def _initial_params() -> np.ndarray:
    scales = np.ones(len(SECTIONS), dtype=float)
    biases = np.zeros(len(SECTIONS), dtype=float)
    return np.concatenate([scales, biases])


def _unpack_params(params: np.ndarray) -> tuple[dict[str, float], dict[str, float]]:
    scales_raw = params[: len(SECTIONS)]
    biases_raw = params[len(SECTIONS):]
    scales = {section: float(scales_raw[idx]) for idx, section in enumerate(SECTIONS)}
    biases = {section: float(biases_raw[idx]) for idx, section in enumerate(SECTIONS)}
    return scales, biases


def _bounds() -> list[tuple[float, float]]:
    return [(0.65, 1.45)] * len(SECTIONS) + [(-6.0, 6.0)] * len(SECTIONS)


def _matrix_scores(race: dict[str, Any], inner_weights: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    scores: dict[str, np.ndarray] = {}
    for section in SECTIONS:
        section_array = race["section_arrays"][section]
        weights = inner_weights.get(section)
        if weights is None:
            weights = np.array([1.0], dtype=float)
        scores[section] = section_array @ weights
    return scores


def _score_race(
    race: dict[str, Any],
    *,
    scales: dict[str, float] | None = None,
    biases: dict[str, float] | None = None,
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    scales = scales or {section: 1.0 for section in SECTIONS}
    biases = biases or {section: 0.0 for section in SECTIONS}
    matrix = _matrix_scores(race, _current_inner_weights())
    calibrated: dict[str, np.ndarray] = {}
    for section in SECTIONS:
        raw = matrix[section]
        calibrated[section] = np.clip(60.0 + float(scales[section]) * (raw - 60.0) + float(biases[section]), 0.0, 100.0)

    ability = np.zeros(len(race["horse_nums"]), dtype=float)
    for section in SECTIONS:
        ability += calibrated[section] * float(CURRENT_MATRIX_WEIGHTS[section])

    is_debut = race.get("is_debut")
    if isinstance(is_debut, np.ndarray) and bool(np.any(is_debut)):
        debut_ability = np.zeros(len(race["horse_nums"]), dtype=float)
        for section, weight in DEBUT_MATRIX_WEIGHTS.items():
            debut_ability += calibrated[section] * float(weight)
        ability = np.where(is_debut, debut_ability, ability)
    return ability, calibrated


def _pairwise_race_loss(ability: np.ndarray, positions: np.ndarray, temperature: float) -> float:
    total = 0.0
    count = 0
    for i in range(len(ability)):
        for j in range(len(ability)):
            if positions[i] >= positions[j]:
                continue
            margin = (ability[i] - ability[j]) / temperature
            total += math.log1p(math.exp(-float(margin)))
            count += 1
    return total / count if count else 0.0


def _loss(
    params: np.ndarray,
    races: list[dict[str, Any]],
    *,
    temperature: float,
    winner_loss_share: float,
    pairwise_loss_share: float,
    regularization: float,
) -> float:
    scales, biases = _unpack_params(params)
    eps = 1e-12
    top4_loss_share = max(0.0, 1.0 - winner_loss_share - pairwise_loss_share)
    total = 0.0
    for race in races:
        ability, _matrix = _score_race(race, scales=scales, biases=biases)
        probs = _softmax((ability - float(np.mean(ability))) / temperature)
        positions = race["positions"]
        target = np.array([TOP4_RELEVANCE.get(int(pos), 0.0) for pos in positions], dtype=float)
        if float(target.sum()) <= 0:
            target[int(np.argmin(positions))] = 1.0
        else:
            target = target / float(target.sum())
        winner_loss = -math.log(float(probs[int(np.argmin(positions))]) + eps)
        top4_loss = -float(np.dot(target, np.log(probs + eps)))
        pairwise_loss = _pairwise_race_loss(ability, positions, temperature)
        total += (
            winner_loss_share * winner_loss
            + pairwise_loss_share * pairwise_loss
            + top4_loss_share * top4_loss
        )

    scale_penalty = float(np.mean((params[: len(SECTIONS)] - 1.0) ** 2))
    bias_penalty = float(np.mean((params[len(SECTIONS):] / 6.0) ** 2))
    return total / max(len(races), 1) + regularization * (scale_penalty + bias_penalty)


def fit_calibration(
    races: list[dict[str, Any]],
    *,
    temperature: float,
    winner_loss_share: float,
    pairwise_loss_share: float,
    regularization: float,
    maxiter: int,
) -> dict[str, Any]:
    if not races:
        return {}
    def objective(params: np.ndarray) -> float:
        return _loss(
            params,
            races,
            temperature=temperature,
            winner_loss_share=winner_loss_share,
            pairwise_loss_share=pairwise_loss_share,
            regularization=regularization,
        )

    result = minimize(
        objective,
        _initial_params(),
        method="L-BFGS-B",
        bounds=_bounds(),
        options={"maxiter": maxiter},
    )
    scales, biases = _unpack_params(result.x)
    return {
        "success": bool(result.success),
        "loss": round(float(result.fun), 6),
        "iterations": int(getattr(result, "nit", 0)),
        "scales": {section: round(scales[section], 4) for section in SECTIONS},
        "biases": {section: round(biases[section], 4) for section in SECTIONS},
    }


def evaluate_races(
    races: list[dict[str, Any]],
    *,
    scales: dict[str, float] | None = None,
    biases: dict[str, float] | None = None,
) -> dict[str, Any]:
    evaluated = []
    for race in races:
        ability, _matrix = _score_race(race, scales=scales, biases=biases)
        ranking = np.argsort(-ability)
        picks = [int(race["horse_nums"][idx]) for idx in ranking[:4]]
        evaluated.append(evaluate_pick_order(picks, race["actual_pos"]))
    return summarize_model_races(evaluated)


def _meeting_count(races: list[dict[str, Any]]) -> int:
    return len({race["meeting"] for race in races})


def _scope_filter(races: list[dict[str, Any]], scope: str) -> list[dict[str, Any]]:
    if scope == "all":
        return races
    if scope == "happy_valley":
        return [race for race in races if "happyvalley" in str(race["meeting"]).lower() or "跑馬地" in str(race["venue"])]
    if scope == "sha_tin":
        return [race for race in races if "shatin" in str(race["meeting"]).lower() or "沙田" in str(race["venue"])]
    return []


def walk_forward(
    races: list[dict[str, Any]],
    *,
    min_train_races: int,
    min_train_meetings: int,
    temperature: float,
    winner_loss_share: float,
    pairwise_loss_share: float,
    regularization: float,
    maxiter: int,
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for race in races:
        grouped[race["meeting"]].append(race)
    ordered = sorted(grouped.items(), key=lambda item: (item[1][0]["date"] or "", item[0]))

    history: list[dict[str, Any]] = []
    baseline_rows: list[dict[str, Any]] = []
    calibrated_rows: list[dict[str, Any]] = []
    fold_rows: list[dict[str, Any]] = []

    for meeting_name, meeting_races in ordered:
        if _meeting_count(history) < min_train_meetings or len(history) < min_train_races:
            history.extend(meeting_races)
            continue

        fit = fit_calibration(
            history,
            temperature=temperature,
            winner_loss_share=winner_loss_share,
            pairwise_loss_share=pairwise_loss_share,
            regularization=regularization,
            maxiter=maxiter,
        )
        if not fit:
            history.extend(meeting_races)
            continue
        baseline = evaluate_races(meeting_races)
        calibrated = evaluate_races(meeting_races, scales=fit["scales"], biases=fit["biases"])
        fold_rows.append(
            {
                "date": meeting_races[0]["date"],
                "meeting": meeting_name,
                "train_races": len(history),
                "eval_races": len(meeting_races),
                "baseline": baseline,
                "calibrated": calibrated,
                "fit": fit,
            }
        )
        for race in meeting_races:
            ability_base, _ = _score_race(race)
            ability_cal, _ = _score_race(race, scales=fit["scales"], biases=fit["biases"])
            base_picks = [int(race["horse_nums"][idx]) for idx in np.argsort(-ability_base)[:4]]
            cal_picks = [int(race["horse_nums"][idx]) for idx in np.argsort(-ability_cal)[:4]]
            baseline_rows.append(evaluate_pick_order(base_picks, race["actual_pos"]))
            calibrated_rows.append(evaluate_pick_order(cal_picks, race["actual_pos"]))
        history.extend(meeting_races)

    return {
        "folds": len(fold_rows),
        "baseline_summary": summarize_model_races(baseline_rows),
        "calibrated_summary": summarize_model_races(calibrated_rows),
        "fold_rows": fold_rows,
    }


def delta(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, float]:
    keys = (
        "gold",
        "good",
        "min_threshold",
        "single",
        "champion",
        "top3_has_champion",
        "order_issue",
        "avg_winner_rank",
        "mrr",
        "avg_pick1_finish",
        "avg_top4_hits",
    )
    return {key: round(float(candidate.get(key, 0)) - float(baseline.get(key, 0)), 4) for key in keys}


def run(args: argparse.Namespace) -> dict[str, Any]:
    dataset = build_dataset(default_meeting_roots(), default_results_roots())
    races = dataset["races"]
    global_fit = fit_calibration(
        races,
        temperature=args.temperature,
        winner_loss_share=args.winner_loss_share,
        pairwise_loss_share=args.pairwise_loss_share,
        regularization=args.regularization,
        maxiter=args.maxiter,
    )

    scopes: dict[str, Any] = {}
    for scope in ("all", "happy_valley", "sha_tin"):
        scope_races = _scope_filter(races, scope)
        baseline = evaluate_races(scope_races)
        calibrated = evaluate_races(scope_races, scales=global_fit.get("scales"), biases=global_fit.get("biases"))
        scopes[scope] = {
            "races": len(scope_races),
            "baseline": baseline,
            "global_calibrated_full_sample": calibrated,
            "delta_full_sample": delta(calibrated, baseline),
        }

    wf = walk_forward(
        races,
        min_train_races=args.min_train_races,
        min_train_meetings=args.min_train_meetings,
        temperature=args.temperature,
        winner_loss_share=args.winner_loss_share,
        pairwise_loss_share=args.pairwise_loss_share,
        regularization=args.regularization,
        maxiter=args.maxiter,
    )
    wf["delta"] = delta(wf["calibrated_summary"], wf["baseline_summary"])
    return {
        "coverage": dataset["coverage"],
        "contract": "score magnitude calibration only; current live outer weights; debut weighting parity enabled; no production scoring change",
        "config": {
            "maxiter": args.maxiter,
            "min_train_races": args.min_train_races,
            "min_train_meetings": args.min_train_meetings,
            "temperature": args.temperature,
            "winner_loss_share": args.winner_loss_share,
            "pairwise_loss_share": args.pairwise_loss_share,
            "regularization": args.regularization,
        },
        "global_fit_full_sample": global_fit,
        "scopes": scopes,
        "walk_forward": wf,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# HKJC 7D Score Magnitude ML Test",
        "",
        f"- Contract: {report['contract']}",
        f"- Coverage: {report['coverage']}",
        f"- Config: {report['config']}",
        "",
        "## Full Sample Calibration",
        f"- Scales: {report['global_fit_full_sample'].get('scales')}",
        f"- Biases: {report['global_fit_full_sample'].get('biases')}",
        "",
        "## Scope Summary",
    ]
    for scope, row in report["scopes"].items():
        lines.extend(
            [
                f"### {scope}",
                f"- Races: {row['races']}",
                f"- Baseline: {row['baseline']}",
                f"- Full-sample calibrated: {row['global_calibrated_full_sample']}",
                f"- Delta: {row['delta_full_sample']}",
            ]
        )
    lines.extend(
        [
            "",
            "## Walk Forward",
            f"- Folds: {report['walk_forward']['folds']}",
            f"- Baseline: {report['walk_forward']['baseline_summary']}",
            f"- Calibrated: {report['walk_forward']['calibrated_summary']}",
            f"- Delta: {report['walk_forward']['delta']}",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    report = run(args)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
