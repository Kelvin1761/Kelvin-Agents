from __future__ import annotations


def calculate_edge(model_probability: float, no_vig_market_probability: float) -> float:
    return model_probability - no_vig_market_probability
