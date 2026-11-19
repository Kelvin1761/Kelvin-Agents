"""forward 退回 arm（`excuse_streak_post_live`，EXP-20261119-06）：關掉連續兩仗有藉口 = 上線前嘅模型。
Δ = 候選（退回）− live；退回版喺 forward Gold、Good、NDCG@5 全部 ≥ 0 → 建議退回（Kelvin 決定）。
"""
ARM_NAME = "excuse_streak_revert"


def apply():
    from hkjc_racing_engine import excuse_streak
    excuse_streak.ENABLED = False
