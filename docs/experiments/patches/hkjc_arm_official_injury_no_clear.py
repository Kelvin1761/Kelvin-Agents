"""EXP-20261020-02 arm：官方傷患記錄頁入馬匹健康分（mode = "no_clear"）。

loader（orchestrator `_load_official_injury_records`）live 同回放都已經行，將記錄寫入
`_data["official_injury_records"]`；呢個 arm 只係將 `scoring.OFFICIAL_INJURY_SCORING`
由 "off" 改做 "no_clear"。見 scoring.py 嘅定義。
"""
import sys

ARM_NAME = "official_injury_no_clear"


def apply():
    import hkjc_racing_engine.scoring as scoring
    scoring.OFFICIAL_INJURY_SCORING = "no_clear"
    for module in list(sys.modules.values()):   # 防止 top-level 同名 module 冇接通
        try:
            hit = getattr(module, "OFFICIAL_INJURY_SCORING", None) is not None
        except Exception:
            hit = False
        if hit:
            module.OFFICIAL_INJURY_SCORING = "no_clear"
    return ARM_NAME
