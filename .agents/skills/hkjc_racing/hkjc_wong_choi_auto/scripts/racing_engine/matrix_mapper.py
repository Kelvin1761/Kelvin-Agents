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
        ("race_shape_context_score", 1.00),
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
    # margin_trend_score 已剔出計分（同 stability 逐仗輸距 credit 重複；
    # 2026-07-08 backtest：淨計 formline_strength 全套指標無倒退、gold/champ 升）。
    "form_line": (
        ("formline_strength_score", 1.00),
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
        score = sum(_component_score(features, name) * weight for name, weight in components)
        matrix_scores[key] = round(clip_score(score), 2)
    return matrix_scores


def _component_score(features, name):
    if name == "race_shape_context_score" and name not in features:
        return clip_score(features.get("draw_score", 60))
    return clip_score(features.get(name, 60))
