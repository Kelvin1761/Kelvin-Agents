from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[5]
ENGINE = (
    ROOT
    / ".agents"
    / "skills"
    / "au_racing"
    / "au_wong_choi_auto"
    / "scripts"
    / "racing_engine"
)
sys.path.insert(0, str(ENGINE))

from engine_core import RacingEngine


def _score(*, wins: int, places: int) -> float:
    horse = {
        "horse_name": "Test Horse",
        "horse_number": "1",
        "jockey": "Test Jockey",
        "trainer": "Test Trainer",
        "_data": {
            "current_jockey_formal_rides": 4,
            "current_jockey_formal_places": places,
            "current_jockey_formal_wins": wins,
        },
    }
    context = {
        "distance": "1400m",
        "field_summary": {"count": 10},
        "meeting_intelligence": {"venue": "Randwick", "going": "Good 4"},
    }
    return RacingEngine(horse, context)._jockey_horse_fit_score()[0]


class JockeyHorseFitTests(unittest.TestCase):
    def test_formal_places_already_include_wins(self) -> None:
        # Both records have two top-three finishes.  A win is already included
        # in formal_places, so changing their composition must not add it twice.
        self.assertAlmostEqual(
            _score(wins=0, places=2),
            _score(wins=2, places=2),
        )

    def test_generic_stored_change_is_enriched_with_jockey_tiers(self) -> None:
        horse = {
            "horse_name": "Test Horse",
            "horse_number": "1",
            "jockey": "Current Rider",
            "_data": {
                "jockey_change_signal": "由 Previous Rider 轉配 Current Rider",
                "latest_official_jockey": "Previous Rider",
            },
        }
        engine = RacingEngine(
            horse,
            {
                "distance": "1400m",
                "field_summary": {"count": 10},
                "meeting_intelligence": {"venue": "Randwick", "going": "Good 4"},
            },
        )
        with patch.object(
            engine,
            "_jockey_rank_value",
            side_effect=lambda name: 3 if "Current" in name else 1,
        ):
            self.assertIn("換上較強騎師", engine._jockey_change_signal())

    def test_specific_stored_change_is_not_overwritten(self) -> None:
        horse = {
            "horse_name": "Test Horse",
            "horse_number": "1",
            "jockey": "Current Rider",
            "_data": {
                "jockey_change_signal": "沿用上仗騎師",
                "latest_official_jockey": "Current Rider",
            },
        }
        engine = RacingEngine(
            horse,
            {
                "distance": "1400m",
                "field_summary": {"count": 10},
                "meeting_intelligence": {"venue": "Randwick", "going": "Good 4"},
            },
        )
        self.assertEqual(engine._jockey_change_signal(), "沿用上仗騎師")


if __name__ == "__main__":
    unittest.main()
