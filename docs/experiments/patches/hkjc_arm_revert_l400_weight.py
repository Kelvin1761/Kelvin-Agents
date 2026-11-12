"""EXP-20261112-13 上線後 forward（`l400_weight_post_live`）：退返舊版 L400（唔按負磅換算），同 live 比較。

Δ = 舊版 − live。Gold／Good／NDCG@5 全部 ≥ 0 即係「舊版唔輸」→ 交 Kelvin 決定要唔要退返。Fixed, nothing fitted.
"""
ARM_NAME = "revert_l400_weight"


def apply():
    from hkjc_racing_engine import scoring

    scoring.L400_WEIGHT_ADJUST = False
