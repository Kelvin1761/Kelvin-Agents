"""forward 退回 arm（`draw_style_post_live`，EXP-20261116-01）：關掉檔位 × 跑法組件 = 上線前嘅模型。
Δ = 候選（退回）− live；退回版喺 forward Gold、Good、NDCG@5 全部 ≥ 0 → 建議退回（Kelvin 決定）。
"""
ARM_NAME = "draw_style_revert"


def apply():
    from hkjc_racing_engine import draw_style
    draw_style.ENABLED = False
