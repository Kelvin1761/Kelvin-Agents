from . import dimensions
from .scoring import clip_score, score_band


# Leaf composition per dimension lives in dimensions.py (single source of truth).
# History of the leaf choices (track_going removed 2026-07-10, confidence removed
# 2026-07-11, margin_trend removed 2026-07-08) is in git and docs/experiments.
MATRIX_FORMULAS = dimensions.formulas()


def matrix_formula_manifest():
    """JSON-safe representation shared by run metadata and validation."""
    return {
        key: [
            {"feature": feature, "weight": weight}
            for feature, weight in components
        ]
        for key, components in MATRIX_FORMULAS.items()
    }


def map_features_to_matrix(features):
    scores = map_features_to_matrix_scores(features)
    return {key: score_band(score) for key, score in scores.items()}


DEBUT_MATRIX_FORMULAS = dimensions.debut_formulas()


def map_features_to_matrix_scores(features, debut=False):
    """`debut` 揀初出馬嘅 leaf 組合同 shim 權重（同 `_ability_score` 用嘅權重一致）。"""
    matrix_scores = {}
    formulas = DEBUT_MATRIX_FORMULAS if debut else MATRIX_FORMULAS
    for key, components in formulas.items():
        score = sum(_component_score(features, name) * weight for name, weight in components)
        matrix_scores[key] = round(clip_score(score), 2)
    split = dimensions.LEGACY_STABILITY_SPLIT
    if split and split["parent"] in matrix_scores and split["child"] in matrix_scores:
        legacy = round(clip_score(sum(
            _component_score(features, name) * weight for name, weight in split["legacy_leaves"]
        )), 2)
        share = split["child_share"]
        matrix_scores[split["parent"]] = round(
            (legacy - share * matrix_scores[split["child"]]) / (1.0 - share), 6
        )
    _apply_weight_merge(features, matrix_scores, debut)
    return matrix_scores


def _apply_weight_merge(features, matrix_scores, debut):
    """負磅分由健康搬入級數優勢（2026-11-05）：保持綜合分同舊結構一模一樣。

    舊結構係兩個各自 round 到 2 位嘅維度。新健康 = 風險分；新級數 =
    (W_c·舊級數 + W_h·舊健康 − W_h'·新健康) / W_c'，所以兩項加權和不變。
    """
    merge = dimensions.LEGACY_WEIGHT_MERGE
    target, donor = merge["target"], merge["donor"]
    if not merge or target not in matrix_scores or donor not in matrix_scores:
        return
    old = merge["legacy_debut_weights"] if debut else merge["legacy_weights"]
    spec_target, spec_donor = dimensions.BY_KEY[target], dimensions.BY_KEY[donor]
    new_target = spec_target.debut_weight if debut else spec_target.weight
    new_donor = spec_donor.debut_weight if debut else spec_donor.weight
    legacy_target = round(clip_score(sum(
        _component_score(features, name) * weight for name, weight in merge["legacy_target_leaves"]
    )), 2)
    legacy_donor = round(clip_score(sum(
        _component_score(features, name) * weight for name, weight in merge["legacy_donor_leaves"]
    )), 2)
    # 唔好 round：綜合分經常啱啱落喺 x.xx5，round 到 6 位（誤差 ≤ 8e-8）都令全語料
    # 5,365 匹有 2 匹 2 位小數翻轉；唔 round 最大誤差 1.4e-14、零翻轉。
    matrix_scores[target] = (
        old[target] * legacy_target + old[donor] * legacy_donor - new_donor * matrix_scores[donor]
    ) / new_target


def _component_score(features, name):
    if name == "race_shape_context_score" and name not in features:
        return clip_score(features.get("draw_score", 60))
    return clip_score(features.get(name, 60))
