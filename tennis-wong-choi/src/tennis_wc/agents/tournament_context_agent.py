from __future__ import annotations

from tennis_wc.agents.base_agent import BaseAgent, edge_label, pct, sample, value


class TournamentContextAgent(BaseAgent):
    name = "tournament_context"

    def review(self, feature_snapshot: dict, pricing: dict | None = None, filter_result: dict | None = None) -> dict:
        context = feature_snapshot["match_context"]
        player_a = feature_snapshot["player_a"]
        player_b = feature_snapshot["player_b"]
        stats_a = player_a.get("tournament_level_stats", {})
        stats_b = player_b.get("tournament_level_stats", {})
        rate_a = value(stats_a.get("shrinked_win_rate")) or value(stats_a.get("win_rate"))
        rate_b = value(stats_b.get("shrinked_win_rate")) or value(stats_b.get("win_rate"))
        sample_a = sample(stats_a)
        sample_b = sample(stats_b)
        warnings = []
        if sample_a is None or sample_a < 10:
            warnings.append(f"{player_a['name']} tournament-level sample is low.")
        if sample_b is None or sample_b < 10:
            warnings.append(f"{player_b['name']} tournament-level sample is low.")
        return {
            "agent": self.name,
            "edge": edge_label(rate_a, rate_b, player_a["name"], player_b["name"]),
            "key_points": [
                f"Current level: {value(context.get('level'))}",
                f"{player_a['name']} level record: {pct(rate_a)}, sample {sample_a}",
                f"{player_b['name']} level record: {pct(rate_b)}, sample {sample_b}",
            ],
            "warnings": warnings,
            "confidence_adjustment": "downgrade" if warnings else "none",
            "stake_adjustment": "reduce" if warnings else "none",
            "decision_override": None,
        }
