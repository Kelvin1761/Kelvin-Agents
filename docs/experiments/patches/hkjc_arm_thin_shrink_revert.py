"""forward 退回 arm（`thin_shrink_post_live`，EXP-20261119-05）：關掉薄證據收窄 = 上線前嘅模型。
Δ = 候選（退回）− live；退回版喺 forward Gold、Good、NDCG@5 全部 ≥ 0 → 建議退回（Kelvin 決定）。
"""
ARM_NAME = "thin_shrink_revert"


def apply():
    from hkjc_racing_engine import thin_evidence
    thin_evidence.ENABLED = False
