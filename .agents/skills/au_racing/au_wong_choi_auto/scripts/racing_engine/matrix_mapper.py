from __future__ import annotations

from scoring import clip_score, score_band


MATRIX_FORMULAS = {
    "stability": (
        ("form_score", 0.60),
        ("consistency_score", 0.40),
    ),
    # distance_score removed from 段速與引擎 (2026-06-29): walk-forward backtest
    # showed dropping it lifts good +0.6pp / champion +1.0pp OOS; weights
    # renormalised onto sectional_score + trial (0.62/0.15 -> 0.805/0.195).
    "sectional": (
        ("sectional_score", 0.805),
        ("trial_score", 0.195),
    ),
    "race_shape": (
        ("pace_map_score", 0.70),
        ("track_score", 0.30),
    ),
    "jockey_trainer": (
        ("jockey_score", 0.28),
        ("trainer_score", 0.20),
        ("jockey_horse_fit_score", 0.52),
    ),
    # rating_score up-weighted 0.15 -> 0.70 (2026-06-29): official handicap rating
    # is the one run-style-independent ability signal that lifts box4 OOS. Combined
    # with the distance removal above, walk-forward (5-fold, fixed sub-weight, no
    # negative fold on box4) gives box4 +0.6pp, good +0.6pp, champion +0.8pp.
    "class_weight": (
        ("class_score", 0.159),
        ("rating_score", 0.70),
        ("weight_score", 0.141),
    ),
    "track": (
        ("track_score", 1.0),
    ),
    "form_line": (
        ("formline_score", 0.78),
        ("form_score", 0.22),
    ),
}


def map_features_to_matrix_scores(features):
    matrix_scores = {}
    for key, components in MATRIX_FORMULAS.items():
        score = sum(clip_score(features.get(name, 60)) * weight for name, weight in components)
        matrix_scores[key] = round(clip_score(score), 2)
    return matrix_scores


def map_features_to_matrix(features):
    scores = map_features_to_matrix_scores(features)
    return {key: score_band(score) for key, score in scores.items()}
