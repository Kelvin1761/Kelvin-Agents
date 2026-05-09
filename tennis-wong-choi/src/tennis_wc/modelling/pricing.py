from __future__ import annotations

from tennis_wc.config import get_settings
from tennis_wc.features.market import implied_probability, remove_vig_two_way
from tennis_wc.modelling.probability_model import predict_match_probability


def _value(payload, default=None):
    if isinstance(payload, dict) and "value" in payload:
        return payload["value"]
    return payload if payload is not None else default


def _market_odds(snapshot: dict) -> tuple[float | None, float | None]:
    market = snapshot.get("market", {})
    return _value(market.get("player_a_odds")), _value(market.get("player_b_odds"))


def _fair_odds(probability: float) -> float:
    return round(1 / probability, 4) if probability > 0 else 999.0


def _minimum_acceptable_odds(probability: float, min_edge: float) -> float:
    playable_probability = max(probability - min_edge, 0.01)
    return round(1 / playable_probability, 4)


def price_match_snapshot(snapshot: dict) -> dict:
    model = predict_match_probability(snapshot)
    odds_a, odds_b = _market_odds(snapshot)
    if odds_a is None or odds_b is None:
        return {
            "model": model,
            "selection_side": None,
            "selection_name": None,
            "model_probability": None,
            "fair_odds": None,
            "current_market_odds": None,
            "market_implied_probability": None,
            "no_vig_market_probability": None,
            "edge": None,
            "minimum_acceptable_odds": None,
            "errors": ["missing_market_odds"],
        }

    prob_a = model["player_a_probability"]
    prob_b = model["player_b_probability"]
    implied_a = implied_probability(float(odds_a))
    implied_b = implied_probability(float(odds_b))
    no_vig_a, no_vig_b = remove_vig_two_way(implied_a, implied_b)

    edge_a = prob_a - no_vig_a
    edge_b = prob_b - no_vig_b
    if edge_a >= edge_b:
        side = "player_a"
        player = snapshot["player_a"]
        model_probability = prob_a
        market_odds = float(odds_a)
        implied = implied_a
        no_vig = no_vig_a
        edge = edge_a
    else:
        side = "player_b"
        player = snapshot["player_b"]
        model_probability = prob_b
        market_odds = float(odds_b)
        implied = implied_b
        no_vig = no_vig_b
        edge = edge_b

    min_edge = get_settings().min_edge_match_winner
    return {
        "model": model,
        "selection_side": side,
        "selection_player_id": _value(player.get("id")),
        "selection_name": player.get("name"),
        "model_probability": round(model_probability, 6),
        "fair_odds": _fair_odds(model_probability),
        "current_market_odds": market_odds,
        "market_implied_probability": round(implied, 6),
        "no_vig_market_probability": round(no_vig, 6),
        "edge": round(edge, 6),
        "minimum_acceptable_odds": _minimum_acceptable_odds(model_probability, min_edge),
        "errors": [],
    }
