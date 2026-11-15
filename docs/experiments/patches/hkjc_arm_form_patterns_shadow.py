"""forward shadow `form_patterns_shadow`（EXP-20261115-15；Kelvin 2026-11-15）：老馬贏後 −4.62、降班＋評分跌返贏馬分 +2.56（raw 分）。
β = 回放 dev（2019/20–2023/24）用馬匹頁定義 walk-forward 全 dev fit（C2、C5）；live 定義見 hkjc_racing_engine/form_patterns.py（近似）。
喺 SIP-C 之後加，登記做 sip_flag（驗證一致；shadow 同步，同 SIP 一樣）。Δ = 候選 − live；Gold／Good／NDCG@5 全部 ≥ 0 → 建議入分（Kelvin 決定）。
"""
import json

ARM_NAME = "form_patterns_shadow"
BETA = {"old_won_last": -4.62, "classdrop_rating_back": 2.56}
_STATE = {"cls": None, "date": None}


def apply():
    import hkjc_auto_orchestrator as orch
    from hkjc_racing_engine.form_patterns import flags
    from hkjc_racing_engine.scoring import compute_grade, to_display_scale
    orig_score = orch.HKJCAutoOrchestrator.score_race

    def score_race(self, race_file, *a, **k):
        try:
            ra = json.load(open(race_file, encoding="utf-8")).get("race_analysis") or {}
            _STATE["cls"], _STATE["date"] = ra.get("race_class"), str(ra.get("race_date") or "")[:10] or None
        except Exception:
            _STATE["cls"], _STATE["date"] = None, None
        return orig_score(self, race_file, *a, **k)

    orig_sip = orch._apply_sip_enhancements

    def sip(horses):
        orig_sip(horses)
        for h in horses.values():
            auto = h.get("python_auto") or {}
            if not auto:
                continue
            f = flags(h, _STATE["cls"], _STATE["date"])
            add = sum(b for k, b in BETA.items() if f.get(k))
            if not add:
                continue
            raw = round(float(auto["ability_score_raw"]) + add, 4)
            auto["ability_score_raw"] = raw
            auto["ability_score"] = round(to_display_scale(raw), 2)
            auto["grade"] = compute_grade(auto["ability_score"])
            flag = {"reason": "form_patterns_shadow", "boost": add, "boost_scale": "raw"}
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

    orch.HKJCAutoOrchestrator.score_race = score_race
    orch._apply_sip_enhancements = sip
