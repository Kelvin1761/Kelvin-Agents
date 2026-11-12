"""EXP-20261113-03 arm：表現數字／全程對馬會標準 併入段速維度（唔加權重，喺 speed_score 入面混合）。

Kelvin 2026-11-13：「試表現數字併入段速維度」＋「每一段對場地標準時間」。逐段篩選（EXP-20261113-02）：
L400／L800／後勁喺模型之上冇增量，早段同全程對標準有（Holm 0.007–0.009），表現數字最強（Holm 0.005）。
預先登記（跑之前寫死）：
  speed' = (1 − a)·speed + a·(60 + SD_speed·(X − mean_X)/SD_X)；冇 X 嘅馬唔郁；之後 clip
  X      fig = 賽果庫 PIT 表現數字 W（WC_EXP_FIG_TABLE）；std = 引擎 `_data.std_pace.p2` 取負（近 6 仗全程對標準＋負磅換算，越大越好）
  mean／SD 只用 dev 半（< 2026-09-06）；SD_speed = 非中性 speed_score 嘅 SD（WC_EXP_BLEND_STATS）
  a ∈ {0.33, 0.5}；四個 arm 全部報；MATRIX_WEIGHTS 唔郁（段速維度權重維持）
  判決 fixed_rule 389 場；Gold、Good 都唔可以負（Kelvin）；過咗都要 forward
"""
import json
import os
from pathlib import Path

SRC = os.environ.get("WC_EXP_BLEND_SRC", "fig")
A = float(os.environ.get("WC_EXP_BLEND_A", "0.33"))
ARM_NAME = f"section_blend_{SRC}_{int(round(A * 100))}"


def apply():
    import hkjc_auto_orchestrator as orch
    from hkjc_racing_engine.features.speed import SpeedScorer
    from hkjc_racing_engine.scoring import clip_score

    st = json.load(open(os.environ["WC_EXP_BLEND_STATS"]))
    mean, sd = st[SRC]
    if SRC == "fig":
        table = json.load(open(os.environ["WC_EXP_FIG_TABLE"]))["table"]
        original = orch._align_runner_headers

        def patched(logic_path, race_context, horses):
            original(logic_path, race_context, horses)
            row = table.get(f"{Path(logic_path).parent.name}|{int(race_context.get('race_number'))}") or {}
            for num, horse in horses.items():
                v = row.get(str(num)) if isinstance(horse, dict) else None
                if v and v[1] is not None:
                    horse.setdefault("_data", {})["exp_blend_x"] = v[1]

        orch._align_runner_headers = patched
    base_compute = SpeedScorer.compute

    def compute(self):
        score, note = base_compute(self)
        data = self._data()
        if SRC == "fig":
            x = data.get("exp_blend_x")
        else:
            pace = data.get("std_pace") or {}
            x = -pace["p2"] if pace.get("p2") is not None else None
        if x is None:
            return score, note
        target = 60.0 + st["speed_sd"] * (x - mean) / sd
        return clip_score((1 - A) * score + A * target), note

    SpeedScorer.compute = compute
