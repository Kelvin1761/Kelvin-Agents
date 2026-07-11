from __future__ import annotations

from scoring import clip_score, score_band


MATRIX_FORMULAS = {
    "stability": (
        ("form_score", 0.60),
        ("consistency_score", 0.40),
    ),
    # 段速表現 (2026-07-10): 段速與引擎 (sectional 0.04535 = 0.805 sec + 0.195 trial)
    # 同 段速實速 (pace_figure 0.14296) 合併為一個維度，總權重 0.18831。內部權重
    # 係舊有效 leaf 權重嘅精確折算（0.14296/0.0365/0.0088 ÷ 0.18831）→ 排名逐匹
    # 完全一致（702場 A/B 驗證 GGP/champ/box4 全部相同）。內部權重 sweep（p.85/.90/
    # 1.0、s.25）全部兩窗唔贏 → 呢個折算比例就係局部最優。
    # Rollback: 拆返 "sectional":(sec .805, trial .195) w=0.04535 + "pace_figure" w=0.14296。
    "pace_perf": (
        ("pace_figure_score", 0.759174),
        ("sectional_score", 0.193864),
        ("trial_score", 0.046962),
    ),
    # 2026-07-11: 檔位形勢 淨化為純檔位/走位（pace_map 100%）。原本借用嘅 30%
    # track_score 已全數歸還「場地適性」維度 —— 消除跨維度重複，track_score 而家
    # 只喺一個維度出現，將來獨立升級唔使兩邊改。權重按代數對調（見 scoring 註）→
    # 逐匹綜合分完全一致（rank-identical，702場驗證 max diff 0.0001）。
    "race_shape": (
        ("pace_map_score", 1.0),
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
