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
    """Each dimension = Σ leaf × share, clipped to 0–100 and rounded to 2 dp.

    `debut` picks the debut leaf mix (only class_advantage differs)."""
    formulas = DEBUT_MATRIX_FORMULAS if debut else MATRIX_FORMULAS
    return {
        key: round(clip_score(sum(_component_score(features, name) * weight for name, weight in components)), 2)
        for key, components in formulas.items()
    }


def _component_score(features, name):
    return clip_score(features.get(name, 60))
