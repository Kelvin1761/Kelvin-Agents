"""Kelvin 2026-11-15 —— forward shadow `draw_curve_shadow`（EXP-20261115-18／19）：保留現有檔位分，再加逐檔殘差曲線，唔入分。

raw' = raw + β·(格值 − 場均)，格 = (組別 HV/ST/AWT/STR × 短 ≤1200／長, 檔號 1–13+, 大場 ≥12)。
格值同 β 凍結喺 hkjc_draw_curve/frozen.json（freeze.py，回放 v3 至 2026-11-11，β = 32.4）。
回放：dev Δlog-loss −0.00081 [−0.00119,−0.00041] PASS；holdout −0.00054（同方向、CI 跨零）→ 交 forward。
冇檔號嘅馬 = 格值 0（同回放一樣）。喺 SIP-C 之後加，登記做 sip_flag。Δ = 候選 − live；Gold／Good／NDCG@5 全部 ≥ 0 → 建議入分（Kelvin 決定）。
"""
import json
import re
from pathlib import Path

ARM_NAME = "draw_curve_shadow"
FROZEN = json.loads((Path(__file__).with_name("hkjc_draw_curve") / "frozen.json").read_text(encoding="utf-8"))
BETA = float(FROZEN["beta"])
CELLS = FROZEN["cells"]
_STATE = {"ra": None}


def group(ra):
    track = str(ra.get("track") or ra.get("surface") or "")
    m = re.search(r"\d{3,4}", str(ra.get("distance") or ""))
    dist = int(m.group()) if m else None
    if dist is None:
        return None
    awt = "全天候" in track or "AWT" in track.upper() or "ALL WEATHER" in track.upper()
    g = "HV" if str(ra.get("venue") or "") == "跑馬地" else ("AWT" if awt else ("STR" if dist == 1000 else "ST"))
    return g + ("S" if dist <= 1200 else "L")


def adjustments(draws, ra):
    """draws: {馬號: 檔號 or None} → {馬號: raw 加減}。場大細 = 今場出賽數。"""
    g = group(ra or {})
    if not g or not draws:
        return {k: 0.0 for k in draws}
    big = int(len(draws) >= 12)
    vals = {}
    for k, d in draws.items():
        try:
            vals[k] = float(CELLS.get(f"{g}|{min(int(d), 13)}|{big}", 0.0))
        except (TypeError, ValueError):
            vals[k] = 0.0
    mean = sum(vals.values()) / len(vals)
    return {k: BETA * (v - mean) for k, v in vals.items()}


def apply():
    import hkjc_auto_orchestrator as orch
    from hkjc_racing_engine.scoring import compute_grade, to_display_scale
    orig_score = orch.HKJCAutoOrchestrator.score_race

    def score_race(self, race_file, *a, **k):
        try:
            _STATE["ra"] = json.load(open(race_file, encoding="utf-8")).get("race_analysis") or {}
        except Exception:
            _STATE["ra"] = None
        return orig_score(self, race_file, *a, **k)

    orig_sip = orch._apply_sip_enhancements

    def sip(horses):
        orig_sip(horses)
        draws = {k: h.get("barrier") or h.get("draw") for k, h in horses.items()
                 if isinstance(h, dict) and isinstance(h.get("python_auto"), dict)}
        for k, add in adjustments(draws, _STATE["ra"]).items():
            if not add:
                continue
            auto = horses[k]["python_auto"]
            raw = round(float(auto.get("ability_score_raw")) + add, 4)
            auto["ability_score_raw"] = raw
            auto["ability_score"] = round(to_display_scale(raw), 2)
            auto["grade"] = compute_grade(auto["ability_score"])
            auto.setdefault("sip_flags", []).append({"reason": "draw_curve_shadow", "boost": round(add, 4), "boost_scale": "raw"})

    orch.HKJCAutoOrchestrator.score_race = score_race
    orch._apply_sip_enhancements = sip
