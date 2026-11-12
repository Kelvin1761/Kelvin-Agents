"""共用：由段速分拎走某一項逐項訊號（分數同明細一齊拎走）。"""


def install(factor, on_strip=None):
    from hkjc_racing_engine.features.speed import SpeedScorer
    from hkjc_racing_engine.scoring import clip_score

    base = SpeedScorer.compute

    def compute(self):
        score, note = base(self)
        detail = list(getattr(self, "detail", []) or [])
        hit = [d for d in detail if d.get("factor") == factor]
        if not hit:
            return score, note
        delta = sum(float(d.get("delta") or 0) for d in hit)
        self.detail = [d for d in detail if d.get("factor") != factor]
        if on_strip:
            on_strip(self, delta)
        return clip_score(score - delta), note

    SpeedScorer.compute = compute
