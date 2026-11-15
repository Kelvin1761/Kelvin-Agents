"""檔位 × 跑法組件（EXP-20261116-01；Kelvin 2026-11-16「檔位 × 跑法」＋「證實改善就上線」）。

現有檔位分（三級＋PIT 欄位調整）保留唔郁；呢個組件加返模型歷史上漏咗嘅檔位殘差，分兩部分：
  跑法格  (組別 HV/ST/AWT/STR × 短≤1200／長, 慣性跑法 F／M／B／U, 檔位段 內1–4／中5–9／外10+)
  逐檔格  (組別, 檔號 1–13+, 大場 ≥12)
  raw' = raw + β_style·(跑法格值 − 場均) + β_curve·(逐檔格值 − 場均)
慣性跑法 = 賽前最多 6 仗（日期嚴格早過今仗）「第一個沿途位置 ÷ 完成匹數」平均（≥2 仗；≤0.3 前置、≤0.6 中置、其餘後上；冇 = U）。
格值同 β 凍結喺 resources/hkjc_draw_style.json（docs/experiments/patches/hkjc_draw_style/freeze.py，回放 v3 至 2026-11-11）。
跑法歷史表 HKJC_Sections/run_style.json 由 hkjc_pit_sections_build.py 每個賽日後重建（同上仗賠率表一樣）。
回放：dev Δlog-loss −0.00101、holdout −0.00093（Holm 2 PASS）、AUC dev +0.0036、頭二選有中 dev +1.21。
冇檔號 → 兩個格值都當 0；冇跑法表 → 跑法當 U。`ENABLED = False` = 退回（forward 退回 arm 用）。
"""
from __future__ import annotations

import json
import re
from bisect import bisect_left
from pathlib import Path

ENABLED = True
FROZEN_PATH = Path(__file__).resolve().parents[2] / "resources" / "hkjc_draw_style.json"
_FROZEN: dict | None = None
_TABLE: dict | None = None


def frozen() -> dict:
    global _FROZEN
    if _FROZEN is None:
        _FROZEN = json.loads(FROZEN_PATH.read_text(encoding="utf-8"))
    return _FROZEN


def load_table(path: str | Path | None = None) -> dict | None:
    global _TABLE
    if path is None and _TABLE is not None:
        return _TABLE
    if path is None:
        import wongchoi_paths
        path = Path(wongchoi_paths.HK_RACING) / "HKJC_Sections" / "run_style.json"
    p = Path(path)
    if not p.exists():
        return None
    _TABLE = json.loads(p.read_text(encoding="utf-8"))
    return _TABLE


def group(race_context: dict) -> str | None:
    track = str(race_context.get("track") or race_context.get("surface") or "")
    m = re.search(r"\d{3,4}", str(race_context.get("distance") or ""))
    if not m:
        return None
    dist = int(m.group())
    awt = "全天候" in track or "AWT" in track.upper() or "ALL WEATHER" in track.upper()
    g = "HV" if "跑馬地" in str(race_context.get("venue") or "") else ("AWT" if awt else ("STR" if dist == 1000 else "ST"))
    return g + ("S" if dist <= 1200 else "L")


def style_class(frac: float | None) -> str:
    return "U" if frac is None else ("F" if frac <= 0.3 else ("M" if frac <= 0.6 else "B"))


def draw_band(d: int) -> str:
    return "I" if d <= 4 else ("C" if d <= 9 else "O")


def horse_code(horse: dict) -> str:
    code = str(horse.get("horse_code") or horse.get("hkjc_horse_id") or "")
    return code.rsplit("_", 1)[-1] if code else ""


def habitual_position(code: str, race_date: str, table: dict | None) -> float | None:
    runs = ((table or {}).get("horses") or {}).get(code) or []
    i = bisect_left([r[0] for r in runs], race_date)      # 嚴格早過今仗
    prev = [float(r[1]) for r in runs[max(0, i - 6):i]]
    return sum(prev) / len(prev) if len(prev) >= 2 else None


def adjustments(horses: dict, race_context: dict, race_date: str, table: dict | None) -> tuple[dict, dict]:
    """horses：{馬號: horse dict} → ({馬號: raw 加減}, {馬號: 說明})。"""
    fz = frozen()
    g = group(race_context or {})
    if not g or not horses:
        return {k: 0.0 for k in horses}, {}
    big = int(len(horses) >= 12)
    s_val, d_val, info = {}, {}, {}
    for k, h in horses.items():
        try:
            d = int(h.get("barrier") or h.get("draw"))
        except (TypeError, ValueError):
            s_val[k] = d_val[k] = 0.0
            continue
        st = style_class(habitual_position(horse_code(h), race_date, table))
        s_val[k] = float(fz["style_cells"].get(f"{g}|{st}|{draw_band(d)}", 0.0))
        d_val[k] = float(fz["curve_cells"].get(f"{g}|{min(d, 13)}|{big}", 0.0))
        info[k] = {"group": g, "style": st, "draw": d}
    ms = sum(s_val.values()) / len(s_val)
    md = sum(d_val.values()) / len(d_val)
    out = {}
    for k in horses:
        out[k] = fz["beta_style"] * (s_val[k] - ms) + fz["beta_curve"] * (d_val[k] - md)
        if k in info:
            info[k].update(style_part=round(fz["beta_style"] * (s_val[k] - ms), 3), curve_part=round(fz["beta_curve"] * (d_val[k] - md), 3))
    return out, info


def apply(horses: dict, race_context: dict | None, table: dict | None = None) -> int:
    """加落 ability_score_raw（上仗賠率之後、grade／排名之前）。返回郁咗幾多匹；冇日期 → 唔郁。"""
    race_context = race_context or {}
    race_date = str(race_context.get("race_date") or "")[:10]
    if not ENABLED or not race_date:
        return 0
    table = table if table is not None else load_table()
    from .scoring import compute_grade, to_display_scale
    scored = {k: h for k, h in horses.items() if isinstance(h, dict) and isinstance(h.get("python_auto"), dict)
              and h["python_auto"].get("ability_score_raw") is not None}
    adds, info = adjustments(scored, race_context, race_date, table)
    n = 0
    for k, add in adds.items():
        auto = scored[k]["python_auto"]
        raw = round(float(auto["ability_score_raw"]) + add, 4)
        auto["ability_score_raw"] = raw
        auto["ability_score"] = round(to_display_scale(raw), 2)
        auto["grade"] = compute_grade(auto["ability_score"])
        auto["draw_style_delta"] = round(add, 4)
        if k in info:
            auto["draw_style_detail"] = info[k]
        # shadow 係同一匹馬嘅反事實：後置加減兩邊一樣（同上仗賠率組件一樣）
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
            shadow.setdefault("sip_flags", []).append({"reason": "draw_style", "boost": round(add, 4), "boost_scale": "raw"})
        n += abs(add) > 1e-9
    return n
