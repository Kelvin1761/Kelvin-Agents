"""AU 大場次檔位分 —— 唯一計算位置（EXP-20261102-07／08）。

**USER-ACCEPTED EXPERIMENTAL LIVE（2026-11-02）**：walk-forward 四個 arm 全正但 Holm 後 p 0.068（REJECT 級證據）；
Kelvin：「i want to have something live and keep monitoring」。即時回退：`WC_AU_DRAW_LIVE=0`。
`au_draw_forward.py` 每晚比較上線版同冇檔位版，夠 1,000 場（≥8 匹）判一次（forward tracker 推 Telegram）。

    出賽馬 ≥ 8 匹：檔位分 = 1.4274 × d，d = −z(場內檔位排名)（0 = 最內；z 用場內 pstdev）
    少過 8 匹、或者有馬冇檔位：0

β = Z8 walk-forward 最後一日（2026-08-05 → 10-31 全部賽果），單位 = 綜合分。用 z 唔用檔位格數：
20 匹同 8 匹最內／最外同一個範圍（R8 格數版證據較弱）；長短途 β 差唔多（1.32／1.52／1.48），唔分路程。
"""
from __future__ import annotations

import math
import os

DRAW_LIVE = os.environ.get("WC_AU_DRAW_LIVE", "1") != "0"
BETA = 1.4274
MIN_FIELD = 8


def _clean(values):
    try:
        out = [float(v) for v in values]
    except (TypeError, ValueError):
        return None
    return out if all(math.isfinite(v) and v > 0 for v in out) else None


def adjustments(barriers, beta=BETA, min_field=MIN_FIELD):
    """同場每匹馬嘅檔位分（同 `barriers` 次序）；唔適用 → 全 0。"""
    n = len(barriers)
    b = _clean(barriers)
    if b is None or n < min_field:
        return [0.0] * n
    order = sorted(range(n), key=lambda i: b[i])
    rank = [0.0] * n
    for k, i in enumerate(order):
        rank[i] = float(k)
    mean = sum(rank) / n
    sd = (sum((r - mean) ** 2 for r in rank) / n) ** 0.5
    return [0.0 if sd <= 0 else beta * -(r - mean) / sd for r in rank]


def horse_adjustment(barrier, field_barriers):
    """一匹馬嘅檔位分；`field_barriers` = 同場全部馬（包括本駒）。上線開關關咗 → 0。"""
    if not DRAW_LIVE or not field_barriers:
        return 0.0
    field = list(field_barriers)
    try:
        i = [float(v) for v in field].index(float(barrier))
    except (TypeError, ValueError):
        return 0.0
    return adjustments(field)[i]
