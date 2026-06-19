#!/usr/bin/env python3
"""
train_hkjc_7d_ml_weights.py — supervised fitter for HKJC 7D matrix weights.

What it does:
1. Loads archived HKJC `Race_*_Logic.json` meetings with matched historical results.
2. Recomputes the current structured feature scores for every horse.
3. Learns:
   - inner weights inside each 7D section
   - outer weights across the 7D matrix
4. Validates the learned weights with an expanding walk-forward split by meeting date.

The script is intentionally isolated from live scoring so we can validate any ML lift
before promoting the learned weights into production.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import minimize

from review_auto_weighting import (
    CURRENT_MATRIX_FORMULAS,
    CURRENT_MATRIX_WEIGHTS,
    _normalize_distance,
    _normalize_venue,
    build_results_index,
    clip_score,
    compute_full_feature_scores,
    dedup_race_key,
    default_meeting_roots,
    default_results_roots,
    evaluate_pick_order,
    hk_meeting_dirs,
    load_published_mainline_predictions,
    load_results,
    meeting_date,
    race_num_from_path,
    summarize_model_races,
    venue_from_meeting_dir,
)


SECTIONS = tuple(CURRENT_MATRIX_FORMULAS.keys())
SECTION_COMPONENTS = {
    section: tuple(feature for feature, _weight in components)
    for section, components in CURRENT_MATRIX_FORMULAS.items()
}
TRAINABLE_SECTIONS = tuple(section for section, components in SECTION_COMPONENTS.items() if len(components) > 1)

TOP4_RELEVANCE = {
    1: 1.00,
    2: 0.55,
    3: 0.30,
    4: 0.12,
}

DEBUT_MATRIX_WEIGHTS = {
    "trainer_signal": 0.30,
    "horse_health": 0.30,
    "race_shape": 0.20,
    "stability": 0.15,
    "class_advantage": 0.05,
}

DEFAULT_TEMPERATURE = 6.0
DEFAULT_WINNER_LOSS_SHARE = 0.45
DEFAULT_PAIRWISE_LOSS_SHARE = 0.35
DEFAULT_REGULARIZATION = 0.18
DEFAULT_MIN_TRAIN_RACES = 48
DEFAULT_MIN_TRAIN_MEETINGS = 8
DEFAULT_MIN_SLICE_RACES = 18
DEFAULT_MIN_SLICE_MEETINGS = 3
DEFAULT_MAXITER = 250


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train ML weights for the HKJC 7D matrix from archive results")
    parser.add_argument("--meeting-root", action="append", default=[], help="Root folder to scan for HKJC meeting dirs")
    parser.add_argument("--results-root", action="append", default=[], help="Root folder containing results json files")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of markdown")
    parser.add_argument("--min-train-races", type=int, default=DEFAULT_MIN_TRAIN_RACES)
    parser.add_argument("--min-train-meetings", type=int, default=DEFAULT_MIN_TRAIN_MEETINGS)
    parser.add_argument("--min-slice-races", type=int, default=DEFAULT_MIN_SLICE_RACES)
    parser.add_argument("--min-slice-meetings", type=int, default=DEFAULT_MIN_SLICE_MEETINGS)
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument("--winner-loss-share", type=float, default=DEFAULT_WINNER_LOSS_SHARE)
    parser.add_argument("--pairwise-loss-share", type=float, default=DEFAULT_PAIRWISE_LOSS_SHARE)
    parser.add_argument("--regularization", type=float, default=DEFAULT_REGULARIZATION)
    parser.add_argument("--maxiter", type=int, default=DEFAULT_MAXITER)
    return parser.parse_args()


def _softmax(values: np.ndarray) -> np.ndarray:
    shifted = values - np.max(values)
    exps = np.exp(shifted)
    denom = np.sum(exps)
    if not np.isfinite(denom) or denom <= 0:
        return np.full_like(values, 1.0 / len(values), dtype=float)
    return exps / denom


def _weights_to_logits(weights: list[float]) -> np.ndarray:
    arr = np.array(weights, dtype=float)
    arr = np.clip(arr, 1e-9, None)
    return np.log(arr)


def _current_inner_weights() -> dict[str, np.ndarray]:
    return {
        section: np.array([weight for _feature, weight in CURRENT_MATRIX_FORMULAS[section]], dtype=float)
        for section in TRAINABLE_SECTIONS
    }


def _current_outer_weights() -> np.ndarray:
    return np.array([CURRENT_MATRIX_WEIGHTS[section] for section in SECTIONS], dtype=float)


def _unpack_params(params: np.ndarray) -> tuple[dict[str, np.ndarray], np.ndarray]:
    offset = 0
    inner_weights: dict[str, np.ndarray] = {}
    for section in TRAINABLE_SECTIONS:
        width = len(SECTION_COMPONENTS[section])
        inner_weights[section] = _softmax(params[offset: offset + width])
        offset += width
    outer_weights = _softmax(params[offset: offset + len(SECTIONS)])
    return inner_weights, outer_weights


def _initial_params() -> np.ndarray:
    chunks: list[np.ndarray] = []
    current_inner = _current_inner_weights()
    for section in TRAINABLE_SECTIONS:
        chunks.append(_weights_to_logits(list(current_inner[section])))
    chunks.append(_weights_to_logits(list(_current_outer_weights())))
    return np.concatenate(chunks)


def _uniform_params() -> np.ndarray:
    chunks: list[np.ndarray] = []
    for section in TRAINABLE_SECTIONS:
        width = len(SECTION_COMPONENTS[section])
        chunks.append(np.zeros(width, dtype=float))
    chunks.append(np.zeros(len(SECTIONS), dtype=float))
    return np.concatenate(chunks)


def _round_weights(values: np.ndarray) -> list[float]:
    return [round(float(value), 4) for value in values]


def _formula_dict(inner_weights: dict[str, np.ndarray]) -> dict[str, list[dict[str, Any]]]:
    payload: dict[str, list[dict[str, Any]]] = {}
    for section in SECTIONS:
        learned = inner_weights.get(section)
        component_rows: list[dict[str, Any]] = []
        for idx, (feature, default_weight) in enumerate(CURRENT_MATRIX_FORMULAS[section]):
            learned_weight = float(learned[idx]) if learned is not None else float(default_weight)
            component_rows.append(
                {
                    "feature": feature,
                    "current_weight": round(float(default_weight), 4),
                    "learned_weight": round(learned_weight, 4),
                }
            )
        payload[section] = component_rows
    return payload


def _distance_token(value: object) -> str:
    text = _normalize_distance(value)
    match = re.search(r"(\d{3,4})", text)
    return match.group(1) if match else text or "unknown"


def _slice_keys(venue: str, distance: str) -> list[str]:
    return [
        f"venue_distance:{venue}:{distance}",
        f"venue:{venue}",
        "global",
    ]


def _prepare_race_payload(race: dict[str, Any]) -> dict[str, Any]:
    horse_nums = np.array([horse["horse_num"] for horse in race["horses"]], dtype=int)
    is_debut = np.array([bool(horse.get("is_debut")) for horse in race["horses"]], dtype=bool)
    section_arrays = {
        section: np.array(
            [
                [clip_score(horse["feature_scores"].get(feature, 60.0)) for feature in SECTION_COMPONENTS[section]]
                for horse in race["horses"]
            ],
            dtype=float,
        )
        for section in SECTIONS
    }
    positions = np.array([int(race["actual_pos"].get(int(horse_num), 99)) for horse_num in horse_nums], dtype=int)
    winner_idx = int(np.argmin(positions))
    target = np.array([TOP4_RELEVANCE.get(int(pos), 0.0) for pos in positions], dtype=float)
    if float(target.sum()) <= 0:
        target[winner_idx] = 1.0
    else:
        target = target / float(target.sum())
    return {
        "meeting": race["meeting"],
        "date": race["date"],
        "race": race["race"],
        "actual_pos": race["actual_pos"],
        "positions": positions,
        "horse_nums": horse_nums,
        "is_debut": is_debut,
        "section_arrays": section_arrays,
        "winner_idx": winner_idx,
        "target_distribution": target,
        "venue": race["venue"],
        "distance": race["distance"],
        "slice_keys": _slice_keys(race["venue"], race["distance"]),
    }


def _score_race(prepared_race: dict[str, Any], inner_weights: dict[str, np.ndarray], outer_weights: np.ndarray) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    matrix_scores: dict[str, np.ndarray] = {}
    for section in SECTIONS:
        section_array = prepared_race["section_arrays"][section]
        if section in inner_weights:
            weights = inner_weights[section]
        else:
            weights = np.array([1.0], dtype=float)
        matrix_scores[section] = section_array @ weights

    ability = np.zeros(len(prepared_race["horse_nums"]), dtype=float)
    for idx, section in enumerate(SECTIONS):
        ability += matrix_scores[section] * float(outer_weights[idx])
    is_debut = prepared_race.get("is_debut")
    if isinstance(is_debut, np.ndarray) and bool(np.any(is_debut)):
        debut_ability = np.zeros(len(prepared_race["horse_nums"]), dtype=float)
        for section, weight in DEBUT_MATRIX_WEIGHTS.items():
            debut_ability += matrix_scores[section] * float(weight)
        ability = np.where(is_debut, debut_ability, ability)
    return ability, matrix_scores


def _loss(
    params: np.ndarray,
    races: list[dict[str, Any]],
    temperature: float,
    winner_loss_share: float,
    pairwise_loss_share: float,
    regularization: float,
) -> float:
    inner_weights, outer_weights = _unpack_params(params)
    current_inner = _current_inner_weights()
    current_outer = _current_outer_weights()

    eps = 1e-12
    top4_loss_share = max(0.0, 1.0 - winner_loss_share - pairwise_loss_share)
    total = 0.0
    for race in races:
        ability, _matrix_scores = _score_race(race, inner_weights, outer_weights)
        probs = _softmax((ability - float(np.mean(ability))) / temperature)
        winner_loss = -math.log(float(probs[race["winner_idx"]]) + eps)
        top4_loss = -float(np.dot(race["target_distribution"], np.log(probs + eps)))
        pairwise_loss = _pairwise_race_loss(ability, race["positions"], temperature)
        total += (
            winner_loss_share * winner_loss
            + pairwise_loss_share * pairwise_loss
            + top4_loss_share * top4_loss
        )

    total /= max(len(races), 1)

    penalty = 0.0
    for section in TRAINABLE_SECTIONS:
        penalty += float(np.sum((inner_weights[section] - current_inner[section]) ** 2))
    penalty += float(np.sum((outer_weights - current_outer) ** 2))
    return total + regularization * penalty


def fit_weights(
    races: list[dict[str, Any]],
    *,
    temperature: float,
    winner_loss_share: float,
    pairwise_loss_share: float,
    regularization: float,
    maxiter: int,
) -> dict[str, Any] | None:
    if not races:
        return None

    starts = [_initial_params(), _uniform_params()]
    best_result = None
    best_params = None

    for start in starts:
        result = minimize(
            _loss,
            start,
            args=(races, temperature, winner_loss_share, pairwise_loss_share, regularization),
            method="L-BFGS-B",
            options={"maxiter": maxiter},
        )
        if best_result is None or float(result.fun) < float(best_result.fun):
            best_result = result
            best_params = result.x

    if best_result is None or best_params is None:
        return None

    inner_weights, outer_weights = _unpack_params(best_params)
    return {
        "success": bool(best_result.success),
        "message": str(best_result.message),
        "loss": round(float(best_result.fun), 6),
        "iterations": int(getattr(best_result, "nit", 0) or 0),
        "races": len(races),
        "outer_weights": {
            section: round(float(outer_weights[idx]), 4)
            for idx, section in enumerate(SECTIONS)
        },
        "inner_weights": _formula_dict(inner_weights),
    }


def evaluate_weight_set(races: list[dict[str, Any]], inner_weights: dict[str, np.ndarray], outer_weights: np.ndarray) -> dict[str, Any]:
    model_races = []
    for race in races:
        ability, _matrix_scores = _score_race(race, inner_weights, outer_weights)
        ranking = np.argsort(-ability)
        picks = [int(race["horse_nums"][idx]) for idx in ranking[:4]]
        model_races.append(evaluate_pick_order(picks, race["actual_pos"]))
    return summarize_model_races(model_races)


def evaluate_current_live(races: list[dict[str, Any]]) -> dict[str, Any]:
    inner_weights = {
        section: np.array([weight for _feature, weight in CURRENT_MATRIX_FORMULAS[section]], dtype=float)
        for section in TRAINABLE_SECTIONS
    }
    return evaluate_weight_set(races, inner_weights, _current_outer_weights())


def evaluate_published_mainline(meeting_predictions: list[dict[str, Any]]) -> dict[str, Any]:
    if not meeting_predictions:
        return {}
    return summarize_model_races(meeting_predictions)


def _pairwise_race_loss(ability: np.ndarray, positions: np.ndarray, temperature: float) -> float:
    losses: list[float] = []
    scale = max(temperature, 1.0)
    for i, pos_i in enumerate(positions):
        if pos_i > 3:
            continue
        for j, pos_j in enumerate(positions):
            if pos_j <= pos_i:
                continue
            diff = float(ability[i] - ability[j]) / scale
            logistic = math.log1p(math.exp(-diff))
            if pos_i == 1:
                weight = 1.0
            elif pos_i == 2:
                weight = 0.6
            else:
                weight = 0.35
            if pos_j >= 8:
                weight *= 1.1
            losses.append(weight * logistic)
    if not losses:
        return 0.0
    return float(sum(losses) / len(losses))


def _weights_from_fit(fit: dict[str, Any]) -> tuple[dict[str, np.ndarray], np.ndarray]:
    inner_raw = {
        section: np.array([row["learned_weight"] for row in fit["inner_weights"][section]], dtype=float)
        for section in TRAINABLE_SECTIONS
    }
    outer_raw = np.array([fit["outer_weights"][section] for section in SECTIONS], dtype=float)
    return inner_raw, outer_raw


def _meeting_count(races: list[dict[str, Any]]) -> int:
    return len({race["meeting"] for race in races})


def _build_slice_models(
    races: list[dict[str, Any]],
    *,
    temperature: float,
    winner_loss_share: float,
    pairwise_loss_share: float,
    regularization: float,
    maxiter: int,
    min_slice_races: int,
    min_slice_meetings: int,
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for race in races:
        grouped[f"venue_distance:{race['venue']}:{race['distance']}"].append(race)
        grouped[f"venue:{race['venue']}"].append(race)

    slice_models: dict[str, dict[str, Any]] = {}
    for key, subset in grouped.items():
        if len(subset) < min_slice_races or _meeting_count(subset) < min_slice_meetings:
            continue
        fit = fit_weights(
            subset,
            temperature=temperature,
            winner_loss_share=winner_loss_share,
            pairwise_loss_share=pairwise_loss_share,
            regularization=regularization,
            maxiter=maxiter,
        )
        if fit:
            fit["slice_key"] = key
            fit["meetings"] = _meeting_count(subset)
            slice_models[key] = fit
    return slice_models


def _choose_fit_for_race(
    race: dict[str, Any],
    global_fit: dict[str, Any],
    slice_models: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], str]:
    for key in race["slice_keys"]:
        if key == "global":
            break
        if key in slice_models:
            return slice_models[key], key
    return global_fit, "global"


def walk_forward_fit(
    races: list[dict[str, Any]],
    *,
    min_train_races: int,
    min_train_meetings: int,
    min_slice_races: int,
    min_slice_meetings: int,
    temperature: float,
    winner_loss_share: float,
    pairwise_loss_share: float,
    regularization: float,
    maxiter: int,
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for race in races:
        grouped[race["meeting"]].append(race)

    ordered_meetings = sorted(
        grouped.items(),
        key=lambda item: (
            item[1][0]["date"] or "",
            item[0],
        ),
    )

    history: list[dict[str, Any]] = []
    evaluated_global_races: list[dict[str, Any]] = []
    evaluated_sliced_races: list[dict[str, Any]] = []
    fold_rows: list[dict[str, Any]] = []
    outer_history: list[np.ndarray] = []
    source_counter: dict[str, int] = defaultdict(int)

    for meeting_idx, (meeting_name, meeting_races) in enumerate(ordered_meetings):
        if meeting_idx < min_train_meetings or len(history) < min_train_races:
            history.extend(meeting_races)
            continue

        fit = fit_weights(
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

        slice_models = _build_slice_models(
            history,
            temperature=temperature,
            winner_loss_share=winner_loss_share,
            pairwise_loss_share=pairwise_loss_share,
            regularization=regularization,
            maxiter=maxiter,
            min_slice_races=min_slice_races,
            min_slice_meetings=min_slice_meetings,
        )

        inner_raw, outer_raw = _weights_from_fit(fit)
        global_summary = evaluate_weight_set(meeting_races, inner_raw, outer_raw)

        per_meeting_model_races: list[dict[str, Any]] = []
        per_meeting_sources: dict[str, int] = defaultdict(int)
        for race in meeting_races:
            chosen_fit, source = _choose_fit_for_race(race, fit, slice_models)
            source_counter[source] += 1
            per_meeting_sources[source] += 1
            chosen_inner, chosen_outer = _weights_from_fit(chosen_fit)
            ability, _matrix_scores = _score_race(race, chosen_inner, chosen_outer)
            ranking = np.argsort(-ability)
            picks = [int(race["horse_nums"][idx]) for idx in ranking[:4]]
            scored = evaluate_pick_order(picks, race["actual_pos"])
            per_meeting_model_races.append(scored)
            evaluated_sliced_races.append(scored)

        sliced_summary = summarize_model_races(per_meeting_model_races)
        if global_summary:
            fold_rows.append(
                {
                    "meeting": meeting_name,
                    "date": meeting_races[0]["date"],
                    "train_races": len(history),
                    "eval_races": len(meeting_races),
                    "global_summary": global_summary,
                    "sliced_summary": sliced_summary,
                    "outer_weights": fit["outer_weights"],
                    "slice_model_count": len(slice_models),
                    "slice_sources": dict(sorted(per_meeting_sources.items())),
                }
            )
            outer_history.append(outer_raw)
            for race in meeting_races:
                ability, _matrix_scores = _score_race(race, inner_raw, outer_raw)
                ranking = np.argsort(-ability)
                picks = [int(race["horse_nums"][idx]) for idx in ranking[:4]]
                evaluated_global_races.append(evaluate_pick_order(picks, race["actual_pos"]))

        history.extend(meeting_races)

    averaged_outer = None
    if outer_history:
        averaged = np.mean(np.vstack(outer_history), axis=0)
        averaged_outer = {
            section: round(float(averaged[idx]), 4)
            for idx, section in enumerate(SECTIONS)
        }

    return {
        "folds": len(fold_rows),
        "global_summary": summarize_model_races(evaluated_global_races),
        "sliced_summary": summarize_model_races(evaluated_sliced_races),
        "fold_rows": fold_rows,
        "average_outer_weights": averaged_outer,
        "slice_source_usage": dict(sorted(source_counter.items())),
    }


def build_dataset(meeting_roots: list[Path], results_roots: list[Path]) -> dict[str, Any]:
    results_index = build_results_index(results_roots)
    meetings = hk_meeting_dirs(meeting_roots)

    coverage = {
        "meetings": 0,
        "races": 0,
        "horses": 0,
        "published_mainline_races": 0,
        "skipped_meetings": [],
        "duplicate_races_skipped": 0,
    }
    seen_race_keys: set[tuple[str | None, str, int]] = set()

    races: list[dict[str, Any]] = []
    published_predictions: list[dict[str, Any]] = []

    for meeting_dir in meetings:
        date = meeting_date(meeting_dir)
        result_path = results_index.get(date or "")
        if not result_path:
            coverage["skipped_meetings"].append(str(meeting_dir))
            continue

        actual_results = load_results(result_path)
        published_by_race = load_published_mainline_predictions(meeting_dir)
        meeting_had_race = False
        meeting_venue = venue_from_meeting_dir(meeting_dir)

        for logic_path in sorted(meeting_dir.glob("Race_*_Logic.json"), key=race_num_from_path):
            race_num = race_num_from_path(logic_path)
            actual_pos = actual_results.get(race_num)
            if not actual_pos:
                continue

            race_key = dedup_race_key(date, meeting_venue, race_num)
            if race_key in seen_race_keys:
                coverage["duplicate_races_skipped"] += 1
                continue
            seen_race_keys.add(race_key)

            logic = json.loads(logic_path.read_text(encoding="utf-8"))
            race_context = dict(logic.get("race_analysis", {}))
            race_context.setdefault("venue", meeting_venue)
            venue = _normalize_venue(race_context.get("venue") or meeting_venue)
            distance = _distance_token(race_context.get("distance"))

            horses = []
            for horse_num_text, horse in logic.get("horses", {}).items():
                try:
                    horse_num = int(horse_num_text)
                except (TypeError, ValueError):
                    continue
                features = compute_full_feature_scores(horse, race_context)
                horses.append(
                    {
                        "horse_num": horse_num,
                        "is_debut": bool(horse.get("is_debut") or horse.get("debut_runner") or horse.get("career_tag") == "DEBUT"),
                        "feature_scores": features,
                    }
                )

            if not horses:
                continue

            meeting_had_race = True
            coverage["races"] += 1
            coverage["horses"] += len(horses)
            races.append(
                {
                    "meeting": str(meeting_dir),
                    "date": date,
                    "race": race_num,
                    "actual_pos": actual_pos,
                    "venue": venue,
                    "distance": distance,
                    "horses": horses,
                }
            )

            published_picks = published_by_race.get(race_num)
            if published_picks:
                coverage["published_mainline_races"] += 1
                published_predictions.append(evaluate_pick_order(published_picks, actual_pos))

        if meeting_had_race:
            coverage["meetings"] += 1

    prepared_races = [_prepare_race_payload(race) for race in races]
    prepared_races.sort(key=lambda race: (race["date"] or "", race["meeting"], race["race"]))

    return {
        "coverage": coverage,
        "races": prepared_races,
        "published_predictions": published_predictions,
    }


def run_training(args: argparse.Namespace) -> dict[str, Any]:
    meeting_roots = [Path(path) for path in args.meeting_root] or default_meeting_roots()
    results_roots = [Path(path) for path in args.results_root] or default_results_roots()

    dataset = build_dataset(meeting_roots, results_roots)
    races = dataset["races"]

    global_fit = fit_weights(
        races,
        temperature=args.temperature,
        winner_loss_share=args.winner_loss_share,
        pairwise_loss_share=args.pairwise_loss_share,
        regularization=args.regularization,
        maxiter=args.maxiter,
    )
    global_slice_models = _build_slice_models(
        races,
        temperature=args.temperature,
        winner_loss_share=args.winner_loss_share,
        pairwise_loss_share=args.pairwise_loss_share,
        regularization=args.regularization,
        maxiter=args.maxiter,
        min_slice_races=args.min_slice_races,
        min_slice_meetings=args.min_slice_meetings,
    )

    current_live_summary = evaluate_current_live(races)
    published_summary = evaluate_published_mainline(dataset["published_predictions"])

    full_sample_summary = {}
    full_sample_sliced_summary = {}
    if global_fit:
        inner_raw, outer_raw = _weights_from_fit(global_fit)
        full_sample_summary = evaluate_weight_set(races, inner_raw, outer_raw)
        sliced_model_races = []
        for race in races:
            chosen_fit, _source = _choose_fit_for_race(race, global_fit, global_slice_models)
            chosen_inner, chosen_outer = _weights_from_fit(chosen_fit)
            ability, _matrix_scores = _score_race(race, chosen_inner, chosen_outer)
            ranking = np.argsort(-ability)
            picks = [int(race["horse_nums"][idx]) for idx in ranking[:4]]
            sliced_model_races.append(evaluate_pick_order(picks, race["actual_pos"]))
        full_sample_sliced_summary = summarize_model_races(sliced_model_races)

    walk_forward = walk_forward_fit(
        races,
        min_train_races=args.min_train_races,
        min_train_meetings=args.min_train_meetings,
        min_slice_races=args.min_slice_races,
        min_slice_meetings=args.min_slice_meetings,
        temperature=args.temperature,
        winner_loss_share=args.winner_loss_share,
        pairwise_loss_share=args.pairwise_loss_share,
        regularization=args.regularization,
        maxiter=args.maxiter,
    )

    return {
        "coverage": dataset["coverage"],
        "config": {
            "temperature": args.temperature,
            "winner_loss_share": args.winner_loss_share,
            "pairwise_loss_share": args.pairwise_loss_share,
            "regularization": args.regularization,
            "maxiter": args.maxiter,
            "min_train_races": args.min_train_races,
            "min_train_meetings": args.min_train_meetings,
            "min_slice_races": args.min_slice_races,
            "min_slice_meetings": args.min_slice_meetings,
        },
        "current_live": {
            "outer_weights": {section: round(float(CURRENT_MATRIX_WEIGHTS[section]), 4) for section in SECTIONS},
            "inner_weights": {
                section: [
                    {
                        "feature": feature,
                        "current_weight": round(float(weight), 4),
                    }
                    for feature, weight in CURRENT_MATRIX_FORMULAS[section]
                ]
                for section in SECTIONS
            },
            "summary": current_live_summary,
        },
        "published_mainline": published_summary,
        "ml_global_fit": global_fit,
        "ml_slice_models": {
            key: {
                "races": model["races"],
                "meetings": model.get("meetings", 0),
                "outer_weights": model["outer_weights"],
            }
            for key, model in sorted(global_slice_models.items())
        },
        "ml_full_sample_summary": full_sample_summary,
        "ml_full_sample_sliced_summary": full_sample_sliced_summary,
        "ml_walk_forward": walk_forward,
    }


def _summary_table_row(label: str, stats: dict[str, Any]) -> str:
    return (
        f"| {label} | {stats.get('races', 0)} | {stats.get('gold', 0)} | {stats.get('good', 0)} | "
        f"{stats.get('min_threshold', 0)} | {stats.get('single', 0)} | {stats.get('champion', 0)} | "
        f"{stats.get('top3_has_champion', 0)} | {stats.get('order_issue', 0)} | "
        f"{stats.get('avg_winner_rank', '-') } | {stats.get('mrr', '-') } | "
        f"{stats.get('avg_pick1_finish', '-') } | {stats.get('avg_top4_hits', '-') } |"
    )


def render_markdown(report: dict[str, Any]) -> str:
    coverage = report["coverage"]
    lines = [
        "# HKJC 7D ML Weight Training",
        "",
        "## Coverage",
        f"- Meetings matched: {coverage['meetings']}",
        f"- Races matched: {coverage['races']}",
        f"- Horses rescored: {coverage['horses']}",
        f"- Published mainline races available: {coverage['published_mainline_races']}",
        f"- Duplicate races skipped: {coverage['duplicate_races_skipped']}",
    ]
    if coverage["skipped_meetings"]:
        lines.append(f"- Meetings skipped without results match: {len(coverage['skipped_meetings'])}")

    config = report["config"]
    lines.extend(
        [
            "",
            "## Training Config",
            f"- Temperature: {config['temperature']}",
            f"- Winner loss share: {config['winner_loss_share']}",
            f"- Pairwise loss share: {config['pairwise_loss_share']}",
            f"- Regularization: {config['regularization']}",
            f"- Min train races: {config['min_train_races']}",
            f"- Min train meetings: {config['min_train_meetings']}",
            f"- Min slice races: {config['min_slice_races']}",
            f"- Min slice meetings: {config['min_slice_meetings']}",
            "",
            "## Scoreboard",
            "",
            "| Model | Races | Gold | Good | Min | Single | Champion | Top3 Champ | Order Issue | Avg Winner Rank | MRR | Avg Pick1 Finish | Avg Top4 Hits |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            _summary_table_row("current_live", report["current_live"]["summary"]),
        ]
    )
    if report["published_mainline"]:
        lines.append(_summary_table_row("published_mainline", report["published_mainline"]))
    if report["ml_full_sample_summary"]:
        lines.append(_summary_table_row("ml_full_sample_global_fit", report["ml_full_sample_summary"]))
    if report["ml_full_sample_sliced_summary"]:
        lines.append(_summary_table_row("ml_full_sample_sliced_fit", report["ml_full_sample_sliced_summary"]))
    if report["ml_walk_forward"]["global_summary"]:
        lines.append(_summary_table_row("ml_walk_forward_global", report["ml_walk_forward"]["global_summary"]))
    if report["ml_walk_forward"]["sliced_summary"]:
        lines.append(_summary_table_row("ml_walk_forward_sliced", report["ml_walk_forward"]["sliced_summary"]))

    global_fit = report.get("ml_global_fit")
    if global_fit:
        lines.extend(
            [
                "",
                "## Learned 7D Outer Weights",
                f"- Current: `{json.dumps(report['current_live']['outer_weights'], ensure_ascii=False, sort_keys=True)}`",
                f"- Learned: `{json.dumps(global_fit['outer_weights'], ensure_ascii=False, sort_keys=True)}`",
                f"- Optimizer: success={global_fit['success']} | iterations={global_fit['iterations']} | loss={global_fit['loss']}",
                "",
                "## Learned Section Weights",
                "",
                "| Section | Feature | Current | Learned |",
                "| --- | --- | ---: | ---: |",
            ]
        )
        for section in SECTIONS:
            for row in global_fit["inner_weights"][section]:
                lines.append(
                    f"| {section} | {row['feature']} | {row['current_weight']:.4f} | {row['learned_weight']:.4f} |"
                )

    if report["ml_slice_models"]:
        lines.extend(
            [
                "",
                "## Slice Models",
                "",
                "| Slice | Meetings | Races | Outer Weights |",
                "| --- | ---: | ---: | --- |",
            ]
        )
        for key, payload in report["ml_slice_models"].items():
            lines.append(
                f"| {key} | {payload['meetings']} | {payload['races']} | `{json.dumps(payload['outer_weights'], ensure_ascii=False, sort_keys=True)}` |"
            )

    walk_forward = report["ml_walk_forward"]
    if walk_forward["fold_rows"]:
        lines.extend(
            [
                "",
                "## Walk-Forward Folds",
                "",
                "| Date | Meeting | Train Races | Eval Races | Slice Models | Global Champ | Sliced Champ | Global MRR | Sliced MRR | Slice Usage |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
            ]
        )
        for row in walk_forward["fold_rows"]:
            global_stats = row["global_summary"] or {}
            sliced_stats = row["sliced_summary"] or {}
            lines.append(
                f"| {row['date']} | {Path(row['meeting']).name} | {row['train_races']} | {row['eval_races']} | "
                f"{row['slice_model_count']} | {global_stats.get('champion', 0)} | {sliced_stats.get('champion', 0)} | "
                f"{global_stats.get('mrr', '-') } | {sliced_stats.get('mrr', '-') } | "
                f"`{json.dumps(row['slice_sources'], ensure_ascii=False, sort_keys=True)}` |"
            )
        if walk_forward["average_outer_weights"]:
            lines.extend(
                [
                    "",
                    "## Average Walk-Forward Outer Weights",
                    f"- `{json.dumps(walk_forward['average_outer_weights'], ensure_ascii=False, sort_keys=True)}`",
                ]
            )
        if walk_forward["slice_source_usage"]:
            lines.extend(
                [
                    "",
                    "## Walk-Forward Slice Usage",
                    f"- `{json.dumps(walk_forward['slice_source_usage'], ensure_ascii=False, sort_keys=True)}`",
                ]
            )

    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    report = run_training(args)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
