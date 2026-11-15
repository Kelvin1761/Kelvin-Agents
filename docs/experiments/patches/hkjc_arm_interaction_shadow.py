"""Kelvin 2026-11-15 —— forward shadow `interaction_shadow`（EXP-20261115-04）：維度 × 情境互動，唔入分。

raw' = raw + Σ β[維度|情境]·(維度分 − 場均)/10，情境 = 短途 ≤1200、長途 ≥1800、泥地、跑馬地（可以同時多個）。
β 凍結 = 回放 v2 baseline 全 dev（2019/20–2023/24，4,151 場）L2 logistic C=0.005 fit（同 holdout 判嗰組一模一樣）。
回放：dev PASS；holdout Δlog-loss −0.00069（同 dev 一樣）但 Holm 99% 唔過 → 交 forward。
喺 SIP-C 之後加，登記做 sip_flag（驗證一致）。Δ = 候選 − live；Gold／Good／NDCG@5 全部 ≥ 0 → 建議入分（Kelvin 決定）。
"""
import json
import re

ARM_NAME = "interaction_shadow"
BETA = {"stability|short": 0.0136, "stability|long": -0.1965, "stability|awt": -0.064, "stability|hv": -0.5411,
        "trainer_signal|short": 0.3472, "trainer_signal|long": 0.3076, "trainer_signal|awt": -0.4988, "trainer_signal|hv": 0.6546,
        "sectional|short": -0.0601, "sectional|long": 0.0618, "sectional|awt": -0.369, "sectional|hv": -0.009,
        "race_shape|short": 0.2895, "race_shape|long": -0.1115, "race_shape|awt": -0.7379, "race_shape|hv": 0.3725,
        "horse_health|short": 0.0825, "horse_health|long": -0.3631, "horse_health|awt": -0.2156, "horse_health|hv": 0.1852,
        "distance_fit|short": 0.2173, "distance_fit|long": -0.4691, "distance_fit|awt": 0.1226, "distance_fit|hv": 0.2839,
        "form_line|short": 0.4096, "form_line|long": 0.0481, "form_line|awt": -0.1168, "form_line|hv": 0.1058,
        "class_advantage|short": -0.8124, "class_advantage|long": -0.3999, "class_advantage|awt": -0.2125, "class_advantage|hv": -0.7925}
_STATE = {"ctx": None}


def context(ra):
    """同 hkjc_eval_harness._race_context 一樣嘅解析（回放 fit 用嗰個）。"""
    track = str(ra.get("track") or ra.get("surface") or "")
    m = re.search(r"\d{3,4}", str(ra.get("distance") or ""))
    dist = int(m.group()) if m else None
    out = set()
    if dist is not None and dist <= 1200:
        out.add("short")
    if dist is not None and dist >= 1800:
        out.add("long")
    if "全天候" in track or "AWT" in track.upper():
        out.add("awt")
    if str(ra.get("venue") or "") == "跑馬地":
        out.add("hv")
    return out


def adjustments(matrix_by_horse, ctx):
    """matrix_by_horse: {馬號: {維度: 分}} → {馬號: raw 加減}。"""
    if not ctx or not matrix_by_horse:
        return {k: 0.0 for k in matrix_by_horse}
    dims = {d.split("|")[0] for d in BETA}
    means = {d: sum(float(m.get(d, 60.0)) for m in matrix_by_horse.values()) / len(matrix_by_horse) for d in dims}
    return {k: sum(BETA[f"{d}|{c}"] * (float(m.get(d, 60.0)) - means[d]) / 10.0 for d in dims for c in ctx)
            for k, m in matrix_by_horse.items()}


def apply():
    import hkjc_auto_orchestrator as orch
    from hkjc_racing_engine.scoring import compute_grade, to_display_scale
    orig_score = orch.HKJCAutoOrchestrator.score_race

    def score_race(self, race_file, *a, **k):
        try:
            _STATE["ctx"] = context(json.load(open(race_file, encoding="utf-8")).get("race_analysis") or {})
        except Exception:
            _STATE["ctx"] = None
        return orig_score(self, race_file, *a, **k)

    orig_sip = orch._apply_sip_enhancements

    def sip(horses):
        orig_sip(horses)
        mats = {k: (h.get("python_auto") or {}).get("matrix_scores") for k, h in horses.items() if isinstance(h, dict)}
        mats = {k: v for k, v in mats.items() if isinstance(v, dict)}
        for k, add in adjustments(mats, _STATE["ctx"]).items():
            if not add:
                continue
            auto = horses[k]["python_auto"]
            raw = round(float(auto.get("ability_score_raw")) + add, 4)
            auto["ability_score_raw"] = raw
            auto["ability_score"] = round(to_display_scale(raw), 2)
            auto["grade"] = compute_grade(auto["ability_score"])
            auto.setdefault("sip_flags", []).append({"reason": "interaction_shadow", "boost": round(add, 4), "boost_scale": "raw"})

    orch.HKJCAutoOrchestrator.score_race = score_race
    orch._apply_sip_enhancements = sip
