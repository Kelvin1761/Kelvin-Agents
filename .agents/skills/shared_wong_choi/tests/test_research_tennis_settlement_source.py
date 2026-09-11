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
from shared_wong_choi.research_index import _hash
from shared_wong_choi.research_tennis_settlement_source import (
    inspect_tennis_settlement_candidates,
    verify_tennis_settlement_candidate_report,
)


EVENT = "2026-09-01"
NOW = datetime(2026, 8, 31, 23, tzinfo=timezone.utc)
END = NOW + timedelta(days=2)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prediction_fixture(tmp_path):
    evidence = tmp_path / "evidence"
    store = EvidenceStore(evidence)
    store.append(EvidenceRecord(
        "wc:tennis:model-release:test", RecordKind.MODEL_RELEASE, Domain.TENNIS,
        "2026-08-01T00:00:00+00:00",
        {"release_stage": "shadow", "code_commit": "a" * 40,
         "evaluation_contract_version": "tennis-v1"},
    ))
    day = tmp_path / "archive" / f"{EVENT} Tennis Analysis"
    snapshot = day / "_prediction_snapshots" / "20260831T230000Z-test"
    snapshot.mkdir(parents=True)
    report = snapshot / "Tennis_Daily_Report.txt"
    report.write_text("Tennis report\n", encoding="utf-8")
    manifest = snapshot / "manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": "wong-choi-prediction-snapshot/v1", "append_only": True,
        "domain": "tennis", "event_id": EVENT,
        "created_at": "2026-08-31T23:00:00+00:00",
        "files": [{"name": report.name, "bytes": report.stat().st_size,
                   "sha256": digest(report)}],
    }) + "\n", encoding="utf-8")
    record_prediction_decision(
        domain=Domain.TENNIS, event_id=EVENT, snapshot=snapshot, evidence_root=evidence,
        decision_state=DecisionState.SHADOW,
        recommendations=[{"id": 101, "decision": "BET", "final_decision": "BET",
                          "edge": 0.08}],
        model_release_id="wc:tennis:model-release:test", created_at=NOW,
        source_cutoff_at="2026-08-31T23:00:00+00:00",
    )
    return evidence, day, snapshot


def outcome_file(day, *, fault=None):
    raw_response_json = json.dumps(
        {"winner_name": "Player B" if fault == "raw_winner" else "Player A",
         "loser_name": "Player A" if fault == "raw_winner" else "Player B"},
        sort_keys=True,
        separators=(",", ":"),
    )
    raw_sha256 = hashlib.sha256(raw_response_json.encode("utf-8")).hexdigest()
    raw_name = f"Tennis_Settlement_Raw_{EVENT}_901_{raw_sha256[:12]}.json"
    raw_path = day / raw_name
    raw_path.write_text(json.dumps({
        "schema_version": "wong-choi-tennis-settlement-raw-result/v1",
        "event_id": EVENT,
        "raw_response_id": 901,
        "source_provider": "tennismylife",
        "fetched_at": "2026-09-01T17:59:00+00:00",
        "created_at": "2026-09-01T17:59:01+00:00",
        "response_sha256": raw_sha256,
        "response_json": raw_response_json,
    }, sort_keys=True) + "\n", encoding="utf-8")
    row = {
        "prediction_id": 101, "match_id": 501, "match_date": EVENT,
        "prediction_created_at": "2026-08-31T22:55:00+00:00",
        "player_a_id": 11, "player_b_id": 22,
        "player_a_name": "Player A", "player_b_name": "Player B",
        "selection_player_id": 11, "model_probability": 0.62,
        "no_vig_market_probability": 0.54, "winner_player_id": 11,
        "result_source_provider": "tennismylife", "result_raw_response_id": 901,
        "result_raw_artifact": raw_name,
        "result_raw_response_sha256": raw_sha256,
        "result_raw_fetched_at": "2026-09-01T17:59:00+00:00",
        "result_raw_created_at": "2026-09-01T17:59:01+00:00",
        "result_created_at": "2026-09-01T18:00:00+00:00",
    }
    if fault == "future_prediction":
        row["prediction_created_at"] = "2026-09-01T01:00:00+00:00"
    elif fault == "wrong_id":
        row["prediction_id"] = 999
    elif fault == "winner":
        row["winner_player_id"] = 0
    path = day / f"Tennis_Settlement_Evidence_{EVENT}.json"
    path.write_text(json.dumps({
        "schema_version": (
            "wong-choi-tennis-settlement-evidence/v1"
            if fault == "legacy_schema"
            else "wong-choi-tennis-settlement-evidence/v2"
        ),
        "event_id": EVENT, "generated_at": "2026-09-02T00:00:00+00:00",
        "rows": [row],
    }) + "\n", encoding="utf-8")
    return path, raw_path


def settled_fixture(tmp_path, *, evidence_outcome=True, evidence_raw=True, fault=None):
    evidence, day, snapshot = prediction_fixture(tmp_path)
    outcome, raw_result = outcome_file(day, fault=fault)
    artifacts = []
    if evidence_outcome:
        artifacts.append(outcome)
    if evidence_raw:
        artifacts.append(raw_result)
    record_settlement_for_event(
        domain=Domain.TENNIS, event_id=EVENT, evidence_root=evidence,
        summary={"settled": 1, "pending_without_result": 0},
        artifacts=artifacts,
        settled_at=datetime(2026, 9, 2, tzinfo=timezone.utc), required=True,
    )
    return evidence, day, snapshot, outcome


def inspect(evidence):
    return inspect_tennis_settlement_candidates(root=evidence, as_of=END)


def test_hash_pinned_complete_projection_proves_labels_only(tmp_path):
    report = inspect(settled_fixture(tmp_path)[0])
    assert (report["settlements_seen"], report["label_verified_settlements"],
            report["verified_outcomes"]) == (1, 1, 1)
    assert report["candidates"][0]["blockers"] == ["feature_availability_unverified"]
    assert report["verified_monitoring_samples"] is None
    assert report["model_promotion_allowed"] is False


def test_id_only_outcome_without_hash_pinned_raw_result_is_blocked(tmp_path):
    report = inspect(settled_fixture(tmp_path, evidence_raw=False)[0])
    assert report["label_verified_settlements"] == 0
    assert "outcome_artifact_incomplete" in report["candidates"][0]["blockers"]


def test_hash_pinned_raw_result_with_opposite_winner_is_blocked(tmp_path):
    report = inspect(settled_fixture(tmp_path, fault="raw_winner")[0])
    assert report["label_verified_settlements"] == 0
    assert "outcome_artifact_incomplete" in report["candidates"][0]["blockers"]


def test_adjacent_projection_not_in_settlement_is_not_evidence(tmp_path):
    report = inspect(settled_fixture(tmp_path, evidence_outcome=False)[0])
    assert report["candidates"][0]["blockers"] == [
        "outcome_artifact_not_evidenced", "feature_availability_unverified",
    ]
    assert report["label_verified_settlements"] == 0


@pytest.mark.parametrize(
    "fault", ["future_prediction", "wrong_id", "winner", "legacy_schema"]
)
def test_incomplete_or_non_pit_projection_is_blocked(tmp_path, fault):
    report = inspect(settled_fixture(tmp_path, fault=fault)[0])
    assert "outcome_artifact_incomplete" in report["candidates"][0]["blockers"]


def test_mutated_projection_fails_closed(tmp_path):
    evidence, _day, _snapshot, outcome = settled_fixture(tmp_path)
    outcome.write_text("{}\n", encoding="utf-8")
    with pytest.raises((ValueError, RuntimeError)):
        inspect(evidence)


def test_missing_prediction_bundle_blocks_labels(tmp_path):
    evidence, _day, snapshot, _outcome = settled_fixture(tmp_path)
    (snapshot / "Tennis_Daily_Report.txt").unlink()
    report = inspect(evidence)
    assert report["candidates"][0]["blockers"] == [
        "prediction_bundle_unverified", "feature_availability_unverified",
    ]


def test_verifier_rejects_forged_sample_authority(tmp_path):
    evidence = settled_fixture(tmp_path)[0]
    report = inspect(evidence)
    report["verified_monitoring_samples"] = 1
    report["content_hash"] = _hash({key: value for key, value in report.items()
                                    if key != "content_hash"})
    with pytest.raises((ValueError, RuntimeError)):
        verify_tennis_settlement_candidate_report(report, root=evidence, as_of=END,
                                                  relocation_roots=())


def test_no_settlement_is_not_source_complete(tmp_path):
    evidence, _day, _snapshot = prediction_fixture(tmp_path)
    report = inspect(evidence)
    assert report["settlements_seen"] == 0
    assert report["verified_monitoring_samples"] is None
