"""Conservative research models for expandable player-prop families."""
from __future__ import annotations

from dataclasses import dataclass
import math

from tennis_wc.props.ace_model import TwoWayProp
from tennis_wc.props.registry import (
    is_value_selection, value_profile, value_profile_for_family,
)

_MIN_HISTORY = 10
_MARKET_SHRINK = 0.35
_GAME_HANDICAP_RAW_SHRINK = 0.65
_PLAYER_GAMES_MEAN_BIAS = 0.75
_PLAYER_GAMES_SD = 4.50
# Measured on 3,238 settled non-retirement matches: the per-match game margin
# has SD 5.53, and 5.09 around a market-probability fit. The 5.2 that was
# hard-coded inline is within that range; naming it stops it reading as a
# tuning knob and records where it came from.
_GAME_MARGIN_RESIDUAL_SD = 5.2
# Games of margin per unit of match probability, fitted on 1,241 settled
# non-retirement matches against the REBUILT model probability: bucket means
# run -2.78, -2.03, -1.22, -0.08, +1.40, +2.46, +3.61 across P(A)=0.2..0.8,
# monotone, r=0.320.  The market's own probability fits 11.17 on the same
# outcomes, so this is a property of tennis rather than of our model.
#
# The borrowed share curve implied 6.15 -- barely half -- which is why the
# model could not represent a one-sided scoreline and the -6.5 and -7.5 lines
# returned -39% and -32%.  Before the rebuild the same fit against the model's
# own probability gave r=0.221 with non-monotone buckets, which is why the
# slope was deliberately NOT widened then: the input could not resolve
# favourites, so a bigger coefficient would only have amplified noise.
_GAME_MARGIN_SLOPE = 11.26


@dataclass(frozen=True)
class CountProfile:
    player_id: int
    n: int
    mean: float
    values: tuple[float, ...]


@dataclass
class BinaryProp:
    match_id: int
    market_key: str
    scope: str
    yes_odds: float
    no_odds: float
    model_prob_yes: float
    fair_prob_yes: float
    tempered_prob_yes: float
    value_side: str | None
    value_odds: float | None
    edge: float
    ev: float
    blended_prob: float
    temper_strength: float
    factors: dict


@dataclass
class HeadToHeadProp:
    match_id: int
    market_key: str
    player_a_id: int
    player_a_name: str
    player_b_id: int
    player_b_name: str
    a_odds: float
    b_odds: float
    model_prob_a: float
    fair_prob_a: float
    tempered_prob_a: float
    value_player_id: int | None
    value_name: str | None
    value_odds: float | None
    edge: float
    ev: float
    blended_prob: float
    temper_strength: float
    factors: dict


@dataclass
class SpreadProp:
    match_id: int
    market_key: str
    player_a_id: int
    player_a_name: str
    player_b_id: int
    player_b_name: str
    a_handicap: float
    b_handicap: float
    a_odds: float
    b_odds: float
    model_prob_a_cover: float
    fair_prob_a_cover: float
    tempered_prob_a_cover: float
    value_player_id: int | None
    value_name: str | None
    value_handicap: float | None
    value_odds: float | None
    edge: float
    ev: float
    blended_prob: float
    temper_strength: float
    predicted_margin: float
    factors: dict


@dataclass
class ExactSetScoreSelection:
    player_id: int
    player_name: str
    sets_lost: int
    odds: float
    model_prob: float
    fair_prob: float
    tempered_prob: float
    blended_prob: float
    edge: float
    ev: float
    is_value: bool


@dataclass
class ExactSetScoreProp:
    match_id: int
    market_key: str
    selections: list[ExactSetScoreSelection]
    temper_strength: float
    factors: dict


@dataclass
class FirstSetMatchSelection:
    outcome: str
    player_id: int
    player_name: str
    first_set_won: bool
    odds: float
    model_prob: float
    fair_prob: float
    tempered_prob: float
    blended_prob: float
    edge: float
    ev: float
    is_value: bool


@dataclass
class FirstSetMatchProp:
    match_id: int
    market_key: str
    selections: list[FirstSetMatchSelection]
    temper_strength: float
    factors: dict


def count_profile(
    conn,
    player_id: int,
    as_of_date: str,
    column: str,
    *,
    surface: str | None = None,
    last_n: int = 25,
) -> CountProfile:
    if column not in {"double_fault_count"}:
        raise ValueError(f"unsupported count column: {column}")
    params: list = [player_id, as_of_date]
    surface_sql = ""
    if surface:
        surface_sql = " AND lower(COALESCE(surface,'')) = lower(?)"
        params.append(surface)
    params.append(last_n)
    rows = conn.execute(
        f"""
        SELECT {column} AS value
        FROM player_match_history
        WHERE player_id = ? AND match_date < ? AND {column} IS NOT NULL
          {surface_sql}
        ORDER BY match_date DESC
        LIMIT ?
        """,
        tuple(params),
    ).fetchall()
    values = tuple(float(row["value"]) for row in rows)
    if len(values) < _MIN_HISTORY and surface:
        return count_profile(
            conn, player_id, as_of_date, column, surface=None, last_n=last_n
        )
    mean = sum(values) / len(values) if values else 0.0
    return CountProfile(player_id, len(values), round(mean, 3), values)


def _empirical_over(line: float, values: tuple[float, ...]) -> float:
    """Beta-smoothed empirical survival probability.

    Counts are over-dispersed, so the player's own observed distribution is a
    safer research prior than assuming a Poisson process.
    """
    successes = sum(1 for value in values if value > line)
    return (successes + 2.0) / (len(values) + 4.0)


def _devig(over_odds: float, under_odds: float) -> float:
    a, b = 1.0 / over_odds, 1.0 / under_odds
    return a / (a + b)


def price_count_two_way(
    match_id: int,
    market_key: str,
    scope: str,
    line: float,
    over_odds: float,
    under_odds: float,
    profile: CountProfile,
    *,
    temper: float = 0.0,
    model_weight: float | None = None,
) -> TwoWayProp | None:
    if profile.n < _MIN_HISTORY or over_odds <= 1 or under_odds <= 1:
        return None
    raw_over = _empirical_over(line, profile.values)
    fair_over = _devig(over_odds, under_odds)
    if model_weight is None:
        strength = min(0.95, max(0.0, float(temper or 0)))
        tempered = 0.5 + (raw_over - 0.5) * (1 - strength)
        blended_over = (
            (1 - _MARKET_SHRINK) * tempered + _MARKET_SHRINK * fair_over
        )
    else:
        from tennis_wc.props.calibration import blend_with_market
        weight = max(0.0, min(1.0, float(model_weight)))
        strength = 1.0 - weight
        blended_over = blend_with_market(raw_over, fair_over, weight)
        tempered = blended_over
    # Named apart from the CountProfile argument: binding both to `profile`
    # shadowed the history and made every predicted_mean/history_n read below
    # an AttributeError. It never surfaced because player_double_faults has
    # never had a fixture with enough history to reach this line.
    limits = value_profile(market_key)
    candidates = {
        "over": (raw_over, blended_over, fair_over, over_odds),
        "under": (1 - raw_over, 1 - blended_over, 1 - fair_over, under_odds),
    }
    side = None
    edge = 0.0
    ev = min(prob * odds - 1 for _raw, prob, _fair, odds in candidates.values())
    value_odds = None
    blended = blended_over
    for candidate in ("over", "under"):
        raw, prob, fair, odds = candidates[candidate]
        if is_value_selection(raw, fair, odds, limits):
            side, edge, ev, value_odds, blended = (
                candidate, raw - fair, raw * odds - 1, odds, prob
            )
            break
    return TwoWayProp(
        match_id=match_id,
        market_key=market_key,
        scope=scope,
        line=line,
        over_odds=round(over_odds, 3),
        under_odds=round(under_odds, 3),
        predicted_mean=profile.mean,
        model_prob_over=round(raw_over, 4),
        fair_prob_over=round(fair_over, 4),
        value_side=side,
        value_odds=round(value_odds, 3) if value_odds else None,
        edge=round(edge, 4),
        ev=round(ev, 4),
        blended_prob=round(blended, 4),
        tempered_prob_over=round(tempered, 4),
        temper_strength=round(strength, 4),
        factors={"history_n": profile.n, "history_mean": profile.mean},
    )


def player_games_over_probability(
    line: float,
    expected_total_games: float,
    player_match_probability: float,
) -> tuple[float, float]:
    """Research estimate for a player's full-match games won.

    A 540-result local calibration estimated game share as
    ``0.4187 + 0.1465 * P(match win)``.  A later time split found that the
    first 109 live scorecard outcomes under-predicted the mean by 0.75 games
    and had 4.40-game residual dispersion.  Pre-registering +0.75 and a rounded
    4.50 SD improved the next 16 outcomes' Brier from 0.3306 to 0.2954.  It
    still trails the market, so the family reliability weight can suppress its
    betting edge while retaining the better-calibrated hit probability.
    """
    share = max(0.34, min(0.66, 0.4187 + 0.1465 * player_match_probability))
    mean = max(1.0, expected_total_games * share + _PLAYER_GAMES_MEAN_BIAS)
    cdf = 0.5 * (
        1 + math.erf(
            ((line + 0.5) - mean) / (_PLAYER_GAMES_SD * math.sqrt(2))
        )
    )
    return max(0.03, min(0.97, 1 - cdf)), round(mean, 3)


def game_handicap_cover_probability(
    player_a_handicap: float,
    expected_total_games: float,
    player_a_match_probability: float,
) -> tuple[float, float]:
    """Conservative probability that player A covers a full-match game line.

    The same calibrated share equation used for player total games determines
    the expected game margin.  A wide 5.2-game residual dispersion, measured
    on locally settled non-retirement matches, deliberately avoids turning a
    small mean difference into false confidence.  An odds-blind 0.65 shrink,
    fitted on 96 earlier outcomes, improved the next 30 outcomes' Brier from
    0.2761 to 0.2510.  That still trailed the market, so this family starts in
    ``RESEARCH_ONLY`` and must beat the market on future scorecard evidence.
    """
    # The share equation is borrowed from player TOTAL games, where it is
    # correct, and reused here for the MARGIN.  Two consequences, both measured
    # on 3,238 settled non-retirement matches:
    #
    #   * 0.4187 + 0.1465*p spans 0.419..0.565 for p in [0,1], so the
    #     [0.34, 0.66] clamp can never bind -- it reads as a guard and is dead
    #     code.  The reachable margin is +/-3.1 games on a 21-game match, while
    #     72.1% of matches finish outside that band (median margin 5.0).  The
    #     model is structurally unable to predict a one-sided scoreline, which
    #     is why the -6.5 and -7.5 lines returned -39% and -32%.
    #   * At p = 0.5 it returns -0.34 games rather than 0, a standing bias
    #     against whichever player the fixture happens to store first.
    #
    # Centring the share on 0.5 removes the bias.  The slope is NOT widened to
    # the empirical 11.16 games per unit of probability here: that figure was
    # fitted against the MARKET's win probability (r=0.453), and this function
    # is fed the model's own (r=0.221, with 80% of predictions inside +/-0.05
    # of a coin flip).  Widening the slope on a predictor that cannot resolve
    # favourites would amplify noise, not signal.  See the review notes for the
    # market-derived alternative, which is a design change, not a constant.
    total = max(1.0, float(expected_total_games))
    share = max(
        0.34,
        min(0.66, 0.5 + (_GAME_MARGIN_SLOPE / (2.0 * total))
            * (float(player_a_match_probability) - 0.5)),
    )
    a_mean = max(1.0, total * share)
    margin_mean = 2.0 * a_mean - total
    z = (-float(player_a_handicap) - margin_mean) / _GAME_MARGIN_RESIDUAL_SD
    cover = 1.0 - 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
    cover = 0.5 + (cover - 0.5) * _GAME_HANDICAP_RAW_SHRINK
    return max(0.03, min(0.97, cover)), round(margin_mean, 3)


def set_handicap_cover_probability(
    player_a_handicap: float,
    player_a_match_probability: float,
    *,
    outcome_probs: dict[str, float] | None = None,
) -> tuple[float, float]:
    """Probability player A covers a BO3 set handicap.

    Uses the empirically calibrated exact BO3 outcome distribution rather than
    assuming independent sets.  Integer/three-way lines are intentionally not
    accepted by the daily parser because pushes need a different contract.
    """
    from tennis_wc.modelling.set_distribution import outcome_distribution

    distribution = (
        dict(outcome_probs)
        if outcome_probs is not None
        else outcome_distribution(float(player_a_match_probability))
    )
    margins = {"a20": 2.0, "a21": 1.0, "b21": -1.0, "b20": -2.0}
    cover = sum(
        float(distribution[outcome])
        for outcome, margin in margins.items()
        if margin + float(player_a_handicap) > 0
    )
    expected_margin = sum(
        float(distribution[outcome]) * margin
        for outcome, margin in margins.items()
    )
    return max(0.01, min(0.99, cover)), round(expected_margin, 3)


def price_probability_two_way(
    match_id: int,
    market_key: str,
    scope: str,
    yes_odds: float,
    no_odds: float,
    raw_yes: float,
    *,
    temper: float = 0.0,
    model_weight: float | None = None,
    factors: dict | None = None,
) -> BinaryProp | None:
    if yes_odds <= 1 or no_odds <= 1:
        return None
    fair_yes = _devig(yes_odds, no_odds)
    if model_weight is None:
        strength = min(0.95, max(0.0, float(temper or 0)))
        tempered = 0.5 + (raw_yes - 0.5) * (1 - strength)
        blended_yes = (
            (1 - _MARKET_SHRINK) * tempered + _MARKET_SHRINK * fair_yes
        )
    else:
        from tennis_wc.props.calibration import blend_with_market
        weight = max(0.0, min(1.0, float(model_weight)))
        strength = 1.0 - weight
        blended_yes = blend_with_market(raw_yes, fair_yes, weight)
        tempered = blended_yes
    profile = value_profile(market_key)
    candidates = {
        "yes": (raw_yes, blended_yes, fair_yes, yes_odds),
        "no": (1 - raw_yes, 1 - blended_yes, 1 - fair_yes, no_odds),
    }
    side = None
    edge = 0.0
    ev = min(prob * odds - 1 for _raw, prob, _fair, odds in candidates.values())
    value_odds = None
    blended = blended_yes
    for candidate in ("yes", "no"):
        raw, prob, fair, odds = candidates[candidate]
        if is_value_selection(raw, fair, odds, profile):
            side, edge, ev, value_odds, blended = (
                candidate, raw - fair, raw * odds - 1, odds, prob
            )
            break
    return BinaryProp(
        match_id, market_key, scope, round(yes_odds, 3), round(no_odds, 3),
        round(raw_yes, 4), round(fair_yes, 4), round(tempered, 4), side,
        round(value_odds, 3) if value_odds else None, round(edge, 4),
        round(ev, 4), round(blended, 4), round(strength, 4), factors or {},
    )


def price_head_to_head(
    match_id: int,
    market_key: str,
    player_a_id: int,
    player_a_name: str,
    player_b_id: int,
    player_b_name: str,
    a_odds: float,
    b_odds: float,
    raw_a: float,
    *,
    temper: float = 0.0,
    model_weight: float | None = None,
    factors: dict | None = None,
    family: str | None = None,
) -> HeadToHeadProp | None:
    """``family`` is the caller's already-resolved family, and it matters here.

    Every other pricer is handed a key it synthesised (``player_win_a_set_7``,
    ``player_game_handicap_2.5``) which ``family_for_market`` reads back
    correctly from the key alone. This one is handed Sportsbet's own key, and
    theirs for the first set is ``winner_related`` -- the family only resolves
    once the market NAME ("Set 1 Winner") is also in hand. Looked up by key
    alone it lands on ``winner_related``, which is in no profile table, so
    ``first_set_winner`` silently took the default limits and any profile
    registered for it was ignored. Found 2026-08-10 when an A/B that raised its
    odds ceiling returned numbers identical to the baseline.
    """
    if a_odds <= 1 or b_odds <= 1:
        return None
    fair_a = _devig(a_odds, b_odds)
    if model_weight is None:
        strength = min(0.95, max(0.0, float(temper or 0)))
        tempered = 0.5 + (raw_a - 0.5) * (1-strength)
        blended_a = (1-_MARKET_SHRINK)*tempered + _MARKET_SHRINK*fair_a
    else:
        from tennis_wc.props.calibration import blend_with_market
        weight = max(0.0, min(1.0, float(model_weight)))
        strength = 1.0 - weight
        blended_a = blend_with_market(raw_a, fair_a, weight)
        tempered = blended_a
    candidates = (
        (player_a_id, player_a_name, a_odds, raw_a, blended_a, fair_a),
        (player_b_id, player_b_name, b_odds, 1-raw_a, 1-blended_a, 1-fair_a),
    )
    profile = (
        value_profile_for_family(family) if family else value_profile(market_key)
    )
    value_pid = None
    value_name = None
    value_odds = None
    edge = 0.0
    ev = min(prob*odds-1 for _pid, _name, odds, _raw, prob, _fair in candidates)
    blended = blended_a
    for pid, name, odds, raw, prob, fair in candidates:
        if is_value_selection(raw, fair, odds, profile):
            value_pid, value_name, value_odds = pid, name, odds
            edge, ev, blended = raw-fair, raw*odds-1, prob
            break
    return HeadToHeadProp(
        match_id, market_key, player_a_id, player_a_name, player_b_id,
        player_b_name, round(a_odds, 3), round(b_odds, 3), round(raw_a, 4),
        round(fair_a, 4), round(tempered, 4), value_pid, value_name,
        round(value_odds, 3) if value_odds else None, round(edge, 4),
        round(ev, 4), round(blended, 4), round(strength, 4), factors or {},
    )


def price_spread_two_way(
    match_id: int,
    market_key: str,
    player_a_id: int,
    player_a_name: str,
    player_b_id: int,
    player_b_name: str,
    a_handicap: float,
    b_handicap: float,
    a_odds: float,
    b_odds: float,
    raw_a_cover: float,
    predicted_margin: float,
    *,
    temper: float = 0.0,
    model_weight: float | None = None,
    factors: dict | None = None,
) -> SpreadProp | None:
    """Price a complementary two-player handicap market.

    Only half-game/half-set lines belong here, so one player covering is the
    exact complement of the other player covering and there is no push state.
    """
    if (
        a_odds <= 1
        or b_odds <= 1
        or abs(float(a_handicap) + float(b_handicap)) > 1e-9
        or abs(abs(float(a_handicap)) % 1.0 - 0.5) > 1e-9
    ):
        return None
    raw_a = max(0.001, min(0.999, float(raw_a_cover)))
    fair_a = _devig(a_odds, b_odds)
    if model_weight is None:
        strength = min(0.95, max(0.0, float(temper or 0)))
        tempered_a = 0.5 + (raw_a - 0.5) * (1 - strength)
        blended_a = (
            (1 - _MARKET_SHRINK) * tempered_a + _MARKET_SHRINK * fair_a
        )
    else:
        from tennis_wc.props.calibration import blend_with_market
        weight = max(0.0, min(1.0, float(model_weight)))
        strength = 1.0 - weight
        blended_a = blend_with_market(raw_a, fair_a, weight)
        tempered_a = blended_a
    candidates = (
        (
            player_a_id, player_a_name, float(a_handicap), a_odds,
            raw_a, blended_a, fair_a,
        ),
        (
            player_b_id, player_b_name, float(b_handicap), b_odds,
            1 - raw_a, 1 - blended_a, 1 - fair_a,
        ),
    )
    profile = value_profile(market_key)
    value_pid = None
    value_name = None
    value_handicap = None
    value_odds = None
    edge = 0.0
    ev = min(prob * odds - 1 for _pid, _name, _h, odds, _raw, prob, _fair in candidates)
    blended = blended_a
    for pid, name, handicap, odds, raw, prob, fair in candidates:
        if is_value_selection(raw, fair, odds, profile):
            value_pid, value_name = pid, name
            value_handicap, value_odds = handicap, odds
            edge, ev, blended = raw - fair, raw * odds - 1, prob
            break
    return SpreadProp(
        match_id=match_id,
        market_key=market_key,
        player_a_id=player_a_id,
        player_a_name=player_a_name,
        player_b_id=player_b_id,
        player_b_name=player_b_name,
        a_handicap=round(float(a_handicap), 3),
        b_handicap=round(float(b_handicap), 3),
        a_odds=round(float(a_odds), 3),
        b_odds=round(float(b_odds), 3),
        model_prob_a_cover=round(raw_a, 4),
        fair_prob_a_cover=round(fair_a, 4),
        tempered_prob_a_cover=round(tempered_a, 4),
        value_player_id=value_pid,
        value_name=value_name,
        value_handicap=round(value_handicap, 3) if value_handicap is not None else None,
        value_odds=round(value_odds, 3) if value_odds else None,
        edge=round(edge, 4),
        ev=round(ev, 4),
        blended_prob=round(blended, 4),
        temper_strength=round(strength, 4),
        predicted_margin=round(float(predicted_margin), 3),
        factors=factors or {},
    )


def price_exact_set_score(
    match_id: int,
    market_key: str,
    player_a_id: int,
    player_a_name: str,
    player_b_id: int,
    player_b_name: str,
    odds_by_outcome: dict[str, float],
    player_a_match_probability: float,
    *,
    temper: float = 0.0,
    model_weight: float | None = None,
    factors: dict | None = None,
    outcome_probs: dict[str, float] | None = None,
) -> ExactSetScoreProp | None:
    """Price the four mutually exclusive BO3 exact-match-score outcomes."""
    from tennis_wc.modelling.set_distribution import outcome_distribution

    required = ("a20", "a21", "b20", "b21")
    if set(odds_by_outcome) != set(required):
        return None
    try:
        odds = {key: float(odds_by_outcome[key]) for key in required}
    except (TypeError, ValueError):
        return None
    if any(value <= 1 for value in odds.values()):
        return None
    inverse_sum = sum(1/value for value in odds.values())
    if inverse_sum <= 0:
        return None
    fair = {key: (1/odds[key])/inverse_sum for key in required}
    distribution = (
        dict(outcome_probs)
        if outcome_probs is not None
        else outcome_distribution(float(player_a_match_probability))
    )
    raw = {key: float(distribution[key]) for key in required}
    if model_weight is None:
        strength = min(0.95, max(0.0, float(temper or 0)))
        tempered = {
            key: 0.25 + (raw[key]-0.25)*(1-strength)
            for key in required
        }
        blended = {
            key: (1-_MARKET_SHRINK)*tempered[key] + _MARKET_SHRINK*fair[key]
            for key in required
        }
    else:
        from tennis_wc.props.calibration import blend_with_market
        weight = max(0.0, min(1.0, float(model_weight)))
        strength = 1.0 - weight
        blended = {
            key: blend_with_market(raw[key], fair[key], weight)
            for key in required
        }
        tempered = dict(blended)
    metadata = {
        "a20": (player_a_id, player_a_name, 0),
        "a21": (player_a_id, player_a_name, 1),
        "b20": (player_b_id, player_b_name, 0),
        "b21": (player_b_id, player_b_name, 1),
    }
    profile = value_profile(market_key)
    selections = []
    for key in required:
        player_id, player_name, sets_lost = metadata[key]
        is_value = is_value_selection(
            raw[key], fair[key], odds[key], profile
        )
        # Selected legs are recorded on the basis they were selected on (the
        # odds-blind model); unselected ones keep the conservative blended view.
        edge = (raw[key] if is_value else blended[key]) - fair[key]
        ev = (raw[key] if is_value else blended[key]) * odds[key] - 1
        selections.append(
            ExactSetScoreSelection(
                player_id=player_id,
                player_name=player_name,
                sets_lost=sets_lost,
                odds=round(odds[key], 3),
                model_prob=round(raw[key], 4),
                fair_prob=round(fair[key], 4),
                tempered_prob=round(tempered[key], 4),
                blended_prob=round(blended[key], 4),
                edge=round(edge if is_value else 0.0, 4),
                ev=round(ev if is_value else min(ev, 0.0), 4),
                is_value=is_value,
            )
        )
    return ExactSetScoreProp(
        match_id=match_id,
        market_key=market_key,
        selections=selections,
        temper_strength=round(strength, 4),
        factors=factors or {},
    )


def price_first_set_match_outcomes(
    match_id: int,
    market_key: str,
    player_a_id: int,
    player_a_name: str,
    player_b_id: int,
    player_b_name: str,
    odds_by_outcome: dict[str, float],
    outcome_probs: dict[str, float],
    *,
    temper: float = 0.0,
    model_weight: float | None = None,
    factors: dict | None = None,
) -> FirstSetMatchProp | None:
    """Price the exhaustive first-set result × match-winner outcome table.

    Sportsbet exposes the table as two separate markets.  De-vigging either
    pair alone is invalid because the pair omits both comeback outcomes, so all
    four prices are required.  Only the two win-first-and-match selections may
    become paper value signals; comeback rows exist for a complete market
    baseline and scorecard only.
    """
    required = ("a_win", "a_lose", "b_win", "b_lose")
    if set(odds_by_outcome) != set(required) or set(outcome_probs) != set(required):
        return None
    try:
        odds = {key: float(odds_by_outcome[key]) for key in required}
        raw = {key: float(outcome_probs[key]) for key in required}
    except (TypeError, ValueError):
        return None
    if any(value <= 1 for value in odds.values()) or any(
        value < 0 or value > 1 for value in raw.values()
    ):
        return None
    if abs(sum(raw.values()) - 1.0) > 1e-6:
        return None
    inverse_sum = sum(1.0 / value for value in odds.values())
    fair = {key: (1.0 / odds[key]) / inverse_sum for key in required}
    if model_weight is None:
        strength = min(0.95, max(0.0, float(temper or 0)))
        tempered = {
            key: 0.25 + (raw[key] - 0.25) * (1.0 - strength)
            for key in required
        }
        blended = {
            key: (1.0 - _MARKET_SHRINK) * tempered[key]
            + _MARKET_SHRINK * fair[key]
            for key in required
        }
    else:
        from tennis_wc.props.calibration import blend_with_market
        weight = max(0.0, min(1.0, float(model_weight)))
        strength = 1.0 - weight
        blended = {
            key: blend_with_market(raw[key], fair[key], weight)
            for key in required
        }
        tempered = dict(blended)
    metadata = {
        "a_win": (player_a_id, player_a_name, True),
        "a_lose": (player_a_id, player_a_name, False),
        "b_win": (player_b_id, player_b_name, True),
        "b_lose": (player_b_id, player_b_name, False),
    }
    limits = value_profile_for_family("player_first_set_match")
    selections: list[FirstSetMatchSelection] = []
    for key in required:
        player_id, player_name, first_set_won = metadata[key]
        is_value = first_set_won and is_value_selection(
            raw[key], fair[key], odds[key], limits
        )
        edge = raw[key] - fair[key] if is_value else 0.0
        ev = raw[key] * odds[key] - 1.0 if is_value else 0.0
        selections.append(FirstSetMatchSelection(
            outcome=key,
            player_id=player_id,
            player_name=player_name,
            first_set_won=first_set_won,
            odds=round(odds[key], 3),
            model_prob=round(raw[key], 4),
            fair_prob=round(fair[key], 4),
            tempered_prob=round(tempered[key], 4),
            blended_prob=round(blended[key], 4),
            edge=round(edge, 4),
            ev=round(ev, 4),
            is_value=is_value,
        ))
    return FirstSetMatchProp(
        match_id=match_id,
        market_key=market_key,
        selections=selections,
        temper_strength=round(strength, 4),
        factors=factors or {},
    )
