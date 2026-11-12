"""EXP-20261112-23：沙田「檔位與走位」入面「近仗消耗分」（全組件審計：場內 AUC 0.468，低過擲毫；模型之上 −0.140／SD [−0.196,−0.082]）。

WC_EXP_TRIP_MODE（預先登記兩個）：
  removed  剷走，檔位同走位匹配按原比例補返（55:25 → 68.75%:31.25%）
  flipped  方向調轉：消耗分 → 120 − 消耗分（以 60 為中心反轉），權重唔郁
跑馬地唔郁（跑馬地本身冇用消耗入分）。Fixed values.
"""
import os

MODE = os.environ["WC_EXP_TRIP_MODE"]
ARM_NAME = f"st_trip_consumption_{MODE}"


def apply():
    from hkjc_racing_engine import scoring
    from hkjc_racing_engine.engine_core import RacingEngine
    from hkjc_racing_engine.scoring import clip_score

    original = RacingEngine._race_shape_context_score

    def patched(self, features):
        score, note, src = original(self, features)
        if not self._is_sha_tin_context():
            return score, note, src
        w = scoring.RACE_SHAPE_CONTEXT_WEIGHTS
        draw = float(features.get("draw_score", 60))
        fit, _ = self._draw_position_fit_score()
        trip, _ = self._trip_consumption_score()
        if MODE == "removed":
            tot = w["sha_tin_draw"] + w["sha_tin_draw_position_fit"]
            new = draw * w["sha_tin_draw"] / tot + fit * w["sha_tin_draw_position_fit"] / tot
        else:
            new = draw * w["sha_tin_draw"] + fit * w["sha_tin_draw_position_fit"] + (120.0 - trip) * w["sha_tin_trip_consumption"]
        return clip_score(new), note, src

    RacingEngine._race_shape_context_score = patched
