from __future__ import annotations


def implied_probability(decimal_odds: float) -> float:
    return 1 / decimal_odds


def remove_vig_two_way(prob_a: float, prob_b: float) -> tuple[float, float]:
    total = prob_a + prob_b
    return prob_a / total, prob_b / total


def calculate_odds_movement(open_odds: float, current_odds: float) -> float:
    return (current_odds - open_odds) / open_odds
