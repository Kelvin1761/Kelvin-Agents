"""EXP-20261118-02 M1：段速分入面「輸頭馬差距」加減分（±8）歸零，量佢同上名／大敗紀錄分係咪重複。
只歸零分數；訊號計數（signals／strong_signals）唔郁，所以只係拎走呢一項嘅分。"""
ARM_NAME = "no_margin_bonus"


def apply():
    from hkjc_racing_engine import scoring
    for k in ("finish_competitive_bonus", "finish_faster_bonus", "finish_slightly_faster_bonus",
              "finish_avg_bonus", "finish_slow_pen", "finish_far_behind_pen"):
        scoring.SPEED_MICRO_WEIGHTS[k] = 0.0
