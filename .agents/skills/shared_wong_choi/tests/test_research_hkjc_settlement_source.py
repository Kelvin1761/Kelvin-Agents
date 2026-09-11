import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared_wong_choi.contracts import Domain
from shared_wong_choi.domain_evidence import record_prediction_decision, record_settlement_for_event
from shared_wong_choi.evidence import DecisionState, EvidenceRecord, EvidenceStore, RecordKind
from shared_wong_choi.research_hkjc_settlement_source import (
    inspect_hkjc_settlement_candidates,
    verify_hkjc_settlement_candidate_report,
)
from shared_wong_choi.research_index import _hash


EVENT = "2026-09-13|ShaTin"
NOW = datetime(2026, 9, 13, 7, tzinfo=timezone.utc)
END = NOW + timedelta(hours=12)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prediction_fixture(tmp_path, *, legacy_manifest=False):
    evidence = tmp_path / "evidence"
    store = EvidenceStore(evidence)
    store.append(EvidenceRecord(
        "wc:hkjc:model-release:test", RecordKind.MODEL_RELEASE, Domain.HKJC,
        "2026-09-01T00:00:00+00:00",
        {"release_stage": "production", "code_commit": "a" * 40,
         "evaluation_contract_version": "hkjc-v2"},
    ))
    meeting = tmp_path / "archive" / "2026-09-13_ShaTin"
    snapshot_root = "Prediction_Snapshots" if legacy_manifest else "_prediction_snapshots"
    snapshot = meeting / snapshot_root / "20260913T000000Z-test"
    snapshot.mkdir(parents=True)
    logic = snapshot / "Race_1_Logic.json"
    logic.write_text('{"horses": {}}\n', encoding="utf-8")
    manifest = snapshot / "manifest.json"
    if legacy_manifest:
        payload = {
            "schema_version": 1, "platform": "hkjc", "meeting": meeting.name,
            "created_at": "2026-09-13T00:00:00+00:00", "signature": "b" * 64,
            "files": [{"name": logic.name, "size": logic.stat().st_size,
                       "sha256": digest(logic)}],
            "immutable_prediction_snapshot": True,
        }
    else:
        payload = {
            "schema_version": "wong-choi-prediction-snapshot/v1",
            "append_only": True, "domain": "hkjc", "event_id": EVENT,
            "created_at": "2026-09-13T00:00:00+00:00",
            "files": [{"name": logic.name, "bytes": logic.stat().st_size,
                       "sha256": digest(logic)}],
        }
    manifest.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    record_prediction_decision(
        domain=Domain.HKJC, event_id=EVENT, snapshot=snapshot, evidence_root=evidence,
        decision_state=DecisionState.SHADOW,
        model_release_id="wc:hkjc:model-release:test", created_at=NOW,
        source_cutoff_at="2026-09-13T00:00:00+00:00",
    )
    return evidence, meeting, snapshot


def result_file(meeting, *, partial=False):
    rows = [
        {"pos": "1", "horse_no": 7, "horse_name": "Fast Horse", "lbw": "-",
         "win_odds": 3.0},
        {"pos": "2", "horse_no": 4, "horse_name": "Second Horse", "lbw": "0.2",
         "win_odds": 4.0},
    ]
    if not partial:
        rows.append({"pos": "3", "horse_no": 2, "horse_name": "Third Horse",
                     "lbw": "0.5", "win_odds": 5.0})
    path = meeting / "2026-09-13_ShaTin_全日賽果.json"
    path.write_text(json.dumps({"1": {"venue": "ShaTin", "results": rows}}) + "\n",
                    encoding="utf-8")
    return path


def settled_fixture(tmp_path, *, evidence_result=True, partial=False,
                    legacy_manifest=False):
    evidence, meeting, snapshot = prediction_fixture(
        tmp_path, legacy_manifest=legacy_manifest,
    )
    results = result_file(meeting, partial=partial)
    report = meeting / "HKJC_Reflection_Report.md"
    report.write_text("# HKJC reflector report\n", encoding="utf-8")
    artifacts = [report, results] if evidence_result else [report]
    record_settlement_for_event(
        domain=Domain.HKJC, event_id=EVENT, evidence_root=evidence,
        summary={"meeting": meeting.name, "reflector_exit": 0}, artifacts=artifacts,
        settled_at=NOW + timedelta(hours=10), required=True,
    )
    return evidence, meeting, snapshot, results


def inspect(evidence):
    return inspect_hkjc_settlement_candidates(root=evidence, as_of=END)


def test_hash_pinned_full_day_results_prove_labels_only(tmp_path):
    report = inspect(settled_fixture(tmp_path)[0])
    candidate = report["candidates"][0]
    assert (report["settlements_seen"], report["label_verified_settlements"],
            report["parsed_result_races"], report["parsed_result_rows"]) == (1, 1, 1, 3)
    assert candidate["blockers"] == ["feature_availability_unverified"]
    assert report["verified_monitoring_samples"] is None
    assert report["model_promotion_allowed"] is False


def test_adjacent_but_unevidenced_results_are_not_labels(tmp_path):
    report = inspect(settled_fixture(tmp_path, evidence_result=False)[0])
    candidate = report["candidates"][0]
    assert candidate["adjacent_unreferenced_result"] is True
    assert candidate["blockers"] == [
        "result_artifact_not_evidenced", "feature_availability_unverified",
    ]
    assert report["label_verified_settlements"] == 0


def test_incomplete_top_three_is_blocked(tmp_path):
    report = inspect(settled_fixture(tmp_path, partial=True)[0])
    assert report["candidates"][0]["blockers"] == [
        "result_artifact_incomplete", "feature_availability_unverified",
    ]


def test_current_legacy_hkjc_snapshot_manifest_cannot_masquerade_as_canonical_bundle(tmp_path):
    report = inspect(settled_fixture(tmp_path, legacy_manifest=True)[0])
    assert report["candidates"][0]["blockers"] == [
        "prediction_bundle_unverified", "result_artifact_incomplete",
        "feature_availability_unverified",
    ]
    assert report["verified_monitoring_samples"] is None


def test_mutated_evidenced_result_fails_closed(tmp_path):
    evidence, _meeting, _snapshot, results = settled_fixture(tmp_path)
    results.write_text("{}\n", encoding="utf-8")
    with pytest.raises((ValueError, RuntimeError)):
        inspect(evidence)


def test_hash_valid_result_from_another_meeting_is_rejected(tmp_path):
    evidence, meeting, _snapshot = prediction_fixture(tmp_path)
    report = meeting / "HKJC_Reflection_Report.md"
    report.write_text("# HKJC reflector report\n", encoding="utf-8")
    other = tmp_path / "archive" / "2026-09-13_HappyValley"
    other.mkdir(parents=True)
    results = result_file(other)
    record_settlement_for_event(
        domain=Domain.HKJC, event_id=EVENT, evidence_root=evidence,
        summary={"meeting": meeting.name}, artifacts=[report, results],
        settled_at=NOW + timedelta(hours=10), required=True,
    )
    with pytest.raises((ValueError, RuntimeError)):
        inspect(evidence)


def test_verifier_rejects_forged_sample_authority(tmp_path):
    evidence = settled_fixture(tmp_path)[0]
    report = inspect(evidence)
    report["verified_monitoring_samples"] = 1
    report["content_hash"] = _hash({key: value for key, value in report.items()
                                    if key != "content_hash"})
    with pytest.raises((ValueError, RuntimeError)):
        verify_hkjc_settlement_candidate_report(report, root=evidence, as_of=END,
                                                relocation_roots=())


def test_no_settlement_is_not_source_complete(tmp_path):
    evidence, _meeting, _snapshot = prediction_fixture(tmp_path)
    report = inspect(evidence)
    assert report["settlements_seen"] == 0
    assert report["source_coverage_complete"] is False
    assert report["verified_monitoring_samples"] is None
