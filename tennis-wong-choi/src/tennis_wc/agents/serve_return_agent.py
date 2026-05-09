from __future__ import annotations

from tennis_wc.agents.base_agent import BaseAgent, edge_label, value


class ServeReturnAgent(BaseAgent):
    name = "serve_return"

    def review(self, feature_snapshot: dict, pricing: dict | None = None, filter_result: dict | None = None) -> dict:
        player_a = feature_snapshot["player_a"]
        player_b = feature_snapshot["player_b"]
        stats_a = player_a.get("tournament_level_stats", {})
        stats_b = player_b.get("tournament_level_stats", {})
        score_a = _score(stats_a)
        score_b = _score(stats_b)
        warnings = []
        if score_a is None:
            warnings.append(f"{player_a['name']} serve/return stats incomplete.")
        if score_b is None:
            warnings.append(f"{player_b['name']} serve/return stats incomplete.")
        return {
            "agent": self.name,
            "edge": edge_label(score_a, score_b, player_a["name"], player_b["name"]),
            "key_points": [
                f"{player_a['name']} hold/break proxy: {score_a}",
                f"{player_b['name']} hold/break proxy: {score_b}",
            ],
            "warnings": warnings,
            "confidence_adjustment": "downgrade" if warnings else "none",
            "stake_adjustment": "none",
            "decision_override": None,
        }


def _score(stats: dict) -> float | None:
    hold = value(stats.get("hold_rate"))
    brk = value(stats.get("break_rate"))
    if hold is None or brk is None:
        return None
    return round((hold + brk) / 2, 4)
