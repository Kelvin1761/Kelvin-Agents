import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared_wong_choi.contracts import Domain
from shared_wong_choi.domain_evidence import record_prediction_decision
from shared_wong_choi.evidence import DecisionState, EvidenceRecord, EvidenceStore, RecordKind
from shared_wong_choi.research_hkjc_feature_provenance import (
    inspect_hkjc_feature_provenance,
    verify_hkjc_feature_provenance_report,
)
from shared_wong_choi.research_index import _hash


CUTOFF = "2026-08-31T23:00:00+00:00"
AS_OF = datetime(2026, 9, 1, 1, tzinfo=timezone.utc)
EVENT = "2026-09-01|ST"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture(tmp_path, mode="valid"):
    evidence = tmp_path / "evidence"
    store = EvidenceStore(evidence)
    store.append(EvidenceRecord(
        "wc:hkjc:model-release:feature", RecordKind.MODEL_RELEASE, Domain.HKJC,
        "2026-08-29T00:00:00+00:00",
        {"release_stage": "production", "code_commit": "a" * 40,
         "evaluation_contract_version": "hkjc-v2"},
    ))
    snapshot = tmp_path / "archive" / EVENT / "_prediction_snapshots" / "feature"
    snapshot.mkdir(parents=True)
    source = snapshot / "2026-09-01 ST Race 1 Facts.md"
    source.write_text("# Pre-race facts\nlast_6_finishes: 1,2,3\n", encoding="utf-8")
    scoring = snapshot / "HKJC_Auto_Scoring.csv"
    scoring.write_text("race_number,rank,horse_number,horse_name,grade\n1,1,7,快馬,B+\n")
    source_ref = {
        "artifact": source.name,
        "sha256": digest(source),
        "available_at": CUTOFF,
        "field": "horses.7.last_6_finishes",
    }
    if mode == "legacy":
        provenance = "last_6_finishes"
    else:
        if mode == "future":
            source_ref["available_at"] = "2026-08-31T23:00:01+00:00"
        elif mode == "digest":
            source_ref["sha256"] = "f" * 64
        elif mode == "output":
            source_ref.update(artifact=scoring.name, sha256=digest(scoring), field="rank")
        provenance = {"derivation": "hkjc.form_score/v1", "sources": [source_ref]}
    logic = snapshot / "Race_1_Logic.json"
    logic.write_text(json.dumps({
        "race_analysis": {"race_number": 1},
        "horses": {"7": {"horse_name": "快馬", "python_auto": {
            "score_provenance": {"form_score": provenance},
        }}},
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    files = [{"name": path.name, "bytes": path.stat().st_size, "sha256": digest(path)}
             for path in (source, scoring, logic)]
    manifest = snapshot / "manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": "wong-choi-prediction-snapshot/v1",
        "append_only": True, "created_at": CUTOFF, "domain": "hkjc",
        "event_id": EVENT, "files": files,
    }) + "\n", encoding="utf-8")
    record_prediction_decision(
        domain=Domain.HKJC, event_id=EVENT, snapshot=snapshot, evidence_root=evidence,
        decision_state=DecisionState.SHADOW,
        model_release_id="wc:hkjc:model-release:feature", created_at=AS_OF,
        source_cutoff_at=CUTOFF,
    )
    return evidence, snapshot


def inspect(evidence):
    return inspect_hkjc_feature_provenance(root=evidence, as_of=AS_OF)


def test_hash_linked_hkjc_input_field_and_cutoff_verify_feature_availability(tmp_path):
    report = inspect(fixture(tmp_path)[0])
    assert (report["input_artifacts"], report["feature_entries"],
            report["verified_feature_entries"]) == (1, 1, 1)
    assert report["feature_availability_verified"] is True
    assert report["verified_monitoring_samples"] is None
    assert report["model_promotion_allowed"] is False


def test_legacy_hkjc_source_key_is_inventory_only(tmp_path):
    report = inspect(fixture(tmp_path, "legacy")[0])
    assert report["legacy_feature_entries"] == 1
    assert report["records"][0]["blockers"] == ["legacy_feature_provenance"]
    assert report["feature_availability_verified"] is False


@pytest.mark.parametrize(
    ("mode", "blocker"),
    [("future", "feature_source_after_cutoff"),
     ("digest", "feature_source_digest_mismatch"),
     ("output", "feature_source_is_prediction_output")],
)
def test_invalid_hkjc_source_binding_is_blocked(tmp_path, mode, blocker):
    report = inspect(fixture(tmp_path, mode)[0])
    assert report["records"][0]["blockers"] == [blocker]
    assert report["verified_feature_entries"] == 0


def test_mutated_hkjc_logic_loses_bundle_authority(tmp_path):
    evidence, snapshot = fixture(tmp_path)
    (snapshot / "Race_1_Logic.json").write_text("{}\n", encoding="utf-8")
    report = inspect(evidence)
    assert report["records"][0]["blockers"] == ["prediction_bundle_unverified"]


def test_hkjc_verifier_rejects_forged_feature_authority(tmp_path):
    evidence = fixture(tmp_path, "legacy")[0]
    report = inspect(evidence)
    report["feature_availability_verified"] = True
    report["content_hash"] = _hash({key: value for key, value in report.items()
                                    if key != "content_hash"})
    with pytest.raises((ValueError, RuntimeError)):
        verify_hkjc_feature_provenance_report(report, root=evidence, as_of=AS_OF,
                                              relocation_roots=())


def test_no_hkjc_prediction_is_not_feature_ready(tmp_path):
    evidence = tmp_path / "evidence"
    EvidenceStore(evidence).append(EvidenceRecord(
        "wc:hkjc:model-release:feature", RecordKind.MODEL_RELEASE, Domain.HKJC,
        "2026-08-29T00:00:00+00:00",
        {"release_stage": "production", "code_commit": "a" * 40,
         "evaluation_contract_version": "hkjc-v2"},
    ))
    report = inspect(evidence)
    assert report["records_seen"] == 0
    assert report["feature_availability_verified"] is False
