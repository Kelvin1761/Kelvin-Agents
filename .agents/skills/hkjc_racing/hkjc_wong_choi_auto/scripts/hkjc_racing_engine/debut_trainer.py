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


# ---- 入分（EXP-20261123-13；Kelvin 2026-11-23「初出馬練馬師初出上名率可以上線」）----
# raw' = raw + β·(z_初出 − 場均)，z 只限初出馬（非初出 = 0），β = 1.88（2026/27 walk-forward，fit 2019/20–2025/26，
# base = 表現數字版；docs/experiments/patches/hkjc_distance/build_debut.py DT）。
# 回放 v5.2：dev −0.00020、holdout −0.00026、六季有初出馬嘅場 −0.00066 [−0.00112,−0.00021]、AUC +0.0021。
# 次序：表現數字之後（回放 base 已含表現數字）、grade／排名之前。冇表 = z 0（唔郁）。`ENABLED = False` = 退回。
ENABLED = True
BETA = 1.88


def is_debut(horse: dict) -> bool:
    return bool(horse.get("is_debut") or horse.get("debut_runner"))


def adjustments(horses: dict, race_date: str, events: list | None = None) -> dict:
    """{馬號: (delta, info)}；info = rate() 結果（非初出馬 None）。"""
    if not horses or not race_date:
        return {}
    zs, infos = {}, {}
    for k, h in horses.items():
        info = rate(str(h.get("trainer") or "").strip(), race_date, events) if is_debut(h) else None
        infos[k] = info
        zs[k] = info["z"] if info else 0.0
    mean = sum(zs.values()) / len(zs)
    return {k: (BETA * (z - mean), infos[k]) for k, z in zs.items()}


def apply(horses: dict, race_context: dict | None = None) -> int:
    if not ENABLED:
        return 0
    from .scoring import compute_grade, to_display_scale
    race_date = str((race_context or {}).get("race_date") or "")[:10]
    scored = {k: h for k, h in horses.items() if isinstance(h, dict) and isinstance(h.get("python_auto"), dict)
              and h["python_auto"].get("ability_score_raw") is not None}
    if not scored or not race_date or not any(is_debut(h) for h in scored.values()):
        return 0
    n = 0
    for k, (add, info) in adjustments(scored, race_date).items():
        auto = scored[k]["python_auto"]
        add = round(add, 4)
        if info:
            auto["debut_trainer"] = {"rate": round(info["rate"], 4), "places": info["places"], "starts": info["starts"],
                                     "z": round(info["z"], 3)}
        raw = round(float(auto["ability_score_raw"]) + add, 4)
        auto["ability_score_raw"] = raw
        auto["ability_score"] = round(to_display_scale(raw), 2)
        auto["grade"] = compute_grade(auto["ability_score"])
        auto["debut_trainer_delta"] = add
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
            shadow.setdefault("sip_flags", []).append({"reason": "debut_trainer", "boost": add, "boost_scale": "raw"})
        n += abs(add) > 1e-9
    return n
