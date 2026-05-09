from __future__ import annotations

from tennis_wc.agents.base_agent import BaseAgent, edge_label, value


class SurfaceAgent(BaseAgent):
    name = "surface"

    def review(self, feature_snapshot: dict, pricing: dict | None = None, filter_result: dict | None = None) -> dict:
        player_a = feature_snapshot["player_a"]
        player_b = feature_snapshot["player_b"]
        elo_a = value(player_a.get("surface_elo"))
        elo_b = value(player_b.get("surface_elo"))
        return {
            "agent": self.name,
            "edge": edge_label(elo_a, elo_b, player_a["name"], player_b["name"]),
            "key_points": [
                f"Surface: {value(feature_snapshot['match_context'].get('surface'))}",
                f"{player_a['name']} surface Elo: {elo_a}",
                f"{player_b['name']} surface Elo: {elo_b}",
            ],
            "warnings": [] if elo_a is not None and elo_b is not None else ["Missing surface Elo."],
            "confidence_adjustment": "none" if elo_a is not None and elo_b is not None else "downgrade",
            "stake_adjustment": "none",
            "decision_override": None,
        }
