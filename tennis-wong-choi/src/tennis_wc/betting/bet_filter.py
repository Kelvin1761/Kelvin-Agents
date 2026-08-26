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


def _context_value(feature_snapshot: dict, key: str) -> str:
    """One `match_context` field, unwrapped.

    Every entry is a datapoint wrapper, so a plain `.get(key)` returns the
    wrapper and any string test on it silently reads UNKNOWN.
    """
    context = feature_snapshot.get("match_context") or {}
    entry = context.get(key)
    if isinstance(entry, dict):
        return str(entry.get("value") or "")
    return str(entry or "")


def apply_bet_filter(feature_snapshot: dict, pricing: dict) -> dict:
    quality = feature_snapshot.get("data_quality", {})
    errors = list(quality.get("errors", [])) + list(pricing.get("errors", []))
    warnings = list(quality.get("warnings", []))
    hard_no_bet_reasons: list[str] = []
    risk_adjustments: list[str] = []

    # The props path refuses ITF and UTR outright, on 482 settled fixtures where
    # our match probability scored Brier 0.2330 against the market's 0.1838
    # (bootstrapped gap +0.0492, CI [+0.035, +0.063]). That evidence is about
    # the match probability itself, and the match-winner path never got it: 165
    # of 472 BET decisions in the record are ITF and 13 are UTR, together 38% of
    # everything the filter passed.
    #
    # Justified on consistency with that decision, not on its own ROI. The
    # match-winner ROI comparison is underpowered -- ITF BET decisions read
    # -13.65% (CI [-32.74, +5.87]) and the surviving allow-listed subset +3.20%
    # (CI [-15.66, +22.21]) on n=166 -- so it supports the direction and settles
    # nothing by itself. Nothing is staked either way: `bet_ledger` and
    # `prop_live_bets` are both empty.
    # The structured level is passed, not just the name. 26 of the tournaments
    # the filter passed carry a bare external id as their "name" (`421-2026`,
    # `188-2026`) covering 390 BET decisions, and `tournament_levels.level`
    # knows those are GRAND_SLAM, ATP_1000 and ATP_250 -- so a name-only test
    # would refuse the best events on the board. Same defect `_tier_of` was
    # given its `level` argument for; the props path passes it and this one has
    # to as well.
    from tennis_wc.props.daily import _tier_bettable, _tier_of

    tournament = _context_value(feature_snapshot, "tournament")
    level = _context_value(feature_snapshot, "level")
    if not _tier_bettable(tournament, level):
        tier = _tier_of(tournament, level).lower()
        hard_no_bet_reasons.append(f"tier_not_bettable_{tier}")

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
    # Rank joins Elo as a hard input requirement.
    #
    # The model has 168 feature leaves and 164 of them are one signal -- past
    # results -- re-sliced; only Elo, surface Elo, rest days and rank carry
    # independent information. Without them it still emits a number, and 27% of
    # predictions land within 0.05 of 0.5 (the market: 12.9%) because that
    # number is the combiner declining to have a view. A no-opinion 0.5 is
    # indistinguishable on the page from an informed 0.5.
    #
    # Gated for measurement before profit: on the 49.5% of fixtures where all
    # the independent inputs are present the model draws level with the market
    # (Delta log-loss +0.0161, CI [-0.0063, +0.0379]); on the rest it loses by
    # +0.0639. Mixing the two into one ROI is what makes that question
    # unanswerable, and the forward window this is meant to measure opens
    # 2026-08-28.
    #
    # Named separately from `data_quality_score_below_65`: "we hold nothing to
    # price this with" and "what we hold looks thin" call for different fixes,
    # and folding them together is how the rank gap stayed invisible for months.
    if any(w.startswith("missing_current_rank") for w in model_warnings):
        hard_no_bet_reasons.append("missing_rank_inputs")
    if any("LLM" in error or "llm" in error for error in errors):
        hard_no_bet_reasons.append("llm_generated_stat_detected")
    if "odds_selection_mapping_failed" in errors:
        hard_no_bet_reasons.append("odds_selection_mapping_failed")

    # Injury gates removed 2026-07-12 (Phase 3): no news/injury provider is
    # wired, feature_builder hardcodes risk=UNKNOWN, so the old D/E hard gate
    # and B/C de-staking could never fire — dead scaffolding, not safety.
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
