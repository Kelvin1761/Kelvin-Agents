"""Kelvin 2026-11-14 決定 3 —— forward shadow `debut_trainer_shadow`（EXP-20261114-06）：
初出馬 raw + 0.75 × z(練馬師初出上名率)，as-of 賽日（hkjc_racing_engine/debut_trainer.py）。
喺 SIP-C 之後加（同 SIP 一樣嘅後置機制，所以驗證／shadow 處理一致）。Δ = 候選 − live；Gold／Good／NDCG@5 全部 ≥ 0 → 建議入分（Kelvin 決定）。
δ = 0.75 係 EXP-20261114-06 全 dev walk-forward 揀出嚟嘅值，固定唔再調。
"""
import json

ARM_NAME = "debut_trainer_shadow"
DELTA = 0.75
_STATE = {"date": None}


def apply():
    import hkjc_auto_orchestrator as orch
    from hkjc_racing_engine.debut_trainer import rate
    from hkjc_racing_engine.scoring import compute_grade, to_display_scale

    orig_score = orch.HKJCAutoOrchestrator.score_race

    def score_race(self, race_file, *a, **k):
        try:
            ra = json.load(open(race_file, encoding="utf-8")).get("race_analysis") or {}
            _STATE["date"] = str(ra.get("race_date") or "")[:10] or None
        except Exception:
            _STATE["date"] = None
        return orig_score(self, race_file, *a, **k)

    orig_sip = orch._apply_sip_enhancements

    def sip(horses):
        orig_sip(horses)
        if not _STATE["date"]:
            return
        for h in horses.values():
            auto = h.get("python_auto") or {}
            if not auto or not (h.get("is_debut") or h.get("debut_runner")):
                continue
            info = rate(str(h.get("trainer") or "").strip(), _STATE["date"])
            if not info:
                continue
            boost = round(DELTA * info["z"], 4)
            raw = round(float(auto.get("ability_score_raw")) + boost, 4)
            auto["ability_score_raw"] = raw
            # 驗證（validation SCORE）將 sip_flags 嘅 boost 計入預期原始分 —— 照 SIP 一樣登記
            auto.setdefault("sip_flags", []).append({"reason": "debut_trainer_shadow", "boost": boost, "boost_scale": "raw"})
            auto["ability_score"] = round(to_display_scale(raw), 2)
            auto["grade"] = compute_grade(auto["ability_score"])

    orch.HKJCAutoOrchestrator.score_race = score_race
    orch._apply_sip_enhancements = sip
