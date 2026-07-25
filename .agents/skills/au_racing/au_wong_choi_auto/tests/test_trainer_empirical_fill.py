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
    """Unlisted trainers are scored from their own last-year record instead of
    silently defaulting to a flat neutral 60 (the biggest matrix coverage hole)."""

    UNLISTED = "Zzz Unlisted Smalltime Trainer"

    def test_strong_unlisted_trainer_scores_above_neutral(self) -> None:
        self.assertGreater(_score(self.UNLISTED, {"rides": 60, "wins": 10, "places": 17}), 61.0)

    def test_weak_unlisted_trainer_scores_below_neutral(self) -> None:
        self.assertLess(_score(self.UNLISTED, {"rides": 50, "wins": 2, "places": 4}), 59.0)

    def test_monotonic_in_place_rate(self) -> None:
        weak = _score(self.UNLISTED, {"rides": 40, "wins": 2, "places": 4})
        mid = _score(self.UNLISTED, {"rides": 40, "wins": 4, "places": 8})
        strong = _score(self.UNLISTED, {"rides": 40, "wins": 7, "places": 12})
        self.assertLess(weak, mid)
        self.assertLess(mid, strong)

    def test_thin_sample_stays_neutral(self) -> None:
        # <10 rides must not move the score at all
        self.assertAlmostEqual(_score(self.UNLISTED, {"rides": 5, "wins": 2, "places": 1}), 60.0, places=1)
        self.assertAlmostEqual(_score(self.UNLISTED, {}), 60.0, places=1)

    def test_shrinkage_bounds_the_adjustment(self) -> None:
        # even an absurd 100% place rate cannot exceed the cap
        extreme = _score(self.UNLISTED, {"rides": 30, "wins": 15, "places": 15})
        self.assertLessEqual(extreme - 60.0, 9.0 + 1e-6)


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
