from __future__ import annotations

from tennis_wc.agents.base_agent import BaseAgent


class FatigueInjuryAgent(BaseAgent):
    name = "fatigue_injury"

    def review(self, feature_snapshot: dict, pricing: dict | None = None, filter_result: dict | None = None) -> dict:
        selection_side = (pricing or {}).get("selection_side")
        warnings = ["Injury/news status is UNKNOWN in current Stage 5 MVP."]
        override = None
        if selection_side in {"player_a", "player_b"}:
            injury_risk = feature_snapshot.get(selection_side, {}).get("injury", {}).get("risk", "UNKNOWN")
            if injury_risk in {"D", "E"}:
                override = "NO_BET"
                warnings.append("Selected player injury risk is D/E.")
        return {
            "agent": self.name,
            "edge": "Neutral",
            "key_points": ["Fatigue and injury data are only read from structured snapshot fields."],
            "warnings": warnings,
            "confidence_adjustment": "downgrade",
            "stake_adjustment": "reduce",
            "decision_override": override,
        }
