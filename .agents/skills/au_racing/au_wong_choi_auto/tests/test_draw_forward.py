"""EXP-20261102-08 大場次檔位分：`draw.py` 一定要同 EXP-20261102-07 walk-forward harness 嘅 Z8 特徵一致。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts"))
sys.path.insert(0, str(ROOT / "scratch"))

from au_racing_engine.draw import BETA, MIN_FIELD, adjustments, horse_adjustment  # noqa: E402
import au_draw_bigfield_arms_20261102 as harness  # noqa: E402


class DrawTests(unittest.TestCase):
    def test_small_field_is_untouched(self) -> None:
        self.assertEqual(adjustments([1, 2, 3, 4, 5, 6, 7]), [0.0] * 7)

    def test_missing_barrier_is_untouched(self) -> None:
        self.assertEqual(adjustments([1, 2, 3, 4, 5, 6, 7, None]), [0.0] * 8)

    def test_inside_gets_the_most_and_sums_to_zero(self) -> None:
        adj = adjustments([5, 1, 9, 2, 7, 3, 8, 4, 6])
        self.assertEqual(max(range(9), key=lambda i: adj[i]), 1)
        self.assertAlmostEqual(sum(adj), 0.0, places=9)

    def test_twenty_and_eight_runners_share_one_range(self) -> None:
        eight, twenty = adjustments(list(range(1, 9))), adjustments(list(range(1, 21)))
        self.assertAlmostEqual(max(eight), BETA * 1.5275, places=3)
        self.assertAlmostEqual(max(twenty), BETA * 1.6475, places=3)

    def test_matches_walk_forward_harness_z8(self) -> None:
        barriers = [3, 11, 1, 7, 14, 2, 9, 5, 12, 4, 6, 8]
        race = {"rows": [{"barrier": b, "n": i + 1} for i, b in enumerate(barriers)]}
        expected = harness.features(race, MIN_FIELD, "z", False)[:, 0] * BETA
        np.testing.assert_allclose(adjustments(barriers), expected, atol=1e-12)

    def test_horse_adjustment_picks_own_barrier(self) -> None:
        field = ["4", "1", "9", "2", "7", "3", "8", "5", "6"]
        self.assertAlmostEqual(horse_adjustment("1", field), adjustments(field)[1])
        self.assertEqual(horse_adjustment(None, field), 0.0)


if __name__ == "__main__":
    unittest.main()
