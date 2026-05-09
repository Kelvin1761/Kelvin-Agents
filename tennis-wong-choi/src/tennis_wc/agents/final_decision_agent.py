from __future__ import annotations

from tennis_wc.agents.base_agent import BaseAgent, pct, value


class FinalDecisionAgent(BaseAgent):
    name = "final_decision"

    def review(self, feature_snapshot: dict, pricing: dict | None = None, filter_result: dict | None = None) -> dict:
        pricing = pricing or {}
        filter_result = filter_result or {}
        context = feature_snapshot["match_context"]
        player_a = feature_snapshot["player_a"]
        player_b = feature_snapshot["player_b"]
        return {
            "agent": self.name,
            "final_format": {
                "Match": f"{player_a['name']} vs {player_b['name']}",
                "Tournament": value(context.get("tournament")),
                "Level": value(context.get("level")),
                "Round": value(context.get("round")),
                "Surface": value(context.get("surface")),
                "Format": value(context.get("format")),
                "Market": "Match Winner",
                "Selection": pricing.get("selection_name"),
                "Current odds": pricing.get("current_market_odds"),
                "Model probability": pct(pricing.get("model_probability")),
                "Fair odds": pricing.get("fair_odds"),
                "No-vig market probability": pct(pricing.get("no_vig_market_probability")),
                "Edge": pct(pricing.get("edge")),
                "Minimum acceptable odds": pricing.get("minimum_acceptable_odds"),
                "Confidence": filter_result.get("confidence"),
                "Data quality": feature_snapshot.get("data_quality", {}).get("score"),
                "Risk": filter_result.get("risk"),
                "Recommended stake": filter_result.get("stake_units"),
                "Decision": filter_result.get("decision"),
                "Red flags": filter_result.get("hard_no_bet_reasons") or filter_result.get("warnings", [])[:5],
            },
            "decision_override": "NO_BET" if filter_result.get("hard_no_bet_reasons") else None,
        }
