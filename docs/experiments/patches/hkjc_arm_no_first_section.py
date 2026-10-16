"""EXP-20261016-53 forward 反事實：將最快第一段四個權重設 0（即上線前嘅模型）。"""
ARM_NAME = "no_first_section"
KEYS = ("first_section_fast_bonus", "first_section_quick_bonus", "first_section_slowish_pen", "first_section_slow_pen")


def apply():
    from hkjc_racing_engine import scoring
    for key in KEYS:
        assert key in scoring.SPEED_MICRO_WEIGHTS, key
        scoring.SPEED_MICRO_WEIGHTS[key] = 0.0
