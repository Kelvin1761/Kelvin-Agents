"""Evidence gates for turning priced tennis props into recommendations.

Pricing and recommending are deliberately separate.  A model may display a
positive-EV estimate while its live sample is still too small to justify a bet.
These thresholds are pre-registered guardrails, not parameters tuned to today's
ROI table.
"""
from __future__ import annotations

MIN_RAW_SCORECARD = 120
MIN_FAMILY_SETTLED = 50
# Full-stake graduation asks whether the family MAKES MONEY, not whether its
# probabilities are better calibrated than the market's.  Those are different
# questions: a family can price worse than the book overall and still profit on
# the slice it actually bets, and requiring the Brier win first meant no family
# could ever graduate -- 0 of 9 cleared it, so the card read "no bet" for two
# months while several families were quietly profitable.  Beating the market on
# Brier is kept as an ALTERNATIVE route, not a precondition.
MAX_LOSS_PROBABILITY = 0.10
# Bankroll protection is part of the contract, not a report footnote: a family
# whose settled equity curve has already dug this deep is demoted regardless of
# its headline ROI.
MAX_FAMILY_DRAWDOWN_UNITS = -25.0
# 2.1 -- which families may be staked at go-live. Decided 2026-08-11.
#
# The gate above judges each family on its own evidence, and all four current
# families clear it into EARLY_MAIN. This allowlist is a narrower, deliberate
# choice on top of that, for one reason: the record the gate reads is no longer
# clean out-of-sample. Five selection changes were fitted on it, so a family that
# looks good there may only look good because it was tuned there.
#
# What survives that objection is agreement across POPULATIONS rather than across
# time. The chronological split at 2026-07-30 is a surface split -- the earlier
# window is 38% clay and 38% grass, the later one 74% hard -- so a family
# positive in both is positive on clay/grass AND on hard, which fitting to one
# record does not buy you.
#
#   family                  n     ROI     later window   in both?
#   player_win_a_set      170  +15.30%   +16.48% (52)    YES
#   first_set_winner       30  +33.97%   +30.44% (18)    yes, but 30 bets
#   player_game_handicap  590  +11.45%    -4.13% (98)    NO -- and it is half
#                                                        of all exposure
#   player_set_handicap    16  +30.20%   -100.0% (1)     not evidence at n=16
#
# So: one family to stake, one to probe, two excluded until there is evidence
# that was not fitted. player_game_handicap is excluded precisely BECAUSE it is
# the largest -- carrying half the exposure on the half that loses out of sample
# is how a positive backtest becomes a negative account.
#
# This is reversible and is meant to be revisited on live bets, which are the
# only genuinely out-of-sample ones left.
LIVE_FAMILIES: frozenset[str] = frozenset({
    "player_win_a_set",
    "first_set_winner",
})
# Kelvin's money definition, fixed 2026-08-13 before the first live wager.
# Units remain the model-independent accounting system; this constant is only
# the explicit conversion to the cash amount a person actually stakes.
LIVE_UNIT_VALUE_AUD = 1.0


def live_stake_aud(units: float) -> float:
    return round(float(units) * LIVE_UNIT_VALUE_AUD, 2)


# 2.2 -- the stop rule, pre-registered 2026-08-11 BEFORE the first bet, because a
# stop chosen while losing is not a stop, it is a mood. Reasoning and the full
# simulation table are in docs/STOP_RULE.md; these are the enforceable numbers.
#
# Chosen against the noise rather than picked round. At 0.5u flat over the first
# 200 settled bets, a book with NO edge at all reaches:
#   -10u  24.8% of the time (@1.90) .. 43.2% (@2.40)   -> unusable, fires on
#                                                         "not winning yet"
#   -15u   4.3% .. 12.8%
#   -20u   0.5% ..  2.8%                               <- chosen
#   -25u   0.1% ..  0.4%                               -> effectively never
# The two allowlisted families' own worst peak-to-trough in the whole record is
# -17.82u at flat 1u, i.e. -8.91u at this cap, so the stop sits 2.2x outside
# anything they have actually done.
LIVE_STOP_DRAWDOWN_UNITS = -20.0
# Where the question becomes answerable: separating a true +15% ROI from zero at
# 95% needs n ~ (1.96 * 1.0 / 0.15)^2 ~ 171 at a per-bet SD of about one stake
# unit. 200 gives margin, and is roughly six weeks at the replay's ~4.5 value
# bets a day for these two families.
LIVE_REVIEW_AFTER_SETTLED = 200
# An interim PAUSE, not the hard stop. It exists so that a mechanical fault -- a
# broken price lookup, a mis-oriented selection, a renamed market -- cannot be
# mistaken for variance for six weeks. A break-even book trips this about 15% of
# the time, which is an acceptable price for a pause that costs a day of reading.
LIVE_INTERIM_CHECK_SETTLED = 100
LIVE_INTERIM_MIN_ROI = -0.10
# NOTE: MAX_FAMILY_DRAWDOWN_UNITS above is a DIFFERENT quantity -- it is measured
# on the research book, which stakes a flat 1u on every logged prop. Do not
# compare the two numbers; they are denominated in different books.


def live_stop_state(settled: int, pnl_units: float, max_drawdown_units: float | None,
                    roi: float | None) -> dict:
    """Evaluate the pre-registered stop rule against the live book.

    Returns the action and the reason, so that a halt is always accompanied by
    the number that caused it rather than a judgement call made afterwards.
    """
    breaches: list[str] = []
    action = "CONTINUE"
    if max_drawdown_units is not None and max_drawdown_units <= LIVE_STOP_DRAWDOWN_UNITS:
        action = "STOP"
        breaches.append(
            f"drawdown {max_drawdown_units:.2f}u reached the pre-registered stop "
            f"of {LIVE_STOP_DRAWDOWN_UNITS:.1f}u"
        )
    elif (settled >= LIVE_INTERIM_CHECK_SETTLED and roi is not None
            and roi < LIVE_INTERIM_MIN_ROI):
        action = "PAUSE"
        breaches.append(
            f"ROI {roi:.2%} is below {LIVE_INTERIM_MIN_ROI:.0%} at "
            f"{settled} settled bets: look for a mechanical fault before continuing"
        )
    due = settled >= LIVE_REVIEW_AFTER_SETTLED
    return {
        "action": action,
        "breaches": breaches,
        "settled": settled,
        "pnl_units": pnl_units,
        "max_drawdown_units": max_drawdown_units,
        "roi": roi,
        "review_due": due,
        "bets_until_review": max(0, LIVE_REVIEW_AFTER_SETTLED - settled),
    }


LIVE_FAMILY_NOTES: dict[str, str] = {
    "player_win_a_set": "only family positive on both clay/grass and hard",
    "first_set_winner": "positive in both windows but only 30 settled bets",
}


def family_may_be_staked(family: str | None) -> bool:
    """Is this family on the go-live allowlist?

    Separate from the evidence gate on purpose. The gate answers "has this family
    earned a tier"; this answers "are we willing to put money on it on day one",
    and the second is a narrower question while the record it would be judged on
    is one the configuration was fitted to.
    """
    if not family:
        return False
    return str(family) in LIVE_FAMILIES


# The recorded drawdown is measured on the research book, which stakes a flat
# 1u on every logged prop. A family admitted here does not bet that book -- it
# bets at the tier's cap. Judging a 0.5u decision by a 1u drawdown compares two
# different quantities: player_game_handicap's -45.9u over 760 research bets is
# -23.0u at the early tier's half unit, inside the limit rather than outside.
RESEARCH_STAKE_UNITS = 1.0
# The probe tier: enough settled bets that the whole-record profit is credible,
# staked flat at one unit regardless of what the recent window is doing.
PROBE_MIN_FAMILY_SETTLED = 100
MAX_PROBE_STAKE_UNITS = 1.0
# Early-stage accelerator: a genuine player-prop family may reach the main card
# before full validation when probability skill is already visible on a useful
# scorecard and its first live-profile paper bets are profitable.  It remains a
# distinct, reversible tier with a hard half-unit cap.
EARLY_MIN_RAW_SCORECARD = 50
EARLY_MIN_FAMILY_SETTLED = 3
# Superseded by registry.VALUE_PROFILES (kept: older stored payloads and the
# reports still read these as the default family's limits).
MIN_LEG_PROBABILITY = 0.58
# feature_snapshots stores a 0-100 score in production (the existing hard
# no-bet contract is 65), while a few older tests/exports use 0-1.  Keep the
# strategy threshold normalised and convert at the boundary.
MIN_DATA_QUALITY = 0.65
MIN_LEG_ODDS = 1.30
MAX_LEG_ODDS = 2.25
# User-facing card preference, not a value or evidence threshold.  A shorter
# price can still be recommended when it passes the same family/ROI/model gates;
# this only gives an otherwise-qualified 2.00+ single the earlier card slot.
PREFERRED_SINGLE_MIN_ODDS = 2.00
# Ranking-only bonus.  Three EV percentage points lets a similarly valuable
# 2.00+ leg win a scarce card slot, but cannot jump a materially stronger short
# price. It never changes the leg's reported EV or its evidence eligibility.
PREFERRED_SINGLE_EV_BONUS = 0.03
MAX_FORMAL_COMBO_LEGS = 2
MIN_COMBO_EV = 0.03
MIN_CONFIDENCE_SCORE = 70
MAX_SINGLE_STAKE_UNITS = 2.0
MAX_COMBO_STAKE_UNITS = 1.0
MAX_EARLY_STAKE_UNITS = 0.5
STAKE_ROUND_UNITS = 0.5
SUPPORTED_FAMILIES = {
    "player_aces",
    "match_total_aces",
    "player_double_faults",
    "player_total_games",
    "player_win_a_set",
    "first_set_winner",
    "player_first_set_match",
    "player_first_set_game_handicap",
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


def _stake_cap(early: bool, probe: bool, combo: bool) -> float:
    if early:
        return MAX_EARLY_STAKE_UNITS
    if probe:
        return MAX_PROBE_STAKE_UNITS
    return MAX_COMBO_STAKE_UNITS if combo else MAX_SINGLE_STAKE_UNITS


def formal_stake_units(
    probability: float,
    odds: float,
    formula_confidence: float,
    *,
    combo: bool = False,
    early: bool = False,
    probe: bool = False,
    selected: bool = False,
) -> float:
    """Confidence-haircut tenth-Kelly stake for an enabled recommendation.

    Research scorekeeping remains flat 1u so formula comparisons are fair.
    Once a family clears the evidence gate, this sizes the displayed bet using
    the calibrated hit probability, then discounts it by formula reliability.
    Singles are capped at 2u and higher-variance two-leg combos at 1u.  The
    reversible EARLY_MAIN tier is capped at 0.5u for either structure.
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
        # Selection reads the odds-blind model and sizing reads the blended
        # one, so a legitimately selected leg can land on a non-positive
        # blended Kelly -- which printed a recommendation at 0u, a bet nobody
        # can act on.  A selected leg gets the minimum stake and the blend only
        # scales it up from there; an unselected one still sizes to nothing.
        if not selected:
            return 0.0
        cap = _stake_cap(early, probe, combo)
        return min(cap, STAKE_ROUND_UNITS)
    units = full_kelly * 0.10 * 100.0 * reliability
    cap = _stake_cap(early, probe, combo)
    units = min(cap, units)
    # An enabled positive-EV bet can use a half-unit probe, but rounding must
    # never lift it above the risk cap.
    units = max(STAKE_ROUND_UNITS, units)
    units = round(units / STAKE_ROUND_UNITS) * STAKE_ROUND_UNITS
    return min(cap, round(units, 2))


def recommendation_gate(scorecard: dict | None, roi: dict | None) -> dict:
    """Return an auditable strategy state and the families allowed to bet.

    Fully validated recommendations require:
      * enough odds-blind model outcomes;
      * model Brier beating market Brier by a small fixed margin;
      * enough settled bets in the specific market family; and
      * positive realised family ROI.

    A player-level family can enter the reversible EARLY_MAIN tier at 50
    scorecard outcomes and three live-profile paper bets when the same Brier
    advantage and positive ROI tests pass.  It is automatically removed from
    the main card whenever either advantage disappears.
    """
    scorecard = scorecard or {}
    roi = roi or {}
    raw_n = int(scorecard.get("settled") or 0)
    reasons: list[str] = []

    enabled: list[str] = []
    validated: list[str] = []
    early_main: list[str] = []
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
        loss_probability = stats.get("loss_probability")
        drawdown = stats.get("max_drawdown_units")
        profitable = family_roi is not None and float(family_roi) > 0
        def within_drawdown_at(cap: float) -> bool:
            if drawdown is None:
                return True
            scaled = float(drawdown) * (cap / RESEARCH_STAKE_UNITS)
            return scaled > MAX_FAMILY_DRAWDOWN_UNITS

        within_drawdown = within_drawdown_at(MAX_SINGLE_STAKE_UNITS)
        within_early_drawdown = within_drawdown_at(MAX_EARLY_STAKE_UNITS)
        # Two independent ways to earn full stakes, either of which is evidence
        # the profit is not a streak: the realised ROI survives resampling, or
        # the odds-blind model genuinely prices better than the book.  Payloads
        # written before loss_probability existed fall back to the Brier route.
        credible_profit = (
            loss_probability is not None
            and float(loss_probability) <= MAX_LOSS_PROBABILITY
        )
        # A decayed edge still totals positive. Hold a family whose most recent
        # third of settled bets has turned negative, however good the whole
        # record looks -- the out-of-sample split is what surfaced this, and a
        # whole-record bootstrap cannot see it.
        recent_roi = stats.get("recent_roi")
        # Two bars, one per tier, because the whole record already has to clear
        # a bootstrap and applying a weaker standard to the MORE relevant data
        # makes no sense. Full stakes need the recent window to be credibly
        # profitable; the reversible half-unit probe only needs it not to be
        # losing. player_win_a_set sits exactly here: +10.08% over 358 bets but
        # +0.32% over its last 122, which is flat, not an edge.
        recent_not_losing = recent_roi is None or float(recent_roi) >= 0
        recent_loss_probability = stats.get("recent_loss_probability")
        recent_credible = (
            recent_roi is None
            or (float(recent_roi) > 0
                and (recent_loss_probability is None
                     or float(recent_loss_probability) <= MAX_LOSS_PROBABILITY))
        )
        # The percentage-of-history tail above is useful for regime analysis,
        # but it expands forever.  A fixed last-100 formal-bet window is the
        # fast circuit breaker: old profit cannot dilute a current losing run.
        # Missing values preserve compatibility with pre-metric payloads.
        short_term_roi = stats.get("short_term_roi")
        short_term_holds = (
            short_term_roi is None or float(short_term_roi) >= 0
        )
        qualified = (
            family in RECOMMENDABLE_PLAYER_FAMILIES
            and score_settled >= MIN_RAW_SCORECARD
            and roi_settled >= MIN_FAMILY_SETTLED
            and profitable
            and within_drawdown
            and recent_credible
            and short_term_holds
            and (credible_profit or model_beats_market)
        )
        # The early tier is a reversible half-unit probe. Requiring statistical
        # credibility here made it identical to VALIDATED and left its own
        # EARLY_MIN_FAMILY_SETTLED of 3 unreachable: the bootstrap needs 20
        # bets, so any family with 3 to 19 could never enter however it
        # performed. first_set_winner sat there at 15 bets and +33.5%.
        #
        # So below the bootstrap's minimum, EARLY asks only that the record and
        # the recent window are both positive. That is a weaker bar on purpose
        # -- the tier is capped at half a unit and reverts the moment either
        # turns negative -- and it is the only bar a 15-bet family can be held
        # to that is not simply "never".
        too_few_to_resample = loss_probability is None
        early_evidence = (
            credible_profit
            or model_beats_market
            or (too_few_to_resample and profitable
                and recent_roi is not None and float(recent_roi) > 0)
        )
        early_qualified = (
            not qualified
            and family in RECOMMENDABLE_PLAYER_FAMILIES
            and score_settled >= EARLY_MIN_RAW_SCORECARD
            and roi_settled >= EARLY_MIN_FAMILY_SETTLED
            and profitable
            and within_early_drawdown
            and recent_not_losing
            and short_term_holds
            and early_evidence
        )
        # PROBE: a deliberate widening. Holding a family out until every test
        # passes means the card reads "no bet" almost every day, and a system
        # that never bets cannot be learned from. A family with a real settled
        # record and a positive one -- whose profit survives resampling -- may
        # stake one unit even when its RECENT window has turned, on the
        # explicit understanding that the recent number is the warning and the
        # stake is the answer to it. player_win_a_set is the case: +13.08% over
        # 370 bets with P(loss) 2.5%, and -1.60% over its last 133.
        probe_qualified = (
            not qualified
            and not early_qualified
            and family in RECOMMENDABLE_PLAYER_FAMILIES
            and score_settled >= MIN_RAW_SCORECARD
            and roi_settled >= PROBE_MIN_FAMILY_SETTLED
            and profitable
            and credible_profit
            and short_term_holds
            and within_drawdown_at(MAX_PROBE_STAKE_UNITS)
        )
        tier = (
            "VALIDATED" if qualified
            else "EARLY_MAIN" if early_qualified
            else "PROBE" if probe_qualified
            else "RESEARCH_ONLY"
        )
        family_states[family] = {
            "enabled": qualified or early_qualified,
            "tier": tier,
            "validated": qualified,
            "early_main": early_qualified,
            "probe": probe_qualified,
            "recommendable_player_prop": family in RECOMMENDABLE_PLAYER_FAMILIES,
            "settled": roi_settled,
            "scorecard_settled": score_settled,
            "roi": family_roi,
            "minimum_settled": MIN_FAMILY_SETTLED,
            "minimum_scorecard": MIN_RAW_SCORECARD,
            "early_minimum_settled": EARLY_MIN_FAMILY_SETTLED,
            "early_minimum_scorecard": EARLY_MIN_RAW_SCORECARD,
            "model_beats_market": model_beats_market,
            "model_brier": (family_score.get("model") or {}).get("brier"),
            "market_brier": (family_score.get("market") or {}).get("brier"),
            "loss_probability": loss_probability,
            "recent_roi": recent_roi,
            "recent_settled": stats.get("recent_settled"),
            "recent_holds": recent_not_losing,
            "recent_credible": recent_credible,
            "recent_loss_probability": stats.get("recent_loss_probability"),
            "short_term_settled": stats.get("short_term_settled"),
            "short_term_roi": short_term_roi,
            "short_term_loss_probability": stats.get("short_term_loss_probability"),
            "short_term_holds": short_term_holds,
            "credible_profit": credible_profit,
            "max_drawdown_units": drawdown,
            "drawdown_at_early_stake": (
                round(float(drawdown) * MAX_EARLY_STAKE_UNITS / RESEARCH_STAKE_UNITS, 2)
                if drawdown is not None else None
            ),
            "maximum_drawdown_units": MAX_FAMILY_DRAWDOWN_UNITS,
            "maximum_loss_probability": MAX_LOSS_PROBABILITY,
        }
        earned = qualified or early_qualified or probe_qualified
        # The go-live allowlist sits on top of the evidence gate, and it is
        # applied HERE because `enabled_families` is the single place every
        # downstream consumer reads -- recommendations, stake sizing and the
        # reports. Filtering downstream instead would have let one of them keep
        # staking a family the other had dropped.
        family_states[family]["earned_tier"] = bool(earned)
        family_states[family]["on_live_allowlist"] = family_may_be_staked(family)
        if earned and not family_may_be_staked(family):
            family_states[family]["held_back_reason"] = (
                "earned its tier but is not on the go-live allowlist: the record "
                "it was judged on is the one the configuration was fitted to"
            )
        if earned and family_may_be_staked(family):
            enabled.append(family)
        if qualified and family_may_be_staked(family):
            validated.append(family)
        elif early_qualified and family_may_be_staked(family):
            early_main.append(family)

    warnings: list[str] = []
    held_back = sorted(
        family for family, state in family_states.items()
        if state.get("earned_tier") and not state.get("on_live_allowlist")
    )
    if held_back:
        # Loud, not silent. A family that vanishes from the card without saying
        # why is indistinguishable from a family that stopped producing bets.
        warnings.append(
            "以下 family 過咗證據閘但唔喺上線白名單，所以唔落注："
            + "、".join(held_back)
            + "。理由：判斷佢哋嘅記錄，正係當前配置擬合出嚟嘅同一份記錄。"
        )
    if early_main:
        warnings.append(
            "EARLY_MAIN 只代表早期正趨勢：每注上限 0.5u；"
            "ROI 或模型對市場優勢轉負會自動降回 RESEARCH_ONLY"
        )
    if not enabled:
        reasons.append(
            "未有 player-prop family 同時達到 family 級記分卡、"
            f"{MIN_FAMILY_SETTLED} 注已結算兼正 ROI"
            f"（正 ROI 仲要通過重抽檢定 P(ROI≤0)≤{MAX_LOSS_PROBABILITY:.0%}"
            "，或者模型 Brier 贏市場）"
        )
    return {
        "status": (
            "VALIDATED_SINGLE" if validated
            else "EARLY_MAIN" if early_main
            else "RESEARCH_ONLY"
        ),
        "recommendations_enabled": bool(enabled),
        "enabled_families": enabled,
        "validated_families": validated,
        "early_main_families": early_main,
        "family_states": family_states,
        "raw_scorecard_settled": raw_n,
        "reasons": reasons,
        "warnings": warnings,
        "live_allowlist": sorted(LIVE_FAMILIES),
        "held_back_by_allowlist": held_back,
        # A price without a known start time cannot be proven pre-match and
        # cannot produce trustworthy CLV. Research rows may still be logged;
        # the production betting card must refuse them.
        "require_verifiable_start": True,
        "preferred_single_min_odds": PREFERRED_SINGLE_MIN_ODDS,
        "preferred_single_ev_bonus": PREFERRED_SINGLE_EV_BONUS,
    }


def meets_formal_profile(
    market_key: str,
    probability_raw,
    probability_blended,
    odds,
    data_quality,
    edge,
    ev,
) -> bool:
    """The per-leg limits, in ONE place.

    Both halves of the system ask this question -- the pricer when deciding
    what to recommend, and settlement when deciding which settled rows count as
    evidence -- and they had drifted apart again. Settlement was still testing
    the global 0.58 floor against the market-BLENDED probability while
    selection had moved to the family's registered limits against the raw
    model. The result: 396 settled player_win_a_set bets in by_family and zero
    in by_family_formal_profile, so the gate could never see the family it was
    supposed to be judging. This is the same failure the ValueProfile docstring
    describes; it was fixed on the selection side only.
    """
    from tennis_wc.props.registry import value_profile_for_family

    profile = value_profile_for_family(family_for_market(market_key or ""))
    try:
        odds_value = float(odds)
        quality = normalise_data_quality(data_quality)
        probability = float(
            probability_raw if probability_raw is not None else probability_blended
        )
    except (TypeError, ValueError):
        return False
    return (
        profile.min_probability <= probability <= 1.0
        and quality >= MIN_DATA_QUALITY
        and profile.min_odds <= odds_value <= profile.max_odds
        and float(edge or 0) > 0
        and float(ev or 0) > 0
    )


def leg_is_formal_candidate(leg: dict, gate: dict) -> bool:
    """Apply the family's registered per-leg limits after the gate has passed.

    The limits come from ``registry.VALUE_PROFILES`` -- the same definition the
    pricer selects on.  They used to be duplicated as module constants here,
    which is how the gate ended up demanding 50 settled bets inside a window
    the pricer never produced.
    """
    from tennis_wc.props.registry import value_profile_for_family

    family = family_for_market(leg.get("market_key") or "")
    if family not in set(gate.get("enabled_families") or []):
        return False
    try:
        passes = meets_formal_profile(
            leg.get("market_key"),
            leg.get("prob_raw"),
            leg["prob"],
            leg["odds"],
            leg["data_quality"],
            leg.get("edge"),
            leg.get("ev"),
        )
    except KeyError:
        return False
    return passes and confidence_score(leg, gate) >= MIN_CONFIDENCE_SCORE
