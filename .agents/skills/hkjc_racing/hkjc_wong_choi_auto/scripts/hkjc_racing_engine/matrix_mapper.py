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


def map_features_to_matrix_scores(features):
    matrix_scores = {}
    for key, components in MATRIX_FORMULAS.items():
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
    return matrix_scores


def _component_score(features, name):
    if name == "race_shape_context_score" and name not in features:
        return clip_score(features.get("draw_score", 60))
    return clip_score(features.get(name, 60))
