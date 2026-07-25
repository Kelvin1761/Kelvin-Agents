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


class TrainerEmpiricalFillRevertedTests(unittest.TestCase):
    """The empirical trainer fill was tested on the whole archive and REVERTED
    (it made accuracy worse; see the comment in _trainer_score). These tests lock
    the revert: unlisted trainers must stay neutral, and the analysis helper must
    remain available but unused."""

    UNLISTED = "Zzz Unlisted Smalltime Trainer"

    def test_unlisted_trainer_stays_neutral_regardless_of_record(self) -> None:
        for ly in ({"rides": 60, "wins": 10, "places": 17},
                   {"rides": 50, "wins": 2, "places": 4},
                   {"rides": 5, "wins": 2, "places": 1},
                   {}):
            self.assertAlmostEqual(_score(self.UNLISTED, ly), 60.0, places=1)

    def test_analysis_helper_kept_for_reproducibility(self) -> None:
        # helper still computes a sane, bounded, monotonic value — but nothing calls it
        eng = RacingEngine({"horse_name": "T", "horse_number": "1", "trainer": self.UNLISTED}, _ctx())
        weak = eng._trainer_empirical_base({"rides": 40, "wins": 2, "places": 4})
        strong = eng._trainer_empirical_base({"rides": 40, "wins": 7, "places": 12})
        self.assertIsNotNone(weak)
        self.assertIsNotNone(strong)
        self.assertLess(weak[0], strong[0])
        self.assertIsNone(eng._trainer_empirical_base({"rides": 5, "wins": 2, "places": 1}))


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
