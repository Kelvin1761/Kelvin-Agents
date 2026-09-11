import json
from datetime import timedelta

import pytest

from shared_wong_choi.contracts import Domain
from shared_wong_choi.domain_evidence import record_settlement_for_event
from shared_wong_choi.research_au_settlement_source import (
    inspect_au_settlement_candidates,
    verify_au_settlement_candidate_report,
)
from shared_wong_choi.research_index import _hash
from test_research_prediction_artifacts import EVENT, NOW, fixture as prediction_fixture


END = NOW + timedelta(hours=2)


def settled_fixture(tmp_path, *, evidence_result: bool):
    evidence, meeting, snapshot, _ = prediction_fixture(tmp_path)
    result_source = meeting / "Race_Results_Reflector.md"
    result_source.write_text(
        "# Results\n\n## Race 1\n"
        "1st: #7 Fast Horse SP$3.00\n"
        "2nd: #4 Second Horse (0.20L) SP$4.00\n"
        "3rd: #2 Third Horse (0.50L) SP$5.00\n",
        encoding="utf-8",
    )
    report = meeting / f"{EVENT}_Reflector_Report.md"
    report.write_text("# Rendered reflector report\n", encoding="utf-8")
    artifacts = [report, result_source] if evidence_result else [report]
    record_settlement_for_event(
        domain=Domain.AU,
        event_id=EVENT,
        evidence_root=evidence,
        summary={"meeting": EVENT, "archive_status": "archived"},
        artifacts=artifacts,
        settled_at=NOW + timedelta(hours=1),
        required=True,
    )
    return evidence, meeting, snapshot, result_source


def inspect(evidence, *roots):
    return inspect_au_settlement_candidates(
        root=evidence,
        as_of=END,
        relocation_roots=tuple(roots),
    )


def test_evidenced_canonical_result_is_parsed_but_not_a_verified_sample(tmp_path):
    evidence, _meeting, _snapshot, _result = settled_fixture(tmp_path, evidence_result=True)
    report = inspect(evidence)
    assert (report["settlements_seen"], report["label_verified_settlements"],
            report["parsed_result_races"], report["parsed_result_rows"]) == (1, 1, 1, 3)
    assert report["candidates"][0]["blockers"] == ["feature_availability_unverified"]
    assert report["verified_monitoring_samples"] is None
    assert report["model_promotion_allowed"] is False


def test_adjacent_but_unevidenced_result_is_inventory_only(tmp_path):
    evidence, _meeting, _snapshot, _result = settled_fixture(tmp_path, evidence_result=False)
    report = inspect(evidence)
    candidate = report["candidates"][0]
    assert candidate["adjacent_unreferenced_result"] is True
    assert candidate["label_source_verified"] is False
    assert candidate["blockers"] == ["result_artifact_not_evidenced", "feature_availability_unverified"]
    assert report["parsed_result_races"] == 0


def test_mutated_evidenced_result_fails_closed(tmp_path):
    evidence, _meeting, _snapshot, result = settled_fixture(tmp_path, evidence_result=True)
    result.write_text("changed after settlement", encoding="utf-8")
    with pytest.raises((ValueError, RuntimeError)):
        inspect(evidence)


def test_hash_valid_result_from_another_event_folder_is_rejected(tmp_path):
    evidence, meeting, _snapshot, _ = prediction_fixture(tmp_path)
    report = meeting / f"{EVENT}_Reflector_Report.md"
    report.write_text("# Rendered reflector report\n", encoding="utf-8")
    other = tmp_path / "archive" / "2026-08-31 Wrong Track Race 1-1"
    other.mkdir(parents=True)
    result_source = other / "Race_Results_Reflector.md"
    result_source.write_text(
        "# Results\n\n## Race 1\n"
        "1st: #7 Fast Horse SP$3.00\n"
        "2nd: #4 Second Horse (0.20L) SP$4.00\n"
        "3rd: #2 Third Horse (0.50L) SP$5.00\n",
        encoding="utf-8",
    )
    record_settlement_for_event(
        domain=Domain.AU,
        event_id=EVENT,
        evidence_root=evidence,
        summary={"meeting": EVENT, "archive_status": "archived"},
        artifacts=[report, result_source],
        settled_at=NOW + timedelta(hours=1),
        required=True,
    )
    with pytest.raises((ValueError, RuntimeError)):
        inspect(evidence)


def test_missing_prediction_bundle_blocks_otherwise_evidenced_result(tmp_path):
    evidence, _meeting, snapshot, _result = settled_fixture(tmp_path, evidence_result=True)
    (snapshot / "Race_1_Logic.json").unlink()
    report = inspect(evidence)
    assert report["candidates"][0]["blockers"] == [
        "prediction_bundle_unverified",
        "feature_availability_unverified",
    ]
    assert report["verified_monitoring_samples"] is None


def test_verifier_rejects_forged_sample_authority(tmp_path):
    evidence, _meeting, _snapshot, _result = settled_fixture(tmp_path, evidence_result=True)
    report = inspect(evidence)
    report["verified_monitoring_samples"] = 1
    report["content_hash"] = _hash({key: value for key, value in report.items() if key != "content_hash"})
    with pytest.raises((ValueError, RuntimeError)):
        verify_au_settlement_candidate_report(
            report, root=evidence, as_of=END, relocation_roots=()
        )


def test_verifier_rejects_unevidenced_result_relabelled_as_verified(tmp_path):
    evidence, _meeting, _snapshot, _result = settled_fixture(tmp_path, evidence_result=False)
    report = inspect(evidence)
    report["candidates"][0]["label_source_verified"] = True
    report["label_verified_settlements"] = 1
    report["label_source_verified"] = True
    report["content_hash"] = _hash({key: value for key, value in report.items() if key != "content_hash"})
    with pytest.raises((ValueError, RuntimeError)):
        verify_au_settlement_candidate_report(
            report, root=evidence, as_of=END, relocation_roots=()
        )


def test_no_settlement_is_not_complete_or_sample_ready(tmp_path):
    evidence, _meeting, _snapshot, _ = prediction_fixture(tmp_path)
    report = inspect(evidence)
    assert report["settlements_seen"] == 0
    assert report["source_coverage_complete"] is False
    assert report["verified_monitoring_samples"] is None
