"""EXP-20261112-04 arm：段速分嘅「L400 絕對值」按今仗負磅調整。

Kelvin 2026-11-12：「輕磅做出嚟嘅段速同頂磅應該有分別，應該用今場磅數做標準調整之前嘅段速。」

調整後 L400 = 上仗 L400 + C ×（今仗實際負磅 − 上仗實際負磅）。今仗重咗 → 當佢上仗段速冇咁快；輕咗 → 當快啲。
之後照舊過引擎嘅固定門檻（22.4／23.0／23.6／24.0／24.6）。其餘段速訊號（趨勢、能量、引擎型態）唔郁。

預先登記（跑之前寫死，冇擬合）：
  C ∈ {0.02, 0.04} 秒／磅，由環境變數 WC_EXP_L400_C 傳入
    0.02 ≈ 慣例「1 kg ≈ 一個馬位／一哩」攤落最後 400m；0.04 = 假設負磅影響集中喺末段，加倍
  上仗 = 賽績檔賽日前最近一仗，而且佢嘅 L400 同 Logic `raw_l400` 相差 ≤0.02s 先調（對唔上就唔郁）
  判決：hkjc_eval_harness compare --stage4 fixed_rule；兩個 C 都報，唔揀好嗰個
"""
import os
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
C = float(os.environ["WC_EXP_L400_C"])
ARM_NAME = f"l400_weight_adjusted_c{C}"


def apply():
    import hkjc_auto_orchestrator as orch
    from hkjc_racing_engine.features.speed import SpeedScorer
    from hkjc_racing_engine.scoring import parse_float
    from hkjc_weight_history_screen import formguide

    original = orch._align_runner_headers

    def patched(logic_path, race_context, horses):
        original(logic_path, race_context, horses)
        md = Path(logic_path).parent
        m = re.match(r"(\d{4}-\d{2}-\d{2})", md.name)
        if not m:
            return
        day = datetime.strptime(m.group(1), "%Y-%m-%d").date()
        _head, fg = formguide(md, int(race_context.get("race_number")))
        for num, horse in horses.items():
            e = fg.get(int(num)) if isinstance(horse, dict) and str(num).isdigit() else None
            if not e:
                continue
            runs = sorted([x for x in e["runs"] if x[0] < day], reverse=True)
            data = horse.setdefault("_data", {})
            raw = parse_float(data.get("raw_l400"))
            if not runs or raw is None or runs[0][3] is None or abs(runs[0][3] - raw) > 0.02:
                continue
            data["exp1112_l400_dw"] = e["today"] - runs[0][1]

    orch._align_runner_headers = patched
    base_data = SpeedScorer._data

    def _data(self):
        data = base_data(self)
        dw = data.get("exp1112_l400_dw")
        raw = parse_float(data.get("raw_l400"))
        if dw is None or raw is None:
            return data
        out = dict(data)
        out["raw_l400"] = f"{raw + C * float(dw):.2f}"
        return out

    SpeedScorer._data = _data
