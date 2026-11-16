"""HKJC 跑法：Wong Choi 唯一標準（Kelvin 2026-11-16「唔好一樣嘢用兩套標準」）。

之前有三套：入分（檔位×跑法，近 6 仗平均位置比例）、dashboard「預計跑法」（近 3 仗、今仗出馬數、多數決）、
即場形勢（單仗、首 3 位／後三分一）。機不可失（2026-11-18 R3）因此同時係「守中」同「後上馬」。
而家全部用呢度：

  每仗比例 = 第一個沿途位置 ÷ 嗰場完成匹數
  分類     = ≤ 0.30 放頭、≤ 0.60 守中、其餘後上
  慣性跑法 = 賽前（日期嚴格早過今仗）最多 6 仗比例嘅平均（≥ 2 仗；唔夠 = 未明）
  一致性   = 嗰幾仗入面同慣性跑法同類嘅比例：≥ 80% 穩定、≥ 50% 大致、其餘多變

入分（draw_style，EXP-20261116-01 回放過閘）一直用緊呢套，所以統一冇改到任何分數。
歷史命中率：同一條規則，跑法表 2025-01-01 → 2026-10-10，16,669 馬次（下仗實際分類 == 預計）。
"""
from __future__ import annotations

from bisect import bisect_left

FRONT_MAX = 0.30
MID_MAX = 0.60
WINDOW = 6
MIN_RUNS = 2
CODE = {"放頭": "F", "守中": "M", "後上": "B"}
HIT_RATE = {
    ("放頭", "穩定"): 71.2, ("放頭", "大致"): 58.0, ("放頭", "多變"): 64.0,
    ("守中", "穩定"): 41.2, ("守中", "大致"): 37.8, ("守中", "多變"): 34.4,
    ("後上", "穩定"): 69.9, ("後上", "大致"): 55.8, ("後上", "多變"): 52.0,
}


def fraction(first_position, runners) -> float | None:
    """第一個沿途位置 ÷ 完成匹數；任何一個冇／唔合理 → None。"""
    try:
        first, n = int(first_position), int(runners)
    except (TypeError, ValueError):
        return None
    if first <= 0 or n <= 0:
        return None
    return first / n


def classify(frac: float | None) -> str | None:
    if frac is None:
        return None
    return "放頭" if frac <= FRONT_MAX else ("守中" if frac <= MID_MAX else "後上")


def prior_runs(code: str, race_date: str, table: dict | None) -> list:
    """跑法表入面日期嚴格早過今仗嘅最近 WINDOW 仗 [[日期, 比例], …]（舊 → 新）。"""
    runs = ((table or {}).get("horses") or {}).get(code) or []
    i = bisect_left([r[0] for r in runs], race_date)
    return runs[max(0, i - WINDOW):i]


def habitual_fraction(code: str, race_date: str, table: dict | None) -> float | None:
    prev = prior_runs(code, race_date, table)
    return sum(float(r[1]) for r in prev) / len(prev) if len(prev) >= MIN_RUNS else None


def habitual(code: str, race_date: str, table: dict | None) -> dict | None:
    """慣性跑法（顯示同入分共用）；唔夠 MIN_RUNS 仗 → None。"""
    prev = prior_runs(code, race_date, table)
    if len(prev) < MIN_RUNS:
        return None
    habit = sum(float(r[1]) for r in prev) / len(prev)
    label = classify(habit)
    styles = [classify(float(r[1])) for r in prev]
    share = styles.count(label) / len(styles)
    consistency = "穩定" if share >= 0.8 else ("大致" if share >= 0.5 else "多變")
    return {
        "label": label,
        "code": CODE[label],
        "habit": round(habit, 3),
        "consistency": consistency,
        "same": styles.count(label),
        "runs": [{"date": d, "frac": round(float(f), 3), "style": s} for (d, f), s in zip(reversed(prev), reversed(styles))],
        "hit_rate": HIT_RATE.get((label, consistency)),
    }
