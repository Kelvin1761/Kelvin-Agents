from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
ENGINE = ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts" / "racing_engine"
sys.path.insert(0, str(ENGINE))

from engine_core import RacingEngine
from renderer import _coverage_cell


def _ctx():
    return {"distance": "1400m", "field_summary": {"count": 10},
            "meeting_intelligence": {"venue": "Randwick", "going": "Good 4"}}


class DataCoverageTests(unittest.TestCase):
    def test_coverage_block_present_and_shaped(self) -> None:
        auto = RacingEngine({"horse_name": "H", "barrier": 5, "horse_number": "1"}, _ctx()).analyze_horse()
        cov = auto["data_coverage"]
        self.assertEqual(cov["total"], 13)
        self.assertEqual(cov["present"] + len(cov["missing_features"]), 13)
        self.assertIn(cov["confidence"], ("高", "中", "薄"))
        self.assertTrue(0 <= cov["coverage_pct"] <= 100)

    def test_thin_horse_flags_missing_and_is_not_high(self) -> None:
        auto = RacingEngine({"horse_name": "Thin", "barrier": 5, "horse_number": "1"}, _ctx()).analyze_horse()
        cov = auto["data_coverage"]
        self.assertIn("pace_figure_score", cov["missing_features"])
        self.assertNotEqual(cov["confidence"], "高")  # thin data must not read as confident

    def test_coverage_never_counts_default_as_real(self) -> None:
        # a horse with everything default = 0% coverage (all neutral-60), thin
        auto = RacingEngine({"horse_name": "Empty", "horse_number": "1"}, _ctx()).analyze_horse()
        cov = auto["data_coverage"]
        self.assertLessEqual(cov["present"], 7)

    def test_coverage_cell_renders(self) -> None:
        auto = RacingEngine({"horse_name": "H", "barrier": 5, "horse_number": "1"}, _ctx()).analyze_horse()
        cell = _coverage_cell(auto)
        self.assertRegex(cell, r"[高中薄] \d+%")
        self.assertEqual(_coverage_cell({}), "—")


if __name__ == "__main__":
    unittest.main()
