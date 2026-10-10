"""Remove the gear-removed −3 on trainer_signal (EXP-20261010-05)."""
ARM_NAME = "no_gear_removed_pen"
def apply():
    from hkjc_racing_engine import engine_core
    from hkjc_racing_engine.scoring import clip_score
    engine_core.RacingEngine._apply_trainer_signal_v3 = lambda self, base: round(clip_score(base), 2)
