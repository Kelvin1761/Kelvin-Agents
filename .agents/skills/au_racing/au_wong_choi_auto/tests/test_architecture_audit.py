import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
ENGINE = SCRIPTS / "racing_engine"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ENGINE))

from au_architecture_audit import architecture_score, neutral_formula


class ArchitectureAuditTests(unittest.TestCase):
    def test_neutral_formula_preserves_unallocated_neutral_weight(self):
        self.assertEqual(neutral_formula(((60.0, 0.70),)), 60.0)
        self.assertAlmostEqual(
            neutral_formula(((70.0, 0.70),)),
            67.0,
        )

    def test_distance_transfer_rewards_only_relative_to_source_matrix(self):
        row = {
            "score": 60.0,
            "feature_scores": {
                "rating_score": 60.0,
                "weight_score": 60.0,
                "distance_score": 70.0,
            },
            "matrix_scores": {
                "class_weight": 60.0,
                "track": 60.0,
                "race_shape": 60.0,
            },
        }
        self.assertAlmostEqual(
            architecture_score(row, "distance_from_track_02"),
            60.2,
        )
        row["matrix_scores"]["track"] = 70.0
        self.assertAlmostEqual(
            architecture_score(row, "distance_from_track_02"),
            60.0,
        )


if __name__ == "__main__":
    unittest.main()
