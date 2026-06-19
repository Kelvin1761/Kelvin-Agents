"""
NBA-Wong-Choi-style combination engine for tennis.

Design goals (ported from the NBA SGM engine, adapted for tennis):
  * One normalised leg pool -> four PARALLEL tiers (Banker / Value / High-odds /
    Value-Bomb), not a cascade.
  * Joint probability = product of MODEL probabilities, then a correlation
    haircut (same-match / same-player legs are correlated, cross-match legs are
    treated as independent).
  * A Monte Carlo pass (Gaussian copula) confirms the analytic hit rate and
    gives a downside (p10) hit estimate.
  * Edge/EV are computed against the de-vigged market and the actual combo odds;
    a HARD +EV / +Kelly gate drops any non-profitable combo.
  * Stakes are half-Kelly on the correlation-adjusted joint probability, floored
    at 1u (same unit system as singles).
  * Every leg carries its factor breakdown (Elo, serve/return, form, pressure,
    H2H, fatigue) so all signals are considered and surfaced.

All math is deterministic Python; the LLM only narrates.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from itertools import combinations

from tennis_wc.betting.staking import kelly_fraction, kelly_stake_units


# Factor labels shown in the per-leg breakdown (drives "all factors considered").
FACTOR_LABELS = {
    "surface_elo_edge": "場地Elo",
    "overall_elo_edge": "整體Elo",
    "serve_return_edge": "發球/接發",
    "recent_form_edge": "近況",
    "opponent_rank_bucket_edge": "對手級數",
    "tournament_level_edge": "同級賽事",
    "round_performance_edge": "圈數",
    "big_match_edge": "大賽",
    "pressure_edge": "壓力球",
    "head_to_head_edge": "交手往績",
    "fatigue_edge": "體能",
}

_MC_RUNS = 10000
_MC_SEED = 20260618
_CORRELATION_CAP = 0.30


@dataclass(frozen=True)
class Leg:
    leg_id: str
    match_id: int
    match_label: str
    selection_name: str
    market_key: str
    market_name: str
    selection_side: str | None
    line: float | None
    decimal_odds: float
    model_probability: float
    no_vig_probability: float | None
    edge: float
    confidence: int
    factors: dict[str, float] = field(default_factory=dict)
    # validated=True -> passed the settlement-validation gate or is a genuine
    # match-winner BET (trustworthy). validated=False -> a modelled-but-not-yet
    # -validated market (e.g. total games / handicap): usable for TRIAL combos
    # only, clearly flagged and small-staked.
    validated: bool = True
    # Human-readable risk-segment flag (e.g. high-variance / low-data small
    # tournament). Empty = low risk. Surfaced in the report, not used in math.
    risk_label: str = ""

    @property
    def implied_probability(self) -> float:
        return 1.0 / self.decimal_odds if self.decimal_odds > 0 else 0.0


# --------------------------------------------------------------------------- #
# Correlation
# --------------------------------------------------------------------------- #
def _pair_correlation(a: Leg, b: Leg) -> float:
    """Rough positive correlation between two legs (0..~0.8)."""
    if a.match_id != b.match_id:
        return 0.0  # different matches -> independent
    # Same match.
    same_side = (
        a.selection_side is not None
        and a.selection_side == b.selection_side
    )
    if a.market_key == b.market_key:
        return 0.85  # essentially the same bet
    # match-winner + a set/games market on the SAME player is strongly correlated
    set_or_games = {"to_win_1st_set", "set_betting", "set_handicap", "game_handicap", "total_games"}
    if same_side and (
        "match_winner" in {a.market_key, b.market_key}
        and (a.market_key in set_or_games or b.market_key in set_or_games)
    ):
        return 0.55
    if same_side:
        return 0.45
    return 0.25  # same match, different player/market -> mild correlation


def correlation_penalty(legs: tuple[Leg, ...]) -> float:
    """Average pairwise correlation, capped. Used as a multiplicative haircut."""
    if len(legs) <= 1:
        return 0.0
    pairs = list(combinations(legs, 2))
    total = sum(_pair_correlation(a, b) for a, b in pairs)
    avg = total / len(pairs)
    return min(_CORRELATION_CAP, avg)


# --------------------------------------------------------------------------- #
# Probability / EV
# --------------------------------------------------------------------------- #
def naive_joint_probability(legs: tuple[Leg, ...]) -> float:
    joint = 1.0
    for leg in legs:
        joint *= max(0.0, min(1.0, leg.model_probability))
    return joint


def adjusted_joint_probability(legs: tuple[Leg, ...]) -> float:
    return naive_joint_probability(legs) * (1.0 - correlation_penalty(legs))


def combo_odds(legs: tuple[Leg, ...]) -> float:
    odds = 1.0
    for leg in legs:
        odds *= leg.decimal_odds
    return odds


def combo_ev(legs: tuple[Leg, ...]) -> float:
    """Expected value per 1u staked: adjusted_hit * combo_odds - 1."""
    return adjusted_joint_probability(legs) * combo_odds(legs) - 1.0


# --------------------------------------------------------------------------- #
# Monte Carlo (Gaussian copula) confirmation
# --------------------------------------------------------------------------- #
def _inv_norm(p: float) -> float:
    """Acklam's rational approximation of the inverse standard-normal CDF."""
    p = min(max(p, 1e-9), 1 - 1e-9)
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def monte_carlo_hit(legs: tuple[Leg, ...], runs: int = _MC_RUNS) -> dict:
    """
    Simulate the combo with a one-factor Gaussian copula per match: legs in the
    same match share a latent shock (rho = their correlation), so correlated
    legs win/lose together. Returns mean hit and the 10th-percentile hit over
    repeated blocks (a downside read).
    """
    if not legs:
        return {"mean_hit": 0.0, "p10_hit": 0.0, "runs": 0}
    rng = random.Random(_MC_SEED + len(legs))
    thresholds = [_inv_norm(leg.model_probability) for leg in legs]
    # rho per leg vs its match shock = max pairwise correlation with same-match peers
    match_ids = [leg.match_id for leg in legs]
    rho = []
    for i, leg in enumerate(legs):
        peers = [legs[j] for j in range(len(legs)) if j != i and legs[j].match_id == leg.match_id]
        r = max((_pair_correlation(leg, peer) for peer in peers), default=0.0)
        rho.append(min(0.95, r))

    block = 1000
    block_hits: list[float] = []
    wins = 0
    done = 0
    while done < runs:
        this_block = min(block, runs - done)
        bh = 0
        for _ in range(this_block):
            match_shock: dict[int, float] = {}
            all_win = True
            for i, leg in enumerate(legs):
                z_match = match_shock.setdefault(match_ids[i], rng.gauss(0, 1))
                x = math.sqrt(rho[i]) * z_match + math.sqrt(1 - rho[i]) * rng.gauss(0, 1)
                # leg wins if latent <= threshold (P(Z<=thr)=model_probability)
                if x > thresholds[i]:
                    all_win = False
                    break
            if all_win:
                bh += 1
        block_hits.append(bh / this_block)
        wins += bh
        done += this_block
    block_hits.sort()
    p10 = block_hits[max(0, int(0.1 * len(block_hits)) - 1)] if block_hits else 0.0
    return {"mean_hit": wins / done, "p10_hit": p10, "runs": done}


# --------------------------------------------------------------------------- #
# Leg quality (uses ALL factors, incl. pressure)
# --------------------------------------------------------------------------- #
def leg_factor_breakdown(leg: Leg) -> list[tuple[str, float]]:
    """Factors that meaningfully support the selection, strongest first."""
    out: list[tuple[str, float]] = []
    for name, prob in leg.factors.items():
        label = FACTOR_LABELS.get(name, name)
        out.append((label, prob))
    out.sort(key=lambda kv: abs(kv[1] - 0.5), reverse=True)
    return out


def leg_quality_score(leg: Leg) -> float:
    """
    Composite 0..1 leg quality from edge, confidence and supporting factors
    (so pressure/serve-return/form/H2H all feed selection ranking, not just Elo).
    """
    edge_part = max(0.0, min(1.0, leg.edge / 0.15))
    conf_part = max(0.0, min(1.0, leg.confidence / 100))
    factor_support = 0.5
    if leg.factors:
        # average how far supportive factors lean toward the pick
        leans = [prob for prob in leg.factors.values()]
        factor_support = sum(leans) / len(leans)
    return round(0.4 * leg.model_probability + 0.25 * edge_part + 0.15 * conf_part + 0.20 * factor_support, 4)


# --------------------------------------------------------------------------- #
# Combo assembly + tiers
# --------------------------------------------------------------------------- #
TIER_BANKER = "穩膽"
TIER_VALUE = "價值膽"
TIER_HIGH = "高倍率"
TIER_BOMB = "火藥庫"

_TIER_ORDER = [TIER_BANKER, TIER_VALUE, TIER_HIGH, TIER_BOMB]


def _combo_valid(legs: tuple[Leg, ...]) -> bool:
    # No two legs backing OPPOSITE players in the same match.
    by_match: dict[int, set[str]] = {}
    market_seen: set[tuple[int, str, object]] = set()
    for leg in legs:
        if leg.selection_side in {"player_a", "player_b"}:
            sides = by_match.setdefault(leg.match_id, set())
            opposite = "player_b" if leg.selection_side == "player_a" else "player_a"
            if opposite in sides:
                return False
            sides.add(leg.selection_side)
        key = (leg.match_id, leg.market_key, leg.line)
        if key in market_seen:
            return False
        market_seen.add(key)
    return True


def build_combo(legs: tuple[Leg, ...]) -> dict | None:
    if not legs or not _combo_valid(legs):
        return None
    odds = combo_odds(legs)
    naive = naive_joint_probability(legs)
    penalty = correlation_penalty(legs)
    adjusted = naive * (1.0 - penalty)
    ev = adjusted * odds - 1.0
    full_kelly = kelly_fraction(adjusted, odds)
    # HARD +EV / +Kelly gate.
    if ev <= 0 or full_kelly <= 0:
        return None
    stake = kelly_stake_units(adjusted, odds)
    min_leg_prob = min(leg.model_probability for leg in legs)
    avg_edge = sum(leg.edge for leg in legs) / len(legs)
    return {
        "legs": list(legs),
        "leg_ids": tuple(sorted(leg.leg_id for leg in legs)),
        "combo_odds": round(odds, 4),
        "naive_hit": round(naive, 4),
        "correlation_penalty": round(penalty, 4),
        "adjusted_hit": round(adjusted, 4),
        # Monte Carlo is filled in only for SELECTED combos (see _attach_monte_carlo)
        # so we don't run 10k sims for thousands of rejected candidates.
        "mc_mean_hit": round(adjusted, 4),
        "mc_p10_hit": round(adjusted, 4),
        "combo_ev": round(ev, 4),
        "kelly_fraction": round(full_kelly, 4),
        "stake_units": stake,
        "min_leg_probability": round(min_leg_prob, 4),
        "average_edge": round(avg_edge, 4),
        "is_same_match": len({leg.match_id for leg in legs}) == 1 and len(legs) > 1,
    }


def _attach_monte_carlo(combo: dict) -> dict:
    mc = monte_carlo_hit(tuple(combo["legs"]))
    combo["mc_mean_hit"] = round(mc["mean_hit"], 4)
    combo["mc_p10_hit"] = round(mc["p10_hit"], 4)
    return combo


def combo_is_validated(combo: dict) -> bool:
    """True only if every leg is a trustworthy/validated leg."""
    return all(getattr(leg, "validated", True) for leg in combo["legs"])


def classify_tier(combo: dict) -> str | None:
    odds = combo["combo_odds"]
    hit = combo["adjusted_hit"]
    ev = combo["combo_ev"]
    min_leg = combo["min_leg_probability"]
    avg_edge = combo["average_edge"]
    # Value Bomb: a safe anchor leg + a value spike, longer odds.
    if odds >= 5.0 and min_leg >= 0.62 and avg_edge >= 0.08 and ev >= 0.10:
        return TIER_BOMB
    if 1.9 <= odds <= 3.6 and hit >= 0.50 and min_leg >= 0.60 and ev > 0:
        return TIER_BANKER
    if 2.5 <= odds <= 5.5 and hit >= 0.33 and avg_edge >= 0.04 and ev >= 0.05:
        return TIER_VALUE
    if 5.0 <= odds <= 21.0 and hit >= 0.12 and ev >= 0.08:
        return TIER_HIGH
    return None


def _combo_rank_key(combo: dict) -> tuple:
    # Prefer higher EV then higher hit then leg quality.
    leg_quality = sum(leg_quality_score(leg) for leg in combo["legs"]) / len(combo["legs"])
    return (-combo["combo_ev"], -combo["adjusted_hit"], -leg_quality)


def build_combinations(legs: list[Leg], max_legs: int = 3, per_tier: int | None = None, max_leg_reuse: int = 2) -> dict:
    """
    Build all valid 2..max_legs combos (plus 1-leg 'single' bankers for legs that
    are already >= 2.0 odds), gate on +EV, classify into four tiers, dedupe legs
    within a tier, and return the selected combos per tier.
    """
    candidates: list[dict] = []
    seen: set[tuple] = set()

    # Single-leg "banker" candidates (a strong pick already priced >= 2.0).
    for leg in legs:
        if leg.decimal_odds >= 2.0:
            combo = build_combo((leg,))
            if combo:
                if combo["leg_ids"] in seen:
                    continue
                seen.add(combo["leg_ids"])
                candidates.append(combo)

    for size in range(2, max_legs + 1):
        for group in combinations(legs, size):
            combo = build_combo(tuple(group))
            if combo is None:
                continue
            if combo["leg_ids"] in seen:
                continue
            seen.add(combo["leg_ids"])
            candidates.append(combo)

    limits = {TIER_BANKER: 5, TIER_VALUE: 5, TIER_HIGH: 4, TIER_BOMB: 3}
    if per_tier is not None:
        limits = {tier: per_tier for tier in _TIER_ORDER}

    # Instead of forbidding ANY shared leg within a tier (which collapses to one
    # combo when only a few legs qualify), cap how many times each leg may reuse
    # across a tier. This surfaces several distinct combos to choose from while
    # stopping one leg from appearing in every combo. Combos are still unique
    # (exact-combo dedup via `seen`), and every combo is independently +EV.
    selected: dict[str, list[dict]] = {tier: [] for tier in _TIER_ORDER}
    for tier in _TIER_ORDER:
        leg_use: dict[str, int] = {}
        tier_candidates = [c for c in candidates if classify_tier(c) == tier]
        tier_candidates.sort(key=_combo_rank_key)
        for combo in tier_candidates:
            if len(selected[tier]) >= limits[tier]:
                break
            if any(leg_use.get(lid, 0) >= max_leg_reuse for lid in combo["leg_ids"]):
                continue
            selected[tier].append(_attach_monte_carlo(combo))
            for lid in combo["leg_ids"]:
                leg_use[lid] = leg_use.get(lid, 0) + 1

    return {
        "tiers": selected,
        "candidate_count": len(candidates),
        "leg_count": len(legs),
    }
