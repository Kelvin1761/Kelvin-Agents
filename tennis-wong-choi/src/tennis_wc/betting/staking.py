from __future__ import annotations

from tennis_wc.config import get_settings


BASE_STAKES = {
    "NO_BET": 0.0,
    "WATCHLIST": 0.0,
    "SMALL_BET": 0.25,
    "STANDARD_BET": 0.5,
    "STRONG_BET": 0.75,
}


def stake_for_decision(decision: str, risk_adjustments: list[str] | None = None) -> float:
    stake = BASE_STAKES.get(decision, 0.0)
    for adjustment in risk_adjustments or []:
        if adjustment in {"injury_B", "low_sample", "stale_but_acceptable"}:
            stake *= 0.75
        if adjustment == "injury_C":
            stake *= 0.5
    return round(min(stake, get_settings().max_stake_units), 3)
