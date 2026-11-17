"""轉場組件（EXP-20261117-06 K2；Kelvin 2026-11-17「谷草 轉 田草 轉 泥地／互相轉場後表現／初次」）。

三種場地（全 Wong Choi 一個標準）：谷草 = 跑馬地草地、田草 = 沙田草地、泥地 = 沙田全天候。
raw' = raw + Σ β_k·(f_k − 場均)：
  谷草→田草（上仗跑馬地、今仗沙田草地） −2.65
  田草→谷草                              +1.12
  初次田草（香港往績從未跑過沙田草地）    −1.70
  初次泥地                                −2.03
β = 2026/27 walk-forward 值（fit 2019/20–2025/26，docs/experiments/patches/hkjc_distance/build_kelvin7.py K2）。
往績 = `_data.hk_history`（orchestrator 由 HKJC 馬匹頁寫，只計香港賽事、日期嚴格早過今仗）；冇往績（初出）= 冇旗。
回放 v4：dev Δlog-loss −0.00072 [−0.00124,−0.00015]、holdout −0.00095 [−0.00149,−0.00040]（Holm 3 PASS），holdout Gold +0.70。
`ENABLED = False` = 退回（forward 退回 arm 用）。
"""
from __future__ import annotations

ENABLED = True
BETA = {"hv_to_st": -2.65, "st_to_hv": 1.12, "first_st": -1.70, "first_awt": -2.03}
LABEL = {"hv_to_st": "跑馬地轉沙田草地", "st_to_hv": "沙田草地轉跑馬地", "first_st": "初次沙田草地", "first_awt": "初次泥地"}
SURFACES = ("谷草", "田草", "泥地")
SURFACE_NAME = {"谷草": "跑馬地", "田草": "沙田草地", "泥地": "泥地"}


def surface_of(venue_track) -> str | None:
    """HKJC 場地字串 → 谷草／田草／泥地；海外 = None。"""
    v = str(venue_track or "")
    if "全天候" in v or "泥" in v:
        return "泥地" if v.startswith("沙田") or "全天候" in v else None
    if v.startswith("跑馬地"):
        return "谷草"
    if v.startswith("沙田"):
        return "田草"
    return None


def today_surface(race_context: dict) -> str | None:
    venue = str((race_context or {}).get("venue") or "")
    track = str((race_context or {}).get("track") or (race_context or {}).get("surface") or "")
    if "全天候" in track or "AWT" in track.upper() or "泥" in track:
        return "泥地"
    if "跑馬地" in venue:
        return "谷草"
    if "沙田" in venue:
        return "田草"
    return None


def flags(horse: dict, today: str | None) -> dict:
    data = horse.get("_data") if isinstance(horse.get("_data"), dict) else {}
    hist = [h for h in (data.get("hk_history") or []) if h.get("surface") in SURFACES]
    out = dict.fromkeys(BETA, False)
    if not hist or today not in SURFACES:
        return out
    prev = hist[0]["surface"]
    seen = {h["surface"] for h in hist}
    out["hv_to_st"] = prev == "谷草" and today == "田草"
    out["st_to_hv"] = prev == "田草" and today == "谷草"
    out["first_st"] = today == "田草" and "田草" not in seen
    out["first_awt"] = today == "泥地" and "泥地" not in seen
    return out


def adjustments(horses: dict, today: str | None) -> tuple[dict, dict]:
    if not horses:
        return {}, {}
    fl = {k: flags(h, today) for k, h in horses.items()}
    raw = {k: sum(BETA[f] for f, on in v.items() if on) for k, v in fl.items()}
    mean = sum(raw.values()) / len(raw)
    return {k: v - mean for k, v in raw.items()}, fl


def apply(horses: dict, race_context: dict | None) -> int:
    """加落 ability_score_raw（大幅增程之後、grade／排名之前）。返回郁咗幾多匹。"""
    today = today_surface(race_context or {})
    if not ENABLED or today is None:
        return 0
    from .scoring import compute_grade, to_display_scale
    scored = {k: h for k, h in horses.items() if isinstance(h, dict) and isinstance(h.get("python_auto"), dict)
              and h["python_auto"].get("ability_score_raw") is not None}
    adds, fl = adjustments(scored, today)
    n = 0
    for k, add in adds.items():
        auto = scored[k]["python_auto"]
        auto["surface_move"] = {"today": today, **{f: bool(v) for f, v in fl[k].items()}}
        raw = round(float(auto["ability_score_raw"]) + add, 4)
        auto["ability_score_raw"] = raw
        auto["ability_score"] = round(to_display_scale(raw), 2)
        auto["grade"] = compute_grade(auto["ability_score"])
        auto["surface_move_delta"] = round(add, 4)
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
            shadow.setdefault("sip_flags", []).append({"reason": "surface_move", "boost": round(add, 4), "boost_scale": "raw"})
        n += abs(add) > 1e-9
    return n
