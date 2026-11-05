"""AU 狀態與穩定性 —— 唯一計算位置（近績質素分，EXP-20261016-06 eq2_N6，用戶 2026-10-16 批准上線）。

    每場往績 v = (z_名次 + z_獎金) / 2
        z_名次 = (0.5 − (名次 − 1) / (出馬數 − 1)) / 0.3191
        z_獎金 = (log10 獎金 − 4.5863) / 0.3544
        z_獎金 > 0 時乘 (1 − 名次百分位)：頭馬攞足、最尾攞 0（EXP-20261105-05 C2）
    raw   = 最近 6 場完整正式賽，權重 1.0／0.8／0.6／0.4／0.3／0.2 嘅加權平均（最少 2 場）
    分數  = 60 + 20 × 場內 z（raw）
    資料唔夠（本駒少過 2 場、全場少過 3 匹有 raw、或者場內冇差異）→ 0.6 × 近績分 + 0.4 × 表現質素分
    英愛法往績為主 → 官方評分代理（`overseas.py`，引擎負責）
    今場路程同最近一場合資格往績差 ≥ 400m → −5（EXP-20261016-71 F2）

**跑得好先攞獎金分（EXP-20261105-05 C2，USER-ACCEPTED 2026-11-05，連 C2 refit 權重）**：以前每場值 = (z_名次 + z_獎金)/2，
z_名次 有界（±1.567）而 z_獎金 冇界（$1M = +3.99），百萬元賽事跑最尾 = +1.21 高過 $55k 賽事贏 = +1.00。
而家正嘅獎金分乘 (1 − 名次百分位)；負嘅（低獎金賽事）照扣，唔會負負得正。§8：fixed arm Good +1.15 [+0.27, +1.97]、
refit arm Good +0.91 [−0.03, +1.77]、AUC +0.33 [+0.00, +0.64]，Gold 冇升 → 判決 REJECT，用戶接受上線。
已知代價：v3 大爛地 Good CI 全負（用戶話之後再處理）。

常數只用 run_date < 2026-08-05 嘅 41,647 條往績計（冇賽果標籤），**凍結，唔准調**。
研究證據（來源 FLAG，唔係正式 v3 WIN）：§8 fixed arm Gold +1.62pp [+0.14, +3.30]，
refit arm Gold +1.89pp [+0.73, +3.12]、Good +1.75pp [+0.14, +3.55]。
增縮程：模型名次層內剩餘超額 −5.8pp [−7.6, −4.1]；v3 RANKING_WIN（Gold ±0、Good +0.28pp），
§8 fixed arm OOS RANKING_WIN，跨 arm Holm p 0.096 —— 冇代價嘅修正，唔係已證實改善。
"""
from __future__ import annotations

import math
import os
import re

from .scoring import clip_score

RECENCY_WEIGHTS = (1.0, 0.8, 0.6, 0.4, 0.3, 0.2)
SD_PCT = 0.3190854842046987
MU_LOG_PRIZE = 4.586282737969997
SD_LOG_PRIZE = 0.35441149811378186
MIN_RUNS = 2
MIN_FIELD = 3
TRIP_CHANGE_M = 400.0
TRIP_CHANGE_PEN = -5.0


# EXP-20261105-06 研究開關（只喺分支）：H1 濕地往績唔打折；H2 今場大爛地用返舊公式。
HEAVY_MODE = os.environ.get("WC_AU_FQ_HEAVY", "").strip().upper()
_HEAVY = re.compile(r"\bHeavy\b", re.I)


def is_heavy_going(going):
    """場地家族係 Heavy（往績 Formguide 只有家族名、冇數字；今場有冇數字都算）。"""
    return bool(_HEAVY.search(str(going or "")))


def digest(runs, *, legacy=False):
    """表現質素分揀好嘅往績（最新先）→ {raw, run_count, runs}；完整往績少過 2 場 → {}。"""
    values = []
    for run in runs:
        finish, starters = int(run.get("finish_pos") or 0), int(run.get("starters") or 0)
        if not (starters >= 2 and 1 <= finish <= starters):
            continue
        pct = (finish - 1) / (starters - 1)
        z_place = (0.5 - pct) / SD_PCT
        z_prize_raw = (math.log10(float(run["prize"])) - MU_LOG_PRIZE) / SD_LOG_PRIZE
        undiscounted = legacy or (HEAVY_MODE == "H1" and is_heavy_going(run.get("going")))
        z_prize = z_prize_raw * (1.0 - pct) if z_prize_raw > 0 and not undiscounted else z_prize_raw
        values.append((run, (z_place + z_prize) / 2, z_place, z_prize, z_prize_raw))
    if len(values) < MIN_RUNS:
        return {}
    weights = RECENCY_WEIGHTS[: len(values)]
    raw = sum(v[1] * w for v, w in zip(values, weights)) / sum(weights)
    return {"raw": round(raw, 6), "run_count": len(values),
            "runs": [{"date": r.get("date"), "finish_pos": r.get("finish_pos"),
                      "starters": r.get("starters"), "prize": r.get("prize"),
                      "distance": r.get("distance"), "value": round(v, 6),
                      "z_place": round(zp, 4), "z_prize": round(zq, 4), "z_prize_raw": round(zr, 4), "weight": w}
                     for (r, v, zp, zq, zr), w in zip(values, weights)]}


def composite(form, quality):
    """資料唔夠時嘅舊 stability 組合：0.6 × 近績分 + 0.4 × 表現質素分。"""
    return clip_score(60.0 + 0.6 * (clip_score(form) - 60.0) + 0.4 * (clip_score(quality) - 60.0))


def field_z(raw, run_count, field_count, mean, stdev):
    """場內 z；資料唔夠 → None。"""
    if raw is None or run_count < MIN_RUNS or field_count < MIN_FIELD or mean is None or not stdev or stdev <= 0:
        return None
    return (raw - mean) / stdev


def trip_change(today_m, last_m):
    """大幅增程／縮程 → (扣分, "增程"／"縮程")；唔適用 → (0.0, "")。"""
    if not (last_m and today_m and abs(today_m - last_m) >= TRIP_CHANGE_M):
        return 0.0, ""
    return TRIP_CHANGE_PEN, "增程" if today_m > last_m else "縮程"


def score_without_proxy(features, detail):
    """由已存嘅 feature 同 `form_quality` detail 重砌冇海外代理時嘅分數（forward 監察用）。"""
    z = field_z(detail.get("raw"), int(detail.get("run_count") or 0), int(detail.get("field_count") or 0),
                detail.get("field_mean"), detail.get("field_stdev") or 0.0)
    score = (composite(features.get("form_score", 60), features.get("performance_quality_score", 60))
             if z is None else clip_score(60.0 + 20.0 * z))
    if detail.get("trip_change"):
        score = clip_score(score + TRIP_CHANGE_PEN)
    return round(score, 6)
