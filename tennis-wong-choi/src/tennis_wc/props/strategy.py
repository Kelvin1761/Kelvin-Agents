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
MIN_DATA_QUALITY = 0.80
MIN_LEG_ODDS = 1.30
MAX_LEG_ODDS = 2.25
MIN_COMBO_ODDS = 2.00
MAX_FORMAL_COMBO_LEGS = 2
SUPPORTED_FAMILIES = {"player_aces", "match_total_aces"}


def family_for_market(market_key: str) -> str:
    key = str(market_key or "")
    if key.startswith("total_match_games"):
        return "match_total_games"
    if key.startswith("total_aces") or key == "total_aces_in_the_match":
        return "match_total_aces"
    if "_aces" in key:
        return "player_aces"
    return key


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
    model = scorecard.get("model") or {}
    market = scorecard.get("market") or {}
    reasons: list[str] = []

    if raw_n < MIN_RAW_SCORECARD:
        reasons.append(f"raw 記分卡 {raw_n}/{MIN_RAW_SCORECARD}")
    try:
        model_beats_market = float(model["brier"]) <= float(market["brier"]) - 0.005
    except (KeyError, TypeError, ValueError):
        model_beats_market = False
    if not model_beats_market:
        reasons.append("模型 Brier 未明顯優於市場")

    enabled: list[str] = []
    family_states: dict[str, dict] = {}
    by_family = roi.get("by_family") or {}
    for family in sorted(SUPPORTED_FAMILIES):
        stats = by_family.get(family) or {}
        settled = int(stats.get("settled") or 0)
        family_roi = stats.get("roi")
        qualified = (
            raw_n >= MIN_RAW_SCORECARD
            and model_beats_market
            and settled >= MIN_FAMILY_SETTLED
            and family_roi is not None
            and float(family_roi) > 0
        )
        family_states[family] = {
            "enabled": qualified,
            "settled": settled,
            "roi": family_roi,
            "minimum_settled": MIN_FAMILY_SETTLED,
        }
        if qualified:
            enabled.append(family)

    if not enabled:
        reasons.append(
            "aces 分類未同時達到 "
            f"{MIN_FAMILY_SETTLED} 注已結算兼正 ROI"
        )
    return {
        "status": "VALIDATED" if enabled else "RESEARCH_ONLY",
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
        data_quality = float(leg["data_quality"])
    except (KeyError, TypeError, ValueError):
        return False
    return (
        MIN_LEG_PROBABILITY <= probability <= 1.0
        and data_quality >= MIN_DATA_QUALITY
        and MIN_LEG_ODDS <= odds <= MAX_LEG_ODDS
        and float(leg.get("edge") or 0) > 0
        and float(leg.get("ev") or 0) > 0
    )
