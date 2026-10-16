"""Sectional review 2026-10-16: finish-time trend reads Facts' real label 改善中 (was 進步, never matched)."""
ARM_NAME = "fix_finish_label"
def apply():
    from hkjc_racing_engine import engine_core, scoring
    from hkjc_racing_engine.scoring import clip_score
    def _apply(self, base_score):
        block = self._text("finish_time_block")
        delta = 0.0
        if "改善中" in block or "進步" in block:
            delta = scoring.FINISH_TREND_MICRO_WEIGHTS["improving"]
        elif "退步" in block:
            delta = scoring.FINISH_TREND_MICRO_WEIGHTS["declining"]
        if delta:
            self.reason_codes.append("finish_time_trend_up" if delta > 0 else "finish_time_trend_down")
        return round(clip_score(base_score + delta), 2)
    engine_core.RacingEngine._apply_finish_time_trend = _apply
