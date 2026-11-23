"""直路表現數字入分（EXP-20261123-18 SF；Kelvin 2026-11-24「實驗性上線」，**未證實改善**）。

只限沙田草地 1000 米（直路）。gap = 直路表現數字 − 整體表現數字（`performance_figure.segment_gap`，唯一定義）；has = 有冇 gap。
raw' = raw + 5.04·(gap − 場均) − 0.16·(has − 場均)（2026/27 walk-forward β，fit 2019/20–2025/26，base = live；
docs/experiments/patches/hkjc_distance/build_awt_figure.py straight）。
回放（六季直路 206 場）：Gold +1.94、Good +2.91、頭二入頭三 +5 [−5,+15]、log-loss −0.00100 [−0.00464,+0.00252] —— CI 跨零，
v5.2 REJECT（場數唔夠）；Kelvin 決定實驗性上線，forward `straight_figure_post_live` 退回監察（先例：EXP-20261119-06）。
次序：初出馬練馬師之後（回放 base 已含表現數字＋初出馬）、grade／排名之前。`ENABLED = False` = 退回。
"""
from __future__ import annotations

import re

ENABLED = True
BETA_GAP = 5.04
BETA_HAS = -0.16


def is_straight(race_context: dict | None) -> bool:
    from .surface_move import today_surface
    rc = race_context or {}
    m = re.search(r"(\d{3,4})", str(rc.get("distance") or ""))
    return today_surface(rc) == "田草" and bool(m) and int(m.group(1)) == 1000


def adjustments(horses: dict, race_date: str) -> dict:
    from . import performance_figure as pf
    from .market_history import horse_code
    table, seg = pf.figures_as_of(race_date), pf.segment_figures(race_date)["straight"]
    vals = {}
    for k, h in horses.items():
        code = horse_code(h) or ""
        r = pf.segment_gap(table.get(code), seg.get(code), pf._weight(h))
        vals[k] = (r["gap"], 1.0, r["n"]) if r else (0.0, 0.0, 0)
    n = len(vals)
    mg = sum(v[0] for v in vals.values()) / n
    mh = sum(v[1] for v in vals.values()) / n
    return {k: (BETA_GAP * (g - mg) + BETA_HAS * (hv - mh), {"gap": round(g, 3) if hv else None, "n": cnt})
            for k, (g, hv, cnt) in vals.items()}


def apply(horses: dict, race_context: dict | None = None) -> int:
    if not ENABLED or not is_straight(race_context):
        return 0
    from .scoring import compute_grade, to_display_scale
    race_date = str((race_context or {}).get("race_date") or "")[:10]
    scored = {k: h for k, h in horses.items() if isinstance(h, dict) and isinstance(h.get("python_auto"), dict)
              and h["python_auto"].get("ability_score_raw") is not None}
    if not scored or not race_date:
        return 0
    try:
        adj = adjustments(scored, race_date)
    except Exception as exc:  # 冇賽果庫 → 唔郁
        print(f"⚠️ 直路表現數字組件跳過：{exc}")
        return 0
    n = 0
    for k, (add, info) in adj.items():
        auto = scored[k]["python_auto"]
        add = round(add, 4)
        auto["straight_figure"] = info
        raw = round(float(auto["ability_score_raw"]) + add, 4)
        auto["ability_score_raw"] = raw
        auto["ability_score"] = round(to_display_scale(raw), 2)
        auto["grade"] = compute_grade(auto["ability_score"])
        auto["straight_figure_delta"] = add
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
            shadow.setdefault("sip_flags", []).append({"reason": "straight_figure", "boost": add, "boost_scale": "raw"})
        n += abs(add) > 1e-9
    return n
