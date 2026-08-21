"""Stage 2: the probability a player holds serve in this match.

Every games and sets prop is a function of this one quantity, which is why the
plan replaces seven closed forms with one estimator. Today each family fits its
own curve against its own outcomes, which is how three of them ended up with
mutually inconsistent implied margins.

The estimator is deliberately simple and its job is to beat a rolling average.
If it cannot, the extra features are noise and the plan stops here -- that test
is the whole reason this module exists before any simulator or pricing.

Two estimators live here, and both are kept on purpose:

``estimate_hold``
    the hand-set version -- a rolling hold rate plus two weights chosen by a
    grid search over one column each. It stays because it is the baseline the
    fitted model has to beat, and every test that pins the shape of the answer
    is written against it.

``estimate_hold_fitted``
    a ridge regression over the whole serve/return profile, fitted by
    ``scripts/fit_hold_ml.py`` on 59,804 walk-forward matches and exported to
    :mod:`tennis_wc.props.hold_coefficients` as plain floats. It is a linear
    model rather than the boosted tree that was also measured because the two
    scored within 0.003 of each other on every population large enough to read,
    and a dict of coefficients costs the daily path no new dependency and no
    pickled artifact to version.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from tennis_wc.features.serve_return import ServeReturnProfile

# League-average hold, used only to centre the opponent adjustment. Measured
# over the settled record rather than assumed.
LEAGUE_HOLD = 0.75
LEAGUE_RETURN_POINTS_WON = 0.36
# How far a fully dominant returner moves a server's hold. Fitted in
# scripts/fit_hold_model.py; a value of 0 makes this the rolling average.
RETURN_STRENGTH_WEIGHT = 0.0
OPPONENT_ELO_WEIGHT = 0.0
ELO_SCALE = 200.0


@dataclass(frozen=True)
class HoldEstimate:
    probability: float
    baseline: float
    return_adjustment: float
    strength_adjustment: float
    matches: int
    is_usable: bool


def estimate_hold(
    server: ServeReturnProfile,
    returner: ServeReturnProfile,
    *,
    return_weight: float = RETURN_STRENGTH_WEIGHT,
    elo_weight: float = OPPONENT_ELO_WEIGHT,
) -> HoldEstimate:
    """P(server holds a given service game) against this specific returner.

    Three terms, each one measurable on its own:

    * the server's own rolling hold rate -- the baseline any addition must beat;
    * how much better than league average this returner is at winning return
      points, which is the piece the current model has no way to express;
    * a correction for the quality of opposition the server's rate was earned
      against, since ``opponent_elo`` is on 95.1% of history rows and a rate
      earned in ITF draws is not the same number as one earned on tour.
    """
    baseline = server.serve.get("hold_rate")
    if baseline is None or not server.is_usable:
        return HoldEstimate(LEAGUE_HOLD, LEAGUE_HOLD, 0.0, 0.0, server.matches, False)

    return_points = returner.returning.get("return_points_won_pct")
    return_adjustment = 0.0
    if returner.is_usable and return_points is not None:
        return_adjustment = -return_weight * (return_points - LEAGUE_RETURN_POINTS_WON)

    strength_adjustment = 0.0
    if server.opponent_elo_mean is not None and returner.opponent_elo_mean is not None:
        # The server's rate was earned against opponents averaging X; this
        # returner sits at Y. Facing stronger opposition than usual should cost.
        gap = (returner.opponent_elo_mean - server.opponent_elo_mean) / ELO_SCALE
        strength_adjustment = -elo_weight * gap

    probability = baseline + return_adjustment + strength_adjustment
    return HoldEstimate(
        probability=max(0.30, min(0.98, probability)),
        baseline=float(baseline),
        return_adjustment=round(return_adjustment, 6),
        strength_adjustment=round(strength_adjustment, 6),
        matches=server.matches,
        is_usable=True,
    )


# --- the fitted estimator -------------------------------------------------
#
# One feature contract, read by the fitter and by the daily path.
#
# Surface is deliberately not in it. Fitted, the surface one-hots bought
# +0.0024 of explained variance -- and they would train on history rows, which
# carry a surface 99.9% of the time, then serve on fixtures, where
# `tournament_levels` resolves one for 406 of the 580 priced fixtures that have
# both holds. Blanking surface on a model fitted with it drops the score from
# 0.272 to 0.161, so the 30% of the board with no surface would have been
# priced by a model evaluated outside the distribution it was fitted on, for a
# gain in the third decimal on the rest. `serve_return_profile` already narrows
# its own window by surface where a player has the matches for it.

# Substituted when a profile has no value for a column, so a missing feature
# lands at the league average rather than at zero. Measured over the same
# corpus the model is fitted on.
FITTED_LEAGUE_DEFAULTS = {
    "hold_rate": 0.75,
    "first_serve_points_won_pct": 0.70,
    "second_serve_points_won_pct": 0.50,
    "ace_count": 4.0,
    "double_fault_count": 3.0,
    "break_point_save_rate": 0.60,
    "return_points_won_pct": 0.36,
    "break_rate": 0.25,
    "break_point_conversion_rate": 0.40,
    "opponent_elo": 1500.0,
}

_FITTED_SERVE_COLUMNS = (
    "hold_rate",
    "first_serve_points_won_pct",
    "second_serve_points_won_pct",
    "ace_count",
    "double_fault_count",
    "break_point_save_rate",
)
_FITTED_RETURN_COLUMNS = (
    "return_points_won_pct",
    "break_rate",
    "break_point_conversion_rate",
)


def fitted_feature_names() -> tuple[str, ...]:
    names: list[str] = []
    for column in _FITTED_SERVE_COLUMNS:
        names += [f"server.{column}", f"server.{column}.present"]
    for column in _FITTED_RETURN_COLUMNS:
        names += [f"returner.{column}", f"returner.{column}.present"]
    names += [
        "server.opponent_elo",
        "elo_gap_over_200",
        "log1p_server_matches",
        "log1p_returner_matches",
        "returner_profile_present",
    ]
    return tuple(names)


def fitted_feature_row(
    server: ServeReturnProfile, returner: ServeReturnProfile | None
) -> list[float]:
    """The feature vector, in the order :func:`fitted_feature_names` declares.

    ``returner`` may be None or unusable: roughly 5% of the corpus has serve
    history for one side only, and refusing to price those would hand the
    fallback back to the closed forms this work replaces.
    """
    usable_returner = returner if (returner is not None and returner.is_usable) else None
    row: list[float] = []
    for column in _FITTED_SERVE_COLUMNS:
        value = server.serve.get(column) if server is not None else None
        row.append(FITTED_LEAGUE_DEFAULTS[column] if value is None else float(value))
        row.append(0.0 if value is None else 1.0)
    for column in _FITTED_RETURN_COLUMNS:
        value = usable_returner.returning.get(column) if usable_returner else None
        row.append(FITTED_LEAGUE_DEFAULTS[column] if value is None else float(value))
        row.append(0.0 if value is None else 1.0)
    server_elo = server.opponent_elo_mean if server is not None else None
    returner_elo = usable_returner.opponent_elo_mean if usable_returner else None
    row.append(
        float(server_elo) if server_elo is not None
        else FITTED_LEAGUE_DEFAULTS["opponent_elo"]
    )
    row.append(
        (float(returner_elo) - float(server_elo)) / ELO_SCALE
        if (server_elo is not None and returner_elo is not None) else 0.0
    )
    row.append(math.log1p(server.matches if server is not None else 0))
    row.append(math.log1p(usable_returner.matches if usable_returner else 0))
    row.append(1.0 if usable_returner else 0.0)
    return row


def estimate_hold_fitted(
    server: ServeReturnProfile, returner: ServeReturnProfile | None
) -> HoldEstimate:
    """P(server holds) from the fitted coefficients.

    Falls back to the hand-set estimator whenever the coefficient module is
    missing or disagrees with the feature contract, so a stale export degrades
    to the previous model rather than to a wrong number.
    """
    from tennis_wc.props import hold_coefficients

    baseline = server.serve.get("hold_rate") if server is not None else None
    if baseline is None or not server.is_usable:
        return HoldEstimate(LEAGUE_HOLD, LEAGUE_HOLD, 0.0, 0.0,
                            server.matches if server is not None else 0, False)
    names = fitted_feature_names()
    coefficients = hold_coefficients.COEFFICIENTS
    if set(names) != set(coefficients):
        return estimate_hold(server, returner, return_weight=0.35, elo_weight=0.04)
    row = fitted_feature_row(server, returner)
    total = hold_coefficients.INTERCEPT
    for name, value in zip(names, row):
        total += coefficients[name] * value
    return HoldEstimate(
        probability=max(0.30, min(0.98, total)),
        baseline=float(baseline),
        return_adjustment=round(total - float(baseline), 6),
        strength_adjustment=0.0,
        matches=server.matches,
        is_usable=True,
    )
