from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
ENGINE = ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts" / "racing_engine"
sys.path.insert(0, str(ENGINE))

from engine_core import RacingEngine


def _ctx():
    return {"distance": "1400m", "field_summary": {"count": 10},
            "meeting_intelligence": {"venue": "Randwick", "going": "Good 4"}}


def _score(trainer: str, ly: dict) -> float:
    horse = {"horse_name": "T", "horse_number": "1", "barrier": 5,
             "trainer": trainer, "_data": {"trainer_ly": ly}}
    score, _note, _src = RacingEngine(horse, _ctx())._trainer_score()
    return score


class TrainerEmpiricalFillTests(unittest.TestCase):
    """Unlisted trainers (~44% of runners) are scored from their own last-year
    record instead of falling through to a flat neutral 60. Magnitude is tuned
    at 0.25 by isolated A/B over 708 archive races; these tests lock the
    behaviour that tuning depends on rather than the exact numbers."""

    UNLISTED = "Zzz Unlisted Smalltime Trainer"

    def test_unlisted_trainer_is_scored_from_own_record(self) -> None:
        strong = _score(self.UNLISTED, {"rides": 60, "wins": 10, "places": 17})
        weak = _score(self.UNLISTED, {"rides": 60, "wins": 1, "places": 4})
        self.assertGreater(strong, 60.0)   # 28% -> above the 30% norm after shrink
        self.assertLess(weak, 60.0)
        self.assertGreater(strong, weak)

    def test_thin_or_missing_record_stays_neutral(self) -> None:
        # under 10 rides says nothing; shrinkage must not manufacture a signal
        for ly in ({"rides": 5, "wins": 2, "places": 1}, {"rides": 0}, {}):
            self.assertAlmostEqual(_score(self.UNLISTED, ly), 60.0, places=1)

    def test_fill_is_bounded_and_tempered_by_magnitude(self) -> None:
        eng = RacingEngine({"horse_name": "T", "horse_number": "1", "trainer": self.UNLISTED}, _ctx())
        extreme = eng._trainer_empirical_base({"rides": 400, "wins": 200, "places": 150})
        self.assertIsNotNone(extreme)
        # cap * magnitude is the hard ceiling — the fill can never dominate the feature
        self.assertLessEqual(abs(extreme[0]),
                             eng._TRAINER_LY_CAP * eng._TRAINER_LY_MAGNITUDE + 1e-6)
        self.assertLess(abs(extreme[0]), eng._TRAINER_LY_CAP)

    def test_magnitude_zero_disables_the_fill_cleanly(self) -> None:
        # the tuning knob must be a real off-switch, not a near-zero nudge
        class _Off(RacingEngine):
            _TRAINER_LY_MAGNITUDE = 0.0
        horse = {"horse_name": "T", "horse_number": "1", "barrier": 5,
                 "trainer": self.UNLISTED, "_data": {"trainer_ly": {"rides": 60, "wins": 10, "places": 17}}}
        self.assertAlmostEqual(_Off(horse, _ctx())._trainer_score()[0], 60.0, places=1)

    def test_coverage_decision_is_magnitude_independent(self) -> None:
        # a trainer who earns a fill at full magnitude must still earn one when
        # tempered — otherwise lowering the knob silently re-opens the data hole
        ly = {"rides": 30, "wins": 3, "places": 6}
        eng = RacingEngine({"horse_name": "T", "horse_number": "1", "trainer": self.UNLISTED}, _ctx())

        class _Full(RacingEngine):
            _TRAINER_LY_MAGNITUDE = 1.0
        full = _Full({"horse_name": "T", "horse_number": "1", "trainer": self.UNLISTED}, _ctx())
        self.assertEqual(eng._trainer_empirical_base(ly) is None,
                         full._trainer_empirical_base(ly) is None)


class ComboStatsResilienceTests(unittest.TestCase):
    def test_scoring_survives_unavailable_combo_stats(self) -> None:
        # The Drive-hosted combo-stats CSV is optional enrichment; an I/O failure
        # (e.g. macOS revoking CloudStorage access) must not crash scoring.
        horse = {"horse_name": "T", "horse_number": "1", "barrier": 5, "trainer": "Chris Waller"}
        auto = RacingEngine(horse, _ctx()).analyze_horse()
        self.assertIn("ability_score", auto)
        self.assertGreater(auto["ability_score"], 0)


if __name__ == "__main__":
    unittest.main()
