"""Arm B: absolute 同程表現 leaf (EXP-20261010-16, pre-registered alongside the residual arm).

Same evidence as `hkjc_arm_distance_fit_continuous.py` (±50 m = 1, ±51–200 m = 0.5),
but shrunk towards the population place rate 0.25 instead of the horse's own rate:
  leaf = 60 + 60 · ((target places + 3·0.25) / (target starts + 3) − 0.25), clipped [40, 80]
More spread than the residual arm, but carries general ability (double counting risk).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hkjc_arm_distance_fit_continuous as base  # noqa: E402

ARM_NAME = "distance_fit_absolute_k3"
POP = 0.25


def leaf(distribution, distance):
    if not distribution or not distance:
        return 60.0
    t_starts = t_places = 0.0
    for d, n, p in distribution:
        gap = abs(d - distance)
        w = 1.0 if gap <= 50 else 0.5 if gap <= 200 else 0.0
        t_starts += w * n
        t_places += w * p
    if t_starts <= 0:
        return 60.0
    rate = (t_places + base.K * POP) / (t_starts + base.K)
    return max(40.0, min(80.0, 60.0 + base.SCALE * (rate - POP)))


def apply():
    base.leaf = leaf
    base.apply()
