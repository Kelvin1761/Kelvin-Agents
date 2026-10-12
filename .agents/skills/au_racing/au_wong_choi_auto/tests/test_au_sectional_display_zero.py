"""Sectional display preserves numeric zero while missing values remain neutral."""
import copy
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from au_racing_engine.renderer import _pace_perf_detail_lines


class SectionalDisplayZeroTest(unittest.TestCase):
    def test_explicit_numeric_base_is_preserved_without_mutating_auto(self):
        for value in (0, 0.0, 0.1, 56, 60, "0"):
            with self.subTest(value=value):
                auto = {"pace_perf_detail": {"sectional": {"has_pi": False, "base": value}}}
                before = copy.deepcopy(auto)
                lines = _pace_perf_detail_lines(auto, "sectional_score")
                self.assertIn(f"維持中性 {float(value):.1f} 分", lines[0])
                self.assertEqual(auto, before)

    def test_missing_base_keeps_existing_neutral_fallback(self):
        for detail in ({"has_pi": False}, {"has_pi": False, "base": None}):
            lines = _pace_perf_detail_lines({"pace_perf_detail": {"sectional": detail}}, "sectional_score")
            self.assertIn("維持中性 60.0 分", lines[0])

    def test_measured_branch_preserves_zero_and_adjustments(self):
        auto = {"pace_perf_detail": {"sectional": {"has_pi": True, "base": 0,
                "score": 2, "items": [{"factor": "test", "delta": 2}]}}}
        lines = _pace_perf_detail_lines(auto, "sectional_score")
        self.assertIn("中性基礎分 0.0", lines[0])
        self.assertIn("test +2.00", lines[1])
        self.assertEqual(lines[-1], "合計 ＝ 2.0")


if __name__ == "__main__":
    unittest.main()
