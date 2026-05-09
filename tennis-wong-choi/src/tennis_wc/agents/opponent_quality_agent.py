from __future__ import annotations

from tennis_wc.agents.base_agent import BaseAgent, edge_label, pct, sample, value
from tennis_wc.modelling.probability_model import select_relevant_rank_bucket


class OpponentQualityAgent(BaseAgent):
    name = "opponent_quality"

    def review(self, feature_snapshot: dict, pricing: dict | None = None, filter_result: dict | None = None) -> dict:
        player_a = feature_snapshot["player_a"]
        player_b = feature_snapshot["player_b"]
        rank_a = value(player_a.get("current_rank"))
        rank_b = value(player_b.get("current_rank"))
        bucket_a = select_relevant_rank_bucket(rank_b)
        bucket_b = select_relevant_rank_bucket(rank_a)
        stats_a = player_a.get("opponent_rank_buckets", {}).get(bucket_a, {})
        stats_b = player_b.get("opponent_rank_buckets", {}).get(bucket_b, {})
        rate_a = value(stats_a.get("shrinked_win_rate")) or value(stats_a.get("win_rate"))
        rate_b = value(stats_b.get("shrinked_win_rate")) or value(stats_b.get("win_rate"))
        sample_a = sample(stats_a)
        sample_b = sample(stats_b)
        warnings = []
        if sample_a is None or sample_a < 10:
            warnings.append("Player A relevant rank-bucket sample is low; treat as weak evidence.")
        if sample_b is None or sample_b < 10:
            warnings.append("Player B relevant rank-bucket sample is low; treat as weak evidence.")
        return {
            "agent": self.name,
            "edge": edge_label(rate_a, rate_b, player_a["name"], player_b["name"]),
            "key_points": [
                f"{player_a['name']} vs {bucket_a}: {pct(rate_a)}, sample {sample_a}",
                f"{player_b['name']} vs {bucket_b}: {pct(rate_b)}, sample {sample_b}",
                "Relevant buckets are selected from opponent current ranking; historical match buckets use rankings at match date.",
            ],
            "warnings": warnings,
            "confidence_adjustment": "downgrade" if warnings else "none",
            "stake_adjustment": "reduce" if warnings else "none",
            "decision_override": None,
        }
