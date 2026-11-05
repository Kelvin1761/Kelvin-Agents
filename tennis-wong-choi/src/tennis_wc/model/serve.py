"""Serve/return form and per-game hold probabilities.

``serve_return_profile`` averages a player's last 25 matches (surface first,
all surfaces if fewer than 5). ``estimate_hold_fitted`` is the ridge model
trained 2024-01-01..2026-05-10 (coefficients below); ``estimate_hold`` is the
hand-set rule still used for first-set-winner pricing.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from tennis_wc.model.history import active_clause, as_of_clause, as_of_params, clean_history_row

DEFAULT_WINDOW = 25
MIN_SAMPLES = 5

_SERVE_COLUMNS = (
    "hold_rate",
    "first_serve_points_won_pct",
    "second_serve_points_won_pct",
    "ace_count",
    "service_games_played",
    "double_fault_count",
    "break_points_saved",
    "break_points_faced",
)
_RETURN_COLUMNS = (
    "break_rate",
    "return_points_won_pct",
    "break_points_converted",
    "break_points_chances",
)


@dataclass(frozen=True)
class ServeReturnProfile:
    player_id: int
    as_of_date: str
    matches: int
    serve: dict
    returning: dict
    opponent_elo_mean: float | None
    surface: str | None
    history_ids: tuple[int,...] = ()

    @property
    def is_usable(self) -> bool:
        """Enough serve history to say anything at all."""
        return self.matches >= MIN_SAMPLES and self.serve.get("hold_rate") is not None

    def get(self, name: str):
        if name in self.serve:
            return self.serve[name]
        return self.returning.get(name)


def _mean(values) -> float | None:
    usable = [float(value) for value in values if value is not None]
    return sum(usable) / len(usable) if usable else None


def serve_return_profile(
    conn,
    player_id: int,
    as_of_date: str,
    *,
    surface: str | None = None,
    window: int = DEFAULT_WINDOW,
    start_time: str | None = None,
) -> ServeReturnProfile:
    """Serve and return rates over the player's last ``window`` matches.

    ``surface`` narrows the window when the player has enough matches on it and
    is otherwise ignored.  Surface is recorded on 46.2% of history rows, so
    treating it as a filter would empty the window for half the board; it is an
    adjustment on a pooled rate, never a gate.
    """

    columns = ", ".join((*_SERVE_COLUMNS, *_RETURN_COLUMNS, "opponent_elo"))
    params: list = [player_id, as_of_date, *as_of_params(as_of_date, start_time)]
    surface_clause = ""
    if surface:
        surface_clause = " AND LOWER(COALESCE(surface,'')) = LOWER(?)"
        params.append(surface)
    params.append(window)
    rows = conn.execute(
        f"""
        SELECT id,{columns} FROM player_match_history
        WHERE player_id = ? AND match_date < ? AND typeof(hold_rate) IN ('integer','real') AND hold_rate BETWEEN 0 AND 1
          {as_of_clause()}
          AND {active_clause()}
          {surface_clause}
        ORDER BY match_date DESC, id DESC
        LIMIT ?
        """,
        tuple(params),
    ).fetchall()
    rows = [clean_history_row(row) for row in rows]
    used_surface = surface
    if surface and len(rows) < MIN_SAMPLES:
        return serve_return_profile(
            conn, player_id, as_of_date, surface=None, window=window,
            start_time=start_time,
        )
    if not surface:
        used_surface = None

    serve = {name: _mean(row[name] for row in rows) for name in _SERVE_COLUMNS}
    returning = {name: _mean(row[name] for row in rows) for name in _RETURN_COLUMNS}
    # Break points are counts, not rates; the ratio is what a model wants and
    # the denominator is what tells it whether to believe the ratio.
    faced = serve.get("break_points_faced")
    saved = serve.get("break_points_saved")
    serve["break_point_save_rate"] = (
        saved / faced if faced and saved is not None and faced > 0 else None
    )
    chances = returning.get("break_points_chances")
    converted = returning.get("break_points_converted")
    returning["break_point_conversion_rate"] = (
        converted / chances if chances and converted is not None and chances > 0 else None
    )
    return ServeReturnProfile(
        player_id=int(player_id),
        as_of_date=str(as_of_date),
        matches=len(rows),
        serve=serve,
        returning=returning,
        opponent_elo_mean=_mean(row["opponent_elo"] for row in rows),
        surface=used_surface,history_ids=tuple(int(r['id']) for r in rows),
    )


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

    baseline = server.serve.get("hold_rate") if server is not None else None
    if baseline is None or not server.is_usable:
        return HoldEstimate(LEAGUE_HOLD, LEAGUE_HOLD, 0.0, 0.0,
                            server.matches if server is not None else 0, False)
    names = fitted_feature_names()
    coefficients = COEFFICIENTS
    if set(names) != set(coefficients):
        return estimate_hold(server, returner, return_weight=0.35, elo_weight=0.04)
    row = fitted_feature_row(server, returner)
    total = INTERCEPT
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


# Ridge fit, see docs/experiments (hold model). Trained 2024-01-01..2026-05-10.
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


# Expected total games: E[games | best_of, closeness] x hold_ratio(combined hold).

# E[total games] by (best_of, closeness bucket of 0.2). Fit on 19,406 matches.
MEAN_BY_CLOSENESS: dict[tuple[int, float], float] = {
    (3, 0.0): 17.84, (3, 0.2): 20.11, (3, 0.4): 21.79, (3, 0.6): 22.89,
    (3, 0.8): 23.31, (3, 1.0): 23.41,
    (5, 0.0): 29.79, (5, 0.2): 33.84, (5, 0.4): 36.49, (5, 0.6): 38.63,
    (5, 0.8): 38.29, (5, 1.0): 40.30,
}

_HOLD_RATIO: list[tuple[float, float]] = [
    # (upper bound of combined hold sum, ratio)
    (1.35, 0.971),
    (1.45, 0.989),
    (1.55, 1.000),
    (1.65, 1.022),
    (9.99, 1.049),
]
_HOLD_MIN_SAMPLES = 5
_HOLD_WINDOW = 20


def hold_ratio(hold_sum: float | None) -> float:
    if hold_sum is None:
        return 1.0
    for upper, ratio in _HOLD_RATIO:
        if hold_sum < upper:
            return ratio
    return 1.0


def combined_hold(conn, player_a_id: int, player_b_id: int, as_of_date: str,
                  start_time: str | None = None) -> float | None:
    """Sum of both players' mean hold rate over their last N matches strictly
    before the match date (walk-forward safe). None unless both have >= 5
    hold samples — unknown must stay neutral, not penalised."""

    sums: list[float] = []
    guard = as_of_params(as_of_date, start_time)
    for pid in (player_a_id, player_b_id):
        rows = conn.execute(
            f"""
            SELECT hold_rate FROM player_match_history
            WHERE player_id = ? AND typeof(hold_rate) IN ('integer','real') AND hold_rate BETWEEN 0 AND 1 AND match_date < ?
              {as_of_clause()}
          AND {active_clause()}
            ORDER BY match_date DESC LIMIT ?
            """,
            (pid, as_of_date, *guard, _HOLD_WINDOW),
        ).fetchall()
        vals = [float(r["hold_rate"]) for r in rows]
        if len(vals) < _HOLD_MIN_SAMPLES:
            return None
        sums.append(sum(vals) / len(vals))
    return sums[0] + sums[1]
def predict_total_games(match_prob: float | None, best_of: int = 3,
                        hold_sum: float | None = None) -> float | None:
    """Expected total match games from the favourite's win probability, scaled
    by the serve-dominance (combined hold) ratio when available."""
    if match_prob is None:
        return None
    p = float(match_prob)
    closeness = 1.0 - abs(2 * p - 1)
    bucket = round(closeness * 5) / 5
    bo = 5 if best_of == 5 else 3
    base = MEAN_BY_CLOSENESS.get((bo, bucket)) or MEAN_BY_CLOSENESS.get((bo, 0.6))
    return base * hold_ratio(hold_sum) if base is not None else None
