"""排程測試嘅預設防線。

`run_prerace` / `run_lineup` 會 best-effort 去 HKJC 抓 SpeedPro 快照。測試入面
好多個 case 直接行呢兩個 function，冇呢道防線就會真係打 HKJC、真係寫入
資料根（Tennis 試過測試寫咗真注單 —— opt-in 隔離一定要有預設）。

要測 SpeedPro wiring 嘅 test 自己 `monkeypatch.delenv` 再 mock subprocess。
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_live_speedpro(monkeypatch):
    monkeypatch.setenv("WC_HKJC_SPEEDPRO_DISABLE", "1")
