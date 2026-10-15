from __future__ import annotations

from .dimensions import MATRIX_FORMULAS

from .scoring import clip_score, score_band



MATRIX_KEYS = tuple(MATRIX_FORMULAS)
LEGACY_MATRIX_ALIASES = {
    "sectional": "pace_perf",
}

# EXP-20260902-07: raw component scores, one set of ranking coefficients.
# Legacy import compatibility only; no live gain or gain fitting remains.
MATRIX_DISPLAY_TARGET_SD = 11.0
MATRIX_DISPLAY_GAINS = {}
MATRIX_ADVANTAGE_CUTOFF = 72.0
MATRIX_DISADVANTAGE_CUTOFF = 48.0


def canonical_matrix_key(key):
    """Return the live matrix key for a current or legacy name."""
    return LEGACY_MATRIX_ALIASES.get(str(key), str(key))


def matrix_score(matrix_scores, key, default=60.0):
    """Read a matrix score without silently losing legacy `sectional` data."""
    scores = matrix_scores if isinstance(matrix_scores, dict) else {}
    canonical = canonical_matrix_key(key)
    if canonical in scores:
        return clip_score(scores[canonical], default)
    if canonical == "pace_perf" and "sectional" in scores:
        return clip_score(scores["sectional"], default)
    return clip_score(default, default)


def canonicalize_matrix_scores(matrix_scores, default=60.0):
    return {
        key: round(matrix_score(matrix_scores, key, default), 2)
        for key in MATRIX_KEYS
    }


def with_form_quality(features):
    """Feature vectors scored before EXP-20261016-06 have no `form_quality_score`.

    Fill it with that leaf's own fallback — the old stability mix
    0.6 × form + 0.4 × performance quality — so stored Logic files, golden
    samples and replay tools keep the exact pre-change stability score instead
    of silently reading a neutral 60.
    """
    if not isinstance(features, dict) or "form_quality_score" in features:
        return features
    form = clip_score(features.get("form_score", 60))
    quality = clip_score(features.get("performance_quality_score", 60))
    return {**features, "form_quality_score": clip_score(60.0 + 0.6 * (form - 60.0) + 0.4 * (quality - 60.0))}


def map_features_to_matrix_scores(features):
    features = with_form_quality(features)
    matrix_scores = {}
    for key, components in MATRIX_FORMULAS.items():
        # Score weighted deviations from neutral.  This is algebraically
        # identical to the old weighted average whenever weights sum to 1, and
        # lets a retired leaf disappear cleanly without shifting the score
        # scale or inventing a fake constant feature.
        score = 60.0 + sum(
            (clip_score(features.get(name, 60)) - 60.0) * weight
            for name, weight in components
        )
        matrix_scores[key] = round(clip_score(score), 2)
    return matrix_scores


def map_features_to_matrix(features):
    scores = map_features_to_matrix_scores(features)
    return {key: score_band(score) for key, score in scores.items()}
