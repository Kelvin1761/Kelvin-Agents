"""9維排名矩陣每行一句＋總評（Kelvin 2026-11-18）。

只有一份 code：`hkjc_racing_engine/summary.enrich`。新 Logic 已經寫咗；舊場次（2026-11-18 之前）
喺度用同一份 code 補返。純顯示文字 —— 唔讀權重、唔郁分數（parser 嘅權重照舊由報告嚟）。
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[3] / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts"


def enrich_summary(auto: dict, field_scores: list[float]) -> None:
    summary = auto.get("summary")
    if not isinstance(summary, dict) or ("dims" in summary and "verdict" in summary):
        return
    try:
        if str(_SCRIPTS) not in sys.path:
            sys.path.insert(0, str(_SCRIPTS))
        importlib.import_module("hkjc_racing_engine.summary").enrich(summary, auto, field_scores)
    except Exception:   # 顯示用：引擎 import 唔到就冇一句話，唔影響其他欄
        return
