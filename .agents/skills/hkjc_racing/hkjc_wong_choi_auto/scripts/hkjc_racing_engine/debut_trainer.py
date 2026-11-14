"""初出馬「練馬師初出紀錄」（EXP-20261114-06；Kelvin 2026-11-14 決定 3：顯示層＋forward shadow，唔入分）。

表 = 本機資料根 `HK_Racing/HKJC_Sections/debut_trainer.json`：{"events": [[日期, 練馬師, 入頭三 0/1], ...]}，
由 `hkjc_pit_sections_build.py` 每個賽日後重建（初出 = 分段頁第一次出現、而且喺 2020-09-01 或之後，避開 2019/20 窗口前已出過賽嘅馬）。
as-of：只計賽日**之前**嘅初出馬。收縮同 EXP-20261114-06 一樣：(入位 + 0.25·k)/(出賽 + k)，k = 10。
z 常數（EXP-20261114-06，2024-08 前）：mean 0.190、SD 0.070。
"""
from __future__ import annotations

import json
from pathlib import Path

K = 10
PRIOR = 0.25
Z_MEAN, Z_SD = 0.190, 0.070
_EVENTS: list | None = None


def load_events(path: str | Path | None = None) -> list:
    global _EVENTS
    if path is None and _EVENTS is not None:
        return _EVENTS
    if path is None:
        import wongchoi_paths
        path = Path(wongchoi_paths.HK_RACING) / "HKJC_Sections" / "debut_trainer.json"
    p = Path(path)
    _EVENTS = json.loads(p.read_text(encoding="utf-8")).get("events", []) if p.exists() else []
    return _EVENTS


def rate(trainer: str, race_date: str, events: list | None = None) -> dict | None:
    """練馬師喺 race_date 之前嘅初出馬上名率（收縮）；冇表 = None。"""
    ev = load_events() if events is None else events
    if not ev or not trainer:
        return None
    places = starts = 0
    for d, tr, p in ev:
        if d < race_date and tr == trainer:
            places += p
            starts += 1
    r = (places + PRIOR * K) / (starts + K)
    return {"rate": r, "places": places, "starts": starts, "z": (r - Z_MEAN) / Z_SD}
