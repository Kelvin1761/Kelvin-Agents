"""EXP-20261112-18 arm：體重 +1 由「微增／微減」（其實係波幅 > 5 磅）改畀「穩定」（波幅 ≤ 5 磅）。
其餘健康分唔郁。Fixed, nothing fitted."""
ARM_NAME = "weight_stable_bonus"
EARLIER = ("急劇變化", "急增", "急減", "顯著轉輕", "大減", "顯著轉重", "大增")


def apply():
    from hkjc_racing_engine import scoring
    from hkjc_racing_engine.engine_core import RacingEngine
    from hkjc_racing_engine.scoring import clip_score

    original = RacingEngine._candidate_health_risk_score

    def patched(self):
        score, note = original(self)
        trend = self._text("weight_trend")
        if any(t in trend for t in EARLIER):
            return score, note
        bonus = scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["weight_micro_bonus"]
        if any(t in trend for t in ("微增", "微減")):
            return clip_score(score - bonus), note
        if "穩定" in trend:
            return clip_score(score + bonus), note
        return score, note

    RacingEngine._candidate_health_risk_score = patched
