"""forward shadow `rating_back_placed_shadow`（EXP-20261117-04；Kelvin 2026-11-17）：上仗入位（1–3）＋評分跌返贏馬分（唔降班）加分。
β = 1.51（raw；fit 2019/20–2025/26 全部回放季，`patches/hkjc_distance/fit_forward_betas.py`）。唔入分；
Δ = 候選 − live；forward Gold／Good／NDCG@5 全部 ≥ 0 → 建議入分（Kelvin 決定）。
"""
import json

ARM_NAME = "rating_back_placed_shadow"
BETA = 1.51
_STATE = {"cls": None, "date": None}


def _flag(h, state):
    from hkjc_racing_engine.form_patterns import _finishes, flags
    f = flags(h, state["cls"], state["date"])
    fin = _finishes(h)
    return bool(f.get("rating_near_win") and f["rating"] is not None and f["win_rating"] is not None
                and f["rating"] <= f["win_rating"] and fin and fin[0] is not None and fin[0] <= 3)


def apply():
    import hkjc_auto_orchestrator as orch
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
        scored = [h for h in horses.values() if isinstance(h, dict) and (h.get("python_auto") or {}).get("ability_score_raw") is not None]
        if not scored:
            return
        fl = [float(bool(_flag(h, _STATE))) for h in scored]
        mean = sum(fl) / len(fl)
        for h, f in zip(scored, fl):
            add = round(BETA * (f - mean), 4)
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

    orch.HKJCAutoOrchestrator.score_race = score_race
    orch._apply_sip_enhancements = sip
