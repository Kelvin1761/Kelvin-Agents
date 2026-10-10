"""Arm: trackwork gallop-trend bases neutral (EXP-20261010-11, pre-registered).

Screening (EXP-11) found the model over-applies the trend: horses whose gallop
times are 放緩 place +1.4pp above model expectation, 加強 −1.2pp. Fixed rule,
nothing fitted: 加強 70 / 放緩 46.24 → 60. Activity bonus and 翻案復刻 untouched.
"""
ARM_NAME = "trackwork_trend_neutral"


def apply():
    from hkjc_racing_engine import scoring

    scoring.TRACKWORK_MICRO_WEIGHTS["improving_base"] = 60.0
    scoring.TRACKWORK_MICRO_WEIGHTS["slowing_base"] = 60.0
