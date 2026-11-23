"""forward 退回 arm（`distance_home_post_live`，EXP-20261124-08 E5）：大幅增程返首本照扣 = 上線前嘅模型。
Δ = 候選（退回）− live；退回版喺 forward Gold、Good、NDCG@5 全部 ≥ 0 → 建議退回（Kelvin 決定）。
"""
ARM_NAME = "distance_home_revert"


def apply():
    from hkjc_racing_engine import distance_move
    distance_move.HOME_EXEMPT = False
