"""騎練訊號審查 2026-10-18：no_trainer_distance —— TRAINER_SIGNAL_CONTEXT_WEIGHTS 設 0。"""
ARM_NAME = "no_trainer_distance"
def apply():
    from hkjc_racing_engine import scoring
    for k in ['trainer_distance_elite', 'trainer_distance_positive', 'trainer_distance_negative']:
        assert k in scoring.TRAINER_SIGNAL_CONTEXT_WEIGHTS, k
        scoring.TRAINER_SIGNAL_CONTEXT_WEIGHTS[k] = 0.0
