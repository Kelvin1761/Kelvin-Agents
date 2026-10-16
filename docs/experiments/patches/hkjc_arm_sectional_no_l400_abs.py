"""Sectional review 2026-10-16: zero no_l400_abs micro-weights (signal count unchanged)."""
ARM_NAME = "no_l400_abs"
def apply():
    from hkjc_racing_engine import scoring
    for k in ['l400_22_4_bonus', 'l400_23_0_bonus', 'l400_23_6_bonus', 'l400_24_0_pen', 'l400_24_6_pen']:
        assert k in scoring.SPEED_MICRO_WEIGHTS, k
        scoring.SPEED_MICRO_WEIGHTS[k] = 0.0
