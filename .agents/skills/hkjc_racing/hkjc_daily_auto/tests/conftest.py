"""排程測試嘅預設防線。

`run_prerace` / `run_lineup` 會 best-effort 去 HKJC 抓 SpeedPro 快照，同埋影賽前
WIN/PLA 賠率快照。測試入面好多個 case 直接行呢兩個 function，冇呢道防線就會真係
打 HKJC、真係寫入資料根（Tennis 試過測試寫咗真注單 —— opt-in 隔離一定要有預設），
網絡失敗仲會多出 Telegram 通知，令「notify 次數」類測試忽紅忽綠。

要測 SpeedPro wiring 嘅 test 自己 `monkeypatch.delenv` 再 mock subprocess；
要測賠率快照嘅 test 自己注入 `capture=`，或者 patch `capture_prerace_odds`。
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_live_hkjc_fetches(monkeypatch):
    monkeypatch.setenv("WC_HKJC_SPEEDPRO_DISABLE", "1")
    monkeypatch.setenv("WC_HKJC_ODDS_CAPTURE", "0")
