import json
import hashlib
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


def test_exact_recovered_version_preserves_records_and_current_report(tmp_path):
    from shared_wong_choi.recovered_settlement_artifacts import register_recovered_artifact

    evidence, _meeting, _snapshot, result = settled_fixture(tmp_path, evidence_result=True)
    records = {p: p.read_bytes() for p in evidence.glob("records/**/*.json")}
    original = result.read_bytes()
    source = tmp_path / "recovered.md"
    source.write_bytes(original)
    args = dict(root=evidence, original=result, sha256=hashlib.sha256(original).hexdigest(),
                event_id=EVENT, source=source)
    recovered = register_recovered_artifact(**args)
    assert register_recovered_artifact(**args) == recovered
    result.write_text("today's different report")
    report = inspect(evidence)
    assert report["label_verified_settlements"] == 1
    assert report["candidates"][0]["referenced_result_artifact"] == str(recovered)
    assert report["model_promotion_allowed"] is False
    assert records == {p: p.read_bytes() for p in evidence.glob("records/**/*.json")}
    assert result.read_text() == "today's different report"
    recovered.chmod(0o644)
    recovered.write_text("corrupt")
    with pytest.raises(ValueError, match="provenance mismatch"):
        inspect(evidence)


def test_recovery_refuses_wrong_bytes_and_cross_event_identity(tmp_path):
    from shared_wong_choi.recovered_settlement_artifacts import register_recovered_artifact

    evidence, _meeting, _snapshot, result = settled_fixture(tmp_path, evidence_result=True)
    args = dict(root=evidence, original=result, sha256="0" * 64,
                event_id=EVENT, source=result)
    with pytest.raises(ValueError, match="recorded hash"):
        register_recovered_artifact(**args)
    args["event_id"] = "different event"
    with pytest.raises(ValueError, match="identity"):
        register_recovered_artifact(**args)


def test_two_recorded_versions_of_one_path_are_both_retained(tmp_path):
    from shared_wong_choi.recovered_settlement_artifacts import register_recovered_artifact

    evidence, _meeting, _snapshot, result = settled_fixture(tmp_path, evidence_result=True)
    original = result.read_bytes()
    register_recovered_artifact(
        root=evidence, original=result, sha256=hashlib.sha256(original).hexdigest(),
        event_id=EVENT, source=result)
    result.write_bytes(original + b"\n# Later rendering\n")
    record_settlement_for_event(
        domain=Domain.AU, event_id=EVENT, evidence_root=evidence,
        summary={"meeting": EVENT, "archive_status": "archived"}, artifacts=[result],
        settled_at=NOW + timedelta(hours=2), required=True)
    report = inspect(evidence)
    assert report["settlements_seen"] == report["label_verified_settlements"] == 2
    assert len({c["referenced_result_artifact"] for c in report["candidates"]}) == 2


@pytest.mark.parametrize("damage", ["manifest", "symlink", "missing"])
def test_recovered_version_damage_fails_closed(tmp_path, damage):
    from shared_wong_choi.recovered_settlement_artifacts import register_recovered_artifact

    evidence, _meeting, _snapshot, result = settled_fixture(tmp_path, evidence_result=True)
    original = result.read_bytes()
    recovered = register_recovered_artifact(
        root=evidence, original=result, sha256=hashlib.sha256(original).hexdigest(),
        event_id=EVENT, source=result)
    result.write_text("new version")
    if damage == "manifest":
        manifest = recovered.parent.parent / "manifest.json"
        manifest.chmod(0o644)
        body = json.loads(manifest.read_text())
        body["original_path"] = str(result) + "wrong"
        manifest.write_text(json.dumps(body))
    else:
        recovered.unlink()
        if damage == "symlink":
            recovered.symlink_to(result)
    with pytest.raises((ValueError, RuntimeError)):
        inspect(evidence)


def test_immutable_capture_preserves_native_reader_checks_after_source_rewrite(tmp_path):
    from shared_wong_choi.immutable_settlement_artifacts import capture_settlement_artifacts

    evidence, meeting, _snapshot, _ = prediction_fixture(tmp_path)
    result = meeting / "Race_Results_Reflector.md"
    result.write_text("# Results\n\n## Race 1\n1st: #7 Fast Horse SP$3.00\n"
                      "2nd: #4 Second Horse (0.20L) SP$4.00\n"
                      "3rd: #2 Third Horse (0.50L) SP$5.00\n", encoding="utf-8")
    report = meeting / f"{EVENT}_Reflector_Report.md"
    report.write_text("# original report\n", encoding="utf-8")
    warm = tmp_path / "warm"
    warm.mkdir()
    captured = capture_settlement_artifacts(
        artifacts=(result, report), event_id=EVENT, root=warm,
    )
    record_settlement_for_event(
        domain=Domain.AU, event_id=EVENT, evidence_root=evidence,
        summary={"meeting": EVENT, "archive_status": "archived"},
        artifacts=captured, settled_at=NOW + timedelta(hours=1), required=True,
    )
    result.write_text("rewritten results", encoding="utf-8")
    report.write_text("rewritten report", encoding="utf-8")
    verified = inspect(evidence)
    assert verified["label_verified_settlements"] == 1
    assert verified["model_promotion_allowed"] is False
    captured[0].chmod(0o644)
    captured[0].write_text("corrupt capture", encoding="utf-8")
    with pytest.raises(ValueError, match="provenance mismatch"):
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
