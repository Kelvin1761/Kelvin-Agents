from __future__ import annotations


def calculate_clv(odds_taken: float, closing_odds: float) -> float:
    """
    Positive value means the bettor beat the closing price.
    For decimal odds, shorter closing odds after bet entry is positive CLV.
    """
    if odds_taken <= 0 or closing_odds <= 0:
        raise ValueError("Odds must be positive.")
    return (odds_taken - closing_odds) / closing_odds


def clv_label(clv: float | None) -> str:
    if clv is None:
        return "UNKNOWN"
    if clv > 0:
        return "POSITIVE"
    if clv < 0:
        return "NEGATIVE"
    return "NEUTRAL"
