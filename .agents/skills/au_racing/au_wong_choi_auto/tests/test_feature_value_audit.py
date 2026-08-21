import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
ENGINE = SCRIPTS / "au_racing_engine"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ENGINE.parent))

from au_feature_value_audit import within_race_auc


class FeatureValueAuditTests(unittest.TestCase):
    def test_within_race_auc_uses_only_in_race_pairs(self):
        race = {
            "rows": [
                {"actual_pos": 1, "feature_scores": {"form_score": 80}},
                {"actual_pos": 2, "feature_scores": {"form_score": 70}},
                {"actual_pos": 3, "feature_scores": {"form_score": 60}},
                {"actual_pos": 4, "feature_scores": {"form_score": 50}},
            ]
        }
        self.assertEqual(within_race_auc([race], "form_score"), 1.0)

    def test_ties_count_as_half(self):
        race = {
            "rows": [
                {"actual_pos": 1, "feature_scores": {"form_score": 60}},
                {"actual_pos": 2, "feature_scores": {"form_score": 60}},
                {"actual_pos": 3, "feature_scores": {"form_score": 60}},
                {"actual_pos": 4, "feature_scores": {"form_score": 60}},
            ]
        }
        self.assertEqual(within_race_auc([race], "form_score"), 0.5)


if __name__ == "__main__":
    unittest.main()
