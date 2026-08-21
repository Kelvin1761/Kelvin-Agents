from __future__ import annotations


def test_residual_weight_refuses_a_model_that_adds_no_signal():
    from scripts.evaluate_market_residual_props import fit_residual_weight

    rows = [
        {"raw": 0.80, "market": 0.60, "actual": 0.0},
        {"raw": 0.20, "market": 0.40, "actual": 1.0},
    ]

    fitted = fit_residual_weight(rows, evidence_prior=0.0)

    assert fitted["raw_weight"] == 0.0
    assert fitted["model_weight"] == 0.0


def test_residual_weight_and_brier_are_scored_on_unseen_rows():
    from scripts.evaluate_market_residual_props import (
        brier_metrics,
        fit_residual_weight,
    )

    train = [
        {"raw": 0.80, "market": 0.55, "actual": 1.0},
        {"raw": 0.20, "market": 0.45, "actual": 0.0},
    ] * 20
    holdout = [
        {"raw": 0.75, "market": 0.55, "actual": 1.0},
        {"raw": 0.25, "market": 0.45, "actual": 0.0},
    ] * 10

    fitted = fit_residual_weight(train, evidence_prior=0.0)
    scored = brier_metrics(holdout, fitted["model_weight"])

    assert fitted["model_weight"] > 0
    assert scored["blended"] < scored["market"]
    assert scored["blended"] <= scored["raw"]


def test_surface_specific_weights_do_not_pool_opposite_regimes():
    from scripts.evaluate_market_residual_props import fit_group_weights

    hard = [
        {"raw": 0.80, "market": 0.55, "actual": 1.0, "surface": "hard"},
        {"raw": 0.20, "market": 0.45, "actual": 0.0, "surface": "hard"},
    ] * 20
    clay = [
        {"raw": 0.80, "market": 0.55, "actual": 0.0, "surface": "clay"},
        {"raw": 0.20, "market": 0.45, "actual": 1.0, "surface": "clay"},
    ] * 20

    weights = fit_group_weights(hard + clay, "surface", evidence_prior=0.0)

    assert weights["hard"]["model_weight"] > 0
    assert weights["clay"]["model_weight"] == 0
