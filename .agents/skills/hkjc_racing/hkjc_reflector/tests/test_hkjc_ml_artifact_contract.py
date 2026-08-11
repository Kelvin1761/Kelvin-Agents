from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ARTIFACTS = Path(__file__).resolve().parents[1] / "artifacts" / "hkjc_ml_program"


def test_full_program_deliverables_exist() -> None:
    required = {
        "hkjc_ml_readiness_report.md",
        "hkjc_ml_experiment_report.md",
        "point_in_time_leakage_test.md",
        "walk_forward_results.csv",
        "learning_curve.csv",
        "calibration_report.md",
        "calibration_curve.csv",
        "feature_importance.csv",
        "permutation_importance.csv",
        "shap_summary.csv",
        "shap_interaction_summary.csv",
        "segment_analysis.csv",
        "model_comparison_scorecard.csv",
        "hybrid_weight_search.csv",
        "betting_layer_report.md",
        "final_hkjc_scorecard.md",
        "promotion_recommendation.md",
        "requirements_audit.md",
    }
    missing = sorted(name for name in required if not (ARTIFACTS / name).is_file())
    assert not missing
    assert len(list((ARTIFACTS / "models").glob("*.joblib"))) == 8


def test_data_and_manifest_contract() -> None:
    quality = json.loads((ARTIFACTS / "data_quality_tests.json").read_text())
    manifest = json.loads((ARTIFACTS / "dataset_manifest.json").read_text())
    metadata = json.loads((ARTIFACTS / "model_metadata.json").read_text())
    assert quality["pass"] is True
    assert quality["duplicate_runner_keys_after_clean"] == 0
    assert quality["all_finish_positions_contiguous"] is True
    assert quality["place_labels_match_hkjc_cutoff"] is True
    assert manifest["coverage"]["valid_races"] == 250
    assert manifest["coverage"]["valid_rows"] == 3109
    assert manifest["champion_freeze_commit"] == "39155166df7fdba5162b19aa872e6fe004b7f3c3"
    selected = metadata["selected_numeric_features"] + metadata["selected_categorical_features"]
    assert not any(name.startswith("prior_") for name in selected)
    assert not any(token in name.lower() for name in selected for token in ("odds", "market", "roi", "dividend"))
    assert metadata["production_changed"] is False


def test_readiness_feature_and_segment_coverage_contract() -> None:
    dictionary = pd.read_csv(ARTIFACTS / "feature_dictionary.csv")
    required_dictionary = {
        "coverage_rate",
        "missing_rate",
        "neutral_default_rate",
        "unique_values",
        "suspicious_values",
        "first_available_date",
        "last_available_date",
        "historical_depth_days",
        "point_in_time_note",
    }
    assert required_dictionary.issubset(dictionary.columns)
    segments = pd.read_csv(ARTIFACTS / "segment_analysis.csv")
    assert {"venue", "track", "course", "distance_bucket", "race_class_label", "field_bucket", "race_confidence_band"}.issubset(
        set(segments["segment_dimension"])
    )
    calibration = pd.read_csv(ARTIFACTS / "calibration_curve.csv")
    assert {"period", "target", "model", "bin", "runners", "mean_probability", "observed_rate"}.issubset(
        calibration.columns
    )


def test_exact_scorecard_and_non_promotion_contract() -> None:
    scorecard = (ARTIFACTS / "final_hkjc_scorecard.md").read_text()
    for label in (
        "Current Matrix Top-1:",
        "Best ML Top-1:",
        "Current Matrix Top-3:",
        "Current Matrix Win Brier:",
        "Current Matrix Place Brier:",
        "ML improved vs Matrix:",
        "Current Matrix Betting ROI:",
        "Current Matrix Max Drawdown:",
        "SEGMENT FINDINGS",
        "KEEP CURRENT MATRIX",
    ):
        assert label in scorecard
    promotion = (ARTIFACTS / "promotion_recommendation.md").read_text()
    assert "DO NOT PROMOTE" in promotion


def test_artifacts_do_not_embed_local_sensitive_paths() -> None:
    forbidden = ("kelvin1761", "/Users/imac/Library/CloudStorage", "/private/tmp/hkjc-ml-program")
    for path in ARTIFACTS.rglob("*"):
        if path.suffix.lower() not in {".md", ".csv", ".json"}:
            continue
        text = path.read_text(encoding="utf-8-sig", errors="replace").lower()
        assert not any(value.lower() in text for value in forbidden), path
