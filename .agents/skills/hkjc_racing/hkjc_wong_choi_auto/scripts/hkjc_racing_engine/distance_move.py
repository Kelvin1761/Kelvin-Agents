"""大幅增程組件（EXP-20261117-03 D1；Kelvin 2026-11-17「增程係真訊號，check 可唔可以入分」）。

raw' = raw + β·([今仗路程 − 上仗路程 ≥ 400 米] − 場均)
β = −0.926（2026/27 walk-forward 值：fit 2019/20–2025/26 全部回放季，docs/experiments/patches/hkjc_distance/build_distance.py D1）。
上仗 = HKJC 馬匹頁最近一場**香港**賽事（日期嚴格早過今仗；`_data.prev_distance`，由 hkjc_auto_orchestrator 寫）——
同回放用嘅馬匹頁往績同一個來源。冇上仗（初出／外隊）= 冇旗（中性）。
回放 v4：dev Δlog-loss −0.00011 [−0.00021,−0.00002]、holdout −0.00013 [−0.00025,−0.00002]（Holm 2 PASS）；Gold／Good 冇變。
`ENABLED = False` = 退回（forward 退回 arm 用）。

返首本豁免（EXP-20261124-08 E5；Kelvin 2026-11-24「大幅增程去返自己首本路程唔應該扣，打和或者更好就拎走」）：
觸發增程但（以前喺今仗路程 ±100 米上過名）或者（上上仗／再前一仗喺今仗路程 ±100 米跑過）→ 唔當增程。
回放（1,121 匹次）：dev Δlog-loss +0.00005 [−0.00001,+0.00011]、holdout 0.00000，頭二入頭三 +2／+1 → 打和，照 Kelvin 預先批准上線。
往績 = `_data.hk_history`（最近先；live 馬匹頁近三季，回放用全部往績 —— 好舊嘅上名紀錄 live 可能睇唔到）。`HOME_EXEMPT = False` = 退回。
"""
from __future__ import annotations

import re

ENABLED = True
BETA_UP = -0.926
BIG_MOVE = 400
HOME_EXEMPT = True
HOME_TOL = 100


def _int(v) -> int | None:
    m = re.search(r"\d{3,4}", str(v or ""))
    return int(m.group()) if m else None


def home_distance(horse: dict, today_distance) -> bool:
    """返首本：以前喺今仗路程 ±100 米上過名，或者上上仗／再前一仗喺今仗路程 ±100 米跑過（唔計上仗）。"""
    data = horse.get("_data") if isinstance(horse.get("_data"), dict) else {}
    hist = [h for h in (data.get("hk_history") or []) if isinstance(h, dict)]
    today = _int(today_distance)
    if not today or not hist:
        return False
    near = lambda h: (_int(h.get("distance")) or 0) and abs(_int(h.get("distance")) - today) <= HOME_TOL  # noqa: E731
    recent = any(near(h) for h in hist[1:3])
    proven = any(near(h) and isinstance(h.get("placing"), int) and 1 <= h["placing"] <= 3 for h in hist)
    return bool(recent or proven)


def flag(horse: dict, today_distance) -> tuple[bool, int | None]:
    data = horse.get("_data") if isinstance(horse.get("_data"), dict) else {}
    prev, today = _int(data.get("prev_distance")), _int(today_distance)
    up = bool(prev and today and today - prev >= BIG_MOVE)
    if up and HOME_EXEMPT and home_distance(horse, today_distance):
        up = False
    return up, prev


def is_home_exempt(horse: dict, today_distance) -> bool:
    data = horse.get("_data") if isinstance(horse.get("_data"), dict) else {}
    prev, today = _int(data.get("prev_distance")), _int(today_distance)
    return bool(HOME_EXEMPT and prev and today and today - prev >= BIG_MOVE and home_distance(horse, today_distance))


def adjustments(horses: dict, today_distance) -> dict:
    if not horses:
        return {}
    raw = {k: BETA_UP * float(flag(h, today_distance)[0]) for k, h in horses.items()}
    mean = sum(raw.values()) / len(raw)
    return {k: v - mean for k, v in raw.items()}


def apply(horses: dict, race_context: dict | None) -> int:
    """加落 ability_score_raw（事件報告之後、grade／排名之前）。返回郁咗幾多匹。"""
    race_context = race_context or {}
    today = race_context.get("distance")
    if not ENABLED or not _int(today):
        return 0
    from .scoring import compute_grade, to_display_scale
    scored = {k: h for k, h in horses.items() if isinstance(h, dict) and isinstance(h.get("python_auto"), dict)
              and h["python_auto"].get("ability_score_raw") is not None}
    n = 0
    for k, add in adjustments(scored, today).items():
        auto = scored[k]["python_auto"]
        up, prev = flag(scored[k], today)
        auto["distance_move"] = {"prev": prev, "today": _int(today), "up": up, "home": is_home_exempt(scored[k], today)}
        raw = round(float(auto["ability_score_raw"]) + add, 4)
        auto["ability_score_raw"] = raw
        auto["ability_score"] = round(to_display_scale(raw), 2)
        auto["grade"] = compute_grade(auto["ability_score"])
        auto["distance_move_delta"] = round(add, 4)
        for shadow in (auto.get("shadow_profiles") or {}).values():   # 反事實同主線一樣加（同其他後置組件）
            try:
                s_raw = round(float(shadow.get("ability_score_raw")) + add, 4)
            except (TypeError, ValueError):
                continue
            s_score = round(to_display_scale(s_raw), 2)
            shadow["ability_score_raw"] = s_raw
            shadow["ability_score"] = s_score
            shadow["grade"] = compute_grade(s_score)
            shadow["ability_delta"] = round(s_score - auto["ability_score"], 2)
            shadow.setdefault("sip_flags", []).append({"reason": "distance_move", "boost": round(add, 4), "boost_scale": "raw"})
        n += abs(add) > 1e-9
    return n
