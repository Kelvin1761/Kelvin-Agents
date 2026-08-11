from __future__ import annotations

import json
import unittest
from pathlib import Path

import joblib
import pandas as pd


ARTIFACTS = (
    Path(__file__).resolve().parents[1]
    / "artifacts"
    / "hkjc_dimension_ml_program"
)


class HkjcDimensionMlArtifactContractTests(unittest.TestCase):
    def test_dimension_deliverables_and_models_exist(self) -> None:
        required = {
            "dimension_ablation_scorecard.csv",
            "dimension_external_results.csv",
            "dimension_feature_audit.csv",
            "dimension_optimizer_diagnostics.csv",
            "dimension_predictions.csv",
            "dimension_program_manifest.json",
            "dimension_promotion_recommendation.md",
            "dimension_rank_movements.csv",
            "dimension_residual_cap_search.csv",
            "dimension_residual_coefficients.csv",
            "dimension_segment_analysis.csv",
            "dimension_walk_forward_results.csv",
            "dimension_weak_race_impact.csv",
            "hkjc_dimension_ml_report.md",
        }
        missing = sorted(name for name in required if not (ARTIFACTS / name).is_file())
        self.assertFalse(missing)
        models = sorted((ARTIFACTS / "models").glob("*.joblib"))
        self.assertEqual(len(models), 6)
        for path in models:
            payload = joblib.load(path)
            self.assertIn("residual_model", payload)
            self.assertIn("preprocessor", payload["residual_model"])
            self.assertIn("coefficients", payload["residual_model"])

    def test_manifest_and_gate_contract(self) -> None:
        manifest = json.loads(
            (ARTIFACTS / "dimension_program_manifest.json").read_text()
        )
        self.assertFalse(manifest["production_modified"])
        self.assertEqual(set(manifest["dimensions"]), {"trainer_signal", "race_shape", "stability"})
        self.assertEqual(manifest["coverage"]["archived_ability_rows_rebuilt"], 3109)
        self.assertFalse(manifest["selected"]["trainer_signal"]["development_gate"])
        self.assertFalse(manifest["selected"]["race_shape"]["development_gate"])
        self.assertTrue(manifest["selected"]["stability"]["development_gate"])
        self.assertFalse(manifest["selected"]["stability"]["external_non_regression"])

    def test_features_are_pre_race_and_market_free(self) -> None:
        audit = pd.read_csv(ARTIFACTS / "dimension_feature_audit.csv")
        self.assertTrue(audit["leakage_safe"].all())
        self.assertTrue(audit["pre_race_available"].all())
        forbidden = ("odds", "market", "roi", "dividend", "prior_")
        self.assertFalse(
            any(
                token in feature.lower()
                for feature in audit["feature"].astype(str)
                for token in forbidden
            )
        )

    def test_report_keeps_production_frozen(self) -> None:
        report = (ARTIFACTS / "hkjc_dimension_ml_report.md").read_text()
        recommendation = (
            ARTIFACTS / "dimension_promotion_recommendation.md"
        ).read_text()
        self.assertIn("Production 七維 Matrix", report)
        self.assertIn("浪漫老撾", report)
        self.assertIn("Do not promote to production", recommendation)


if __name__ == "__main__":
    unittest.main()
