from __future__ import annotations

from tennis_wc.agents.base_agent import BaseAgent, edge_label, pct, value


class FormAgent(BaseAgent):
    name = "form"

    def review(self, feature_snapshot: dict, pricing: dict | None = None, filter_result: dict | None = None) -> dict:
        player_a = feature_snapshot["player_a"]
        player_b = feature_snapshot["player_b"]
        a_rate = value(player_a.get("opponent_rank_buckets", {}).get("TOP_100", {}).get("shrinked_win_rate"))
        b_rate = value(player_b.get("opponent_rank_buckets", {}).get("TOP_100", {}).get("shrinked_win_rate"))
        return {
            "agent": self.name,
            "edge": edge_label(a_rate, b_rate, player_a["name"], player_b["name"]),
            "key_points": [
                f"{player_a['name']} recent proxy vs Top 100: {pct(a_rate)}",
                f"{player_b['name']} recent proxy vs Top 100: {pct(b_rate)}",
            ],
            "warnings": ["Stage 5 form proxy uses API-fed bucket stats until dedicated form API mapping exists."],
            "confidence_adjustment": "downgrade",
            "stake_adjustment": "none",
            "decision_override": None,
        }
