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

# --------------------------------------------------------------------------- #
# Empirical calibration curve: ratio = line / predicted_mean -> P(total >= line)
# Fit on player_match_history (Sackmann + TML challenger/quali/main),
# walk-forward (only prior matches used per prediction).
# Monotonic by construction; we linearly interpolate and clamp to the ends.
# Regenerate with scripts/build_ace_calibration.py if the history grows a lot.
# --------------------------------------------------------------------------- #
# MATCH total aces (both players combined). Fit on 64,210 paired matches
# (Sackmann + TML challenger/quali/main; regenerated 2026-07-12).
MATCH_ACE_CURVE: list[tuple[float, float]] = [(0.3, 0.9524), (0.35, 0.9325), (0.4, 0.9141), (0.45, 0.8869), (0.5, 0.8568), (0.55, 0.8265), (0.6, 0.7874), (0.65, 0.7546), (0.7, 0.7149), (0.75, 0.6784), (0.8, 0.6354), (0.85, 0.5933), (0.9, 0.5553), (0.95, 0.5197), (1.0, 0.4743), (1.05, 0.4425), (1.1, 0.4059), (1.15, 0.3716), (1.2, 0.3387), (1.25, 0.3101), (1.3, 0.2839), (1.35, 0.2552), (1.4, 0.2329), (1.45, 0.21), (1.5, 0.1897), (1.55, 0.1737), (1.6, 0.1549)]
# SINGLE player's aces. Fit on 137,017 player-matches. Flatter than the match
# curve -- individual ace counts are more dispersed relative to their mean.
PLAYER_ACE_CURVE: list[tuple[float, float]] = [(0.3, 0.8603), (0.35, 0.8367), (0.4, 0.8141), (0.45, 0.7825), (0.5, 0.7534), (0.55, 0.7229), (0.6, 0.6903), (0.65, 0.6578), (0.7, 0.6231), (0.75, 0.5899), (0.8, 0.5587), (0.85, 0.5298), (0.9, 0.4984), (0.95, 0.4634), (1.0, 0.4345), (1.05, 0.4068), (1.1, 0.3822), (1.15, 0.3549), (1.2, 0.3332), (1.25, 0.3), (1.3, 0.2833), (1.35, 0.2613), (1.4, 0.2413), (1.45, 0.2224), (1.5, 0.1998), (1.55, 0.1888), (1.6, 0.1748), (1.65, 0.1553), (1.7, 0.1423), (1.75, 0.1345), (1.8, 0.1214)]
# Per-surface curves (holdout-validated 2026-07-12: beat the global curve on
# EVERY surface for both scopes -- match Brier 0.10706->0.10487, player
# 0.08756->0.08638; biggest gains on clay/grass where all-surface averaging
# distorts most). Fall back to the global curve when a surface is unknown.
MATCH_ACE_CURVE_BY_SURFACE: dict[str, list[tuple[float, float]]] = {
    "hard": [(0.3, 0.9666), (0.35, 0.951), (0.4, 0.9344), (0.45, 0.9117), (0.5, 0.8843), (0.55, 0.8558), (0.6, 0.8191), (0.65, 0.7868), (0.7, 0.7495), (0.75, 0.712), (0.8, 0.6707), (0.85, 0.6262), (0.9, 0.586), (0.95, 0.5451), (1.0, 0.5032), (1.05, 0.4683), (1.1, 0.4291), (1.15, 0.3951), (1.2, 0.3552), (1.25, 0.3306), (1.3, 0.2983), (1.35, 0.2709), (1.4, 0.2458), (1.45, 0.2251), (1.5, 0.2002), (1.55, 0.1869), (1.6, 0.1639)],
    "clay": [(0.3, 0.919), (0.35, 0.8886), (0.4, 0.8629), (0.45, 0.8242), (0.5, 0.7861), (0.55, 0.7498), (0.6, 0.7008), (0.65, 0.6656), (0.7, 0.617), (0.75, 0.5806), (0.8, 0.5307), (0.85, 0.4905), (0.9, 0.4545), (0.95, 0.4292), (1.0, 0.3745), (1.05, 0.3504), (1.1, 0.3171), (1.15, 0.2858), (1.2, 0.2631), (1.25, 0.2306), (1.3, 0.217), (1.35, 0.189), (1.4, 0.1738), (1.45, 0.1531), (1.5, 0.1382), (1.55, 0.125), (1.6, 0.1137)],
    "grass": [(0.3, 0.9854), (0.35, 0.9795), (0.4, 0.9746), (0.45, 0.9634), (0.5, 0.9438), (0.55, 0.9304), (0.6, 0.9111), (0.65, 0.8872), (0.7, 0.8677), (0.75, 0.8361), (0.8, 0.8075), (0.85, 0.7801), (0.9, 0.7476), (0.95, 0.7126), (1.0, 0.6802), (1.05, 0.6325), (1.1, 0.6134), (1.15, 0.5677), (1.2, 0.5365), (1.25, 0.5066), (1.3, 0.4662), (1.35, 0.4345), (1.4, 0.3988), (1.45, 0.3619), (1.5, 0.3578), (1.55, 0.3066), (1.6, 0.2897)],
}
PLAYER_ACE_CURVE_BY_SURFACE: dict[str, list[tuple[float, float]]] = {
    "hard": [(0.3, 0.8876), (0.35, 0.867), (0.4, 0.8452), (0.45, 0.8122), (0.5, 0.7826), (0.55, 0.7571), (0.6, 0.7225), (0.65, 0.6894), (0.7, 0.6543), (0.75, 0.6219), (0.8, 0.5912), (0.85, 0.5583), (0.9, 0.525), (0.95, 0.489), (1.0, 0.4635), (1.05, 0.4274), (1.1, 0.4057), (1.15, 0.3724), (1.2, 0.3498), (1.25, 0.318), (1.3, 0.297), (1.35, 0.2748), (1.4, 0.2536), (1.45, 0.2305), (1.5, 0.2072), (1.55, 0.1965), (1.6, 0.1801), (1.65, 0.1621), (1.7, 0.1448), (1.75, 0.1408), (1.8, 0.1242)],
    "clay": [(0.3, 0.7899), (0.35, 0.7584), (0.4, 0.7324), (0.45, 0.7022), (0.5, 0.6707), (0.55, 0.6324), (0.6, 0.5968), (0.65, 0.568), (0.7, 0.5323), (0.75, 0.4922), (0.8, 0.4602), (0.85, 0.4408), (0.9, 0.4117), (0.95, 0.3745), (1.0, 0.3471), (1.05, 0.3284), (1.1, 0.2995), (1.15, 0.2817), (1.2, 0.2646), (1.25, 0.2354), (1.3, 0.2191), (1.35, 0.1984), (1.4, 0.1908), (1.45, 0.1742), (1.5, 0.1559), (1.55, 0.1427), (1.6, 0.136), (1.65, 0.1171), (1.7, 0.1124), (1.75, 0.1001), (1.8, 0.0944)],
    "grass": [(0.3, 0.9258), (0.35, 0.9215), (0.4, 0.9096), (0.45, 0.8899), (0.5, 0.8738), (0.55, 0.8397), (0.6, 0.8293), (0.65, 0.7902), (0.7, 0.7669), (0.75, 0.7465), (0.8, 0.7229), (0.85, 0.6748), (0.9, 0.6574), (0.95, 0.6417), (1.0, 0.5784), (1.05, 0.5752), (1.1, 0.5447), (1.15, 0.5225), (1.2, 0.4939), (1.25, 0.4323), (1.3, 0.4441), (1.35, 0.4204), (1.4, 0.3609), (1.45, 0.36), (1.5, 0.3293), (1.55, 0.3252), (1.6, 0.2997), (1.65, 0.2633), (1.7, 0.2547), (1.75, 0.2354), (1.8, 0.2174)],
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
_SURFACE_WEIGHT = 0.30  # weight of surface-specific mean vs overall
_CONCEDE_WEIGHT = 0.25  # weight of opponent's conceded-aces vs raw serve rate
_MARKET_SHRINK = 0.25   # blend model P toward de-vigged market P (conservative)
_MARKET_VIG_DIVISOR = 1.06  # approx Sportsbet ace-ladder hold; de-vig each rung
_ANCHOR_TARGET_PROB = 0.70  # NBA-style: highest line still >= this hit prob
_MIN_EDGE = 0.04        # min (model - market_fair) to flag a value prop
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
        SELECT match_date, surface, ace_count
        FROM player_match_history
        WHERE player_id = ? AND ace_count IS NOT NULL AND match_date < ?
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
         AND o.match_date = p.match_date
        WHERE p.player_id = ? AND p.match_date < ? AND o.ace_count IS NOT NULL
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
    model_prob_over: float
    fair_prob_over: float      # exact two-way de-vig
    # the side the model prefers as value (or None)
    value_side: str | None     # "over" | "under" | None
    value_odds: float | None
    edge: float                # blended - fair on the value side (0 if none)
    ev: float                  # blended*odds-1 on the value side (<=0 if none)
    blended_prob: float        # blended prob of the value side (or of over if none)
    factors: dict = field(default_factory=dict)


def price_two_way(match_id: int, market_key: str, scope: str, line: float,
                  over_odds: float, under_odds: float, predicted_mean: float,
                  curve: list[tuple[float, float]], factors: dict | None = None,
                  within_range_ratio: float = _MAX_LINE_RATIO,
                  temper: float = 0.0) -> TwoWayProp | None:
    """Price an Over/Under ace market. Exact two-way de-vig (Over+Under),
    calibrated model P(over), shrink toward market, pick the +EV value side.
    Refuses lines outside the calibration range (fake-edge protection). `temper`
    (0..1) pulls the model prob toward 0.5 before edge/EV to keep EV honest while
    the model is under-validated (see props.calibration)."""
    if predicted_mean <= 0 or over_odds <= 1.0 or under_odds <= 1.0:
        return None
    if line > within_range_ratio * predicted_mean or line < 0.30 * predicted_mean:
        return None  # outside where the curve is trustworthy
    model_over = interp_prob_over(line, predicted_mean, curve)
    if temper:
        model_over = 0.5 + (model_over - 0.5) * (1.0 - min(0.95, max(0.0, temper)))
    imp_over, imp_under = 1.0 / over_odds, 1.0 / under_odds
    overround = imp_over + imp_under
    fair_over = imp_over / overround
    blended_over = (1 - _MARKET_SHRINK) * model_over + _MARKET_SHRINK * fair_over
    blended_under = 1.0 - blended_over
    ev_over = blended_over * over_odds - 1.0
    ev_under = blended_under * under_odds - 1.0
    fair_under = 1.0 - fair_over
    edge_over = blended_over - fair_over
    edge_under = blended_under - fair_under
    side, s_odds, s_edge, s_ev, s_blend = None, None, 0.0, min(ev_over, ev_under), blended_over
    if edge_over >= _MIN_EDGE and ev_over > 0:
        side, s_odds, s_edge, s_ev, s_blend = "over", over_odds, edge_over, ev_over, blended_over
    elif edge_under >= _MIN_EDGE and ev_under > 0:
        side, s_odds, s_edge, s_ev, s_blend = "under", under_odds, edge_under, ev_under, blended_under
    return TwoWayProp(
        match_id=match_id, market_key=market_key, scope=scope, line=line,
        over_odds=round(over_odds, 3), under_odds=round(under_odds, 3),
        predicted_mean=predicted_mean, model_prob_over=round(model_over, 4),
        fair_prob_over=round(fair_over, 4), value_side=side,
        value_odds=round(s_odds, 3) if s_odds else None, edge=round(s_edge, 4),
        ev=round(s_ev, 4), blended_prob=round(s_blend, 4), factors=factors or {},
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
        edge = blended - market_fair
        ev = blended * odds - 1.0
        legs.append(PricedAceLeg(
            match_id=match_id, line=line, decimal_odds=round(odds, 3),
            model_prob=round(model_p, 4), market_prob_fair=round(market_fair, 4),
            blended_prob=round(blended, 4), edge=round(edge, 4), ev=round(ev, 4),
            is_value=(edge >= _MIN_EDGE and ev > 0),
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
