#!/usr/bin/env python3
"""
AU Wong Choi Auto scoring primitives.
"""

from __future__ import annotations

import re


FEATURE_KEYS = (
    "form_score",
    "trial_score",
    "sectional_score",
    "pace_map_score",
    "jockey_score",
    "trainer_score",
    "jockey_horse_fit_score",
    "class_score",
    "weight_score",
    "distance_score",
    "track_score",
    "formline_score",
    "consistency_score",
    "health_score",
    "confidence_score",
)

MATRIX_WEIGHTS = {
    "stability": 0.18,
    "sectional": 0.16,
    "race_shape": 0.12,
    "jockey_trainer": 0.16,
    "class_weight": 0.10,
    "track": 0.10,
    "form_line": 0.18,
}

# Weight floors and ceilings for dynamic adjustment
_WEIGHT_FLOOR = {"stability": 0.10}
_WEIGHT_CEILING = {"class_weight": 0.16, "track": 0.17}


def get_dynamic_matrix_weights(race_context):
    """Return context-adjusted MATRIX_WEIGHTS for a given race.

    Adjustments target the 3 main failure patterns:
    1. Stability over-trust (largest false-positive source)
       -> Reduced for large fields and wet tracks
    2. Class/Weight underestimation (systematically low)
       -> Boosted for BM handicap races
    3. Track suitability underestimation (weakest section: pairwise 0.514)
       -> Boosted for wet tracks and large fields

    Weights are renormalised to sum to 1.0 after adjustments.
    """
    weights = dict(MATRIX_WEIGHTS)

    field_summary = race_context.get("field_summary", {})
    field_count = int(field_summary.get("count", 0))
    going = str(race_context.get("going", "") or "").lower()
    race_class = str(race_context.get("race_class", "") or "").lower()

    # ── 1. Field-size: reduce stability, shift to class_weight + track ──
    # Field 13+ is 0% Gold / 22% Minimum in current baseline
    if field_count >= 13:
        weights["stability"] -= 0.03
        weights["class_weight"] += 0.015
        weights["track"] += 0.015
    elif field_count >= 11:
        weights["stability"] -= 0.015
        weights["class_weight"] += 0.01
        weights["track"] += 0.005

    # ── 2. Wet track: reduce stability, boost track ──
    # Soft track is 0% Gold in current baseline
    if "soft" in going or "heavy" in going:
        weights["stability"] -= 0.02
        weights["track"] += 0.02

    # ── 3. BM handicap: boost class_weight ──
    # BM58-70 is the single largest Minimum gap group (30 races short)
    if "bm" in race_class:
        bm_tokens = tuple(f"bm{n}" for n in range(50, 100))
        if any(t in race_class for t in bm_tokens):
            weights["class_weight"] += 0.01

    # ── Renormalise ──
    total = sum(weights.values())
    if total > 0:
        for key in weights:
            weights[key] = weights[key] / total

    # ── Hard clamp floors and ceilings (no redistribution) ──
    for key, floor_val in _WEIGHT_FLOOR.items():
        if weights[key] < floor_val:
            weights[key] = floor_val
    for key, ceil_val in _WEIGHT_CEILING.items():
        if weights[key] > ceil_val:
            weights[key] = ceil_val

    # Round for cleanliness
    for key in weights:
        weights[key] = round(weights[key], 4)

    return weights

PLACE_TIGHTENING_FEATURE_WEIGHTS = {
    "form_score": 0.103,
    "trial_score": 0.199,
    "trainer_score": 0.234,
    "jockey_horse_fit_score": 0.170,
    "consistency_score": 0.093,
    "distance_score": -0.033,
    "confidence_score": 0.027,
    "weight_score": -0.141,
}

PLACE_TIGHTENING_SCALE = 1.4
PLACE_TIGHTENING_MAX_ABS_BONUS = 4.0

GRADE_THRESHOLDS = (
    (96, "S+"),
    (92, "S"),
    (88, "S-"),
    (84, "A+"),
    (80, "A"),
    (76, "A-"),
    (72, "B+"),
    (68, "B"),
    (64, "B-"),
    (60, "C+"),
    (56, "C"),
    (52, "C-"),
    (48, "D"),
    (0, "E"),
)


def clip_score(value, default=60.0):
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = default
    return max(0.0, min(100.0, score))


def compute_grade(ability_score):
    score = clip_score(ability_score, 0)
    for threshold, grade in GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "E"


def score_band(score):
    score = clip_score(score)
    if score >= 85:
        return "✅✅"
    if score >= 70:
        return "✅"
    if score >= 55:
        return "➖"
    if score >= 40:
        return "❌"
    return "❌❌"


def parse_float(value):
    if isinstance(value, (int, float)):
        return float(value)
    if not value:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", str(value))
    return float(match.group(0)) if match else None


def parse_numbers(value):
    if not value:
        return []
    return [float(item) for item in re.findall(r"-?\d+(?:\.\d+)?", str(value))]


def parse_record_line(value):
    text = str(value or "")
    match = re.search(r"(\d+):(\d+)-(\d+)-(\d+)", text)
    if not match:
        return None
    starts, wins, seconds, thirds = (int(part) for part in match.groups())
    return {
        "starts": starts,
        "wins": wins,
        "seconds": seconds,
        "thirds": thirds,
        "places": wins + seconds + thirds,
    }


def parse_recent_finishes(value):
    text = str(value or "")
    values = []
    for token in re.findall(r"[0-9xX]+", text):
        if token.lower() == "x":
            continue
        try:
            values.append(10 if token == "0" else int(token))
        except ValueError:
            continue
    return values


def safe_ratio(numerator, denominator):
    if not denominator:
        return 0.0
    return float(numerator) / float(denominator)
