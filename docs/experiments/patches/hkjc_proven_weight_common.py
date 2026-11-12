"""EXP-20261112-02 共用：喺評分前將「今仗實際負磅」同「近 6 仗有冇喺今仗磅數上過名」塞入每匹馬 `_data`。

定義同 EXP-20261112-01 screening 一樣（跑之前寫死，冇擬合）：
  重磅   = 今仗實際負磅 ≥ 130（賽績檔，已扣見習減磅）
  證明過 = 賽日之前最近 6 仗，有一仗跑入頭三而嗰仗負磅 ≥ 今仗 − 2 磅
冇往績（初出）= 唔塞，arm 唔郁佢。
"""
from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
HEAVY, NEAR = 130, 2


def install():
    import hkjc_auto_orchestrator as orch
    from hkjc_weight_history_screen import formguide

    if getattr(orch, "_exp1112_context_installed", False):
        return
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
            runs = sorted([x for x in e["runs"] if x[0] < day], reverse=True)[:6]
            if not runs:
                continue
            t = e["today"]
            data = horse.setdefault("_data", {})
            data["exp1112_heavy"] = t >= HEAVY
            data["exp1112_proven"] = any(x[2] is not None and x[2] <= 3 and x[1] >= t - NEAR for x in runs)

    orch._align_runner_headers = patched
    orch._exp1112_context_installed = True
