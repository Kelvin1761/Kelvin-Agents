from __future__ import annotations

from tennis_wc.agents.base_agent import BaseAgent


class FatigueInjuryAgent(BaseAgent):
    name = "fatigue_injury"

    def review(self, feature_snapshot: dict, pricing: dict | None = None, filter_result: dict | None = None) -> dict:
        # Injury override removed 2026-07-12 (Phase 3): no injury data source
        # is wired (feature_builder hardcodes risk=UNKNOWN), so the old D/E
        # NO_BET override could never fire. This agent now only states the
        # honest data gap; fatigue itself is priced by the model's
        # fatigue_edge nudge.
        return {
            "agent": self.name,
            "edge": "Neutral",
            "key_points": ["Fatigue and injury data are only read from structured snapshot fields."],
            "warnings": ["Injury/news status is UNKNOWN — no injury data source is wired."],
            "confidence_adjustment": "downgrade",
            "stake_adjustment": "reduce",
            "decision_override": None,
        }
