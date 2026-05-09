from __future__ import annotations

from tennis_wc.agents.base_agent import BaseAgent


class DataQualityAgent(BaseAgent):
    name = "data_quality"

    def review(self, feature_snapshot: dict, pricing: dict | None = None, filter_result: dict | None = None) -> dict:
        quality = feature_snapshot.get("data_quality", {})
        return {
            "agent": self.name,
            "edge": "Neutral",
            "key_points": [
                f"Data quality score: {quality.get('score')}",
                f"Validation valid: {quality.get('is_valid')}",
                f"Errors: {len(quality.get('errors', []))}",
            ],
            "warnings": quality.get("warnings", [])[:12],
            "confidence_adjustment": "downgrade" if quality.get("score", 0) < 80 else "none",
            "stake_adjustment": "reduce" if quality.get("warnings") else "none",
            "decision_override": "NO_BET" if not quality.get("is_valid", False) else None,
        }
