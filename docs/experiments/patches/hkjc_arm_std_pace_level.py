"""EXP-20261112-09 arm：段速維度「步速修正等級」改用 Kelvin 2026-11-12 嘅定義。

輸入由 hkjc_std_pace_table.py 生成（WC_EXP_STD_TABLE），定義同門檻寫喺嗰個檔嘅 docstring（跑之前寫死）：
  P0  近 6 仗完成時間對馬會標準偏差（共同標準 = 今仗班次）
  P1  P0 ＋ 逐段對標準嘅步速修正
  P2  P1 ＋ 逐仗按今仗負磅換算（Kelvin 完整定義，主 arm）
四級加減分（+8／+1／−4／−8）同其餘段速訊號唔郁；冇新數值嘅馬保留原本等級。
判決：hkjc_eval_harness compare --stage4 fixed_rule（全語料）＋ holdout 半（≥ 2026-09-06，門檻冇用過）；
三個都報，P2 − P1 = 負磅換算嘅邊際貢獻，P1 − P0 = 步速修正嘅邊際貢獻。
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
MODE = os.environ["WC_EXP_STD_MODE"]
ARM_NAME = f"std_pace_level_{MODE}"
LABELS = ("✅ 步速修正後仍具競爭力", "➖ 步速修正後接近平均", "⚠️ 步速修正後仍偏慢", "❌ 步速修正後明顯落後")


def apply():
    import hkjc_auto_orchestrator as orch
    from hkjc_racing_engine.features.speed import SpeedScorer

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
    base_data = SpeedScorer._data

    def _data(self):
        data = base_data(self)
        v = data.get("exp1112_std")
        if v is None:
            return data
        k = 0 if v < cuts[0] else 1 if v < cuts[1] else 2 if v < cuts[2] else 3
        out = dict(data)
        out["finish_time_adj_level"] = f"{LABELS[k]} (近 6 仗對標準偏差 {v:+.2f}s)"
        return out

    SpeedScorer._data = _data
