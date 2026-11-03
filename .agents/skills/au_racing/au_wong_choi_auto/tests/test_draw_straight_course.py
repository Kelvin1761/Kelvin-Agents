"""EXP-20261103-08：Flemington 直路賽（≤1200m）檔位分歸零；彎道賽同其他場地照舊。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts"))

from au_racing_engine.draw import explain, horse_adjustment, is_straight  # noqa: E402
from au_racing_engine.engine_core import RacingEngine  # noqa: E402

FIELD = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]


class StraightCourseTests(unittest.TestCase):
    def test_flemington_sprints_are_straight(self) -> None:
        for d in (1000, 1100, 1200):
            self.assertTrue(is_straight("Flemington", d))
        self.assertFalse(is_straight("Flemington", 1400))
        self.assertFalse(is_straight("Randwick", 1000))
        self.assertFalse(is_straight("Flemington", 0))

    def test_straight_zeroes_draw_and_says_why(self) -> None:
        self.assertGreater(horse_adjustment(1, FIELD), 1.0)
        self.assertEqual(horse_adjustment(1, FIELD, straight=True), 0.0)
        e = explain(1, FIELD, straight=True)
        self.assertFalse(e["applies"])
        self.assertIn("直路", e["reason"])

    def test_engine_reads_venue_and_distance(self) -> None:
        def engine(venue, distance):
            ctx = {"distance": distance, "meeting_intelligence": {"venue": venue}}
            return RacingEngine({"barrier": 1}, ctx)
        self.assertTrue(engine("Flemington", "1200m")._straight_course())
        self.assertFalse(engine("Flemington", "1600m")._straight_course())
        self.assertFalse(engine("Caulfield", "1000m")._straight_course())


if __name__ == "__main__":
    unittest.main()
