"""Arm: trackwork activity-count bonus removed (EXP-20261010-11, pre-registered).

The activity bonus is dominated by routine swimming/trotting counts (≈3 points
for almost every horse, floor −4 unreachable). Fixed rule: bonus → 0.
"""
ARM_NAME = "trackwork_activity_off"


def apply():
    from hkjc_racing_engine import scoring

    for key in ("gallop_weight", "trial_weight", "trotting_weight", "swimming_weight"):
        scoring.TRACKWORK_MICRO_WEIGHTS[key] = 0.0
