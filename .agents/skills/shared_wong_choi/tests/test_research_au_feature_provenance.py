import hashlib
import json
from datetime import datetime, timezone

import pytest

from shared_wong_choi.contracts import Domain
from shared_wong_choi.domain_evidence import record_prediction_decision
from shared_wong_choi.evidence import DecisionState, EvidenceRecord, EvidenceStore, RecordKind
from shared_wong_choi.research_au_feature_provenance import (
    inspect_au_feature_provenance,
    verify_au_feature_provenance_report,
)
from shared_wong_choi.research_index import _hash


CUTOFF = "2026-08-31T00:00:00+00:00"
AS_OF = datetime(2026, 8, 31, 1, tzinfo=timezone.utc)
EVENT = "2026-08-31 Feature Track Race 1-1"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture(tmp_path, mode="valid"):
    evidence = tmp_path / "evidence"
    store = EvidenceStore(evidence)
    store.append(EvidenceRecord(
        "wc:au:model-release:feature", RecordKind.MODEL_RELEASE, Domain.AU,
        "2026-08-29T00:00:00+00:00",
        {"release_stage": "shadow", "code_commit": "a" * 40,
         "evaluation_contract_version": "au-v2"},
    ))
    snapshot = tmp_path / "hot" / EVENT / "_prediction_snapshots" / "feature"
    snapshot.mkdir(parents=True)
    source = snapshot / "Race_1_Facts.md"
    source.write_text("# Pre-race facts\nrecent_form: 123\n", encoding="utf-8")
    scoring = snapshot / "Meeting_Auto_Scoring.csv"
    scoring.write_text("race_number,rank,horse_number,horse_name,grade\n1,1,7,Fast Horse,B+\n")
    source_ref = {
        "artifact": source.name,
        "sha256": digest(source),
        "available_at": CUTOFF,
        "field": "horses.7.recent_form",
    }
    projection_mode = mode.startswith("projection")
    if mode == "legacy" or projection_mode:
        provenance = "recent_form+class_weighted"
    else:
        if mode == "future":
            source_ref["available_at"] = "2026-08-31T00:00:01+00:00"
        elif mode == "digest":
            source_ref["sha256"] = "f" * 64
        elif mode == "output":
            source_ref.update(artifact=scoring.name, sha256=digest(scoring),
                              field="scoring.rank")
        provenance = {"derivation": "recent_form+class_weighted", "sources": [source_ref]}
    logic = snapshot / "Race_1_Logic.json"
    logic.write_text(json.dumps({
        "race_analysis": {"race_number": 1},
        "horses": {"7": {"horse_name": "Fast Horse", "python_auto": {
            "score_provenance": {"form_score": provenance},
        }}},
    }) + "\n")
    paths = [source, scoring, logic]
    if projection_mode:
        odds = snapshot / "odds_history.json"
        odds.write_text('{"1":{"2026-08-30T10:00:00+00:00|analysis":{"7":["4.0","1.8"]}}}\n')
        projection = snapshot / "AU_Research_Feature_Provenance.json"
        market_digest = digest(odds)
        market_time = "2026-08-30T10:00:00+00:00"
        if mode == "projection_bad_market_digest":
            market_digest = "f" * 64
        elif mode == "projection_future_market":
            market_time = "2026-08-31T00:00:01+00:00"
        projection.write_text(json.dumps({
            "schema_version": "wong-choi-au-research-feature-provenance/v1",
            "domain": "au",
            "event_id": EVENT,
            "captured_at": CUTOFF,
            "append_only": True,
            "logic_files": [{
                "name": logic.name,
                "sha256": digest(logic),
                "horses": {"7": {"form_score": {
                    "derivation": "recent_form+class_weighted",
                    "sources": [source_ref],
                }}},
            }],
            "market": {
                "status": "complete",
                "artifact": odds.name,
                "sha256": market_digest,
                "earliest_analysis": {"1": {
                    "snapshot_key": "2026-08-30T10:00:00+00:00|analysis",
                    "captured_at": market_time,
                    "prices": {"7": ["4.0", "1.8"]},
                }},
            },
            "model_promotion_allowed": False,
        }, sort_keys=True) + "\n", encoding="utf-8")
        paths.extend((odds, projection))
    files = [{"name": path.name, "bytes": path.stat().st_size, "sha256": digest(path)}
             for path in paths]
    manifest = snapshot / "manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": "wong-choi-prediction-snapshot/v1",
        "append_only": True,
        "created_at": CUTOFF,
        "domain": "au",
        "event_id": EVENT,
        "files": files,
        "recommendations": [],
        "signature": "b" * 64,
    }) + "\n")
    record_prediction_decision(
        domain=Domain.AU, event_id=EVENT, snapshot=snapshot, evidence_root=evidence,
        decision_state=DecisionState.SHADOW,
        model_release_id="wc:au:model-release:feature", created_at=AS_OF,
        source_cutoff_at=CUTOFF,
    )
    return evidence


def inspect(evidence):
    return inspect_au_feature_provenance(root=evidence, as_of=AS_OF)


def test_hash_linked_input_field_and_cutoff_make_feature_availability_verifiable(tmp_path):
    report = inspect(fixture(tmp_path))
    assert (report["input_artifacts"], report["feature_entries"],
            report["verified_feature_entries"]) == (1, 1, 1)
    assert report["feature_availability_verified"] is True
    assert report["verified_monitoring_samples"] is None
    assert report["model_promotion_allowed"] is False


def test_legacy_string_provenance_is_inventory_only(tmp_path):
    report = inspect(fixture(tmp_path, "legacy"))
    assert report["legacy_feature_entries"] == 1
    assert report["verified_feature_entries"] == 0
    assert report["records"][0]["blockers"] == ["legacy_feature_provenance"]
    assert report["feature_availability_verified"] is False


def test_hash_bound_producer_projection_can_upgrade_legacy_logic_without_mutating_it(tmp_path):
    report = inspect(fixture(tmp_path, "projection"))
    assert report["structured_feature_entries"] == 1
    assert report["legacy_feature_entries"] == 0
    assert report["verified_feature_entries"] == 1
    assert report["feature_availability_verified"] is True


@pytest.mark.parametrize("mode", ["projection_bad_market_digest", "projection_future_market"])
def test_producer_projection_market_binding_is_reverified(tmp_path, mode):
    with pytest.raises(ValueError):
        inspect(fixture(tmp_path, mode))


@pytest.mark.parametrize(
    ("mode", "blocker"),
    [("future", "feature_source_after_cutoff"),
     ("digest", "feature_source_digest_mismatch"),
     ("output", "feature_source_is_prediction_output")],
)
def test_invalid_source_binding_is_blocked(tmp_path, mode, blocker):
    report = inspect(fixture(tmp_path, mode))
    assert report["records"][0]["blockers"] == [blocker]
    assert report["verified_feature_entries"] == 0


def test_verifier_rejects_forged_feature_authority(tmp_path):
    evidence = fixture(tmp_path, "legacy")
    report = inspect(evidence)
    report["feature_availability_verified"] = True
    report["content_hash"] = _hash({key: value for key, value in report.items() if key != "content_hash"})
    with pytest.raises((ValueError, RuntimeError)):
        verify_au_feature_provenance_report(report, root=evidence, as_of=AS_OF,
                                            relocation_roots=())


def test_no_prediction_is_not_feature_ready(tmp_path):
    evidence = tmp_path / "evidence"
    store = EvidenceStore(evidence)
    store.append(EvidenceRecord(
        "wc:au:model-release:feature", RecordKind.MODEL_RELEASE, Domain.AU,
        "2026-08-29T00:00:00+00:00",
        {"release_stage": "shadow", "code_commit": "a" * 40,
         "evaluation_contract_version": "au-v2"},
    ))
    report = inspect(evidence)
    assert report["records_seen"] == 0
    assert report["feature_availability_verified"] is False
    assert report["verified_monitoring_samples"] is None
