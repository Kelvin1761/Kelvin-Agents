"""forward 退回 arm（`venue_age_post_live`，EXP-20261119-01）：關掉同程場地＋馬齡兩個組件 = 上線前嘅模型。
Δ = 候選（退回）− live；退回版喺 forward Gold、Good、NDCG@5 全部 ≥ 0 → 建議退回（Kelvin 決定）。
"""
ARM_NAME = "venue_age_revert"


def apply():
    from hkjc_racing_engine import horse_age, venue_distance
    venue_distance.ENABLED = False
    horse_age.ENABLED = False
