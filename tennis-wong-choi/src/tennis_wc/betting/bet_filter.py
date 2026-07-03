from __future__ import annotations

from tennis_wc.betting.staking import stake_for_decision
from tennis_wc.config import get_settings

# Backtest-driven NO_BET cutoffs (see apply_bet_filter). Perceived edge at/above
# this is an artifact (model-vs-sharp-market disagreement) that loses long-term;
# decimal odds at/above the longshot cutoff bleed ~-37% ROI vs the closing line.
_EDGE_ARTIFACT_NO_BET = 0.20
_LONGSHOT_NO_BET_ODDS = 5.0


def classify_edge(edge: float | None) -> str:
    if edge is None:
        return "NO_BET"
    if edge < 0.02:
        return "NO_BET"
    if edge < 0.035:
        return "WATCHLIST"
    if edge < 0.05:
        return "SMALL_BET"
    if edge < 0.08:
        return "STANDARD_BET"
    return "STRONG_BET"


def apply_bet_filter(feature_snapshot: dict, pricing: dict) -> dict:
    quality = feature_snapshot.get("data_quality", {})
    errors = list(quality.get("errors", [])) + list(pricing.get("errors", []))
    warnings = list(quality.get("warnings", []))
    hard_no_bet_reasons: list[str] = []
    risk_adjustments: list[str] = []

    if quality.get("score", 0) < 65:
        hard_no_bet_reasons.append("data_quality_score_below_65")
    if not quality.get("is_valid", False):
        hard_no_bet_reasons.append("data_provenance_validation_failed")
    if pricing.get("current_market_odds") is None:
        hard_no_bet_reasons.append("missing_market_odds")
    elif pricing["current_market_odds"] < pricing.get("minimum_acceptable_odds", 999):
        hard_no_bet_reasons.append("current_odds_below_minimum_acceptable_odds")
    elif pricing["current_market_odds"] >= 5.0 and quality.get("score", 0) < 80:
        hard_no_bet_reasons.append("longshot_requires_higher_data_quality")
    model_warnings = _model_warnings(pricing)
    if "missing_surface_elo" in model_warnings or "missing_overall_elo" in model_warnings:
        hard_no_bet_reasons.append("missing_core_elo_inputs")
    if any("LLM" in error or "llm" in error for error in errors):
        hard_no_bet_reasons.append("llm_generated_stat_detected")
    if "odds_selection_mapping_failed" in errors:
        hard_no_bet_reasons.append("odds_selection_mapping_failed")

    injury_risk = _injury_risk(feature_snapshot, pricing.get("selection_side"))
    if injury_risk in {"D", "E"}:
        hard_no_bet_reasons.append("injury_risk_hard_no_bet")
    if injury_risk == "B":
        risk_adjustments.append("injury_B")
    if injury_risk == "C":
        risk_adjustments.append("injury_C")
    if any("low_sample" in warning for warning in warnings):
        risk_adjustments.append("low_sample")
    if any("stale" in warning for warning in warnings):
        risk_adjustments.append("stale_but_acceptable")
    if "rank_seed_elo" in model_warnings:
        risk_adjustments.append("rank_seed_elo")

    edge_decision = classify_edge(pricing.get("edge"))
    decision_band = "NO_BET" if hard_no_bet_reasons else edge_decision
    stake = stake_for_decision(
        decision_band,
        model_probability=pricing.get("model_probability"),
        decimal_odds=pricing.get("current_market_odds"),
        risk_adjustments=risk_adjustments,
    )
    # Half-Kelly returns 0 when the pick is not +EV at the actual (vigged) price,
    # even if it cleared the no-vig edge gate. Such a bet should not be placed.
    if decision_band in {"SMALL_BET", "STANDARD_BET", "STRONG_BET"} and stake <= 0:
        hard_no_bet_reasons.append("negative_ev_at_market_price")
        decision_band = "NO_BET"
    # Backtest-driven NO_BET gates. External walk-forward backtest (10,643 bets,
    # 2022-24, vs Pinnacle closing) shows the model has NO profitable subset and
    # that two zones bleed badly with large, monotonic samples:
    #   * perceived edge >= 20%  -> ROI -17.5%, and >= 30% -> -27.2%
    #   * decimal odds   >= 5.0  -> ROI -36.6% (1974 bets)
    # These are not real value -- the model is simply wrong when it disagrees this
    # much with the close. Refuse them outright (user-approved: no-bet the losers).
    # Remaining bets are still ~-5..-10% vs close, so the surviving rank-fallback
    # picks are kept at minimum stake only (live reliability hygiene).
    edge_val = pricing.get("edge") or 0
    odds_val = pricing.get("current_market_odds") or 0
    if decision_band in {"SMALL_BET", "STANDARD_BET", "STRONG_BET"}:
        if edge_val >= _EDGE_ARTIFACT_NO_BET:
            hard_no_bet_reasons.append("edge_artifact_no_bet")
            decision_band = "NO_BET"
            stake = 0.0
        elif odds_val >= _LONGSHOT_NO_BET_ODDS:
            hard_no_bet_reasons.append("longshot_negative_roi_no_bet")
            decision_band = "NO_BET"
            stake = 0.0
        elif "rank_seed_elo" in risk_adjustments and stake > get_settings().min_stake_units:
            risk_adjustments.append("rank_seed_destaked")
            stake = get_settings().min_stake_units
    # Confidence must NOT be inflated by perceived edge. The external backtest
    # (6934 bets, 2023-24 vs Pinnacle closing) shows the model's edge has no
    # predictive value (ROI ~-10% at every edge band), so a large edge is a sign
    # of model-vs-sharp-market disagreement (often rank-fallback Elo), not of a
    # reliable pick. Cap the edge contribution so a huge artifact edge can't mint
    # a "92 confidence". A BET already requires data-quality >= 65, so this cap
    # never changes which bets qualify -- it only makes the number honest.
    edge_bonus = min(max((pricing.get("edge") or 0), 0), 0.10) * 100
    confidence = max(0, min(100, int(quality.get("score", 0) + edge_bonus)))
    if "rank_seed_elo" in risk_adjustments:
        confidence = max(0, confidence - 8)
    if decision_band in {"SMALL_BET", "STANDARD_BET", "STRONG_BET"} and confidence < 65:
        hard_no_bet_reasons.append("confidence_below_bet_floor")
        decision_band = "NO_BET"
        stake = 0.0
    return {
        "decision": "BET" if decision_band in {"SMALL_BET", "STANDARD_BET", "STRONG_BET"} else decision_band,
        "decision_band": decision_band,
        "stake_units": stake,
        "confidence": confidence,
        "risk": _risk_label(confidence, warnings, hard_no_bet_reasons),
        "hard_no_bet_reasons": hard_no_bet_reasons,
        "risk_adjustments": sorted(set(risk_adjustments)),
        "warnings": warnings,
        "errors": errors,
    }


def _injury_risk(feature_snapshot: dict, selection_side: str | None) -> str:
    if selection_side not in {"player_a", "player_b"}:
        return "UNKNOWN"
    injury = feature_snapshot.get(selection_side, {}).get("injury", {})
    return injury.get("risk", "UNKNOWN")


def _model_warnings(pricing: dict) -> set[str]:
    warnings = set()
    for component in pricing.get("model", {}).get("components", []):
        warnings.update(component.get("warnings", []))
    return warnings


def _risk_label(confidence: int, warnings: list[str], hard_no_bet_reasons: list[str]) -> str:
    if hard_no_bet_reasons:
        return "High"
    if confidence >= 80 and not warnings:
        return "Low"
    if confidence >= 65:
        return "Medium"
    return "High"
