"""Fitted hold-model coefficients. GENERATED -- do not edit by hand.

Written by ``scripts/fit_hold_ml.py``. Refit it rather than adjusting a
number here: the feature order is declared by
``hold_model.fitted_feature_names`` and the two must agree or
``estimate_hold_fitted`` falls back to the hand-set estimator.
"""
from __future__ import annotations

TRAINED_FROM = '2024-01-01'
TRAINED_THROUGH = '2026-05-10'
TRAINING_ROWS = 59804
HOLDOUT_ROWS = 5536
RIDGE_ALPHA = 0.14873521072935117

# Out-of-sample on the held-out window, MAE and the share of the
# achievable (above-binomial-floor) variance explained.
HOLDOUT_METRICS = {
    "rolling": {
        "mae": 0.138746,
        "rmse": 0.176287,
        "r2_vs_binomial_floor": 0.0808,
        "bootstrap_vs_rolling": None
    },
    "hand-set": {
        "mae": 0.137605,
        "rmse": 0.174515,
        "r2_vs_binomial_floor": 0.1168,
        "bootstrap_vs_rolling": {
            "mean_improvement": 0.001133,
            "ci_95": [
                0.00064,
                0.001624
            ],
            "probability_no_improvement": 0.0
        }
    },
    "fitted": {
        "mae": 0.130947,
        "rmse": 0.166784,
        "r2_vs_binomial_floor": 0.2696,
        "bootstrap_vs_rolling": {
            "mean_improvement": 0.007788,
            "ci_95": [
                0.006516,
                0.009098
            ],
            "probability_no_improvement": 0.0
        }
    }
}

INTERCEPT = 0.6019120239079421

COEFFICIENTS = {
    'server.hold_rate': 0.213560203965803,
    'server.hold_rate.present': 0.0,
    'server.first_serve_points_won_pct': 0.34351661329356653,
    'server.first_serve_points_won_pct.present': 0.0,
    'server.second_serve_points_won_pct': 0.19778288012658707,
    'server.second_serve_points_won_pct.present': 0.0,
    'server.ace_count': 0.004077491672546785,
    'server.ace_count.present': 0.0,
    'server.double_fault_count': -0.0029602430378190547,
    'server.double_fault_count.present': 0.0,
    'server.break_point_save_rate': -0.053319112007038205,
    'server.break_point_save_rate.present': 0.0,
    'returner.return_points_won_pct': -0.7165880175738836,
    'returner.return_points_won_pct.present': -0.006510654687596151,
    'returner.break_rate': -0.11922236949291065,
    'returner.break_rate.present': -0.006510654687596151,
    'returner.break_point_conversion_rate': 0.0020848304019014385,
    'returner.break_point_conversion_rate.present': -0.006510654687596151,
    'server.opponent_elo': -4.5411557039187755e-06,
    'elo_gap_over_200': -0.08602838470812557,
    'log1p_server_matches': 0.010525284849707717,
    'log1p_returner_matches': -0.006954564159817878,
    'returner_profile_present': -0.006510654687596151,
}
