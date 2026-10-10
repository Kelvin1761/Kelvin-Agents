"""Arm: weight_score = handicap weight only (EXP-20261010-04, pre-registered, fixed rule).

1. Drop the body-weight-trend ±4 from weight_score. Body weight is a health
   signal and risk_score already scores it — in the opposite direction
   (轉輕 is −3 in health but +4 here), so it was double-counted and contradictory.
2. Use the weight actually carried (handicap − apprentice allowance) for the
   ≤120 / ≥132 lb bands. `_data.jockey_allowance` is extracted but unused.
No new constants; the 54/64/70 bands are unchanged.
"""
ARM_NAME = "weight_score_handicap_only"


def apply():
    from hkjc_racing_engine import engine_core, scoring
    from hkjc_racing_engine.scoring import clip_score, parse_float

    def _weight_score(self, _features):
        weight = parse_float(self._value("weight_carried") or self._value("weight"))
        if weight is None:
            return 60, "負磅資料不足，負磅分60分。", "missing_neutral"
        allowance = parse_float(self._value("jockey_allowance")) or 0.0
        carried = weight - allowance
        score = scoring.WEIGHT_MICRO_WEIGHTS.get("base", 64.0)
        if carried <= 120:
            score = scoring.WEIGHT_MICRO_WEIGHTS.get("light_weight_base", 54.0)
        elif carried >= 132:
            score = scoring.WEIGHT_MICRO_WEIGHTS.get("heavy_weight_base", 70.0)
        return clip_score(score), f"實際負磅 {carried:.0f} 磅。", "weight_carried"

    engine_core.RacingEngine._weight_score = _weight_score
