"""EXP-20261123-17 量度 arm：關掉檔位×跑法組件，攞每匹馬嘅檔位×跑法貢獻（base − 呢個 = 貢獻）。唔係候選。"""
ARM_NAME = "draw_style_off"


def apply():
    from hkjc_racing_engine import draw_style
    draw_style.ENABLED = False
