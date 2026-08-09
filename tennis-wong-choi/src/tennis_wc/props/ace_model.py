"""Total-match-aces prop model + pricer (empirically calibrated).

Pipeline for one match:
  1. Build each player's recent-form ace profile (last-N matches, no leakage):
     overall mean, surface-conditioned mean, and "aces conceded" (returner effect).
  2. Predict the match total-ace MEAN by blending both players' serve rate with
     the opponent's conceded rate (a good returner suppresses aces).
  3. Convert (line, predicted_mean) -> P(total >= line) via CALIBRATION_CURVE,
     an empirical survival curve fit on 27,299 historical matches. Because it is
     a realised frequency, P(over) is calibrated by construction (no Poisson /
     Normal skew error -- both were rejected during the build).
  4. Price each offered Sportsbet "N+" rung: de-vig the market, shrink the model
     toward the market prior (we cannot yet backtest, so stay conservative),
     compute edge + EV, and pick the NBA-style "line below form" anchor.

All functions take an open sqlite connection so they are unit-testable.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from tennis_wc.props.registry import (
    DEFAULT_VALUE_PROFILE,
    is_value_selection,
    value_profile,
)

# --------------------------------------------------------------------------- #
# Empirical calibration curve: ratio = line / predicted_mean -> P(total >= line)
# Fit on player_match_history (Sackmann + TML challenger/quali/main),
# walk-forward (only prior matches used per prediction).
# Monotonic by construction; we linearly interpolate and clamp to the ends.
# Regenerate with scripts/build_ace_calibration.py if the history grows a lot.
# --------------------------------------------------------------------------- #
# MATCH total aces (both players combined). Frozen strictly before the first
# evaluation slate (2026-05-10): 62,683 paired matches.
MATCH_ACE_CURVE: list[tuple[float, float]] = [(0.3, 0.9545), (0.35, 0.9359), (0.4, 0.9155), (0.45, 0.8894), (0.5, 0.8613), (0.55, 0.8333), (0.6, 0.791), (0.65, 0.7584), (0.7, 0.723), (0.75, 0.6822), (0.8, 0.6422), (0.85, 0.6002), (0.9, 0.5579), (0.95, 0.523), (1.0, 0.4803), (1.05, 0.4443), (1.1, 0.4109), (1.15, 0.3726), (1.2, 0.3424), (1.25, 0.3112), (1.3, 0.2812), (1.35, 0.2569), (1.4, 0.232), (1.45, 0.2103), (1.5, 0.1877), (1.55, 0.1721), (1.6, 0.1549)]
# SINGLE player's aces. Frozen on the same cutoff: 133,372 player-matches.
# Flatter than the match
# curve -- individual ace counts are more dispersed relative to their mean.
PLAYER_ACE_CURVE: list[tuple[float, float]] = [(0.3, 0.8622), (0.35, 0.8399), (0.4, 0.813), (0.45, 0.7859), (0.5, 0.7564), (0.55, 0.7279), (0.6, 0.6921), (0.65, 0.6592), (0.7, 0.6268), (0.75, 0.5965), (0.8, 0.5643), (0.85, 0.5317), (0.9, 0.502), (0.95, 0.469), (1.0, 0.4402), (1.05, 0.4096), (1.1, 0.3866), (1.15, 0.3576), (1.2, 0.3321), (1.25, 0.3067), (1.3, 0.2843), (1.35, 0.2603), (1.4, 0.2457), (1.45, 0.222), (1.5, 0.2008), (1.55, 0.1871), (1.6, 0.171), (1.65, 0.1612), (1.7, 0.1407), (1.75, 0.1305), (1.8, 0.1198)]
# Per-surface curves (holdout-validated 2026-07-12: beat the global curve on
# EVERY surface for both scopes -- match Brier 0.10706->0.10487, player
# 0.08756->0.08638; biggest gains on clay/grass where all-surface averaging
# distorts most). Fall back to the global curve when a surface is unknown.
MATCH_ACE_CURVE_BY_SURFACE: dict[str, list[tuple[float, float]]] = {
    "hard": [(0.3, 0.9657), (0.35, 0.9492), (0.4, 0.9319), (0.45, 0.9105), (0.5, 0.8823), (0.55, 0.8543), (0.6, 0.8166), (0.65, 0.785), (0.7, 0.7494), (0.75, 0.7063), (0.8, 0.6698), (0.85, 0.6221), (0.9, 0.5835), (0.95, 0.5424), (1.0, 0.5004), (1.05, 0.4621), (1.1, 0.4274), (1.15, 0.3895), (1.2, 0.3533), (1.25, 0.3246), (1.3, 0.2913), (1.35, 0.2683), (1.4, 0.2407), (1.45, 0.2203), (1.5, 0.1927), (1.55, 0.1783), (1.6, 0.1607)],
    "clay": [(0.3, 0.9251), (0.35, 0.9013), (0.4, 0.8714), (0.45, 0.8334), (0.5, 0.8019), (0.55, 0.7732), (0.6, 0.7143), (0.65, 0.6809), (0.7, 0.6452), (0.75, 0.5989), (0.8, 0.5572), (0.85, 0.5199), (0.9, 0.4724), (0.95, 0.4481), (1.0, 0.4007), (1.05, 0.3752), (1.1, 0.3421), (1.15, 0.303), (1.2, 0.2877), (1.25, 0.2502), (1.3, 0.2335), (1.35, 0.2086), (1.4, 0.187), (1.45, 0.1686), (1.5, 0.1531), (1.55, 0.1414), (1.6, 0.123)],
    "grass": [(0.3, 0.9858), (0.35, 0.9748), (0.4, 0.9644), (0.45, 0.9555), (0.5, 0.9337), (0.55, 0.9147), (0.6, 0.9056), (0.65, 0.8657), (0.7, 0.8325), (0.75, 0.8293), (0.8, 0.7792), (0.85, 0.7459), (0.9, 0.7161), (0.95, 0.679), (1.0, 0.6444), (1.05, 0.5914), (1.1, 0.5671), (1.15, 0.5287), (1.2, 0.4926), (1.25, 0.4599), (1.3, 0.4064), (1.35, 0.38), (1.4, 0.3656), (1.45, 0.3241), (1.5, 0.3078), (1.55, 0.2711), (1.6, 0.2672)],
}
PLAYER_ACE_CURVE_BY_SURFACE: dict[str, list[tuple[float, float]]] = {
    "hard": [(0.3, 0.8869), (0.35, 0.8624), (0.4, 0.8404), (0.45, 0.8109), (0.5, 0.7822), (0.55, 0.7553), (0.6, 0.7191), (0.65, 0.6882), (0.7, 0.6505), (0.75, 0.6215), (0.8, 0.5918), (0.85, 0.5566), (0.9, 0.5249), (0.95, 0.4919), (1.0, 0.4579), (1.05, 0.426), (1.1, 0.405), (1.15, 0.3729), (1.2, 0.3447), (1.25, 0.3181), (1.3, 0.2954), (1.35, 0.2674), (1.4, 0.2554), (1.45, 0.2274), (1.5, 0.2063), (1.55, 0.1916), (1.6, 0.1748), (1.65, 0.164), (1.7, 0.1419), (1.75, 0.1341), (1.8, 0.1227)],
    "clay": [(0.3, 0.7909), (0.35, 0.7742), (0.4, 0.7388), (0.45, 0.7133), (0.5, 0.6808), (0.55, 0.6501), (0.6, 0.6108), (0.65, 0.5726), (0.7, 0.5502), (0.75, 0.5179), (0.8, 0.4772), (0.85, 0.4527), (0.9, 0.4243), (0.95, 0.3953), (1.0, 0.373), (1.05, 0.3473), (1.1, 0.3194), (1.15, 0.2959), (1.2, 0.2792), (1.25, 0.2558), (1.3, 0.2355), (1.35, 0.2154), (1.4, 0.2037), (1.45, 0.1854), (1.5, 0.1671), (1.55, 0.1549), (1.6, 0.1426), (1.65, 0.1353), (1.7, 0.1202), (1.75, 0.106), (1.8, 0.0992)],
    "grass": [(0.3, 0.9249), (0.35, 0.9152), (0.4, 0.8888), (0.45, 0.8787), (0.5, 0.8571), (0.55, 0.8231), (0.6, 0.805), (0.65, 0.7794), (0.7, 0.7452), (0.75, 0.7167), (0.8, 0.6982), (0.85, 0.6461), (0.9, 0.6358), (0.95, 0.5912), (1.0, 0.571), (1.05, 0.5343), (1.1, 0.5086), (1.15, 0.4813), (1.2, 0.4503), (1.25, 0.4187), (1.3, 0.3981), (1.35, 0.3881), (1.4, 0.3397), (1.45, 0.3274), (1.5, 0.297), (1.55, 0.2859), (1.6, 0.2562), (1.65, 0.2468), (1.7, 0.2216), (1.75, 0.2068), (1.8, 0.1859)],
}


def match_curve_for_surface(surface: str | None) -> list[tuple[float, float]]:
    key = (surface or "").lower()
    key = "hard" if key == "carpet" else key
    return MATCH_ACE_CURVE_BY_SURFACE.get(key) or MATCH_ACE_CURVE


def player_curve_for_surface(surface: str | None) -> list[tuple[float, float]]:
    key = (surface or "").lower()
    key = "hard" if key == "carpet" else key
    return PLAYER_ACE_CURVE_BY_SURFACE.get(key) or PLAYER_ACE_CURVE


# Back-compat alias (older callers / tests import CALIBRATION_CURVE).
CALIBRATION_CURVE = MATCH_ACE_CURVE

_LAST_N = 15            # recency window for the ace profile
_MIN_HISTORY = 5        # both players need >= this many prior ace matches to price
# Odds-blind walk-forward sweep on three recent cutoffs (2024/2025/2026,
# 65,814/40,639/16,329 player-matches) selected the same pair.  The previous
# 0.30/0.25 weights had higher holdout mean-squared error on every cutoff.
_SURFACE_WEIGHT = 0.60  # surface-specific mean vs overall
_CONCEDE_WEIGHT = 0.30  # opponent's conceded-aces vs raw serve rate
_MARKET_SHRINK = 0.25   # blend model P toward de-vigged market P (conservative)
_MARKET_VIG_DIVISOR = 1.06  # approx Sportsbet ace-ladder hold; de-vig each rung
_ANCHOR_TARGET_PROB = 0.70  # NBA-style: highest line still >= this hit prob
# Value limits now live in tennis_wc.props.registry.VALUE_PROFILES so the pricer
# and the evidence gate read one definition; see is_value_selection there.
_GLOBAL_ACE_FALLBACK = 5.0  # per-player mean if a side is thin (rarely used)
# HARD line cap: only price rungs whose line is within the calibration range of
# the predicted mean. Beyond ~1.25x the mean the curve is EXTRAPOLATING and the
# model reports fake "value" on longshots -- the exact model-error trap that sank
# match-winner betting. We refuse those rungs outright (never surfaced, never bet).
_MAX_LINE_RATIO = 1.25


def interp_prob_over(line: float, predicted_mean: float,
                     curve: list[tuple[float, float]] = MATCH_ACE_CURVE) -> float:
    """Empirical P(aces >= line) given the model's predicted mean. Pass
    PLAYER_ACE_CURVE for a single-player prop, MATCH_ACE_CURVE (default) for the
    match total."""
    if predicted_mean <= 0 or line <= 0:
        return 0.0
    curve = _monotone_nonincreasing_curve(curve)
    ratio = line / predicted_mean
    if ratio <= curve[0][0]:
        return curve[0][1]
    if ratio >= curve[-1][0]:
        # extrapolate the tail gently toward 0 (never below a small floor)
        return max(0.02, curve[-1][1] * (curve[-1][0] / ratio))
    for (r0, p0), (r1, p1) in zip(curve, curve[1:]):
        if r0 <= ratio <= r1:
            t = (ratio - r0) / (r1 - r0)
            return p0 + t * (p1 - p0)
    return curve[-1][1]


def _monotone_nonincreasing_curve(
    curve: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Conservatively repair empirical survival-curve sampling noise.

    A survival probability must never rise when the requested line rises.  Raw
    low-sample surface bins can wiggle, so cap every point at the preceding
    probability before interpolation.
    """
    ceiling = 1.0
    cleaned: list[tuple[float, float]] = []
    for ratio, probability in curve:
        bounded = min(ceiling, max(0.0, min(1.0, float(probability))))
        cleaned.append((float(ratio), bounded))
        ceiling = bounded
    return cleaned


# --------------------------------------------------------------------------- #
# Recent-form ace profile
# --------------------------------------------------------------------------- #
@dataclass
class AceProfile:
    player_id: int
    n: int
    overall_mean: float
    surface_mean: float
    conceded_mean: float | None  # aces this player usually ALLOWS opponents
    serve_estimate: float        # blended overall+surface serve-ace rate


def player_ace_profile(conn, player_id: int, as_of_date: str, surface: str | None,
                       last_n: int = _LAST_N) -> AceProfile:
    """Serve-ace form from the player's matches STRICTLY BEFORE as_of_date."""
    surf = (surface or "hard").lower()
    rows = conn.execute(
        """
        SELECT h.match_date, h.surface, h.ace_count
        FROM player_match_history h
        WHERE h.player_id = ? AND h.ace_count IS NOT NULL AND h.match_date < ?
          AND (
              SELECT COUNT(*)
              FROM player_match_history duplicate
              WHERE duplicate.player_id = h.player_id
                AND duplicate.opponent_id = h.opponent_id
                AND duplicate.match_date = h.match_date
                AND duplicate.ace_count IS NOT NULL
          ) = 1
        ORDER BY match_date DESC
        LIMIT ?
        """,
        (player_id, as_of_date, last_n),
    ).fetchall()
    aces = [float(r["ace_count"]) for r in rows]
    surf_aces = [float(r["ace_count"]) for r in rows if (r["surface"] or "").lower() == surf]
    overall = sum(aces) / len(aces) if aces else _GLOBAL_ACE_FALLBACK
    surface_mean = sum(surf_aces) / len(surf_aces) if surf_aces else overall
    serve_est = (1 - _SURFACE_WEIGHT) * overall + _SURFACE_WEIGHT * surface_mean
    # aces this player conceded = opponent's aces in the player's recent matches
    conc_rows = conn.execute(
        """
        SELECT o.ace_count AS opp_aces
        FROM player_match_history p
        JOIN player_match_history o
          ON o.opponent_id = p.player_id AND o.player_id = p.opponent_id
         AND o.source_provider = p.source_provider
         AND replace(replace(o.provider_match_id, '-winner', ''), '-loser', '')
             = replace(replace(p.provider_match_id, '-winner', ''), '-loser', '')
        WHERE p.player_id = ? AND p.match_date < ? AND o.ace_count IS NOT NULL
          AND p.ace_count IS NOT NULL
          AND (
              SELECT COUNT(*)
              FROM player_match_history duplicate
              WHERE duplicate.player_id = p.player_id
                AND duplicate.opponent_id = p.opponent_id
                AND duplicate.match_date = p.match_date
                AND duplicate.ace_count IS NOT NULL
          ) = 1
        ORDER BY p.match_date DESC LIMIT ?
        """,
        (player_id, as_of_date, last_n),
    ).fetchall()
    conc = [float(r["opp_aces"]) for r in conc_rows]
    conceded = sum(conc) / len(conc) if conc else None
    return AceProfile(
        player_id=player_id, n=len(aces), overall_mean=round(overall, 2),
        surface_mean=round(surface_mean, 2), conceded_mean=round(conceded, 2) if conceded is not None else None,
        serve_estimate=round(serve_est, 3),
    )


def predict_match_ace_mean(a: AceProfile, b: AceProfile) -> float:
    """Blend each side's serve rate with the opponent's conceded-aces rate."""
    a_pred = a.serve_estimate
    b_pred = b.serve_estimate
    if b.conceded_mean is not None:
        a_pred = (1 - _CONCEDE_WEIGHT) * a_pred + _CONCEDE_WEIGHT * b.conceded_mean
    if a.conceded_mean is not None:
        b_pred = (1 - _CONCEDE_WEIGHT) * b_pred + _CONCEDE_WEIGHT * a.conceded_mean
    return round(a_pred + b_pred, 2)


def predict_player_ace_mean(player: AceProfile, opponent: AceProfile) -> float:
    """A SINGLE player's expected aces: own serve rate nudged by how many aces
    the opponent usually concedes (a poor returner lets the server ace more)."""
    pred = player.serve_estimate
    if opponent.conceded_mean is not None:
        pred = (1 - _CONCEDE_WEIGHT) * pred + _CONCEDE_WEIGHT * opponent.conceded_mean
    return round(pred, 2)


# --------------------------------------------------------------------------- #
# Two-way (Over/Under) pricing -- the clean case: exact de-vig from both sides.
# --------------------------------------------------------------------------- #
@dataclass
class TwoWayProp:
    match_id: int
    market_key: str
    scope: str                 # "match" or a player name
    line: float
    over_odds: float
    under_odds: float
    predicted_mean: float
    # RAW, odds-blind model P(over) straight off the calibrated curve. This is the
    # only number that can honestly answer "does our model beat the market", so it
    # must never be overwritten by a risk haircut (see temper_strength below).
    model_prob_over: float
    fair_prob_over: float      # exact two-way de-vig
    # the side the model prefers as value (or None)
    value_side: str | None     # "over" | "under" | None
    value_odds: float | None
    edge: float                # blended - fair on the value side (0 if none)
    ev: float                  # blended*odds-1 on the value side (<=0 if none)
    blended_prob: float        # blended prob of the value side (or of over if none)
    # P(over) after the temper haircut but BEFORE the market shrink. Staking-side
    # number; kept separate so the raw model stays measurable.
    tempered_prob_over: float = 0.0
    temper_strength: float = 0.0
    factors: dict = field(default_factory=dict)


def price_two_way(match_id: int, market_key: str, scope: str, line: float,
                  over_odds: float, under_odds: float, predicted_mean: float,
                  curve: list[tuple[float, float]], factors: dict | None = None,
                  within_range_ratio: float = _MAX_LINE_RATIO,
                  temper: float = 0.0,
                  model_weight: float | None = None) -> TwoWayProp | None:
    """Price an Over/Under ace market. Exact two-way de-vig (Over+Under),
    calibrated model P(over), shrink toward market, pick the +EV value side.
    Refuses lines outside the calibration range (fake-edge protection). `temper`
    (0..1) pulls the model prob toward 0.5 before edge/EV to keep EV honest while
    the model is under-validated (see props.calibration)."""
    if predicted_mean <= 0 or over_odds <= 1.0 or under_odds <= 1.0:
        return None
    if line > within_range_ratio * predicted_mean or line < 0.30 * predicted_mean:
        return None  # outside where the curve is trustworthy
    # RAW model output. Deliberately NOT reassigned below: the temper haircut used
    # to overwrite this, which meant the scorecard graded a probability already
    # pulled toward 0.5, while the temper strength was itself derived from that
    # scorecard. Keeping the two apart breaks that loop.
    model_over = interp_prob_over(line, predicted_mean, curve)
    imp_over, imp_under = 1.0 / over_odds, 1.0 / under_odds
    overround = imp_over + imp_under
    fair_over = imp_over / overround
    if model_weight is None:
        # Backward-compatible research path for callers/tests that explicitly
        # supply the old coin-flip temper.
        strength = min(0.95, max(0.0, temper)) if temper else 0.0
        tempered_over = 0.5 + (model_over - 0.5) * (1.0 - strength)
        blended_over = (
            (1 - _MARKET_SHRINK) * tempered_over
            + _MARKET_SHRINK * fair_over
        )
    else:
        from tennis_wc.props.calibration import blend_with_market
        weight = max(0.0, min(1.0, float(model_weight)))
        strength = 1.0 - weight
        blended_over = blend_with_market(model_over, fair_over, weight)
        tempered_over = blended_over
    blended_under = 1.0 - blended_over
    ev_over = blended_over * over_odds - 1.0
    ev_under = blended_under * under_odds - 1.0
    fair_under = 1.0 - fair_over
    edge_over = blended_over - fair_over
    edge_under = blended_under - fair_under
    side, s_odds, s_edge, s_ev, s_blend = None, None, 0.0, min(ev_over, ev_under), blended_over
    # A risk haircut must never CREATE an opinion in the opposite direction, and
    # it must not decide the selection either: `is_value_selection` reads the
    # odds-blind model, while the blended probability below still sets edge, EV
    # and stake.
    profile = value_profile(market_key)
    if is_value_selection(model_over, fair_over, over_odds, profile):
        side, s_odds, s_blend = "over", over_odds, blended_over
        s_edge, s_ev = model_over - fair_over, model_over * over_odds - 1.0
    elif is_value_selection(1.0 - model_over, fair_under, under_odds, profile):
        side, s_odds, s_blend = "under", under_odds, blended_under
        model_under = 1.0 - model_over
        s_edge, s_ev = model_under - fair_under, model_under * under_odds - 1.0
    return TwoWayProp(
        match_id=match_id, market_key=market_key, scope=scope, line=line,
        over_odds=round(over_odds, 3), under_odds=round(under_odds, 3),
        predicted_mean=predicted_mean, model_prob_over=round(model_over, 4),
        fair_prob_over=round(fair_over, 4), value_side=side,
        value_odds=round(s_odds, 3) if s_odds else None, edge=round(s_edge, 4),
        ev=round(s_ev, 4), blended_prob=round(s_blend, 4),
        tempered_prob_over=round(tempered_over, 4), temper_strength=round(strength, 4),
        factors=factors or {},
    )


# --------------------------------------------------------------------------- #
# Pricing
# --------------------------------------------------------------------------- #
@dataclass
class PricedAceLeg:
    match_id: int
    line: float
    decimal_odds: float
    model_prob: float          # calibrated P(over) from the curve
    market_prob_fair: float    # de-vigged Sportsbet implied P(over)
    blended_prob: float        # model shrunk toward market (what we bet on)
    edge: float                # blended - market_fair
    ev: float                  # blended * odds - 1
    is_value: bool
    predicted_mean: float
    factors: dict = field(default_factory=dict)


def _devig(implied: float) -> float:
    return min(0.98, implied / _MARKET_VIG_DIVISOR)


def price_ace_legs(conn, match_id: int, player_a_id: int, player_b_id: int,
                   as_of_date: str, surface: str | None,
                   offered_lines: dict[float, float]) -> list[PricedAceLeg]:
    """Price each offered {line: decimal_odds} rung for a match. Returns [] if
    either player is too thin to model (no fabricated edges on low data)."""
    a = player_ace_profile(conn, player_a_id, as_of_date, surface)
    b = player_ace_profile(conn, player_b_id, as_of_date, surface)
    if a.n < _MIN_HISTORY or b.n < _MIN_HISTORY:
        return []
    pred_mean = predict_match_ace_mean(a, b)
    if pred_mean <= 0:
        return []
    legs: list[PricedAceLeg] = []
    for line, odds in sorted(offered_lines.items()):
        try:
            odds = float(odds)
            line = float(line)
        except (TypeError, ValueError):
            continue
        if odds <= 1.0:
            continue
        # Refuse longshot rungs beyond the calibration range (fake-edge trap).
        if line > _MAX_LINE_RATIO * pred_mean:
            continue
        model_p = interp_prob_over(line, pred_mean)
        market_fair = _devig(1.0 / odds)
        blended = (1 - _MARKET_SHRINK) * model_p + _MARKET_SHRINK * market_fair
        is_value = is_value_selection(
            model_p, market_fair, odds, DEFAULT_VALUE_PROFILE
        )
        edge = (model_p if is_value else blended) - market_fair
        ev = (model_p if is_value else blended) * odds - 1.0
        legs.append(PricedAceLeg(
            match_id=match_id, line=line, decimal_odds=round(odds, 3),
            model_prob=round(model_p, 4), market_prob_fair=round(market_fair, 4),
            blended_prob=round(blended, 4), edge=round(edge, 4), ev=round(ev, 4),
            is_value=is_value,
            predicted_mean=pred_mean,
            factors={
                "a_serve": a.serve_estimate, "b_serve": b.serve_estimate,
                "a_conceded": a.conceded_mean, "b_conceded": b.conceded_mean,
                "a_n": a.n, "b_n": b.n,
            },
        ))
    return legs


def anchor_leg(legs: list[PricedAceLeg], target_prob: float = _ANCHOR_TARGET_PROB) -> PricedAceLeg | None:
    """NBA-style 'line below form' anchor: a HIGH-hit, LOW-line play (win a little,
    win often), NOT a longshot. Prefer the highest line that still hits >=
    target_prob (blended) -- that is the most points at a safe probability. If no
    line clears the target, fall back to the SAFEST available leg (highest
    blended prob = lowest line), never the longest odds. Returns None if empty."""
    if not legs:
        return None
    qualifying = [lg for lg in legs if lg.blended_prob >= target_prob]
    if qualifying:
        # highest line among the safe ones -> most aces at >= target hit rate
        return max(qualifying, key=lambda lg: (lg.line, lg.blended_prob))
    # nothing safe enough: the single highest-probability leg (the chalkiest line)
    return max(legs, key=lambda lg: lg.blended_prob)
