from scoring import clip_score, score_band


MATRIX_FORMULAS = {
    "stability": (
        ("form_score", 0.50),
        ("consistency_score", 0.40),
        ("trackwork_trend_score", 0.10),
    ),
    "sectional": (
        ("speed_score", 0.65),
        ("track_going_score", 0.35),
    ),
    "race_shape": (
        ("draw_score", 1.00),
    ),
    "trainer_signal": (
        ("jockey_score", 0.55),
        ("trainer_score", 0.45),
    ),
    "horse_health": (
        ("risk_score", 0.55),
        ("weight_score", 0.35),
        ("confidence_score", 0.10),
    ),
    "form_line": (
        ("formline_strength_score", 0.70),
        ("margin_trend_score", 0.30),
    ),
    "class_advantage": (
        ("class_score", 0.75),
        ("weight_score", 0.25),
    ),
}


def map_features_to_matrix(features):
    scores = map_features_to_matrix_scores(features)
    return {key: score_band(score) for key, score in scores.items()}


def map_features_to_matrix_scores(features):
    matrix_scores = {}
    for key, components in MATRIX_FORMULAS.items():
        score = sum(clip_score(features.get(name, 60)) * weight for name, weight in components)
        matrix_scores[key] = round(clip_score(score), 2)
    return matrix_scores
