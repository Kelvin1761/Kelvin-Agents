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
# Fit on 27,299 historical matches (player_match_history, both sides paired),
# walk-forward (only prior matches used per prediction), ~12k samples per bucket.
# Monotonic by construction; we linearly interpolate and clamp to the ends.
# Regenerate with scripts/build_ace_calibration.py if the history grows a lot.
# --------------------------------------------------------------------------- #
CALIBRATION_CURVE: list[tuple[float, float]] = [
    (0.30, 0.9551), (0.35, 0.9324), (0.40, 0.9159), (0.45, 0.8881),
    (0.50, 0.8578), (0.55, 0.8244), (0.60, 0.7859), (0.65, 0.7515),
    (0.70, 0.7134), (0.75, 0.6731), (0.80, 0.6261), (0.85, 0.5890),
    (0.90, 0.5497), (0.95, 0.5117), (1.00, 0.4651), (1.05, 0.4458),
    (1.10, 0.4023), (1.15, 0.3638), (1.20, 0.3334), (1.25, 0.3056),
    (1.30, 0.2718), (1.35, 0.2535), (1.40, 0.2320), (1.45, 0.2056),
    (1.50, 0.1847), (1.55, 0.1772), (1.60, 0.1559),
]

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


def interp_prob_over(line: float, predicted_mean: float) -> float:
    """Empirical P(total aces >= line) given the model's predicted mean."""
    if predicted_mean <= 0 or line <= 0:
        return 0.0
    ratio = line / predicted_mean
    curve = CALIBRATION_CURVE
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
