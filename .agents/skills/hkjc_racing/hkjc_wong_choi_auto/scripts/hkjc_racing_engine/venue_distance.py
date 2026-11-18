"""同程上名要同場地（EXP-20261119-01 V2；Kelvin 2026-11-19「沙田1000直路同谷草1000轉彎係兩件事」）。

live「同程有上名」（distance_fit，+0.4284）只睇路程、唔睇場地。回放：同程上名但**全部**喺另一場地
（谷草／田草／泥地，標準同 surface_move.py）嘅馬，入頭三少過模型估計 dev −2.7pp、holdout −4.6pp。
raw' = raw + β·([同程有上名、但冇一次喺今仗場地] − 場均)，β = −1.27（2026/27 walk-forward 值：
fit 2019/20–2025/26，docs/experiments/patches/hkjc_samedist_venue/build_venue.py V2）。distance_fit 嘅 +0.4284 照留，
所以呢類馬淨效果約 −0.84。往績 = `_data.hk_history`（同轉場組件同一份；香港賽事、日期嚴格早過今仗）；
冇往績（初出／外隊）= 冇旗。回放 v4：dev Δlog-loss −0.00016 [−0.00029,−0.00003]、
holdout −0.00032 [−0.00051,−0.00013]、capture@5 +0.31（Holm 2 PASS）。`ENABLED = False` = 退回（forward 退回 arm 用）。
"""
from __future__ import annotations

import re

from .surface_move import SURFACE_NAME, SURFACES, today_surface

ENABLED = True
BETA = -1.27


def _int(v) -> int | None:
    m = re.search(r"\d{3,4}", str(v or ""))
    return int(m.group()) if m else None


def flag(horse: dict, today: str | None, today_distance) -> dict:
    """{'on': bool, 'placed_at': [場地…], 'n': 同程上名次數}"""
    data = horse.get("_data") if isinstance(horse.get("_data"), dict) else {}
    dist = _int(today_distance)
    placed = [h for h in (data.get("hk_history") or [])
              if isinstance(h, dict) and h.get("surface") in SURFACES and _int(h.get("distance")) == dist
              and isinstance(h.get("placing"), int) and 1 <= h["placing"] <= 3]
    at = sorted({h["surface"] for h in placed}, key=SURFACES.index)
    on = bool(placed and dist and today in SURFACES and today not in at)
    return {"on": on, "placed_at": at, "n": len(placed)}


def adjustments(horses: dict, today: str | None, today_distance) -> tuple[dict, dict]:
    if not horses:
        return {}, {}
    fl = {k: flag(h, today, today_distance) for k, h in horses.items()}
    raw = {k: BETA * float(v["on"]) for k, v in fl.items()}
    mean = sum(raw.values()) / len(raw)
    return {k: v - mean for k, v in raw.items()}, fl


def label(info: dict, today_distance) -> str:
    where = "／".join(SURFACE_NAME[s] for s in info.get("placed_at") or [])
    return f"{_int(today_distance)}米上名只喺{where}"


def apply(horses: dict, race_context: dict | None) -> int:
    """加落 ability_score_raw（轉場之後、grade／排名之前）。返回郁咗幾多匹。"""
    race_context = race_context or {}
    today, dist = today_surface(race_context), race_context.get("distance")
    if not ENABLED or today is None or not _int(dist):
        return 0
    from .scoring import compute_grade, to_display_scale
    scored = {k: h for k, h in horses.items() if isinstance(h, dict) and isinstance(h.get("python_auto"), dict)
              and h["python_auto"].get("ability_score_raw") is not None}
    adds, fl = adjustments(scored, today, dist)
    n = 0
    for k, add in adds.items():
        auto = scored[k]["python_auto"]
        auto["same_distance_venue"] = {"today": today, "distance": _int(dist), **fl[k]}
        raw = round(float(auto["ability_score_raw"]) + add, 4)
        auto["ability_score_raw"] = raw
        auto["ability_score"] = round(to_display_scale(raw), 2)
        auto["grade"] = compute_grade(auto["ability_score"])
        auto["same_distance_venue_delta"] = round(add, 4)
        for shadow in (auto.get("shadow_profiles") or {}).values():
            try:
                s_raw = round(float(shadow.get("ability_score_raw")) + add, 4)
            except (TypeError, ValueError):
                continue
            s_score = round(to_display_scale(s_raw), 2)
            shadow["ability_score_raw"] = s_raw
            shadow["ability_score"] = s_score
            shadow["grade"] = compute_grade(s_score)
            shadow["ability_delta"] = round(s_score - auto["ability_score"], 2)
            shadow.setdefault("sip_flags", []).append({"reason": "same_distance_venue", "boost": round(add, 4), "boost_scale": "raw"})
        n += abs(add) > 1e-9
    return n
