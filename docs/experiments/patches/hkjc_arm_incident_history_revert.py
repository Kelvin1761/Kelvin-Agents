"""forward 退回 arm（`incident_history_post_live`，EXP-20261116-06）：關掉上仗事件報告組件 = 上線前嘅模型。
Δ = 候選（退回）− live；退回版喺 forward Gold、Good、NDCG@5 全部 ≥ 0 → 建議退回（Kelvin 決定）。
"""
ARM_NAME = "incident_history_revert"


def apply():
    from hkjc_racing_engine import incident_history
    incident_history.ENABLED = False
