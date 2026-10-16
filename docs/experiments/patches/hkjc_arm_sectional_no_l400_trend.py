"""Sectional review 2026-10-16: zero no_l400_trend micro-weights (signal count unchanged)."""
ARM_NAME = "no_l400_trend"
def apply():
    from hkjc_racing_engine import scoring
    for k in ['l400_trend_up_bonus', 'l400_trend_steady_bonus', 'l400_trend_fluctuate_pen', 'l400_trend_decline_pen']:
        assert k in scoring.SPEED_MICRO_WEIGHTS, k
        scoring.SPEED_MICRO_WEIGHTS[k] = 0.0
