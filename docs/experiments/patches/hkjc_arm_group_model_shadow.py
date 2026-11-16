"""forward shadow `group_model_shadow`（EXP-20261116-13 G2a；回放 dev PASS（Holm）、holdout CI 啱啱跨零，唔入分；Kelvin 2026-11-16 開）：
  分級賽（一／二／三級賽）raw += Σγ_k·(外層維度分_k − 場均) + β_r·(評分 − 場均)/10 + β_w·(負磅 − 場均)/10；其他場次唔郁。
γ／β = L2 logistic（C=0.01）fit 2019/20–2025/26 全部回放分級賽（docs/experiments/patches/hkjc_group_model/build.py）。
維度分 = python_auto.matrix_scores；評分 = Logic `_data.current_rating`；負磅 = `weight`（實際負磅，同回放一樣）。冇值 → 場均。
喺所有後置組件之後加，登記做 sip_flag（shadow 同步）。Δ = 候選 − live；forward Gold／Good／NDCG@5 全部 ≥ 0 → 建議入分（Kelvin 決定）。
"""
ARM_NAME = "group_model_shadow"
GAMMA = {"stability": 0.02539691960700705, "trainer_signal": -0.05346847039964146, "sectional": -0.03156361229484553,
         "race_shape": -0.1494764318842752, "horse_health": 0.06155321682016838, "trackwork": 0.0,
         "distance_fit": -0.054194263514294065, "form_line": 0.012321896987728625, "class_advantage": -0.04078908959900242}
BETA_RATING, BETA_WEIGHT = 1.964039072827929, -2.2960780478135057


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _centred(d: dict, scale: float = 1.0) -> dict:
    obs = [v for v in d.values() if v is not None]
    if not obs:
        return {k: 0.0 for k in d}
    fill = sum(obs) / len(obs)
    x = {k: (fill if v is None else v) for k, v in d.items()}
    m = sum(x.values()) / len(x)
    return {k: (v - m) / scale for k, v in x.items()}


def adds(horses: dict, race_class: str) -> dict:
    if "級賽" not in str(race_class or ""):
        return {}
    out = {k: 0.0 for k in horses}
    for dim, g in GAMMA.items():
        if not g:
            continue
        c = _centred({k: _num(((h.get("python_auto") or {}).get("matrix_scores") or {}).get(dim)) for k, h in horses.items()})
        for k in horses:
            out[k] += g * c[k]
    r = _centred({k: _num((h.get("_data") or {}).get("current_rating")) for k, h in horses.items()}, 10.0)
    w = _centred({k: _num(h.get("weight")) for k, h in horses.items()}, 10.0)
    for k in horses:
        out[k] += BETA_RATING * r[k] + BETA_WEIGHT * w[k]
    return out


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
            flag = {"reason": ARM_NAME, "boost": round(add, 4), "boost_scale": "raw"}
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
