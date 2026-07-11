from scoring import clip_score, score_band


MATRIX_FORMULAS = {
    "stability": (
        ("form_score", 0.50),
        ("consistency_score", 0.40),
        ("trackwork_trend_score", 0.10),
    ),
    # 場地分 (track_going_score) 已全移除：HKJC 無場地適性數據，佢一直恒 60、零 signal，
    # 只做壓縮 anchor。改為純速度分，維度 7D 權重同步下調並重新歸一（見 MATRIX_WEIGHTS），
    # pit_backtest 確認 gold/min/champ 不變、single/t3c 微升。維度改名「段速」。
    "sectional": (
        ("speed_score", 1.00),
    ),
    "race_shape": (
        ("race_shape_context_score", 1.00),
    ),
    "trainer_signal": (
        ("jockey_score", 0.55),
        ("trainer_score", 0.45),
    ),
    # 信心分（confidence_score）2026-07-11 移除：佢係「資料完整度」計量表，非初出
    # 幾乎全部 83 分（近常數）、佔總分僅 0.10×0.0404≈0.4%，pit 回測移除後 5/6 指標
    # 不變（good −0.7 屬 1 場噪音）→ 純噪音兼令報告難明。0.10 按比例撥返 risk/weight。
    "horse_health": (
        ("risk_score", 0.611),
        ("weight_score", 0.389),
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
