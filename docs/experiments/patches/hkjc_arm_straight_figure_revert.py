"""forward 退回 arm（`straight_figure_post_live`，EXP-20261123-18 SF 實驗性上線）：關掉直路表現數字入分 = 上線前嘅模型。
Δ = 候選（退回）− live；退回版喺 forward Gold、Good、NDCG@5 全部 ≥ 0 → 建議退回（Kelvin 決定）。
直路每季只有 ~35 場，forward 要好耐先夠數 —— 判決要人手睇郁過嘅場次。
"""
ARM_NAME = "straight_figure_revert"


def apply():
    from hkjc_racing_engine import straight_figure
    straight_figure.ENABLED = False
