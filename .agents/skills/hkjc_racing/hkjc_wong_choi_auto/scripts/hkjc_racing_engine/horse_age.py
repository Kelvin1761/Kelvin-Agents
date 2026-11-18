"""馬齡組件（EXP-20261119-01 A2；Kelvin 2026-11-19「9 歲係咪太老？年齡真係唔重要？」）。

raw' = raw + β·(max(0, 馬齡 − 6) − 場均)，β = −0.37（每大一歲；2026/27 walk-forward 值：fit 2019/20–2025/26，
docs/experiments/patches/hkjc_samedist_venue/build_age.py A2）。回放：8 歲以上入頭三少過模型估計約 1.5–2pp。
馬齡 = HKJC 馬匹頁（`_data.age`，orchestrator 寫）；冇馬齡 = 當 ≤6（中性）。
回放用「進口年份＋進口類別」推算馬齡（馬匹頁存檔冇馬齡），live 用真馬齡。
回放 v4：dev Δlog-loss −0.00043 [−0.00061,−0.00024]、holdout −0.00031 [−0.00052,−0.00009]（Holm 2 PASS）；
但 holdout AUC −0.0006、capture@5 −0.18 —— 主要改善機率校準，唔係排名。`ENABLED = False` = 退回。
"""
from __future__ import annotations

ENABLED = True
BETA_PER_YEAR = -0.37
PIVOT = 6


def age_of(horse: dict) -> int | None:
    data = horse.get("_data") if isinstance(horse.get("_data"), dict) else {}
    try:
        a = int(str(data.get("age") or "").strip())
    except ValueError:
        return None
    return a if 2 <= a <= 15 else None


def years_over(horse: dict) -> int:
    a = age_of(horse)
    return max(0, a - PIVOT) if a else 0


def adjustments(horses: dict) -> dict:
    if not horses:
        return {}
    raw = {k: BETA_PER_YEAR * years_over(h) for k, h in horses.items()}
    mean = sum(raw.values()) / len(raw)
    return {k: v - mean for k, v in raw.items()}


def apply(horses: dict, race_context: dict | None = None) -> int:
    """加落 ability_score_raw（同程場地之後、grade／排名之前）。返回郁咗幾多匹。"""
    if not ENABLED:
        return 0
    from .scoring import compute_grade, to_display_scale
    scored = {k: h for k, h in horses.items() if isinstance(h, dict) and isinstance(h.get("python_auto"), dict)
              and h["python_auto"].get("ability_score_raw") is not None}
    n = 0
    for k, add in adjustments(scored).items():
        auto = scored[k]["python_auto"]
        auto["horse_age"] = {"age": age_of(scored[k]), "years_over": years_over(scored[k])}
        raw = round(float(auto["ability_score_raw"]) + add, 4)
        auto["ability_score_raw"] = raw
        auto["ability_score"] = round(to_display_scale(raw), 2)
        auto["grade"] = compute_grade(auto["ability_score"])
        auto["horse_age_delta"] = round(add, 4)
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
            shadow.setdefault("sip_flags", []).append({"reason": "horse_age", "boost": round(add, 4), "boost_scale": "raw"})
        n += abs(add) > 1e-9
    return n
