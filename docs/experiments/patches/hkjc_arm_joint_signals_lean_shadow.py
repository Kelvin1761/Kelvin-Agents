"""forward shadow `joint_signals_lean_shadow`（EXP-20261117-07：J1 精簡版，逐個拎走之後剷走匆匆再出、受阻、大幅減程、首次配備；
β 係 9 個特徵重新 fit 2019/20–2025/26；揀特徵用咗 dev，holdout 已喺 EXP-05 用過，所以只由 forward 判）
原 docstring：forward shadow `joint_signals_shadow`（EXP-20261117-05 J1；Kelvin 2026-11-17「refit，factor in all components that has signals」）。

13 個「有訊號但單獨入唔到分」嘅特徵一齊加（線性 L2，β = 2026/27 walk-forward 值，fit 2019/20–2025/26）。
回放 v4：dev Δlog-loss −0.00062 [−0.00105,−0.00018]（Holm p≈0.0015）；holdout −0.00108 [−0.00164,−0.00050]、AUC +0.0019，
但 Good −0.29 [−1.28,+0.65] 下界穿咗 −1pp 護欄 → 按規則 REJECT，所以只做 forward shadow（唔入分）。
live 定義（同回放近似）：事件報告表（R／W／B／S 旗）、form_patterns（贏馬分）、排位表配備代碼（- 除去、1 首次）、
`_data.prev_distance`、`_data.current_rating`＋班次、休賽日數。全部場內減場均。
Δ = 候選 − live；forward Gold／Good／NDCG@5 全部 ≥ 0 → 建議入分（Kelvin 決定）。
"""
import json
import re
from pathlib import Path

ARM_NAME = "joint_signals_lean_shadow"
BETA = {"ride_q": 1.67, "wide2": 1.01, "slow": 0.68, "rb_placed": 1.21, "rb_any": 0.31, "drop_rb": 2.70,
        "old_won": -4.12, "gear_off": 0.56, "class_pos": -0.32}
BAND_HIGH = {"第三班": 80, "第四班": 60, "第五班": 40}
_STATE = {"cls": None, "date": None, "dist": None, "dir": None, "race": None}


def _num(v):
    m = re.search(r"-?\d+(?:\.\d+)?", str(v or ""))
    return float(m.group()) if m else None


def features(h, state, table, gear_codes):  # 同完整版一樣；只用 BETA 入面 9 個
    from hkjc_racing_engine import incident_history as ih
    from hkjc_racing_engine.form_patterns import _finishes, flags
    from hkjc_racing_engine.market_history import horse_code
    data = h.get("_data") if isinstance(h.get("_data"), dict) else {}
    auto = h.get("python_auto") or {}
    f = dict.fromkeys(BETA, 0.0)
    code, d = horse_code(h), state["date"]
    if table and code and d:
        last, two = ih.prev_two(code, d, table)
        if last is not None:
            f["ride_q"] = float("R" in last)
            f["wide2"] = float(two is not None and "W" in two and "W" not in last)
            f["blocked2"] = float("B" in last or (two is not None and "B" in two))
            f["slow"] = float("S" in last)
    fp = flags(h, state["cls"], d)
    r, w = fp.get("rating"), fp.get("win_rating")
    back = r is not None and w is not None and r <= w
    fin = _finishes(h)
    f["rb_any"] = float(back and not fp["classdrop_rating_back"])
    f["rb_placed"] = float(f["rb_any"] and bool(fin) and fin[0] is not None and fin[0] <= 3)
    f["drop_rb"] = float(fp["classdrop_rating_back"])
    f["old_won"] = float(fp["old_won_last"])
    f["gear_off"] = float(any(str(g).strip().endswith("-") for g in gear_codes))
    f["gear_on"] = float(any(re.fullmatch(r"[A-Z]+1", str(g).strip().upper()) for g in gear_codes))
    prev, today = _num(data.get("prev_distance")), _num(state["dist"])
    f["dist_down"] = float(bool(prev and today and prev - today >= 400))
    rating = _num(data.get("current_rating"))
    band = next((v for k, v in BAND_HIGH.items() if k in str(state["cls"] or "")), None)
    f["class_pos"] = (rating - band) / 10.0 if (rating is not None and band is not None) else 0.0
    days = auto.get("days_since_last", data.get("days_since_last"))
    f["backup10"] = float(isinstance(days, (int, float)) and 0 < days <= 10)
    return f


def apply():
    import hkjc_auto_orchestrator as orch
    from hkjc_racing_engine import incident_history as ih
    from hkjc_racing_engine.scoring import compute_grade, to_display_scale
    from hkjc_racing_engine.tags import load_gear
    orig_score = orch.HKJCAutoOrchestrator.score_race

    def score_race(self, race_file, *a, **k):
        try:
            ra = json.load(open(race_file, encoding="utf-8")).get("race_analysis") or {}
            _STATE.update(cls=ra.get("race_class"), date=str(ra.get("race_date") or "")[:10] or None,
                          dist=ra.get("distance"), dir=Path(race_file).parent, race=ra.get("race_number"))
        except Exception:
            _STATE.update(cls=None, date=None, dist=None, dir=None, race=None)
        return orig_score(self, race_file, *a, **k)

    orig_sip = orch._apply_sip_enhancements

    def sip(horses):
        orig_sip(horses)
        items = [(no, h) for no, h in horses.items() if isinstance(h, dict)
                 and (h.get("python_auto") or {}).get("ability_score_raw") is not None]
        if not items:
            return
        try:
            table = ih.load_table()
        except Exception:
            table = None
        gear = load_gear(_STATE["dir"], _STATE["race"]) if _STATE["dir"] else {}
        feats = [features(h, _STATE, table, gear.get(str(no), [])) for no, h in items]
        means = {k: sum(f[k] for f in feats) / len(feats) for k in BETA}
        for (no, h), f in zip(items, feats):
            add = round(sum(BETA[k] * (f[k] - means[k]) for k in BETA), 4)
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
