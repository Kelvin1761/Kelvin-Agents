"""
Deterministic models for non-match-winner markets (Total Games, Game Handicap,
Aces). All grounded in hold/serve stats already stored in player_match_history.

These are intentionally CONSERVATIVE and shrink toward population means so they
do not emit the over-confident, fake-edge probabilities the old ad-hoc code did.
They remain "review only" until the settlement-validation gate clears them — but
they are now sound enough to enter that pipeline.
"""
from __future__ import annotations

import math


# Tour population priors (from stored Sackmann history).
TOUR_ACE_MEAN = {"ATP": 6.26, "WTA": 2.72}
DEFAULT_ACE_MEAN = 4.56
LEAGUE_HOLD = 0.719  # blended ATP+WTA average hold rate


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


# --------------------------------------------------------------------------- #
# Total games / game handicap (from hold rates)
# --------------------------------------------------------------------------- #
def expected_games_per_set(hold_a: float, hold_b: float) -> float:
    """
    Expected games in a set as a function of both players' hold rates.

    Intuition (grounded, then clamped to a sane band):
      * The more reliably BOTH players hold, the longer sets run (more 6-4 / 7-5
        / 7-6) -> more games.
      * The bigger the hold mismatch, the more one-sided the set (6-2/6-1) ->
        fewer games.
    Anchored so two league-average holders (~0.72) give ~9.6 games/set, two
    strong holders (~0.85) give ~10.6, and a big mismatch trims toward ~8.5.
    """
    avg_hold = (hold_a + hold_b) / 2
    mismatch = abs(hold_a - hold_b)
    # Anchored so two league-average holders give ~9.0 games/set (=> ~22.5 total
    # games over ~2.5 sets, matching typical BO3 lines and avoiding a structural
    # Over lean).
    games = 9.0 + (avg_hold - LEAGUE_HOLD) * 7.0 - mismatch * 4.0
    return _clamp(games, 7.0, 12.0)


def expected_sets(match_win_probability: float, best_of: int = 3) -> float:
    """
    Expected number of sets played, derived from the per-set win probability
    (a compressed version of the match-win probability).
    """
    p = _clamp(0.5 + (match_win_probability - 0.5) * 0.7, 0.05, 0.95)
    q = 1 - p
    if best_of >= 5:
        p3 = p**3 + q**3
        p4 = 3 * (p**3 * q) + 3 * (q**3 * p)
        p5 = max(0.0, 1 - p3 - p4)
        return 3 * p3 + 4 * p4 + 5 * p5
    p2 = p**2 + q**2  # decided in 2 sets
    return 2 * p2 + 3 * (2 * p * q)


def expected_total_games(hold_a: float, hold_b: float, match_win_probability: float, best_of: int = 3) -> float:
    return expected_games_per_set(hold_a, hold_b) * expected_sets(match_win_probability, best_of)


def _normal_cdf(x: float, mean: float, sd: float) -> float:
    if sd <= 0:
        return 1.0 if x >= mean else 0.0
    return 0.5 * (1 + math.erf((x - mean) / (sd * math.sqrt(2))))


def total_games_over_probability(line: float, expected_games: float, best_of: int = 3) -> float:
    """P(total games > line). Games count is treated as Normal around the
    expected total; sd scales with best_of (more sets -> more dispersion)."""
    sd = 4.0 if best_of < 5 else 5.5
    # P(X > line) with a half-game continuity correction.
    return _clamp(1 - _normal_cdf(line + 0.5, expected_games, sd), 0.02, 0.98)


def set_total_games_over_probability(line: float, expected_set_games: float) -> float:
    """P(games in a single set > line). Tighter dispersion than a full match."""
    sd = 2.3
    return _clamp(1 - _normal_cdf(line + 0.5, expected_set_games, sd), 0.02, 0.98)


def game_handicap_cover_probability(
    line: float,
    favourite_side: bool,
    hold_a: float,
    hold_b: float,
    match_win_probability: float,
    best_of: int = 3,
) -> float:
    """
    Probability the selection covers a game handicap `line` (negative = giving
    games). Derived from the expected game margin, which scales with the
    match-win edge and the total games on offer.
    """
    total = expected_total_games(hold_a, hold_b, match_win_probability, best_of)
    # Expected game margin for player_a ~ edge over 0.5 times the games pool.
    expected_margin = (match_win_probability - 0.5) * total * 0.9
    margin = expected_margin if favourite_side else -expected_margin
    sd = 4.0 if best_of < 5 else 5.5
    # selection covers if (its game margin + line) > 0
    return _clamp(1 - _normal_cdf(-line + 0.5, margin, sd), 0.03, 0.97)


# --------------------------------------------------------------------------- #
# Aces (shrunk Poisson)
# --------------------------------------------------------------------------- #
def shrunk_ace_mean(
    sample_values: list[float],
    tour: str | None,
    best_of: int = 3,
) -> float | None:
    """
    Per-player expected aces, shrunk toward the tour population mean by sample
    size (kills the over-confident means from short histories), then scaled for
    best-of-5. Returns None when there is no usable history.
    """
    values = [float(v) for v in sample_values if v is not None]
    if not values:
        return None
    n = len(values)
    raw = sum(values) / n
    prior = TOUR_ACE_MEAN.get((tour or "").upper(), DEFAULT_ACE_MEAN)
    k = 6.0  # prior weight (~6 pseudo-matches)
    shrunk = (n * raw + k * prior) / (n + k)
    if best_of >= 5:
        shrunk *= 1.5  # ~50% more games served in a BO5
    return max(0.1, shrunk)


def poisson_over_probability(line: float, mean: float) -> float:
    """P(count > line) for a Poisson(mean)."""
    k = int(math.floor(line))
    cdf = 0.0
    for i in range(max(0, k) + 1):
        cdf += math.exp(-mean) * mean**i / math.factorial(i)
    return _clamp(1 - cdf, 0.02, 0.98)
