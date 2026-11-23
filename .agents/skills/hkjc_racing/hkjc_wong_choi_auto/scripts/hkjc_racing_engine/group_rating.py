"""級際賽淨評分（EXP-20261124-09 NRGo；Kelvin 2026-11-24「實驗性上線（只喺級際賽計評分），要做得啱」）—— **未證實改善**。

只限一／二／三級賽。淨評分 =（官方評分 − 場均）÷10 −（今仗負磅 − 場均）÷10（香港讓磅 1 分 = 1 磅；級際賽有性別／年齡讓磅）。
raw' = raw + 4.41·(淨評分 − 場均)（2026/27 walk-forward β，fit 2019/20–2025/26，base = live；
docs/experiments/patches/hkjc_distance/build_group_class.py NRGo）。
點解只喺級際賽：讓磅賽負磅已經抵銷評分（全部場一條式 NR REJECT、EXP-20261112-22 well-in 冇訊號）；級際賽冇抵銷。
回放（六季級際賽 160 場）：Δlog-loss −0.00248 [−0.01078,+0.00626]、首選贏 +7、Good −1.88（CI ±6）—— v5.2 REJECT（場數唔夠）；
淨評分好過純評分（−0.00058、首選贏 0）。全期 holdout 首選贏 +5 [+1,+10]。Kelvin 決定實驗性上線；forward `group_rating_post_live` 退回監察。
外隊馬冇香港評分 → 成場唔計（Kelvin 2026-11-24：唔可以當平均；國際評分要等國際賽日排位表核實）。
評分 = `_data.current_rating`；負磅 = 排位表 `weight`。次序：直路表現數字之後、grade／排名之前。`ENABLED = False` = 退回。
"""
from __future__ import annotations

import re

ENABLED = True
BETA = 4.41
GROUP_RE = re.compile(r"[一二三]級賽")


def _num(v) -> float | None:
    m = re.search(r"-?\d+(?:\.\d+)?", str(v if v is not None else ""))
    return float(m.group()) if m else None


def is_group(race_context: dict | None) -> bool:
    return bool(GROUP_RE.search(str((race_context or {}).get("race_class") or "")))


def adjustments(horses: dict) -> dict | None:
    """{馬號: (delta, info)}；有馬冇評分或者冇負磅（外隊馬）→ None（成場唔計）。"""
    vals = {}
    for k, h in horses.items():
        data = h.get("_data") if isinstance(h.get("_data"), dict) else {}
        r, w = _num(data.get("current_rating")), _num(h.get("weight"))
        if r is None or w is None or r <= 0:
            return None
        vals[k] = (r, w)
    if len(vals) < 2:
        return None
    mr = sum(r for r, _ in vals.values()) / len(vals)
    mw = sum(w for _, w in vals.values()) / len(vals)
    net = {k: (r - mr) / 10.0 - (w - mw) / 10.0 for k, (r, w) in vals.items()}
    mn = sum(net.values()) / len(net)
    return {k: (BETA * (v - mn), {"rating": vals[k][0], "weight": vals[k][1], "net": round((v - mn) * 10, 1)})
            for k, v in net.items()}


def apply(horses: dict, race_context: dict | None = None) -> int:
    if not ENABLED or not is_group(race_context):
        return 0
    from .scoring import compute_grade, to_display_scale
    scored = {k: h for k, h in horses.items() if isinstance(h, dict) and isinstance(h.get("python_auto"), dict)
              and h["python_auto"].get("ability_score_raw") is not None}
    adj = adjustments(scored) if scored else None
    if not adj:
        return 0
    n = 0
    for k, (add, info) in adj.items():
        auto = scored[k]["python_auto"]
        add = round(add, 4)
        auto["group_rating"] = info
        raw = round(float(auto["ability_score_raw"]) + add, 4)
        auto["ability_score_raw"] = raw
        auto["ability_score"] = round(to_display_scale(raw), 2)
        auto["grade"] = compute_grade(auto["ability_score"])
        auto["group_rating_delta"] = add
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
            shadow.setdefault("sip_flags", []).append({"reason": "group_rating", "boost": add, "boost_scale": "raw"})
        n += abs(add) > 1e-9
    return n
