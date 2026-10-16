"""Sectional review 2026-10-16: zero no_engine micro-weights (signal count unchanged)."""
ARM_NAME = "no_engine"
def apply():
    from hkjc_racing_engine import scoring
    for k in ['engine_progressive_bonus', 'engine_steady_bonus', 'engine_mixed_low_conf_pen', 'engine_fast_slow_pen', 'engine_low_conf_pen']:
        assert k in scoring.SPEED_MICRO_WEIGHTS, k
        scoring.SPEED_MICRO_WEIGHTS[k] = 0.0
