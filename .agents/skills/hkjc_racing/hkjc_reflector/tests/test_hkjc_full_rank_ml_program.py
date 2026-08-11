from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_reflector" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from hkjc_full_rank_ml_program import (  # noqa: E402
    MODEL_VERSION,
    _development_gate,
    _sort_for_groups,
    assert_full_rank_feature_safe,
    competitiveness_relevance,
    hybrid_rank_score,
    prediction_export,
    select_candidate,
    within_race_percentile,
)


class HkjcFullRankMlProgramTests(unittest.TestCase):
    def test_competitiveness_relevance_values_top_five(self) -> None:
        finish = pd.Series([1, 2, 3, 4, 5, 6, np.nan])
        self.assertListEqual(
            competitiveness_relevance(finish).tolist(), [4, 3, 2, 1, 1, 0, 0]
        )

    def test_rank_groups_are_contiguous_and_cover_rows(self) -> None:
        frame = pd.DataFrame(
            {
                "date": ["2026-01-02", "2026-01-01", "2026-01-01"],
                "meeting_name": ["B", "A", "A"],
                "race_number": [1, 1, 1],
                "horse_number": [1, 2, 1],
                "race_key": ["B", "A", "A"],
            }
        )
        ordered, groups = _sort_for_groups(frame)
        self.assertListEqual(groups.tolist(), [2, 1])
        self.assertListEqual(ordered["race_key"].tolist(), ["A", "A", "B"])

    def test_within_race_percentile_does_not_mix_races(self) -> None:
        frame = pd.DataFrame({"race_key": ["A", "A", "B", "B"]})
        values = np.array([10.0, 20.0, 100.0, 200.0])
        np.testing.assert_allclose(
            within_race_percentile(frame, values), [0.5, 1.0, 0.5, 1.0]
        )

    def test_hybrid_weight_one_preserves_matrix_order(self) -> None:
        frame = pd.DataFrame(
            {
                "race_key": ["A", "A", "A"],
                "current_live_recomputed_ability": [80.0, 70.0, 60.0],
            }
        )
        score = hybrid_rank_score(frame, np.array([0.0, 10.0, 20.0]), 1.0)
        self.assertListEqual(np.argsort(-score).tolist(), [0, 1, 2])

    def test_feature_contract_rejects_post_race_and_market_fields(self) -> None:
        with self.assertRaises(ValueError):
            assert_full_rank_feature_safe(["finish_pos"])
        with self.assertRaises(ValueError):
            assert_full_rank_feature_safe(["market_rank"])
        with self.assertRaises(ValueError):
            assert_full_rank_feature_safe(["prior_combo_win_rate"])

    def test_development_gate_requires_non_regression_and_two_gains(self) -> None:
        baseline = {
            "top3_capture_at5": 0.62,
            "competitive_ndcg_at5": 0.55,
            "winner_top3": 0.53,
            "top2_zero_hit": 0.25,
            "log_loss": 0.25,
            "winner_top2": 0.41,
            "actual_top3_average_rank": 4.9,
        }
        candidate = {
            **baseline,
            "top2_zero_hit": 0.24,
            "winner_top2": 0.42,
        }
        passed, gains = _development_gate(candidate, baseline)
        self.assertTrue(passed)
        self.assertEqual(gains, 2)

    def test_candidate_selection_never_uses_external_columns(self) -> None:
        table = pd.DataFrame(
            [
                {
                    "model": MODEL_VERSION,
                    "feature_scope": "safe",
                    "matrix_weight": 0.8,
                    "development_gate": True,
                    "selection_score": 1.0,
                    "external_gate": False,
                },
                {
                    "model": MODEL_VERSION,
                    "feature_scope": "external_better",
                    "matrix_weight": 0.7,
                    "development_gate": True,
                    "selection_score": 0.9,
                    "external_gate": True,
                },
            ]
        )
        scope, weight, passed = select_candidate(table)
        self.assertEqual(scope, "safe")
        self.assertEqual(weight, 0.8)
        self.assertTrue(passed)

    def test_prediction_export_drops_unneeded_training_columns(self) -> None:
        frame = pd.DataFrame(
            {
                "date": ["2026-01-01"],
                "meeting_name": ["M"],
                "race_number": [1],
                "horse_number": [1],
                "race_key": ["R"],
                "probability": [0.1],
                "finish_pos": [1],
                "prior_combo_roi": [99.0],
            }
        )
        exported = prediction_export(frame)
        self.assertIn("probability", exported)
        self.assertNotIn("prior_combo_roi", exported)


if __name__ == "__main__":
    unittest.main()
