"""EXP-20261114-04 上線後 forward（`sectional_ft_post_live`）：退返冇段速 FT 組件，同 live 比較。
Δ = 舊版 − live。Gold／Good／NDCG@5 全部 ≥ 0 即係「舊版唔輸」→ 交 Kelvin 決定退唔退。Fixed, nothing fitted.
"""
ARM_NAME = "revert_sectional_ft"


def apply():
    from hkjc_racing_engine import scoring
    if not hasattr(scoring, "SECTIONAL_FT"):
        raise RuntimeError("scoring.SECTIONAL_FT 唔存在 —— 冇接通")
    scoring.SECTIONAL_FT = False
