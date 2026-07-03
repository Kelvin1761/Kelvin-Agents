from __future__ import annotations

from tennis_wc.config import get_settings


BET_BANDS = {"SMALL_BET", "STANDARD_BET", "STRONG_BET"}

# Risk multipliers applied to the half-Kelly stake (compounding).
_RISK_MULTIPLIERS = {
    "injury_B": 0.75,
    "low_sample": 0.75,
    "stale_but_acceptable": 0.75,
    "rank_seed_elo": 0.5,
    "injury_C": 0.5,
}


def kelly_fraction(model_probability: float | None, decimal_odds: float | None) -> float:
    """
    Full-Kelly fraction of bankroll for a single bet.

        f* = (p * b - (1 - p)) / b ,  where b = decimal_odds - 1

    Returns 0 when the bet is not +EV at the actual price (so vig-eaten
    "edges" are not staked). p is the model win probability for the selection.
    """
    if not model_probability or not decimal_odds or decimal_odds <= 1.0:
        return 0.0
    p = float(model_probability)
    b = float(decimal_odds) - 1.0
    f = (p * b - (1.0 - p)) / b
    return max(0.0, f)


def _round_to_increment(value: float, increment: float) -> float:
    if increment <= 0:
        return round(value, 3)
    return round(round(value / increment) * increment, 3)


def kelly_stake_units(
    model_probability: float | None,
    decimal_odds: float | None,
    risk_adjustments: list[str] | None = None,
) -> float:
    """
    Half-Kelly (configurable fraction) stake in units, floored at
    MIN_STAKE_UNITS for any +EV bet and capped at MAX_STAKE_UNITS. 1 unit is
    1/bankroll of the bank (default bankroll 100u, so 1u ~= 1% of bankroll).
    """
    settings = get_settings()
    full = kelly_fraction(model_probability, decimal_odds)
    if full <= 0:
        return 0.0
    units = full * settings.kelly_fraction * settings.default_bankroll_units
    for adjustment in risk_adjustments or []:
        units *= _RISK_MULTIPLIERS.get(adjustment, 1.0)
    if units <= 0:
        return 0.0
    units = max(settings.min_stake_units, units)
    units = min(units, settings.max_stake_units)
    return _round_to_increment(units, settings.stake_round_increment)


def stake_for_decision(
    decision: str,
    model_probability: float | None = None,
    decimal_odds: float | None = None,
    risk_adjustments: list[str] | None = None,
) -> float:
    """
    Stake in units for a decision band. Non-bet bands stake 0. Bet bands are
    sized by half-Kelly on (model_probability, decimal_odds); when those are not
    supplied (legacy callers) the bet is floored at MIN_STAKE_UNITS.
    """
    if decision not in BET_BANDS:
        return 0.0
    settings = get_settings()
    if model_probability is None or decimal_odds is None:
        stake = settings.min_stake_units
        for adjustment in risk_adjustments or []:
            stake *= _RISK_MULTIPLIERS.get(adjustment, 1.0)
        return _round_to_increment(min(stake, settings.max_stake_units), settings.stake_round_increment)
    return kelly_stake_units(model_probability, decimal_odds, risk_adjustments)
