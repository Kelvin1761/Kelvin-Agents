"""EXP-20261124-17 forward shadow arm：打開初出馬試閘時間數字入分（live 預設 ENABLED=False，唔入分）。"""
ARM_NAME = "trial_time_shadow"


def apply():
    from hkjc_racing_engine import barrier_trial
    barrier_trial.ENABLED = True
