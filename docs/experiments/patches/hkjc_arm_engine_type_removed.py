"""EXP-20261112-16b arm（訊號檢查之後加，跑 A/B 之前寫死）：剷走段速分入面「引擎型態」加減分。
訊號檢查：舊標籤模型之上每分 +0.006 [−0.020,+0.031]、新標籤 −0.033 [−0.084,+0.011]，兩個都冇訊號。Fixed."""
ARM_NAME = "engine_type_removed"


def apply():
    from hkjc_racing_engine.features.speed import SpeedScorer

    base_data = SpeedScorer._data

    def _data(self):
        data = base_data(self)
        if not data.get("engine_type"):
            return data
        out = dict(data)
        out["engine_type"] = ""          # 段速分見到冇引擎型態 → 唔計呢個訊號
        return out

    SpeedScorer._data = _data
