"""EXP-20261112-21：跑馬地非初出馬「檔位與走位」入面檔位偏離 60 嘅份量乘 k（Kelvin 2026-11-12：「test lowering HV draw weight」）。

依據（訊號檢查，hkjc_label_signal_check2.py）：跑馬地非初出馬檔位分喺模型之上每分 −0.0204 [−0.0323, −0.0087]
（模型已經用多咗檔位）；谷草表現項本身 AUC 0.609。
現行：leaf = 檔位 ＋ 0.45 ×（谷草表現 − 60）。arm：leaf = 60 ＋ k ×（檔位 − 60）＋ 0.45 ×（谷草表現 − 60）。
k 由環境變數 WC_EXP_HV_DRAW_K 傳入，預先登記兩個值：0.5（主）、0（檔位完全唔入，對照）。
沙田同跑馬地初出馬唔郁。注意：k 嘅方向係由同一批場次嘅訊號檢查得出，唔算完全樣本外。Fixed values.
"""
import os

K = float(os.environ["WC_EXP_HV_DRAW_K"])
ARM_NAME = f"hv_draw_weight_k{K}"


def apply():
    from hkjc_racing_engine.engine_core import RacingEngine
    from hkjc_racing_engine.scoring import clip_score

    original = RacingEngine._race_shape_context_score

    def patched(self, features):
        score, note, src = original(self, features)
        if self._is_happy_valley_context() and not self._is_debut():
            draw = float(features.get("draw_score", 60))
            score = clip_score(score - (1.0 - K) * (draw - 60.0))
        return score, note, src

    RacingEngine._race_shape_context_score = patched
