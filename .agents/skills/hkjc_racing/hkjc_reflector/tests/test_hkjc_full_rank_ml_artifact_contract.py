from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ARTIFACTS = Path(__file__).resolve().parents[1] / "artifacts" / "hkjc_full_rank_ml_program"


def test_full_rank_artifact_pack_is_complete() -> None:
    required = {
        "development_candidate_scorecard.csv",
        "external_predictions.csv",
        "feature_audit.csv",
        "feature_importance.csv",
        "final_comparison.csv",
        "full_rank_ml_report.md",
        "manifest.json",
        "rank3_placegetter_to_top2.csv",
        "rank_movements.csv",
        "scope_feature_importance.csv",
        "walk_forward_predictions.csv",
        "weak_race_pattern_summary.csv",
        "weak_race_review.csv",
        "models/matrix_anchored_lambdarank.joblib",
    }
    missing = [name for name in required if not (ARTIFACTS / name).exists()]
    assert not missing, f"missing full-rank ML artifacts: {missing}"


def test_manifest_freezes_external_and_production_state() -> None:
    manifest = json.loads((ARTIFACTS / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["external_not_used_for_selection"] is True
    assert manifest["selection"]["production_promoted"] is False
    assert manifest["selection"]["feature_scope"] in {
        "matrix_7d",
        "matrix_plus_components",
        "matrix_plus_components_raw",
    }
    assert 0.0 < manifest["selection"]["matrix_weight"] <= 1.0
    assert len(manifest["model"]["sha256"]) == 64


def test_scorecard_contains_competitiveness_and_weak_race_metrics() -> None:
    scorecard = pd.read_csv(ARTIFACTS / "development_candidate_scorecard.csv", encoding="utf-8-sig")
    required = {
        "top2_zero_hit",
        "top2_one_hit",
        "top3_capture_at5",
        "top5_capture_at5",
        "competitive_ndcg_at5",
        "actual_top3_average_rank",
        "development_gate",
    }
    assert required.issubset(scorecard.columns)
    assert len(scorecard) == 10


def test_report_records_no_direct_production_promotion() -> None:
    report = (ARTIFACTS / "full_rank_ml_report.md").read_text(encoding="utf-8")
    assert "Production Matrix: unchanged" in report
    assert "external" in report.lower()
