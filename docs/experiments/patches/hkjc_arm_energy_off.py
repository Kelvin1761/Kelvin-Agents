"""forward `energy_off`（Kelvin 2026-11-15「forward test 能量／段速細節」）：拎走段速分入面「能量趨勢」嗰行（±1.5–4 分）。
回放語料 energy_trend 100% 係 N/A（死欄位），所以能量從來冇驗證過，只可以 live forward 判。
Δ = 候選（冇能量）− live；Gold／Good／NDCG@5 全部 ≥ 0 → 建議拎走能量（Kelvin 決定）；否則保留。
"""
ARM_NAME = "energy_off"


def apply():
    from hkjc_racing_engine.features import speed as sp
    from hkjc_racing_engine.scoring import clip_score
    orig = sp.SpeedScorer.compute

    def compute(self):
        score, note = orig(self)
        old = sum(float(r.get("delta") or 0) for r in (getattr(self, "detail", []) or []) if r.get("factor") == "能量趨勢")
        if not old:
            return score, note
        self.detail = [r for r in self.detail if r.get("factor") != "能量趨勢"]
        return clip_score(score - old), note
    sp.SpeedScorer.compute = compute
