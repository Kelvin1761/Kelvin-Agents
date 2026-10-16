"""Sectional review 2026-10-16: zero no_energy micro-weights (signal count unchanged)."""
ARM_NAME = "no_energy"
def apply():
    from hkjc_racing_engine import scoring
    for k in ['energy_up_bonus', 'energy_steady_bonus', 'energy_down_pen']:
        assert k in scoring.SPEED_MICRO_WEIGHTS, k
        scoring.SPEED_MICRO_WEIGHTS[k] = 0.0
