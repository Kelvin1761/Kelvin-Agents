import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
ENGINE = SCRIPTS / "au_racing_engine"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ENGINE.parent))

from au_matrix_weight_search import (
    candidate_weights,
    passes_confirmation,
    score_races,
    selection_summary,
)
from au_runtime_micro_ablation import metrics_for_scored_races
from au_racing_engine.scoring import MATRIX_WEIGHTS


class MatrixWeightSearchTests(unittest.TestCase):
    def test_candidates_preserve_total_weight_and_change_one_pair(self):
        candidates = candidate_weights()
        baseline_total = sum(MATRIX_WEIGHTS.values())
        for name, weights in candidates.items():
            self.assertAlmostEqual(sum(weights.values()), baseline_total)
            if name == "revised_current":
                continue
            changed = [
                key
                for key in MATRIX_WEIGHTS
                if weights[key] != MATRIX_WEIGHTS[key]
            ]
            self.assertEqual(len(changed), 2)

    def test_matrix_recomposition_preserves_neutral_score(self):
        row = {
            "horse_number": 1,
            "horse_name": "Neutral",
            "score": 61.25,
            "actual_pos": 1,
            "result_sp_label": 5.0,
            "matrix_scores": {
                key: 60.0 for key in MATRIX_WEIGHTS
            },
        }
        dataset = {
            "races": [{"metadata": {"date": "2026-01-01"}, "rows": [row]}]
        }
        weights = candidate_weights()["stability_to_track_100bp"]
        self.assertEqual(score_races(dataset, weights)[0][0]["score"], 61.25)

    def test_selection_and_confirmation_prioritise_recall_and_zero_hit(self):
        good = {
            "good_positional": 0.01,
            "top3_all_within_top4": 0.01,
            "competitive_recall_at5": 0.01,
            "ndcg_at5": 0.01,
            "winner_top5": 0.01,
            "zero_hit": -0.01,
        }
        summary = selection_summary([good, good, good, good])
        self.assertTrue(summary["eligible"])
        self.assertTrue(passes_confirmation(good))
        bad = {**good, "zero_hit": 0.01}
        self.assertFalse(passes_confirmation(bad))
        self.assertFalse(
            passes_confirmation({**good, "good_positional": -0.01})
        )
        self.assertFalse(
            passes_confirmation({**good, "top3_all_within_top4": -0.01})
        )

    def test_compact_metrics_keep_positional_good_distinct_from_top4_capture(self):
        def scored_row(number, score, actual_pos):
            return {
                "horse_number": number,
                "horse_name": f"Horse {number}",
                "score": score,
                "actual_pos": actual_pos,
                "result_sp_label": None,
            }

        races = [
            [
                scored_row(1, 80, 1),
                scored_row(4, 70, 4),
                scored_row(2, 60, 2),
                scored_row(3, 50, 3),
            ],
            [
                scored_row(1, 80, 1),
                scored_row(2, 70, 2),
                scored_row(4, 60, 4),
                scored_row(3, 50, 3),
            ],
        ]
        metrics = metrics_for_scored_races(races)
        self.assertEqual(metrics["good_positional"], 0.5)
        self.assertEqual(metrics["top3_all_within_top4"], 1.0)


if __name__ == "__main__":
    unittest.main()
