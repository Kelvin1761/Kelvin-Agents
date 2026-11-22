"""聯合訊號組件（EXP-20261122-34 J3；Kelvin 2026-11-22「J1 加埋同程一齊入」）。

17 個「單獨細過把尺、一齊量得到」嘅訊號一齊入分：raw' = raw + Σ β_k·(f_k − 場均)。
β = J3 2026/27 walk-forward 值（線性 L2 C=0.1，fit 2019/20–2025/26，base = live；
`docs/experiments/patches/hkjc_distance/build_joint_plus.py`）。
回放尺 v5.1：dev Δlog-loss −0.00103 [−0.00162,−0.00043]；holdout −0.00152 [−0.00227,−0.00075]、AUC +0.0032 [+0.0010,+0.0054]、
Gold +0.64、Good +0.99（舊護欄都過）。
live 定義同 J1 forward shadow（`hkjc_arm_joint_signals_shadow.py`）一樣（回放用馬匹頁全往績，live 係近似）：
  事件報告表（R／W／B／S 旗）、form_patterns（贏馬分、老馬贏後、降班）、排位表配備代碼（- 除去、1 首次）、
  `_data.prev_distance`、`_data.current_rating`＋班次、休賽日數；同程四項用 `_data.hk_history`（同轉場組件同一份往績）。
`ENABLED = False` = 退回（forward 退回 arm 用）。
"""
from __future__ import annotations

import re
from pathlib import Path

ENABLED = True
# 2026/27 walk-forward β，fit 喺 live base（base_live_20261122 = base_venue_age ＋ X1 連續藉口 ＋ 薄證據收窄）上；
# 同 base_venue_age 版差 ≤0.1，dev Δlog-loss −0.00100 [−0.00159,−0.00040]（v5.1 PASS）→ 同 excuse_streak 冇重複計數。
BETA = {"ride_q": 1.65, "wide2": 0.95, "blocked2": 0.66, "slow": 0.63, "rb_placed": 1.13, "rb_any": 0.47,
        "drop_rb": 2.89, "old_won": -3.62, "gear_off": 0.75, "gear_on": -0.41, "dist_down": 0.39,
        "class_pos": -0.54, "backup10": 0.20, "sd_worse": -2.51, "sd_hicls": 0.56, "sd_locls": -0.91, "sd_rate": 1.44}
LABEL = {"ride_q": "上仗騎法被查詢", "wide2": "上上仗走外疊冇遮擋", "blocked2": "近兩仗受阻", "slow": "上仗出閘慢",
         "rb_placed": "上仗入位＋評分跌返贏馬分", "rb_any": "評分跌返贏馬分", "drop_rb": "降班＋評分跌返贏馬分",
         "old_won": "老馬贏後", "gear_off": "除去配備", "gear_on": "首次戴配備", "dist_down": "大幅減程",
         "class_pos": "評分喺班內位置", "backup10": "十日內再出", "sd_worse": "同程表現差過自己平均",
         "sd_hicls": "同程喺更高班上過名", "sd_locls": "同程只喺低班上過名", "sd_rate": "同程上名率高（>2/3）"}
BAND_HIGH = {"第三班": 80, "第四班": 60, "第五班": 40}
_CLASS_NO = {"第一班": 1, "第二班": 2, "第三班": 3, "第四班": 4, "第五班": 5}


def _num(v):
    m = re.search(r"-?\d+(?:\.\d+)?", str(v or ""))
    return float(m.group()) if m else None


def _class_no(text) -> int | None:
    """班次 → 數字（細 = 高班）。同回放定義（build_joint_plus.sd_feats）一模一樣：純數字 = 嗰個班；
    其他非空字串（G1／G2／G3、4R、4YO、GRIFFIN、級賽、新馬…）一律當 0（最高）；空 = None。"""
    t = str(text or "").strip()
    if not t:
        return None
    for k, v in _CLASS_NO.items():
        if k in t:
            return v
    try:
        return int(float(t))
    except ValueError:
        return 0


def same_distance(horse: dict, dist, today_cls) -> dict:
    """同程四項（香港往績、日期嚴格早過今仗、完全同米數、任何場地）。"""
    out = dict.fromkeys(("sd_worse", "sd_hicls", "sd_locls", "sd_rate"), 0.0)
    data = horse.get("_data") if isinstance(horse.get("_data"), dict) else {}
    hist = [h for h in (data.get("hk_history") or []) if isinstance(h, dict)]
    d = _num(dist)
    if not hist or not d:
        return out
    placed = lambda h: isinstance(h.get("placing"), int) and 1 <= h["placing"] <= 3   # noqa: E731
    allr = sum(1 for h in hist if placed(h)) / len(hist)
    sd = [h for h in hist if _num(h.get("distance")) == d]
    pl = [h for h in sd if placed(h)]
    if len(sd) >= 2:
        out["sd_worse"] = float(len(pl) / len(sd) - allr < -0.25)
        out["sd_rate"] = float(len(pl) / len(sd) > 2 / 3)
    if today_cls is not None and pl:
        cls = [c for c in (_class_no(h.get("class")) for h in pl) if c is not None]
        out["sd_hicls"] = float(any(c < today_cls for c in cls))
        out["sd_locls"] = float(bool(cls) and all(c > today_cls for c in cls))
    return out


def features(h: dict, ctx: dict, table, gear_codes) -> dict:
    from . import incident_history as ih
    from .form_patterns import _finishes, flags
    from .market_history import horse_code
    data = h.get("_data") if isinstance(h.get("_data"), dict) else {}
    auto = h.get("python_auto") or {}
    f = dict.fromkeys(BETA, 0.0)
    code, d = horse_code(h), ctx.get("date")
    if table and code and d:
        last, two = ih.prev_two(code, d, table)
        if last is not None:
            f["ride_q"] = float("R" in last)
            f["wide2"] = float(two is not None and "W" in two and "W" not in last)
            f["blocked2"] = float("B" in last or (two is not None and "B" in two))
            f["slow"] = float("S" in last)
    fp = flags(h, ctx.get("cls"), d)
    r, w = fp.get("rating"), fp.get("win_rating")
    back = r is not None and w is not None and r <= w
    fin = _finishes(h)
    f["rb_any"] = float(back and not fp["classdrop_rating_back"])
    f["rb_placed"] = float(f["rb_any"] and bool(fin) and fin[0] is not None and fin[0] <= 3)
    f["drop_rb"] = float(fp["classdrop_rating_back"])
    f["old_won"] = float(fp["old_won_last"])
    f["gear_off"] = float(any(str(g).strip().endswith("-") for g in gear_codes))
    f["gear_on"] = float(any(re.fullmatch(r"[A-Z]+1", str(g).strip().upper()) for g in gear_codes))
    prev, today = _num(data.get("prev_distance")), _num(ctx.get("dist"))
    f["dist_down"] = float(bool(prev and today and prev - today >= 400))
    rating = _num(data.get("current_rating"))
    band = next((v for k, v in BAND_HIGH.items() if k in str(ctx.get("cls") or "")), None)
    f["class_pos"] = (rating - band) / 10.0 if (rating is not None and band is not None) else 0.0
    days = auto.get("days_since_last", data.get("days_since_last"))
    f["backup10"] = float(isinstance(days, (int, float)) and 0 < days <= 10)
    f.update(same_distance(h, ctx.get("dist"), _class_no(ctx.get("cls"))))
    return f


def apply(horses: dict, race_context: dict | None, meeting_dir: Path | None = None) -> int:
    """加落 ability_score_raw（馬齡之後、grade／排名之前）。返回郁咗幾多匹。"""
    if not ENABLED:
        return 0
    from . import incident_history as ih
    from .scoring import compute_grade, to_display_scale
    from .tags import load_gear
    rc = race_context or {}
    ctx = {"cls": rc.get("race_class"), "date": str(rc.get("race_date") or "")[:10] or None, "dist": rc.get("distance")}
    items = [(no, h) for no, h in horses.items() if isinstance(h, dict)
             and isinstance(h.get("python_auto"), dict) and h["python_auto"].get("ability_score_raw") is not None]
    if not items:
        return 0
    try:
        table = ih.load_table()
    except Exception:
        table = None
    gear = load_gear(meeting_dir, rc.get("race_number")) if meeting_dir else {}
    feats = [features(h, ctx, table, gear.get(str(no), [])) for no, h in items]
    means = {k: sum(f[k] for f in feats) / len(feats) for k in BETA}
    n = 0
    for (no, h), f in zip(items, feats):
        parts = {k: round(BETA[k] * (f[k] - means[k]), 4) for k in BETA}
        add = round(sum(parts.values()), 4)
        auto = h["python_auto"]
        auto["joint_signals"] = {"flags": {k: f[k] for k in BETA if f[k]}, "parts": {k: v for k, v in parts.items() if abs(v) >= 0.005}}
        auto["joint_signals_delta"] = add
        raw = round(float(auto["ability_score_raw"]) + add, 4)
        auto["ability_score_raw"] = raw
        auto["ability_score"] = round(to_display_scale(raw), 2)
        auto["grade"] = compute_grade(auto["ability_score"])
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
            shadow.setdefault("sip_flags", []).append({"reason": "joint_signals", "boost": add, "boost_scale": "raw"})
        n += abs(add) > 1e-9
    return n
