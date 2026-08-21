"""Which priced legs become recommendations, and why the rest did not.

Lifted out of ``reports.daily_report``.  That module is 5,000 lines and holds
the rendering, and it also decided what gets bet -- selection quality for ace
families was computed one way there and another way in
``props.settlement.prop_roi_report``.  A reporting layer must not be able to
change which bets exist.
"""
from __future__ import annotations

from datetime import datetime, timezone


# How much of a head start a recommendation has to give you. A pick whose match
# is already under way cannot be placed at the priced market at all; one that
# starts in three minutes cannot realistically be placed either. Measured on
# 2026-08-16: 35.9% of the matches on a card had already started when it was
# pushed, and 42.3% were unplaceable once a one-hour window was required.
MIN_LEAD_MINUTES = 10


def _minutes_until_start(leg: dict, now: datetime) -> float | None:
    """Minutes from ``now`` to the match start; ``None`` when unknown.

    Unknown is NOT the same as started. Only 27-63% of fixtures carry a
    published start time, so treating a missing one as disqualifying would
    throw away most of the card to fix a third of it.
    """
    raw = leg.get("start_time_utc")
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (parsed - now).total_seconds() / 60.0


def recommended_picks(prop: dict | None, now: datetime | None = None) -> dict:
    """Assemble evidence-gated prop picks without legacy category fallbacks."""
    from tennis_wc.props import strategy

    prop = prop or {}
    now = now or datetime.now(timezone.utc)
    picks: dict = {"validated_singles": [], "validated_2_leg": None}
    gate = prop.get("strategy") or {}
    value_legs = []
    started: list[dict] = []
    unverifiable: list[dict] = []
    require_verifiable_start = bool(gate.get("require_verifiable_start"))
    for leg in (prop.get("value_legs") or []):
        if not strategy.leg_is_formal_candidate(leg, gate):
            continue
        lead = _minutes_until_start(leg, now)
        leg = dict(leg)
        leg["minutes_to_start"] = lead
        if lead is None and require_verifiable_start:
            unverifiable.append(leg)
            continue
        if lead is not None and lead < MIN_LEAD_MINUTES:
            started.append(leg)
            continue
        value_legs.append(leg)
    # Reported, not silently dropped: "no bet today" and "the bets all started
    # before you were told" are different days and must not look the same.
    picks["dropped_already_started"] = started
    picks["dropped_unverifiable_start"] = unverifiable
    # Do not disguise correlated same-match exposure as two independent
    # singles. Keep the strongest qualified prop per fixture, max two fixtures.
    selected_singles: list[dict] = []
    selected_matches: set[int] = set()
    preferred_min_odds = float(
        gate.get(
            "preferred_single_min_odds",
            strategy.PREFERRED_SINGLE_MIN_ODDS,
        )
    )
    preferred_ev_bonus = float(
        gate.get(
            "preferred_single_ev_bonus",
            strategy.PREFERRED_SINGLE_EV_BONUS,
        )
    )
    # This is deliberately a soft preference. Every leg here has already
    # passed the same evidence, value and timing contract. Price tier decides
    # which similarly valuable candidates get the two scarce card slots.  A
    # small ranking-only EV bonus cannot let a weak long price jump a materially
    # stronger short price, and it never alters reported EV or staking.
    ordered_legs = sorted(
        value_legs,
        key=lambda v: float(v["ev"]) + (
            preferred_ev_bonus
            if float(v["odds"]) >= preferred_min_odds
            else 0.0
        ),
        reverse=True,
    )
    for leg in ordered_legs:
        match_id = int(leg["match_id"])
        if match_id in selected_matches:
            continue
        leg = dict(leg)
        leg["confidence_score"] = leg.get(
            "confidence_score"
        ) or strategy.confidence_score(leg, gate)
        family_state = (gate.get("family_states") or {}).get(
            strategy.family_for_market(leg.get("market_key") or "")
        ) or {}
        tier = family_state.get("tier")
        early = tier == "EARLY_MAIN"
        leg["strategy_tier"] = {
            "EARLY_MAIN": "EARLY_MAIN_SINGLE",
            "PROBE": "PROBE_SINGLE",
        }.get(tier, "VALIDATED_SINGLE")
        leg["price_preference"] = (
            "PREFERRED_2_PLUS"
            if float(leg["odds"]) >= preferred_min_odds
            else "POSITIVE_EDGE_FALLBACK"
        )
        leg["stake_units"] = strategy.formal_stake_units(
            leg["prob"], leg["odds"], leg["confidence_score"], early=early,
            probe=(tier == "PROBE"), selected=True,
        )
        selected_singles.append(leg)
        selected_matches.add(match_id)
        if len(selected_singles) == 2:
            break
    picks["validated_singles"] = selected_singles
    if not selected_singles:
        picks["blocked_by"] = closest_blocked_legs(prop.get("value_legs") or [], gate)
    allowed_ids = {leg["id"] for leg in value_legs}
    combos = [
        combo for combo in (prop.get("combos") or [])
        if len(combo["legs"]) == strategy.MAX_FORMAL_COMBO_LEGS
        and float(combo["ev"]) >= strategy.MIN_COMBO_EV
        and all(leg["id"] in allowed_ids for leg in combo["legs"])
    ]
    if combos:
        combo = dict(combos[0])
        combo_early = any(
            ((gate.get("family_states") or {}).get(
                strategy.family_for_market(leg.get("market_key") or "")
            ) or {}).get("tier") == "EARLY_MAIN"
            for leg in combo["legs"]
        )
        combo["strategy_tier"] = (
            "EARLY_MAIN_2_LEG" if combo_early else "VALIDATED_2_LEG"
        )
        combo["stake_units"] = strategy.formal_stake_units(
            combo["prob"], combo["odds"],
            min(float(leg.get("confidence_score") or 0) for leg in combo["legs"]),
            combo=True,
            early=combo_early,
            selected=True,
        )
        picks["validated_2_leg"] = combo
    return picks


def closest_blocked_legs(value_legs: list[dict], gate: dict, limit: int = 3) -> list[dict]:
    """Name the single limit that stopped each of the nearest misses.

    An empty card is a legitimate output, which is exactly why it hid a broken
    pipeline for two months: nothing errored, the report printed "no bet" every
    day, and no number said whether a bet could physically have come out. This
    turns that silence into a line you can act on.
    """
    from tennis_wc.props import strategy
    from tennis_wc.props.registry import value_profile_for_family

    enabled = set(gate.get("enabled_families") or [])
    blocked = []
    for leg in value_legs:
        family = strategy.family_for_market(leg.get("market_key") or "")
        if family not in enabled:
            continue
        profile = value_profile_for_family(family)
        try:
            odds = float(leg["odds"])
            quality = strategy.normalise_data_quality(leg["data_quality"])
            probability = float(
                leg["prob_raw"] if leg.get("prob_raw") is not None else leg["prob"]
            )
        except (KeyError, TypeError, ValueError):
            continue
        confidence = strategy.confidence_score(leg, gate)
        # (label, shortfall) -- shortfall is how far off the limit it landed,
        # so the nearest miss sorts first and a threshold worth revisiting is
        # obvious rather than inferred.
        checks = []
        if probability < profile.min_probability:
            checks.append((f"命中率 {probability:.3f} < {profile.min_probability:.2f}",
                           profile.min_probability - probability))
        if odds < profile.min_odds:
            checks.append((f"賠率 {odds:g} < {profile.min_odds:g}", profile.min_odds - odds))
        if odds > profile.max_odds:
            checks.append((f"賠率 {odds:g} > {profile.max_odds:g}", odds - profile.max_odds))
        if quality < strategy.MIN_DATA_QUALITY:
            checks.append((f"資料質素 {quality:.2f} < {strategy.MIN_DATA_QUALITY:.2f}",
                           strategy.MIN_DATA_QUALITY - quality))
        if confidence < strategy.MIN_CONFIDENCE_SCORE:
            checks.append((f"信心 {confidence} < {strategy.MIN_CONFIDENCE_SCORE}",
                           (strategy.MIN_CONFIDENCE_SCORE - confidence) / 100.0))
        if float(leg.get("edge") or 0) <= 0:
            checks.append(("edge ≤ 0", 1.0))
        if float(leg.get("ev") or 0) <= 0:
            checks.append(("EV ≤ 0", 1.0))
        if not checks:
            continue
        blocked.append({
            "family": family,
            "desc": leg.get("desc") or leg.get("market_name") or family,
            "match_label": leg.get("match_label"),
            "reasons": [label for label, _ in checks],
            "shortfall": min(gap for _, gap in checks),
            "blocking_count": len(checks),
        })
    blocked.sort(key=lambda item: (item["blocking_count"], item["shortfall"]))
    return blocked[:limit]


def prop_source_quality(family: str, carrier, fallback) -> float:
    """Return quality for the data the family model actually consumes."""
    from tennis_wc.props.strategy import normalise_data_quality

    factors = getattr(carrier, "factors", {}) or {}
    if family == "match_total_aces":
        samples = [factors.get("a_history_n"), factors.get("b_history_n")]
    elif family == "player_aces":
        samples = [
            factors.get("subject_history_n"), factors.get("opponent_history_n")
        ]
    elif family == "player_double_faults":
        samples = [factors.get("history_n")]
    else:
        return normalise_data_quality(fallback)
    valid = [float(value) for value in samples if value is not None]
    if len(valid) != len(samples) or not valid:
        return 0.0
    return min(1.0, min(valid) / 15.0)


def raw_selected_probability(leg: dict):
    """The odds-blind model probability of the side this leg actually backs.

    Selection reads the raw model and the market blend only sizes the bet, so
    the recommendation limits must be applied to the same number the pricer
    selected on.  Testing the blended probability instead re-applies the
    market shrink at the recommendation step and undoes the split.
    """
    carrier = leg.get("tw")
    if carrier is None:
        return None
    for attribute in ("model_prob_over", "model_prob_yes"):
        value = getattr(carrier, attribute, None)
        if value is not None:
            backs_first_side = leg.get("side") == "over"
            return float(value) if backs_first_side else 1.0 - float(value)
    for attribute in ("model_prob_a", "model_prob_a_cover"):
        value = getattr(carrier, attribute, None)
        if value is not None:
            backs_a = getattr(carrier, "value_player_id", None) == getattr(
                carrier, "player_a_id", None
            )
            return float(value) if backs_a else 1.0 - float(value)
    value = getattr(carrier, "model_prob", None)
    return float(value) if value is not None else None
