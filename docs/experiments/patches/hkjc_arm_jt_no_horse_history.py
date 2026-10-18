"""騎練訊號審查 2026-10-18：no_horse_history —— TRAINER_SIGNAL_CONTEXT_WEIGHTS 設 0。"""
ARM_NAME = "no_horse_history"
def apply():
    from hkjc_racing_engine import scoring
    for k in ['horse_history_strong', 'horse_history_supportive', 'horse_history_zero_place', 'horse_history_weak']:
        assert k in scoring.TRAINER_SIGNAL_CONTEXT_WEIGHTS, k
        scoring.TRAINER_SIGNAL_CONTEXT_WEIGHTS[k] = 0.0
