"""Remove the blanket jockey-change −1.5 (EXP-20261010-05 direction audit)."""
ARM_NAME = "no_jockey_change_pen"
def apply():
    from hkjc_racing_engine import engine_core
    engine_core.RacingEngine._jockey_change_adjustment = lambda self, rows: 0.0
