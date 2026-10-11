"""Arm C: graded V1 同程表現 (EXP-20261010-16, pre-registered after A/B failed; same family, Holm).

Keeps the live evidence — the exact-distance PIT record in `season_stats` 同程 (w-s-t-r) —
and only replaces "placed at least once" with a graded place rate:
  rate = (places + 0.25) / (starts + 1)            (one pseudo-start at the population rate)
  rate ≥ 0.25 → leaf = 60 + 21.5 · min(1, (rate − 0.25) / 0.25)   (V1 placed = +21.5)
  rate < 0.25 → leaf = 60 −  8.5 · (0.25 − rate) / 0.25           (V1 unplaced = −8.5)
No record / debut → 60. One placing in one start = rate 0.625 → +21.5, identical to V1;
what changes is horses with many unplaced attempts around one placing, and 0-for-1 vs 0-for-6.
"""
ARM_NAME = "distance_fit_graded_v1"


def graded_leaf(starts, places):
    if starts <= 0:
        return 60.0
    rate = (places + 0.25) / (starts + 1.0)
    if rate >= 0.25:
        return 60.0 + 21.5 * min(1.0, (rate - 0.25) / 0.25)
    return 60.0 - 8.5 * (0.25 - rate) / 0.25


def apply():
    from hkjc_racing_engine import engine_core
    from hkjc_racing_engine.scoring import CENTRED_MATRIX_WEIGHTS

    weight = CENTRED_MATRIX_WEIGHTS["distance_fit"]
    original = engine_core.RacingEngine._distance_suitability_adjustment

    def graded(self, features, matrix_scores):
        out = dict(original(self, features, matrix_scores))
        if self._is_debut():
            return out
        record = self._same_distance_record()
        if not record or record["starts"] <= 0:
            return out
        out["raw_adjustment"] = round(weight * (graded_leaf(record["starts"], record["places"]) - 60.0), 6)
        out["signal"] = "graded_same_distance"
        return out

    engine_core.RacingEngine._distance_suitability_adjustment = graded
