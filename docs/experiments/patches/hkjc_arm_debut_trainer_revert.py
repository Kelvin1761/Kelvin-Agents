"""forward 退回 arm（`debut_trainer_post_live`，EXP-20261123-13）：關掉初出馬練馬師初出紀錄入分 = 上線前嘅模型。
Δ = 候選（退回）− live；退回版喺 forward Gold、Good、NDCG@5 全部 ≥ 0 → 建議退回（Kelvin 決定）。
"""
ARM_NAME = "debut_trainer_revert"


def apply():
    from hkjc_racing_engine import debut_trainer
    debut_trainer.ENABLED = False
