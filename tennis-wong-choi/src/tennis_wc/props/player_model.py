"""Conservative research models for expandable player-prop families."""
from __future__ import annotations

from dataclasses import dataclass
import math

from tennis_wc.props.ace_model import TwoWayProp

_MIN_HISTORY = 10
_MARKET_SHRINK = 0.35
_MIN_EDGE = 0.04
_GAME_HANDICAP_RAW_SHRINK = 0.65


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
) -> TwoWayProp | None:
    if profile.n < _MIN_HISTORY or over_odds <= 1 or under_odds <= 1:
        return None
    raw_over = _empirical_over(line, profile.values)
    strength = min(0.95, max(0.0, float(temper or 0)))
    tempered = 0.5 + (raw_over - 0.5) * (1 - strength)
    fair_over = _devig(over_odds, under_odds)
    blended_over = (1 - _MARKET_SHRINK) * tempered + _MARKET_SHRINK * fair_over
    candidates = {
        "over": (blended_over, fair_over, over_odds),
        "under": (1 - blended_over, 1 - fair_over, under_odds),
    }
    side = None
    edge = 0.0
    ev = min(prob * odds - 1 for prob, _fair, odds in candidates.values())
    value_odds = None
    blended = blended_over
    for candidate in ("over", "under"):
        prob, fair, odds = candidates[candidate]
        candidate_edge = prob - fair
        candidate_ev = prob * odds - 1
        raw_supports = (
            (candidate == "over" and raw_over > fair_over)
            or (candidate == "under" and raw_over < fair_over)
        )
        if raw_supports and candidate_edge >= _MIN_EDGE and candidate_ev > 0:
            side, edge, ev, value_odds, blended = (
                candidate, candidate_edge, candidate_ev, odds, prob
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
    ``0.4187 + 0.1465 * P(match win)``.  Dispersion is intentionally wide.
    """
    share = max(0.34, min(0.66, 0.4187 + 0.1465 * player_match_probability))
    mean = max(1.0, expected_total_games * share)
    sd = 3.6
    cdf = 0.5 * (1 + math.erf(((line + 0.5) - mean) / (sd * math.sqrt(2))))
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
    share = max(
        0.34,
        min(0.66, 0.4187 + 0.1465 * float(player_a_match_probability)),
    )
    a_mean = max(1.0, float(expected_total_games) * share)
    margin_mean = 2.0 * a_mean - float(expected_total_games)
    z = (-float(player_a_handicap) - margin_mean) / 5.2
    cover = 1.0 - 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
    cover = 0.5 + (cover - 0.5) * _GAME_HANDICAP_RAW_SHRINK
    return max(0.03, min(0.97, cover)), round(margin_mean, 3)


def set_handicap_cover_probability(
    player_a_handicap: float,
    player_a_match_probability: float,
) -> tuple[float, float]:
    """Probability player A covers a BO3 set handicap.

    Uses the empirically calibrated exact BO3 outcome distribution rather than
    assuming independent sets.  Integer/three-way lines are intentionally not
    accepted by the daily parser because pushes need a different contract.
    """
    from tennis_wc.modelling.set_distribution import outcome_distribution

    distribution = outcome_distribution(float(player_a_match_probability))
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
    factors: dict | None = None,
) -> BinaryProp | None:
    if yes_odds <= 1 or no_odds <= 1:
        return None
    strength = min(0.95, max(0.0, float(temper or 0)))
    tempered = 0.5 + (raw_yes - 0.5) * (1 - strength)
    fair_yes = _devig(yes_odds, no_odds)
    blended_yes = (1 - _MARKET_SHRINK) * tempered + _MARKET_SHRINK * fair_yes
    candidates = {
        "yes": (blended_yes, fair_yes, yes_odds),
        "no": (1 - blended_yes, 1 - fair_yes, no_odds),
    }
    side = None
    edge = 0.0
    ev = min(prob * odds - 1 for prob, _fair, odds in candidates.values())
    value_odds = None
    blended = blended_yes
    for candidate in ("yes", "no"):
        prob, fair, odds = candidates[candidate]
        candidate_edge = prob - fair
        candidate_ev = prob * odds - 1
        raw_supports = (
            (candidate == "yes" and raw_yes > fair_yes)
            or (candidate == "no" and raw_yes < fair_yes)
        )
        if raw_supports and candidate_edge >= _MIN_EDGE and candidate_ev > 0:
            side, edge, ev, value_odds, blended = (
                candidate, candidate_edge, candidate_ev, odds, prob
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
    factors: dict | None = None,
) -> HeadToHeadProp | None:
    if a_odds <= 1 or b_odds <= 1:
        return None
    strength = min(0.95, max(0.0, float(temper or 0)))
    tempered = 0.5 + (raw_a - 0.5) * (1-strength)
    fair_a = _devig(a_odds, b_odds)
    blended_a = (1-_MARKET_SHRINK)*tempered + _MARKET_SHRINK*fair_a
    candidates = (
        (player_a_id, player_a_name, a_odds, raw_a, blended_a, fair_a),
        (player_b_id, player_b_name, b_odds, 1-raw_a, 1-blended_a, 1-fair_a),
    )
    value_pid = None
    value_name = None
    value_odds = None
    edge = 0.0
    ev = min(prob*odds-1 for _pid, _name, odds, _raw, prob, _fair in candidates)
    blended = blended_a
    for pid, name, odds, raw, prob, fair in candidates:
        candidate_edge = prob-fair
        candidate_ev = prob*odds-1
        if raw > fair and candidate_edge >= _MIN_EDGE and candidate_ev > 0:
            value_pid, value_name, value_odds = pid, name, odds
            edge, ev, blended = candidate_edge, candidate_ev, prob
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
    strength = min(0.95, max(0.0, float(temper or 0)))
    raw_a = max(0.001, min(0.999, float(raw_a_cover)))
    tempered_a = 0.5 + (raw_a - 0.5) * (1 - strength)
    fair_a = _devig(a_odds, b_odds)
    blended_a = (1 - _MARKET_SHRINK) * tempered_a + _MARKET_SHRINK * fair_a
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
    value_pid = None
    value_name = None
    value_handicap = None
    value_odds = None
    edge = 0.0
    ev = min(prob * odds - 1 for _pid, _name, _h, odds, _raw, prob, _fair in candidates)
    blended = blended_a
    for pid, name, handicap, odds, raw, prob, fair in candidates:
        candidate_edge = prob - fair
        candidate_ev = prob * odds - 1
        if raw > fair and candidate_edge >= _MIN_EDGE and candidate_ev > 0:
            value_pid, value_name = pid, name
            value_handicap, value_odds = handicap, odds
            edge, ev, blended = candidate_edge, candidate_ev, prob
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
    factors: dict | None = None,
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
    distribution = outcome_distribution(float(player_a_match_probability))
    raw = {key: float(distribution[key]) for key in required}
    strength = min(0.95, max(0.0, float(temper or 0)))
    tempered = {
        key: 0.25 + (raw[key]-0.25)*(1-strength)
        for key in required
    }
    blended = {
        key: (1-_MARKET_SHRINK)*tempered[key] + _MARKET_SHRINK*fair[key]
        for key in required
    }
    metadata = {
        "a20": (player_a_id, player_a_name, 0),
        "a21": (player_a_id, player_a_name, 1),
        "b20": (player_b_id, player_b_name, 0),
        "b21": (player_b_id, player_b_name, 1),
    }
    selections = []
    for key in required:
        player_id, player_name, sets_lost = metadata[key]
        edge = blended[key]-fair[key]
        ev = blended[key]*odds[key]-1
        is_value = raw[key] > fair[key] and edge >= _MIN_EDGE and ev > 0
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
