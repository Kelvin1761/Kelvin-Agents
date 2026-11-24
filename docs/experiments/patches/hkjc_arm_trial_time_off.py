"""EXP-20261124-17 forward 退回 arm。"""
ARM_NAME = "trial_time_off"


def apply():
    from hkjc_racing_engine import barrier_trial
    barrier_trial.ENABLED = False
