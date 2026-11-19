"""薄證據長休馬收窄信心（EXP-20261119-05 S3；Kelvin 2026-11-19「實驗性上線收窄，呢類情況寧願保守啲」）。

⚠️ **實驗性上線、未證實改善**：回放 dev 三個候選全部 REJECT（每季只有 ~20 匹次，把尺冇功效），
Kelvin 明文決定照上，並由 forward `thin_shrink_post_live` 退回式監察。

群組 = 本地馬（唔係外隊）、香港往績 ≤2 仗、上一仗（香港）距今 >180 日。
歷史（2020/21–2026/27，本地 116 匹）：模型排 1–2 嘅 14 匹入位 29%、模型估 55%；排 3–5 33%／28%；6+ 11%／10%。
做法 = **收窄、唔係扣分**：raw' = 場均 + λ·(raw − 場均)，λ = 0.5（S3 逐季 walk-forward：0.14、0.19、0.18、0.43、0.31、
2026/27 = 0.50）；之後全場重新置中，場均唔變。高分嘅跌、低分嘅升 → 唔會壓冷門。
往績 = `_data.hk_history`（同轉場組件同一份；香港賽事、日期嚴格早過今仗）；冇往績（初出）= 唔套用。
`ENABLED = False` = 退回（forward 退回 arm 用）。
"""
from __future__ import annotations

from datetime import date

ENABLED = True
LAMBDA = 0.5
MAX_STARTS = 2
MIN_GAP_DAYS = 180


def _iso(v) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def profile(horse: dict, race_date) -> dict | None:
    """群組資料 {starts, gap}；唔喺群組 → None。"""
    from .tags import is_foreign
    if is_foreign(horse):
        return None
    data = horse.get("_data") if isinstance(horse.get("_data"), dict) else {}
    hist = data.get("hk_history") or []
    today, last = _iso(race_date), _iso(hist[0].get("date")) if hist else None
    if not hist or len(hist) > MAX_STARTS or today is None or last is None:
        return None
    gap = (today - last).days
    return {"starts": len(hist), "gap": gap} if gap > MIN_GAP_DAYS else None


def adjustments(raws: dict, members: set) -> dict:
    """raws：{馬號: raw}；members：群組馬號 → {馬號: raw 加減}（全場置中，場均唔變）。"""
    if not raws or not members & set(raws):
        return {}
    mean = sum(raws.values()) / len(raws)
    new = {k: (mean + LAMBDA * (r - mean)) if k in members else r for k, r in raws.items()}
    shift = sum(new.values()) / len(new) - mean
    return {k: new[k] - shift - raws[k] for k in raws}


def apply(horses: dict, race_context: dict | None) -> int:
    """改 ability_score_raw（馬齡之後、grade／排名之前）。返回郁咗幾多匹。"""
    if not ENABLED:
        return 0
    ctx = race_context or {}
    race_date = ctx.get("race_date") or ctx.get("date")
    from .scoring import compute_grade, to_display_scale
    scored = {k: h for k, h in horses.items() if isinstance(h, dict) and isinstance(h.get("python_auto"), dict)
              and h["python_auto"].get("ability_score_raw") is not None}
    prof = {k: p for k, h in scored.items() if (p := profile(h, race_date))}
    adds = adjustments({k: float(h["python_auto"]["ability_score_raw"]) for k, h in scored.items()}, set(prof))
    n = 0
    for k, add in adds.items():
        auto = scored[k]["python_auto"]
        if k in prof:
            auto["thin_evidence"] = dict(prof[k], lam=LAMBDA)
        raw = round(float(auto["ability_score_raw"]) + add, 4)
        auto["ability_score_raw"] = raw
        auto["ability_score"] = round(to_display_scale(raw), 2)
        auto["grade"] = compute_grade(auto["ability_score"])
        auto["thin_evidence_delta"] = round(add, 4)
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
            shadow.setdefault("sip_flags", []).append({"reason": "thin_evidence", "boost": round(add, 4), "boost_scale": "raw"})
        n += abs(add) > 1e-9
    return n
