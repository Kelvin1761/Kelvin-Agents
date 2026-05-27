from __future__ import annotations

from scoring import clip_score, score_band


MATRIX_FORMULAS = {
    "stability": (
        ("form_score", 0.60),
        ("consistency_score", 0.40),
    ),
    "sectional": (
        ("sectional_score", 0.62),
        ("distance_score", 0.23),
        ("trial_score", 0.15),
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
    "class_weight": (
        ("class_score", 0.40),
        ("rating_score", 0.25),
        ("weight_score", 0.35),
    ),
    "track": (
        ("track_score", 0.82),
        ("health_score", 0.18),
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
