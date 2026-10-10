"""Remove the finish-time trend ±5 on sectional (EXP-20261010-05)."""
ARM_NAME = "no_finish_trend"
def apply():
    from hkjc_racing_engine import engine_core
    from hkjc_racing_engine.scoring import clip_score
    engine_core.RacingEngine._apply_finish_time_trend = lambda self, base: round(clip_score(base), 2)
