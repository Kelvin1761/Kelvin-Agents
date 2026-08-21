import sys
import json
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
ENGINE = SCRIPTS / "au_racing_engine"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ENGINE.parent))

from au_architecture_audit import architecture_score, displayed_formula, neutral_formula
from au_racing_engine.matrix_mapper import map_features_to_matrix_scores
from au_matrix_refit import Dataset


class ArchitectureAuditTests(unittest.TestCase):
    def test_refit_accepts_current_runtime_snapshot_schema(self):
        payload = {"races": [{
            "metadata": {"date": "2026-08-08", "race_number": 1, "field_size": 2},
            "rows": [
                {"horse_number": 1, "horse_name": "A", "actual_pos": 1,
                 "feature_scores": {"form_score": 70}, "wet_form_feature": 1,
                 "score": 66},
                {"horse_number": 2, "horse_name": "B", "actual_pos": 2,
                 "feature_scores": {"form_score": 50}, "wet_form_feature": 0,
                 "score": 55},
            ],
        }]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "runtime.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            dataset = Dataset(path)
        self.assertEqual(dataset.n, 2)
        self.assertEqual(dataset.races[0]["date"], "2026-08-08")
        self.assertEqual(dataset.rows[0]["features"]["form_score"], 70)
        self.assertEqual(dataset.rows[0]["wet"], 1)

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

    def test_drop_weight_variant_matches_live_formula_after_weight_retirement(self):
        features = {
            "rating_score": 70.0,
            "weight_score": 35.0,
            "distance_score": 60.0,
        }
        matrices = map_features_to_matrix_scores(features)
        row = {
            "score": 60.0,
            "feature_scores": features,
            "matrix_scores": matrices,
        }
        self.assertEqual(
            matrices["class_weight"],
            round(displayed_formula("class_weight", ((70.0, 0.70),)), 2),
        )
        self.assertEqual(architecture_score(row, "drop_weight_leaf"), 60.0)


if __name__ == "__main__":
    unittest.main()
