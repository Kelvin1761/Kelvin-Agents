from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from au_paired_significance import outcomes  # noqa: E402


class PairedSignificanceMetricTests(unittest.TestCase):
    def test_pass_is_any_two_of_model_top_three(self) -> None:
        result = outcomes(["A", "X", "B", "Y"], {"A": 1, "B": 2, "C": 3, "X": 4})
        self.assertTrue(result["pass"])
        self.assertFalse(result["good_positional"])
        self.assertNotIn("good_any2", result)
        self.assertNotIn("pass_any1", result)

    def test_gold_uses_capture_at_four_not_strict_top_three(self) -> None:
        result = outcomes(["A", "B", "X", "C"], {"A": 1, "B": 2, "C": 3, "X": 4})
        self.assertTrue(result["gold"])

    def test_gold_rejects_a_missing_placed_horse(self) -> None:
        result = outcomes(["A", "B", "X", "Y"], {"A": 1, "B": 2, "C": 3, "X": 4})
        self.assertFalse(result["gold"])


if __name__ == "__main__":
    unittest.main()
