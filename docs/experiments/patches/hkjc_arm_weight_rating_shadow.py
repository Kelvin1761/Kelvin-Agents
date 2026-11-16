"""forward shadow `weight_rating_shadow`（EXP-20261116-07 HR；回放 dev CI 跨零，唔入分）：
  一二班（讓賽）raw += β_r1·(評分 − 場均)/10；分級賽 raw += β_w·(負磅 − 場均)/10 + β_rg·(評分 − 場均)/10。
β = 2026/27 walk-forward（fit 2019/20–2025/26；docs/experiments/patches/hkjc_weight_resid/build_hr.py）。
評分 = Logic `_data.current_rating`，負磅 = `weight`（排位表，賽前已知）。喺所有後置組件之後加，登記做 sip_flag（shadow 同步）。
Δ = 候選 − live；forward Gold／Good／NDCG@5 全部 ≥ 0 → 建議入分（Kelvin 決定）。
"""
ARM_NAME = "weight_rating_shadow"
BETA_R12, BETA_W_GROUP, BETA_R_GROUP = -1.77, -6.51, 4.69


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def adds(horses: dict, race_class: str) -> dict:
    c = str(race_class or "")
    hi = c.startswith(("第一班", "第二班"))
    grp = "級賽" in c
    if not (hi or grp):
        return {}
    rt = {k: _num((h.get("_data") or {}).get("current_rating")) for k, h in horses.items()}
    w = {k: _num(h.get("weight")) for k, h in horses.items()}

    def centred(d):
        obs = [v for v in d.values() if v is not None]
        if not obs:
            return {k: 0.0 for k in d}
        fill = sum(obs) / len(obs)
        x = {k: (fill if v is None else v) for k, v in d.items()}
        m = sum(x.values()) / len(x)
        return {k: (v - m) / 10.0 for k, v in x.items()}
    r, ww = centred(rt), centred(w)
    if hi:
        return {k: BETA_R12 * r[k] for k in horses}
    return {k: BETA_W_GROUP * ww[k] + BETA_R_GROUP * r[k] for k in horses}


def apply():
    import hkjc_auto_orchestrator as orch
    from hkjc_racing_engine import incident_history
    from hkjc_racing_engine.scoring import compute_grade, to_display_scale
    orig_score = orch.HKJCAutoOrchestrator.score_race
    state = {"cls": None}

    def score_race(self, race_file, *a, **k):
        import json
        try:
            state["cls"] = (json.load(open(race_file, encoding="utf-8")).get("race_analysis") or {}).get("race_class")
        except Exception:
            state["cls"] = None
        return orig_score(self, race_file, *a, **k)

    orig_apply = incident_history.apply

    def apply_after(horses, race_date, table=None):
        n = orig_apply(horses, race_date, table)
        scored = {k: h for k, h in horses.items() if isinstance(h, dict) and isinstance(h.get("python_auto"), dict)
                  and h["python_auto"].get("ability_score_raw") is not None}
        for k, add in adds(scored, state["cls"]).items():
            if abs(add) < 1e-9:
                continue
            auto = scored[k]["python_auto"]
            auto["ability_score_raw"] = round(float(auto["ability_score_raw"]) + add, 4)
            auto["ability_score"] = round(to_display_scale(auto["ability_score_raw"]), 2)
            auto["grade"] = compute_grade(auto["ability_score"])
            flag = {"reason": "weight_rating_shadow", "boost": round(add, 4), "boost_scale": "raw"}
            auto.setdefault("sip_flags", []).append(flag)
            for shadow in (auto.get("shadow_profiles") or {}).values():
                try:
                    s_raw = round(float(shadow["ability_score_raw"]) + add, 4)
                except (KeyError, TypeError, ValueError):
                    continue
                shadow["ability_score_raw"] = s_raw
                shadow["ability_score"] = round(to_display_scale(s_raw), 2)
                shadow["grade"] = compute_grade(shadow["ability_score"])
                shadow["ability_delta"] = round(shadow["ability_score"] - auto["ability_score"], 2)
                shadow.setdefault("sip_flags", []).append(dict(flag))
        return n

    orch.HKJCAutoOrchestrator.score_race = score_race
    incident_history.apply = apply_after
    orch.incident_history.apply = apply_after
