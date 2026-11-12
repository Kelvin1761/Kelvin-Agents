"""EXP-20261112-09 arm（加入版）：保留現行「輸頭馬幾多秒」等級，另外加一項「近 6 仗對標準步速修正偏差」。

背景：P0／P1／P2 用新數值**取代**現行等級，三個都跌（EXP-20261112-09）。呢度測「加多一項」而唔係取代。

預先登記（跑之前寫死）：
  新項四級（門檻同 hkjc_std_pace_table.py 一樣）加減分 = 現行等級加減分嘅一半：+4／+0.5／−2／−4
    —— 兩項都係量完成表現，新項攞一半，冇擬合
  加法同頭段速度一樣：喺段速分所有返回路徑之後加，再 clip
  WC_EXP_STD_MODE = P1（步速修正，唔理負磅，ablation）或 P2（再按今仗負磅換算，主 arm）
  判決：hkjc_eval_harness compare --stage4 fixed_rule（全語料）＋ holdout 半
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
MODE = os.environ["WC_EXP_STD_MODE"]
ARM_NAME = f"std_pace_added_{MODE}"
POINTS = (4.0, 0.5, -2.0, -4.0)


def apply():
    import hkjc_auto_orchestrator as orch
    from hkjc_racing_engine.features.speed import SpeedScorer
    from hkjc_racing_engine.scoring import clip_score

    T = json.load(open(os.environ["WC_EXP_STD_TABLE"]))
    cuts, table, col = T["cuts"][MODE], T["table"], int(MODE[1])
    original = orch._align_runner_headers

    def patched(logic_path, race_context, horses):
        original(logic_path, race_context, horses)
        row = table.get(f"{Path(logic_path).parent.name}|{int(race_context.get('race_number'))}") or {}
        for num, horse in horses.items():
            v = row.get(str(num)) if isinstance(horse, dict) else None
            if v:
                horse.setdefault("_data", {})["exp1112_std"] = v[col]

    orch._align_runner_headers = patched
    base_compute = SpeedScorer.compute

    def compute(self):
        score, note = base_compute(self)
        v = self._data().get("exp1112_std")
        if v is None:
            return score, note
        k = 0 if v < cuts[0] else 1 if v < cuts[1] else 2 if v < cuts[2] else 3
        return clip_score(score + POINTS[k]), note

    SpeedScorer.compute = compute
