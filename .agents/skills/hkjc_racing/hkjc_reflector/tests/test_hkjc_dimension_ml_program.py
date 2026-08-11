from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_reflector" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from hkjc_dimension_ml_program import (  # noqa: E402
    _ablated_ability,
    _apply_delta,
    _fit_offset_residual,
    _rank_movements,
    _select_cap,
)
from hkjc_ml_program import PRODUCTION_MATRIX_WEIGHTS  # noqa: E402


class HkjcDimensionMlProgramTests(unittest.TestCase):
    def test_ablation_removes_dimension_and_renormalises(self) -> None:
        frame = pd.DataFrame(
            {
                "current_live_recomputed_ability": [70.0],
                "matrix_trainer_signal": [80.0],
            }
        )
        weight = PRODUCTION_MATRIX_WEIGHTS["matrix_trainer_signal"]
        expected = (70.0 - weight * 80.0) / (1.0 - weight)
        self.assertAlmostEqual(float(_ablated_ability(frame, "trainer_signal").iloc[0]), expected)

    def test_bounded_win_residual_preserves_race_probability_sum(self) -> None:
        frame = pd.DataFrame(
            {
                "race_key": ["A", "A", "A", "B", "B"],
                "field_size": [3, 3, 3, 2, 2],
            }
        )
        baseline = np.array([0.5, 0.3, 0.2, 0.6, 0.4])
        raw_delta = np.array([10.0, -10.0, 0.0, 5.0, -5.0])
        adjusted = _apply_delta(frame, baseline, raw_delta, 0.10, "Win")
        totals = pd.Series(adjusted).groupby(frame["race_key"]).sum()
        np.testing.assert_allclose(totals.to_numpy(), np.ones(2))
        self.assertTrue(np.all(adjusted > 0))

    def test_offset_fit_learns_pre_race_feature_direction(self) -> None:
        frame = pd.DataFrame(
            {
                "signal": [-2.0, -1.0, 1.0, 2.0] * 10,
                "field_size": [4] * 40,
                "is_win": [0, 0, 1, 1] * 10,
            }
        )
        baseline = np.full(len(frame), 0.25)
        model = _fit_offset_residual(
            frame,
            ["signal"],
            [],
            "Win",
            baseline,
            l2_penalty=0.1,
        )
        delta = model.raw_delta(frame[["signal"]])
        self.assertGreater(float(delta[frame["signal"] > 0].mean()), 0)
        self.assertLess(float(delta[frame["signal"] < 0].mean()), 0)

    def test_cap_selection_uses_development_gate_before_score(self) -> None:
        rows = pd.DataFrame(
            [
                {
                    "dimension": "stability",
                    "target": "Win",
                    "method": "Residual cap=0.05",
                    "development_gate": True,
                    "selection_score": 0.01,
                    "log_loss": 0.25,
                },
                {
                    "dimension": "stability",
                    "target": "Win",
                    "method": "Residual cap=0.20",
                    "development_gate": False,
                    "selection_score": 0.50,
                    "log_loss": 0.24,
                },
            ]
        )
        cap, passed = _select_cap(rows, "stability")
        self.assertEqual(cap, 0.05)
        self.assertTrue(passed)

    def test_rank_movements_identify_rank3_entering_top2(self) -> None:
        baseline = pd.DataFrame(
            {
                "date": ["2026-01-01"] * 3,
                "meeting_name": ["M"] * 3,
                "race_number": [1] * 3,
                "race_key": ["R"] * 3,
                "horse_number": [1, 2, 3],
                "horse_name": ["A", "B", "C"],
                "finish_pos": [1, 3, 2],
                "is_win": [1, 0, 0],
                "is_top3": [1, 1, 1],
                "probability": [0.5, 0.3, 0.2],
            }
        )
        candidate = baseline.copy()
        candidate["probability"] = [0.5, 0.2, 0.3]
        movement = _rank_movements(
            baseline, candidate, "stability", "walk_forward", "Residual cap=0.05"
        )
        horse3 = movement[movement["horse_number"] == 3].iloc[0]
        horse2 = movement[movement["horse_number"] == 2].iloc[0]
        self.assertTrue(horse3["entered_top2"])
        self.assertTrue(horse2["left_top2"])


if __name__ == "__main__":
    unittest.main()
