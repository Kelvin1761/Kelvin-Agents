"""forward 退回 arm（`joint_signals_post_live`，EXP-20261122-34）：關掉聯合訊號組件 = 上線前嘅模型。
Δ = 候選（退回）− live；退回版 forward Gold、Good、NDCG@5 全部 ≥ 0 → 建議退回（Kelvin 決定）。
"""
ARM_NAME = "joint_signals_revert"


def apply():
    from hkjc_racing_engine import joint_signals
    joint_signals.ENABLED = False
