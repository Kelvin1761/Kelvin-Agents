"""Evidence gates for turning priced tennis props into recommendations.

Pricing and recommending are deliberately separate.  A model may display a
positive-EV estimate while its live sample is still too small to justify a bet.
These thresholds are pre-registered guardrails, not parameters tuned to today's
ROI table.
"""
from __future__ import annotations

MIN_RAW_SCORECARD = 120
MIN_FAMILY_SETTLED = 50
MIN_LEG_PROBABILITY = 0.58
# feature_snapshots stores a 0-100 score in production (the existing hard
# no-bet contract is 65), while a few older tests/exports use 0-1.  Keep the
# strategy threshold normalised and convert at the boundary.
MIN_DATA_QUALITY = 0.65
MIN_LEG_ODDS = 1.30
MAX_LEG_ODDS = 2.25
MAX_FORMAL_COMBO_LEGS = 2
MIN_COMBO_EV = 0.03
MIN_CONFIDENCE_SCORE = 70
MAX_SINGLE_STAKE_UNITS = 2.0
MAX_COMBO_STAKE_UNITS = 1.0
STAKE_ROUND_UNITS = 0.5
SUPPORTED_FAMILIES = {
    "player_aces",
    "match_total_aces",
    "player_double_faults",
    "player_total_games",
    "player_win_a_set",
    "first_set_winner",
    "player_game_handicap",
    "player_set_handicap",
    "player_exact_set_score",
}
# Match totals stay on the research scorecard, but the recommendation contract
# is intentionally player-level.  This reflects both the product direction and
# the current evidence: player aces beat the market Brier while match-total
# aces do not.
RECOMMENDABLE_PLAYER_FAMILIES = SUPPORTED_FAMILIES - {"match_total_aces"}


def family_for_market(market_key: str) -> str:
    from tennis_wc.props.registry import family_for_market as classify
    return classify(market_key)


def normalise_data_quality(value) -> float:
    try:
        quality = float(value)
    except (TypeError, ValueError):
        return 0.0
    if quality > 1.0:
        quality /= 100.0
    return max(0.0, min(1.0, quality))


def confidence_score(leg: dict, gate: dict) -> int:
    """Reliability of the probability estimate, not chance of winning.

    Hit probability and confidence used to be the same number.  This score
    instead combines source quality, family sample maturity and whether the
    odds-blind model actually improves on the market.  A 70% hit estimate can
    therefore carry low confidence when it comes from a thin/new family.
    """
    quality = normalise_data_quality(leg.get("data_quality"))
    family = family_for_market(leg.get("market_key") or "")
    state = (gate.get("family_states") or {}).get(family) or {}
    if not state and family in set(gate.get("enabled_families") or []):
        # Backward-compatible stored/test gate: an already-enabled family from
        # the old payload has implicitly passed the family evidence checks.
        return round(100 * quality)
    evidence = min(1.0, float(state.get("scorecard_settled") or 0) / MIN_RAW_SCORECARD)
    try:
        advantage = float(state["market_brier"]) - float(state["model_brier"])
        skill = max(0.0, min(1.0, 0.5 + advantage / 0.04))
    except (KeyError, TypeError, ValueError):
        skill = 0.25
    return round(100 * (0.45 * quality + 0.35 * evidence + 0.20 * skill))


def formal_stake_units(
    probability: float,
    odds: float,
    formula_confidence: float,
    *,
    combo: bool = False,
) -> float:
    """Confidence-haircut tenth-Kelly stake for a validated recommendation.

    Research scorekeeping remains flat 1u so formula comparisons are fair.
    Once a family clears the evidence gate, this sizes the displayed bet using
    the calibrated hit probability, then discounts it by formula reliability.
    Singles are capped at 2u and higher-variance two-leg combos at 1u.
    """
    try:
        p = float(probability)
        price = float(odds)
        reliability = max(0.0, min(1.0, float(formula_confidence) / 100.0))
    except (TypeError, ValueError):
        return 0.0
    if not 0 < p < 1 or price <= 1 or reliability < MIN_CONFIDENCE_SCORE / 100:
        return 0.0
    net_odds = price - 1.0
    full_kelly = (p * price - 1.0) / net_odds
    if full_kelly <= 0:
        return 0.0
    units = full_kelly * 0.10 * 100.0 * reliability
    cap = MAX_COMBO_STAKE_UNITS if combo else MAX_SINGLE_STAKE_UNITS
    units = min(cap, units)
    # A validated positive-EV bet can use a half-unit probe, but rounding must
    # never lift it above the risk cap.
    units = max(STAKE_ROUND_UNITS, units)
    units = round(units / STAKE_ROUND_UNITS) * STAKE_ROUND_UNITS
    return min(cap, round(units, 2))


def recommendation_gate(scorecard: dict | None, roi: dict | None) -> dict:
    """Return an auditable strategy state and the families allowed to bet.

    Formal recommendations require:
      * enough odds-blind model outcomes;
      * model Brier beating market Brier by a small fixed margin;
      * enough settled bets in the specific market family; and
      * positive realised family ROI.

    Until all four pass, signals stay on the observation board and may still be
    tracked for research, but they cannot reach the headline betting card.
    """
    scorecard = scorecard or {}
    roi = roi or {}
    raw_n = int(scorecard.get("settled") or 0)
    reasons: list[str] = []

    enabled: list[str] = []
    family_states: dict[str, dict] = {}
    # Prefer ROI from the exact live-eligible profile.  The fallback preserves
    # compatibility with old stored/test summaries that predate segmentation.
    by_family = (
        roi.get("by_family_formal_profile")
        if "by_family_formal_profile" in roi
        else roi.get("by_family")
    ) or {}
    score_by_family = scorecard.get("by_family") or {}
    for family in sorted(SUPPORTED_FAMILIES):
        stats = by_family.get(family) or {}
        family_score = score_by_family.get(family) or {}
        score_settled = int(family_score.get("settled") or 0)
        roi_settled = int(stats.get("settled") or 0)
        family_roi = stats.get("roi")
        try:
            model_beats_market = (
                float(family_score["model"]["brier"])
                <= float(family_score["market"]["brier"]) - 0.005
            )
        except (KeyError, TypeError, ValueError):
            model_beats_market = False
        qualified = (
            family in RECOMMENDABLE_PLAYER_FAMILIES
            and score_settled >= MIN_RAW_SCORECARD
            and model_beats_market
            and roi_settled >= MIN_FAMILY_SETTLED
            and family_roi is not None
            and float(family_roi) > 0
        )
        family_states[family] = {
            "enabled": qualified,
            "recommendable_player_prop": family in RECOMMENDABLE_PLAYER_FAMILIES,
            "settled": roi_settled,
            "scorecard_settled": score_settled,
            "roi": family_roi,
            "minimum_settled": MIN_FAMILY_SETTLED,
            "minimum_scorecard": MIN_RAW_SCORECARD,
            "model_beats_market": model_beats_market,
            "model_brier": (family_score.get("model") or {}).get("brier"),
            "market_brier": (family_score.get("market") or {}).get("brier"),
        }
        if qualified:
            enabled.append(family)

    if not enabled:
        reasons.append(
            "未有 player-prop family 同時達到 family 級記分卡、"
            f"{MIN_FAMILY_SETTLED} 注已結算兼正 ROI"
        )
    return {
        "status": "VALIDATED_SINGLE" if enabled else "RESEARCH_ONLY",
        "recommendations_enabled": bool(enabled),
        "enabled_families": enabled,
        "family_states": family_states,
        "raw_scorecard_settled": raw_n,
        "reasons": reasons,
    }


def leg_is_formal_candidate(leg: dict, gate: dict) -> bool:
    """Apply fixed per-leg limits after the evidence gate has passed."""
    if family_for_market(leg.get("market_key") or "") not in set(gate.get("enabled_families") or []):
        return False
    try:
        probability = float(leg["prob"])
        odds = float(leg["odds"])
        data_quality = normalise_data_quality(leg["data_quality"])
    except (KeyError, TypeError, ValueError):
        return False
    return (
        MIN_LEG_PROBABILITY <= probability <= 1.0
        and data_quality >= MIN_DATA_QUALITY
        and MIN_LEG_ODDS <= odds <= MAX_LEG_ODDS
        and float(leg.get("edge") or 0) > 0
        and float(leg.get("ev") or 0) > 0
        and confidence_score(leg, gate) >= MIN_CONFIDENCE_SCORE
    )
