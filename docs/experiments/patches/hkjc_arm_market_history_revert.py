"""forward 退回 arm（`market_history_post_live`，EXP-20261115-07）：關掉上仗賠率組件 = 上線前嘅模型。
Δ = 候選（退回）− live；退回版喺 forward Gold、Good、NDCG@5 全部 ≥ 0 → 建議退回（Kelvin 決定）。
"""
ARM_NAME = "market_history_revert"


def apply():
    from hkjc_racing_engine import market_history
    market_history.ENABLED = False
