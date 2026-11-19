"""連續兩仗有藉口（EXP-20261119-06 X1；Kelvin 2026-11-19「實驗性上線 X1」）。

⚠️ **實驗性上線、未證實改善**：回放 dev／holdout Δlog-loss −0.00007／−0.00020 名義 PASS，但預先登記嘅 Holm（家族 2）
holdout p 0.0155 > 0.0125 差少少；改善嘅係機率準度，排名（capture@5 −0.16、AUC −0.0003）輕微負。forward `excuse_streak_post_live` 退回式監察。

指標 = 上兩仗（香港、日期嚴格早過今仗）**都有事件報告而且都有嚴格藉口**、而且**兩仗都未入位（第 4 或之後）**。
嚴格藉口 = 事件報告表旗 B（受阻／搵唔到位）｜W（走外疊冇遮擋）｜R（騎法被質疑：策騎指示交代／被查詢／被告誡、未有力策），
即係 `incident_history` 同一份表、同一套 regex（回放 `patches/hkjc_excuse_streak/diag_excuse_streak.py` 用嘅亦係同一套）。
raw' = raw + β·(指標 − 場均)，β = +1.69（2026/27 walk-forward：fit 2019/20–2025/26）。
回放殘差：dev +3.8pp [+0.8,+6.9]、holdout +4.2pp [+1.2,+7.3]，7 季全正；淨係「受阻」兩仗冇訊號（訊號嚟自混合）。
名次 = `_data.hk_history`（同轉場組件同一份）；搵唔到嗰仗名次 → 唔套用（唔估）。外隊馬中性。`ENABLED = False` = 退回。
"""
from __future__ import annotations

from bisect import bisect_left

ENABLED = True
BETA = 1.69
EXCUSE_FLAGS = ("B", "W", "R")


def _has_excuse(flag: str | None) -> bool:
    return flag is not None and any(c in flag for c in EXCUSE_FLAGS)


def last_two(code: str, race_date: str, table: dict) -> list[tuple[str, str | None]]:
    """上兩仗 [(日期, 旗)]（新 → 舊）；表 = incident_history.json，每仗一行，冇報告 = None。"""
    runs = (table.get("horses") or {}).get(code) or []
    i = bisect_left([r[0] for r in runs], race_date)      # 嚴格早過今仗
    return [(runs[j][0], runs[j][1]) for j in (i - 1, i - 2) if j >= 0]


def streak(horse: dict, race_date: str, table: dict) -> dict | None:
    """符合 X1 → {dates, flags, placings}；唔符合 → None。"""
    from .market_history import horse_code
    from .tags import is_foreign
    if is_foreign(horse):
        return None
    two = last_two(horse_code(horse), race_date, table)
    if len(two) < 2 or not all(_has_excuse(f) for _d, f in two):
        return None
    data = horse.get("_data") if isinstance(horse.get("_data"), dict) else {}
    placing = {str(h.get("date"))[:10]: h.get("placing") for h in (data.get("hk_history") or [])}
    pl = [placing.get(d) for d, _f in two]
    if not all(isinstance(p, int) for p in pl) or any(p <= 3 for p in pl):
        return None
    return {"dates": [d for d, _f in two], "flags": [f for _d, f in two], "placings": pl}


def adjustments(horses: dict, race_date: str, table: dict) -> tuple[dict, dict]:
    if not horses:
        return {}, {}
    info = {k: s for k, h in horses.items() if (s := streak(h, race_date, table))}
    raw = {k: BETA * (k in info) for k in horses}
    mean = sum(raw.values()) / len(raw)
    return {k: v - mean for k, v in raw.items()}, info


def apply(horses: dict, race_date: str | None, table: dict | None = None) -> int:
    """加落 ability_score_raw（馬齡之後、薄證據收窄之前）。返回郁咗幾多匹；冇表／冇日期 → 唔郁。"""
    if not ENABLED or not race_date:
        return 0
    if table is None:
        from .incident_history import load_table
        table = load_table()
    if not table:
        return 0
    from .scoring import compute_grade, to_display_scale
    scored = {k: h for k, h in horses.items() if isinstance(h, dict) and isinstance(h.get("python_auto"), dict)
              and h["python_auto"].get("ability_score_raw") is not None}
    adds, info = adjustments(scored, str(race_date)[:10], table)
    if not info:
        return 0
    n = 0
    for k, add in adds.items():
        auto = scored[k]["python_auto"]
        if k in info:
            auto["excuse_streak"] = info[k]
        raw = round(float(auto["ability_score_raw"]) + add, 4)
        auto["ability_score_raw"] = raw
        auto["ability_score"] = round(to_display_scale(raw), 2)
        auto["grade"] = compute_grade(auto["ability_score"])
        auto["excuse_streak_delta"] = round(add, 4)
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
            shadow.setdefault("sip_flags", []).append({"reason": "excuse_streak", "boost": round(add, 4), "boost_scale": "raw"})
        n += abs(add) > 1e-9
    return n
