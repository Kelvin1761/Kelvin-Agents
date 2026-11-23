"""forward 退回 arm（`performance_figure_post_live`，EXP-20261123-10）：關掉表現數字 = 返返用段速維度（上線前嘅模型）。
Δ = 候選（退回）− live；退回版喺 forward Gold、Good、NDCG@5 全部 ≥ 0 → 建議退回（Kelvin 決定）。
"""
ARM_NAME = "performance_figure_revert"


def apply():
    from hkjc_racing_engine import performance_figure
    performance_figure.ENABLED = False
