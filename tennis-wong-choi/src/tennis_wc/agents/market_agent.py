from __future__ import annotations

from tennis_wc.agents.base_agent import BaseAgent
from tennis_wc.features.market import calculate_odds_movement


class MarketAgent(BaseAgent):
    name = "market"

    def review(self, feature_snapshot: dict, pricing: dict | None = None, filter_result: dict | None = None) -> dict:
        pricing = pricing or {}
        market = feature_snapshot.get("market", {})
        warnings = []
        movement = None
        selection_side = pricing.get("selection_side")
        if selection_side == "player_a":
            open_odds = _value(market.get("player_a_open_odds"))
        else:
            open_odds = _value(market.get("player_b_open_odds"))
        current_odds = pricing.get("current_market_odds")
        if open_odds and current_odds:
            movement = calculate_odds_movement(float(open_odds), float(current_odds))
        if current_odds and pricing.get("minimum_acceptable_odds") and current_odds < pricing["minimum_acceptable_odds"]:
            warnings.append("Current odds are below minimum acceptable odds.")
        return {
            "agent": self.name,
            "edge": pricing.get("selection_name") or "Neutral",
            "key_points": [
                f"Selection: {pricing.get('selection_name')}",
                f"Current odds: {current_odds}",
                f"Edge: {pricing.get('edge')}",
                f"Odds movement: {movement}",
            ],
            "warnings": warnings,
            "confidence_adjustment": "downgrade" if warnings else "none",
            "stake_adjustment": "none",
            "decision_override": "NO_BET" if warnings else None,
        }


def _value(payload, default=None):
    if isinstance(payload, dict) and "value" in payload:
        return payload["value"]
    return payload if payload is not None else default
