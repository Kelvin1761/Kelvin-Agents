"""Recalibrate the match probability without touching what it ranks.

Measured on 1,017 fixtures where an as-of Elo exists: the nine logit nudges
gain 0.044 AUC over raw Elo and lose 0.0024 Brier.  They order matches better
and price them worse, which is the signature of a miscalibrated score rather
than a useless one -- deleting them, which a smaller sample first suggested,
would throw away real ordering information.

Platt scaling is the minimal fix: fit ``sigmoid(a * logit(p) + b)`` on outcomes
that were already settled, which rescales confidence and cannot reorder
anything (``a > 0`` is monotone in ``p``).  The fit is strictly walk-forward --
a calibration learned on matches the prediction has not happened yet is the
same look-ahead this rebuild spent its first two phases removing.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

MIN_CALIBRATION_SAMPLE = 200
MAX_ITERATIONS = 60
_EPS = 1e-6


@dataclass(frozen=True)
class Calibration:
    slope: float
    intercept: float
    sample: int
    fitted_through: str | None

    @property
    def is_identity(self) -> bool:
        return abs(self.slope - 1.0) < 1e-9 and abs(self.intercept) < 1e-9


IDENTITY = Calibration(slope=1.0, intercept=0.0, sample=0, fitted_through=None)


def _logit(p: float) -> float:
    p = min(max(float(p), _EPS), 1 - _EPS)
    return math.log(p / (1 - p))


def _sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    value = math.exp(x)
    return value / (1.0 + value)


def fit(samples: list[tuple[float, float]]) -> Calibration:
    """Newton fit of ``sigmoid(a * logit(p) + b)`` to (probability, outcome).

    Returns the identity below ``MIN_CALIBRATION_SAMPLE``: a slope fitted on
    fifty matches is noise wearing a coefficient, and applying it would move
    every price for no reason.
    """
    usable = [(_logit(p), float(y)) for p, y in samples if p is not None and y is not None]
    if len(usable) < MIN_CALIBRATION_SAMPLE:
        return IDENTITY
    slope, intercept = 1.0, 0.0
    for _ in range(MAX_ITERATIONS):
        g_a = g_b = h_aa = h_ab = h_bb = 0.0
        for x, y in usable:
            predicted = _sigmoid(slope * x + intercept)
            residual = predicted - y
            weight = max(predicted * (1 - predicted), 1e-9)
            g_a += residual * x
            g_b += residual
            h_aa += weight * x * x
            h_ab += weight * x
            h_bb += weight
        determinant = h_aa * h_bb - h_ab * h_ab
        if abs(determinant) < 1e-12:
            break
        step_a = (g_a * h_bb - g_b * h_ab) / determinant
        step_b = (g_b * h_aa - g_a * h_ab) / determinant
        slope -= step_a
        intercept -= step_b
        if abs(step_a) < 1e-9 and abs(step_b) < 1e-9:
            break
    # A non-positive slope would inverse the ranking, which is never a
    # calibration result -- it means the fit failed. Fall back to identity.
    if not math.isfinite(slope) or not math.isfinite(intercept) or slope <= 0:
        return IDENTITY
    return Calibration(round(slope, 6), round(intercept, 6), len(usable), None)


def apply(probability: float, calibration: Calibration) -> float:
    if probability is None or calibration.is_identity:
        return probability
    return _sigmoid(calibration.slope * _logit(probability) + calibration.intercept)


def fit_as_of(conn, as_of_date: str) -> Calibration:
    """Fit on every match settled STRICTLY BEFORE ``as_of_date``."""
    rows = conn.execute(
        """
        SELECT m.player_a_id, r.winner_player_id,
               (SELECT CASE WHEN p.selection_player_id = m.player_a_id
                            THEN p.model_probability ELSE 1.0 - p.model_probability END
                  FROM predictions p WHERE p.match_id = m.id
                 ORDER BY p.id DESC LIMIT 1) AS model_p
        FROM matches m JOIN match_results r ON r.match_id = m.id
        WHERE m.match_date < ? AND r.winner_player_id IS NOT NULL
          AND m.player_a_id <> m.player_b_id
        """,
        (as_of_date,),
    ).fetchall()
    samples = [
        (float(row["model_p"]),
         1.0 if row["winner_player_id"] == row["player_a_id"] else 0.0)
        for row in rows
        if row["model_p"] is not None
    ]
    calibration = fit(samples)
    if calibration.is_identity:
        return calibration
    return Calibration(
        calibration.slope, calibration.intercept, calibration.sample, as_of_date
    )
