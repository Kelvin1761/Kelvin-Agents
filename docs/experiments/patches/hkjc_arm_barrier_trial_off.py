"""EXP-20261124-16 forward 退回 arm。"""
ARM_NAME = "barrier_trial_off"

def apply():
    from hkjc_racing_engine import barrier_trial
    barrier_trial.ENABLED = False
