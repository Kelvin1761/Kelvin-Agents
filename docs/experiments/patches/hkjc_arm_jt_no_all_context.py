"""騎練訊號審查 2026-10-18：no_all_context —— TRAINER_SIGNAL_CONTEXT_WEIGHTS 設 0。"""
ARM_NAME = "no_all_context"
def apply():
    from hkjc_racing_engine import scoring
    for k in ['horse_history_strong', 'horse_history_supportive', 'horse_history_zero_place', 'horse_history_weak', 'combo_elite', 'combo_positive', 'combo_negative', 'jockey_distance_elite', 'jockey_distance_positive', 'jockey_distance_negative', 'trainer_distance_elite', 'trainer_distance_positive', 'trainer_distance_negative', 'jockey_change_negative']:
        assert k in scoring.TRAINER_SIGNAL_CONTEXT_WEIGHTS, k
        scoring.TRAINER_SIGNAL_CONTEXT_WEIGHTS[k] = 0.0
