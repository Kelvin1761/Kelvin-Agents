from __future__ import annotations

from tennis_wc.agents.data_quality_agent import DataQualityAgent
from tennis_wc.agents.fatigue_injury_agent import FatigueInjuryAgent
from tennis_wc.agents.final_decision_agent import FinalDecisionAgent
from tennis_wc.agents.form_agent import FormAgent
from tennis_wc.agents.market_agent import MarketAgent
from tennis_wc.agents.opponent_quality_agent import OpponentQualityAgent
from tennis_wc.agents.round_pressure_agent import RoundPressureAgent
from tennis_wc.agents.serve_return_agent import ServeReturnAgent
from tennis_wc.agents.surface_agent import SurfaceAgent
from tennis_wc.agents.tournament_context_agent import TournamentContextAgent


AGENTS = [
    DataQualityAgent(),
    FormAgent(),
    SurfaceAgent(),
    OpponentQualityAgent(),
    TournamentContextAgent(),
    RoundPressureAgent(),
    ServeReturnAgent(),
    FatigueInjuryAgent(),
    MarketAgent(),
    FinalDecisionAgent(),
]


def run_agents(feature_snapshot: dict, pricing: dict, filter_result: dict) -> dict:
    reviews = [agent.review(feature_snapshot, pricing, filter_result) for agent in AGENTS]
    overrides = [review.get("decision_override") for review in reviews if review.get("decision_override")]
    final_decision = "NO_BET" if "NO_BET" in overrides else filter_result["decision"]
    return {
        "reviews": reviews,
        "final_decision": final_decision,
        "overrides": overrides,
    }
