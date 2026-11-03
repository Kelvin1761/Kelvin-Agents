"""AU 大場次檔位分 —— 唯一計算位置（EXP-20261102-07／08）。

**USER-ACCEPTED EXPERIMENTAL LIVE（2026-11-02）**：walk-forward 四個 arm 全正但 Holm 後 p 0.068（REJECT 級證據）；
Kelvin：「i want to have something live and keep monitoring」。即時回退：`WC_AU_DRAW_LIVE=0`。
`au_draw_forward.py` 每晚比較上線版同冇檔位版，夠 1,000 場（≥8 匹）判一次（forward tracker 推 Telegram）。

    出賽馬 ≥ 8 匹：檔位分 = 1.4274 × d，d = −z(場內檔位排名)（0 = 最內；z 用場內 pstdev）
    少過 8 匹、或者有馬冇檔位：0

β = Z8 walk-forward 最後一日（2026-08-05 → 10-31 全部賽果），單位 = 綜合分。用 z 唔用檔位格數：
20 匹同 8 匹最內／最外同一個範圍（R8 格數版證據較弱）；長短途 β 差唔多（1.32／1.52／1.48），唔分路程。

直路賽（EXP-20261103-08，USER-ACCEPTED）：Flemington ≤1200m 冇彎，內欄路程短嘅機制唔存在 → 0。
實測最內五分位上名率 20.6%（其他場地 ≤1200m 32.1%）；乾淨窗口得 12 場，冇功效。其他場地嘅直路資料冇標記，唔加。
"""
from __future__ import annotations

import math
import os

DRAW_LIVE = os.environ.get("WC_AU_DRAW_LIVE", "1") != "0"
BETA = 1.4274
MIN_FIELD = 8
STRAIGHT_MAX_M = {"flemington": 1200}


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


def is_straight(venue, distance_m):
    """直路賽（冇彎）→ True。"""
    v = str(venue or "").lower()
    return bool(distance_m) and any(k in v and distance_m <= m for k, m in STRAIGHT_MAX_M.items())


def horse_adjustment(barrier, field_barriers, straight=False):
    """一匹馬嘅檔位分；`field_barriers` = 同場全部馬（包括本駒）。上線開關關咗或者直路賽 → 0。"""
    if not DRAW_LIVE or straight or not field_barriers:
        return 0.0
    field = list(field_barriers)
    try:
        i = [float(v) for v in field].index(float(barrier))
    except (TypeError, ValueError):
        return 0.0
    return adjustments(field)[i]


def explain(barrier, field_barriers, straight=False):
    """報告用：{applies, n, rank（1 = 最內）, z, adj, reason}。同 `horse_adjustment` 同一套數。"""
    field = list(field_barriers or [])
    n = len(field)
    out = {"applies": False, "n": n, "rank": None, "z": None, "adj": 0.0, "reason": ""}
    b = _clean(field)
    try:
        own = float(barrier)
    except (TypeError, ValueError):
        own = None
    if own is None or b is None or own not in b:
        out["reason"] = "檔位資料唔齊"
        return out
    if n < MIN_FIELD:
        out["reason"] = f"得 {n} 匹（少過 {MIN_FIELD} 匹），檔位唔計分"
        return out
    if not DRAW_LIVE:
        out["reason"] = "檔位分已關（WC_AU_DRAW_LIVE=0）"
        return out
    if straight:
        out["reason"] = "直路賽（冇彎），檔位唔計分"
        return out
    i = b.index(own)
    adj = adjustments(b)[i]
    out.update(applies=True, rank=sorted(b).index(own) + 1, z=round(adj / BETA, 2), adj=round(adj, 4))
    return out
