"""EXP-20261112-18b arm（訊號檢查之後加，跑 A/B 之前寫死）：剷走體重「微增／微減」+1，「穩定」亦唔加。
訊號檢查：穩定 − 微增減 −2.51pp [−9.52,+5.15]（穩定得 109 匹）；冇訊號。Fixed."""
ARM_NAME = "weight_micro_removed"
EARLIER = ("急劇變化", "急增", "急減", "顯著轉輕", "大減", "顯著轉重", "大增")


def apply():
    from hkjc_racing_engine import scoring
    from hkjc_racing_engine.engine_core import RacingEngine
    from hkjc_racing_engine.scoring import clip_score

    original = RacingEngine._candidate_health_risk_score

    def patched(self):
        score, note = original(self)
        trend = self._text("weight_trend")
        if not any(t in trend for t in EARLIER) and any(t in trend for t in ("微增", "微減")):
            return clip_score(score - scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["weight_micro_bonus"]), note
        return score, note

    RacingEngine._candidate_health_risk_score = patched
