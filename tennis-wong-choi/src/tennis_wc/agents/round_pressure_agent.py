from __future__ import annotations

from tennis_wc.agents.base_agent import BaseAgent, edge_label, pct, sample, value


class RoundPressureAgent(BaseAgent):
    name = "round_pressure"

    def review(self, feature_snapshot: dict, pricing: dict | None = None, filter_result: dict | None = None) -> dict:
        player_a = feature_snapshot["player_a"]
        player_b = feature_snapshot["player_b"]
        round_name = value(feature_snapshot["match_context"].get("round"))
        round_a = player_a.get("round_stats", {})
        round_b = player_b.get("round_stats", {})
        big_a = player_a.get("big_match_stats", {})
        big_b = player_b.get("big_match_stats", {})
        rate_a = value(round_a.get("shrinked_win_rate")) or value(round_a.get("win_rate"))
        rate_b = value(round_b.get("shrinked_win_rate")) or value(round_b.get("win_rate"))
        warnings = []
        if (sample(round_a) or 0) < 10:
            warnings.append(f"{player_a['name']} round sample is low.")
        if (sample(round_b) or 0) < 10:
            warnings.append(f"{player_b['name']} round sample is low.")
        return {
            "agent": self.name,
            "edge": edge_label(rate_a, rate_b, player_a["name"], player_b["name"]),
            "key_points": [
                f"Current round: {round_name}",
                f"{player_a['name']} round record: {pct(rate_a)}, big-match record: {pct(value(big_a.get('win_rate')))}",
                f"{player_b['name']} round record: {pct(rate_b)}, big-match record: {pct(value(big_b.get('win_rate')))}",
            ],
            "warnings": warnings,
            "confidence_adjustment": "downgrade" if warnings else "none",
            "stake_adjustment": "reduce" if warnings else "none",
            "decision_override": None,
        }
