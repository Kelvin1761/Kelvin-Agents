"""EXP-20261112-08 arm：段速維度「步速修正等級」嘅輸入，由「近 3 仗輸頭馬幾多秒」換做 PIT 表現數字（近 6 仗）。

預先登記（跑之前寫死）：
  表   hkjc_fig_level_table.py 生成（WC_EXP_FIG_TABLE）；門檻 = dev 半現行四級比例喺 F 上嘅分位數，唔睇賽果
  U    用未換算嘅 F 定等級（只換輸入，唔理負磅）—— ablation
  W    用按今仗負磅換算嘅 W 定等級（主 arm）；W − U = 負磅換算嘅邊際貢獻
  冇表現數字嘅馬保留原本等級；四級加減分（+8／+1／−4／−8）同其餘段速訊號唔郁
  判決：hkjc_eval_harness compare --stage4 fixed_rule（全語料），另報 holdout 半（≥ 2026-09-06，門檻冇用過嗰半）
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
MODE = os.environ["WC_EXP_FIG_MODE"]
ARM_NAME = f"fig_level_{MODE}"
LABELS = ("✅ 步速修正後仍具競爭力", "➖ 步速修正後接近平均", "⚠️ 步速修正後仍偏慢", "❌ 步速修正後明顯落後")


def apply():
    import hkjc_auto_orchestrator as orch
    from hkjc_racing_engine.features.speed import SpeedScorer

    T = json.load(open(os.environ["WC_EXP_FIG_TABLE"]))
    cuts, table, col = T["cuts"], T["table"], {"U": 0, "W": 1}[MODE]
    original = orch._align_runner_headers

    def patched(logic_path, race_context, horses):
        original(logic_path, race_context, horses)
        row = table.get(f"{Path(logic_path).parent.name}|{int(race_context.get('race_number'))}") or {}
        for num, horse in horses.items():
            v = row.get(str(num)) if isinstance(horse, dict) else None
            if v:
                horse.setdefault("_data", {})["exp1112_fig"] = v[col]

    orch._align_runner_headers = patched
    base_data = SpeedScorer._data

    def _data(self):
        data = base_data(self)
        v = data.get("exp1112_fig")
        if v is None:
            return data
        k = 0 if v >= cuts[0] else 1 if v >= cuts[1] else 2 if v >= cuts[2] else 3
        out = dict(data)
        out["finish_time_adj_level"] = f"{LABELS[k]} (表現數字 {v:+.3f} s/km)"
        return out

    SpeedScorer._data = _data
