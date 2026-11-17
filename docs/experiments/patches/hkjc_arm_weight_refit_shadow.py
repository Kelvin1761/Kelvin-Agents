"""forward shadow `weight_refit_shadow`（EXP-20261117-07 R1；Kelvin 2026-11-17「可以開 forward 觀察」）。

現行模型 9 個維度外層權重修正：raw' = raw + Σ γ_k·(維度原始分_k − 場均)，γ = 2026/27 walk-forward 值（fit 2019/20–2025/26，
L2 C=0.1，base = live 加晒事件報告／檔位×跑法／大幅增程）。即係有效權重：穩定性 0.245→0.136、檔位走位 0.193→0.112、
段速 0.129→0.090、騎練 0.330→0.307、評分與經驗 0→−0.116（評分高嘅馬其他維度已計多咗）。
回放 dev：場內 AUC +0.0031 [+0.0011,+0.0051]、Gold +0.40、Good +0.76，但 log-loss −0.00036 [−0.00097,+0.00028] 跨零 → REJECT，所以只做 forward。
Δ = 候選 − live；forward Gold／Good／NDCG@5 全部 ≥ 0 → 建議改權重（Kelvin 決定）。
"""
ARM_NAME = "weight_refit_shadow"
GAMMA = {"stability": -0.109, "trainer_signal": -0.023, "sectional": -0.039, "race_shape": -0.081, "horse_health": -0.015,
         "trackwork": 0.0, "distance_fit": 0.014, "form_line": -0.015, "class_advantage": -0.116}


def apply():
    import hkjc_auto_orchestrator as orch
    from hkjc_racing_engine.scoring import compute_grade, to_display_scale
    orig_sip = orch._apply_sip_enhancements

    def sip(horses):
        orig_sip(horses)
        items = [h for h in horses.values() if isinstance(h, dict)
                 and (h.get("python_auto") or {}).get("ability_score_raw") is not None]
        if not items:
            return
        ms = [{k: float((h["python_auto"].get("matrix_scores") or {}).get(k, 60.0) or 60.0) for k in GAMMA} for h in items]
        mean = {k: sum(m[k] for m in ms) / len(ms) for k in GAMMA}
        for h, m in zip(items, ms):
            add = round(sum(GAMMA[k] * (m[k] - mean[k]) for k in GAMMA), 4)
            if not add:
                continue
            auto = h["python_auto"]
            raw = round(float(auto["ability_score_raw"]) + add, 4)
            auto["ability_score_raw"] = raw
            auto["ability_score"] = round(to_display_scale(raw), 2)
            auto["grade"] = compute_grade(auto["ability_score"])
            flag = {"reason": ARM_NAME, "boost": add, "boost_scale": "raw"}
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

    orch._apply_sip_enhancements = sip
