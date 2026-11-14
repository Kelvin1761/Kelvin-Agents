"""EXP-20261114-03 上線後 forward（`s_weights_post_live`）：退返舊外層權重，同 live（S 版）比較。
Δ = 舊版 − live。Gold／Good／NDCG@5 全部 ≥ 0 即係「舊版唔輸」→ 交 Kelvin 決定退唔退。Fixed, nothing fitted.
舊權重 = 2026-11-14 上線前 origin/main 嘅 dimensions.weights()。
"""
ARM_NAME = "revert_s_weights"
OLD = {"stability": 0.08847, "trainer_signal": 0.2362, "sectional": 0.1285, "race_shape": 0.2737, "horse_health": 0.0246844, "trackwork": 0.00983, "form_line": 0.0801, "class_advantage": 0.1585156}


def apply():
    from hkjc_racing_engine import scoring
    if set(OLD) != set(scoring.MATRIX_WEIGHTS):
        raise RuntimeError("維度唔對 —— 冇接通")
    scoring.MATRIX_WEIGHTS.update(OLD)
