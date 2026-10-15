"""AU point-in-time（PIT）模式：「呢場係 live 定係歷史回放？」只有一個定義。

點解要有呢個（2026-10-15，EXP-20261015-04）：L1 嘅「加未來唔可以改過去」測試
（`test_au_future_append_invariance.py`）捉到四個冇日期閘嘅來源 —— 表格頁累積
統計、騎練 `(LY:)` cache、檔位矩陣、騎練 tier 表。四個都係「live 賽前用最新
版本係啱嘅，但回放／重抽舊場次就食咗未來」。修法一律係：

    賽事日期 D **早過**今日（悉尼時間）→ 歷史 → 只准用 D 之前已知嘅資訊
    否則（今日或之後）              → live → 行為同以前一模一樣

`WC_AU_PIT_TODAY=YYYY-MM-DD` 可以覆寫「今日」—— 只係俾 A/B、golden 證明
「live 分支冇郁」用（例如設 `2000-01-01` = 全部當 live）。生產唔好 set。
"""
from __future__ import annotations

import os
import re
from datetime import date, datetime, time, timezone

SYDNEY = "Australia/Sydney"
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _tz():
    from zoneinfo import ZoneInfo
    return ZoneInfo(SYDNEY)


def today_sydney() -> str:
    override = str(os.environ.get("WC_AU_PIT_TODAY") or "").strip()
    if _ISO.match(override):
        return override
    return datetime.now(_tz()).date().isoformat()


def is_iso_date(value) -> bool:
    return bool(_ISO.match(str(value or "").strip()))


def is_historical(race_date) -> bool:
    """D < 今日（悉尼）。日期唔合法 → False（維持 live 行為，唔會靜靜改 live）。"""
    text = str(race_date or "").strip()[:10]
    if not is_iso_date(text):
        return False
    return text < today_sydney()


def day_start_utc(race_date: str) -> datetime:
    """D 當日悉尼 00:00 嘅 UTC 時刻。「嚴格早過 D」= captured_at < 呢個時刻。"""
    d = date.fromisoformat(str(race_date)[:10])
    return datetime.combine(d, time(0, 0), tzinfo=_tz()).astimezone(timezone.utc)


def parse_timestamp(value):
    """ISO timestamp → aware UTC datetime；攞唔到回 None。冇時區當 UTC。"""
    try:
        t = datetime.fromisoformat(str(value or "").strip())
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return t.astimezone(timezone.utc)
