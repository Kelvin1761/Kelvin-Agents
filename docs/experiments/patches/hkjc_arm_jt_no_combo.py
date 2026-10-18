"""騎練訊號審查 2026-10-18：no_combo —— TRAINER_SIGNAL_CONTEXT_WEIGHTS 設 0。"""
ARM_NAME = "no_combo"
def apply():
    from hkjc_racing_engine import scoring
    for k in ['combo_elite', 'combo_positive', 'combo_negative']:
        assert k in scoring.TRAINER_SIGNAL_CONTEXT_WEIGHTS, k
        scoring.TRAINER_SIGNAL_CONTEXT_WEIGHTS[k] = 0.0
