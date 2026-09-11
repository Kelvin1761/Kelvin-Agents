import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from shared_wong_choi.contracts import Domain
from shared_wong_choi.domain_evidence import record_prediction_decision
from shared_wong_choi.evidence import DecisionState, EvidenceRecord, EvidenceStore, RecordKind
from shared_wong_choi.research_prediction_artifacts import (
    inspect_prediction_artifacts,
    verify_prediction_artifact_report,
)


NOW = datetime(2026, 8, 31, 12, tzinfo=timezone.utc)
EVENT = "2026-08-31 Test Track Race 1-1"


def _release(store):
    return store.append(EvidenceRecord(
        "wc:au:model-release:test", RecordKind.MODEL_RELEASE, Domain.AU,
        "2026-08-29T00:00:00+00:00",
        {"release_stage": "shadow", "code_commit": "a" * 40,
         "evaluation_contract_version": "au-v2"},
    )).path


def fixture(tmp_path):
    evidence = tmp_path / "evidence"
    store = EvidenceStore(evidence)
    _release(store)
    meeting = tmp_path / "hot" / EVENT
    snapshot = meeting / "_prediction_snapshots" / "20260831T000000Z-test"
    snapshot.mkdir(parents=True)
    scoring = snapshot / "Meeting_Auto_Scoring.csv"
    scoring.write_text("race_number,rank,horse_number,horse_name,grade\n1,1,7,Fast Horse,B+\n")
    logic = snapshot / "Race_1_Logic.json"
    logic.write_text('{"horses":[]}\n')
    files = [{"name": path.name, "bytes": path.stat().st_size,
              "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
             for path in (scoring, logic)]
    manifest = snapshot / "manifest.json"
    manifest.write_text(json.dumps({"append_only": True, "created_at": "2026-08-31T00:00:00+00:00",
                                    "domain": "au", "event_id": EVENT, "files": files}) + "\n")
    result = record_prediction_decision(
        domain=Domain.AU, event_id=EVENT, snapshot=snapshot,
        evidence_root=evidence, decision_state=DecisionState.SHADOW,
        model_release_id="wc:au:model-release:test", created_at=NOW,
        source_cutoff_at="2026-08-31T00:00:00+00:00",
    )
    return evidence, meeting, snapshot, result


def inspect(evidence, *roots):
    return inspect_prediction_artifacts(root=evidence, domain=Domain.AU, as_of=NOW,
                                        relocation_roots=tuple(roots))


def test_direct_snapshot_bundle_is_verified_but_not_a_pit_dataset(tmp_path):
    evidence, _meeting, snapshot, _ = fixture(tmp_path)
    before = {p: p.read_bytes() for p in snapshot.iterdir()}
    report = inspect(evidence)
    assert (report["records_seen"], report["artifact_refs"], report["direct_verified"],
            report["relocated_verified"], report["unavailable_refs"]) == (1, 3, 3, 0, 0)
    assert report["records"][0]["snapshot_bundle_verified"] is True
    assert report["normalized_source_verified"] is False
    assert report["verified_monitoring_samples"] is None
    assert report["model_promotion_allowed"] is False
    assert {p: p.read_bytes() for p in snapshot.iterdir()} == before


def test_exact_event_relative_relocation_recovers_moved_bundle(tmp_path):
    evidence, meeting, snapshot, _ = fixture(tmp_path)
    archive = tmp_path / "archive"
    relocated = archive / EVENT / snapshot.relative_to(meeting)
    relocated.parent.mkdir(parents=True)
    snapshot.rename(relocated)
    report = inspect(evidence, archive)
    assert report["direct_verified"] == 0
    assert report["relocated_verified"] == 3
    assert report["records"][0]["resolved_snapshot_root"] == str(relocated)


@pytest.mark.parametrize("fault", ["missing", "hash", "manifest", "partial_relocation"])
def test_missing_or_inconsistent_bundle_is_blocked_not_qualified(tmp_path, fault):
    evidence, meeting, snapshot, _ = fixture(tmp_path)
    roots = ()
    if fault == "missing":
        (snapshot / "Race_1_Logic.json").unlink()
    elif fault == "hash":
        (snapshot / "Race_1_Logic.json").write_text("changed")
    elif fault == "manifest":
        value = json.loads((snapshot / "manifest.json").read_text())
        value["event_id"] = "2026-08-31 Wrong Event"
        (snapshot / "manifest.json").write_text(json.dumps(value))
    else:
        archive = tmp_path / "archive"
        relocated = archive / EVENT / snapshot.relative_to(meeting)
        relocated.parent.mkdir(parents=True)
        snapshot.rename(relocated)
        (relocated / "Race_1_Logic.json").unlink()
        roots = (archive,)
    report = inspect(evidence, *roots)
    assert report["records"][0]["snapshot_bundle_verified"] is False
    assert report["unavailable_refs"] > 0 or report["records"][0]["manifest_consistent"] is False
    assert report["verified_monitoring_samples"] is None


def test_relocation_never_searches_by_basename_or_hash(tmp_path):
    evidence, meeting, snapshot, _ = fixture(tmp_path)
    archive = tmp_path / "archive"
    wrong = archive / "different-event" / snapshot.name
    wrong.parent.mkdir(parents=True)
    snapshot.rename(wrong)
    assert inspect(evidence, archive)["unavailable_refs"] == 3


def test_no_prediction_is_not_reported_as_healthy_or_sample_ready(tmp_path):
    evidence = tmp_path / "evidence"
    _release(EvidenceStore(evidence))
    report = inspect(evidence)
    assert report["records_seen"] == 0
    assert report["source_coverage_complete"] is False
    assert report["verified_monitoring_samples"] is None


def test_report_verifier_rejects_invented_authority(tmp_path):
    evidence, _, _, _ = fixture(tmp_path)
    report = inspect(evidence)
    report["verified_monitoring_samples"] = 1
    report["content_hash"] = hashlib.sha256(json.dumps(
        {k: v for k, v in report.items() if k != "content_hash"}, sort_keys=True,
        separators=(",", ":")).encode()).hexdigest()
    with pytest.raises((ValueError, RuntimeError)):
        verify_prediction_artifact_report(report, root=evidence, domain=Domain.AU,
                                          as_of=NOW, relocation_roots=())


def test_report_verifier_rejects_forged_resolved_path(tmp_path):
    from shared_wong_choi.research_index import _hash
    evidence, _, _, _ = fixture(tmp_path)
    report = inspect(evidence)
    report["records"][0]["resolved_snapshot_root"] = "relative/forged"
    report["content_hash"] = _hash({k: v for k, v in report.items() if k != "content_hash"})
    with pytest.raises((ValueError, RuntimeError)):
        verify_prediction_artifact_report(report, root=evidence, domain=Domain.AU,
                                          as_of=NOW, relocation_roots=())


@pytest.mark.parametrize(
    ("field", "value"),
    [("records_seen", True), ("artifact_contents_verified", 1), ("content_hash", "x" * 64)],
)
def test_report_verifier_rejects_noncanonical_aggregate_types_and_hash(tmp_path, field, value):
    from shared_wong_choi.research_index import _hash
    evidence, _, _, _ = fixture(tmp_path)
    report = inspect(evidence)
    report[field] = value
    if field != "content_hash":
        report["content_hash"] = _hash({k: v for k, v in report.items() if k != "content_hash"})
    with pytest.raises((ValueError, RuntimeError)):
        verify_prediction_artifact_report(report, root=evidence, domain=Domain.AU,
                                          as_of=NOW, relocation_roots=())


def test_corrupt_direct_copy_can_use_exact_archive_copy_but_degradation_is_visible(tmp_path):
    evidence, meeting, snapshot, _ = fixture(tmp_path)
    archive = tmp_path / "archive"
    relocated = archive / EVENT / snapshot.relative_to(meeting)
    relocated.mkdir(parents=True)
    for path in snapshot.iterdir():
        (relocated / path.name).write_bytes(path.read_bytes())
    (snapshot / "Race_1_Logic.json").write_text("corrupt")
    report = inspect(evidence, archive)
    assert report["records"][0]["snapshot_bundle_verified"] is True
    assert report["direct_invalid_refs"] == 1
    assert report["relocated_verified"] == 3


def test_as_of_excludes_later_prediction_without_reading_artifacts(tmp_path):
    evidence, _, snapshot, _ = fixture(tmp_path)
    for path in snapshot.iterdir():
        path.unlink()
    report = inspect_prediction_artifacts(
        root=evidence, domain=Domain.AU,
        as_of=datetime(2026, 8, 30, 12, tzinfo=timezone.utc), relocation_roots=())
    assert report["records_seen"] == 0 and report["artifact_refs"] == 0


def test_symlinked_relocation_root_is_rejected(tmp_path):
    evidence, _, _, _ = fixture(tmp_path)
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises((ValueError, RuntimeError)):
        inspect(evidence, link)
