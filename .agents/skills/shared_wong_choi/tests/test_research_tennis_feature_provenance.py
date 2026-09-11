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
from shared_wong_choi.research_index import _hash
from shared_wong_choi.research_tennis_feature_provenance import (
    inspect_tennis_feature_provenance,
    verify_tennis_feature_provenance_report,
)


EVENT = "2026-09-01"
CUTOFF = "2026-08-31T23:00:00+00:00"
AS_OF = datetime(2026, 9, 1, 1, tzinfo=timezone.utc)
COMPONENTS = (
    "surface_elo_edge", "overall_elo_edge", "serve_return_edge",
    "recent_form_edge", "opponent_rank_bucket_edge", "tournament_level_edge",
    "round_performance_edge", "big_match_edge", "pressure_edge",
    "head_to_head_edge", "fatigue_edge",
)
RAW_RESPONSES = {
    901: {"ratings": [1650, 1550], "tour": "ATP", "level": "ATP 250"},
    902: {"player_a_odds": 1.8, "player_b_odds": 2.1},
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def point(value, raw_id=901, *, future=False):
    provider = "sportsbet" if raw_id == 902 else "tennismylife"
    endpoint = "/odds" if raw_id == 902 else "/ratings"
    return {
        "value": value,
        "provenance": {
            "source_provider": provider,
            "source_endpoint": endpoint,
            "source_timestamp": "2026-09-01T00:00:00+00:00" if future else "2026-08-31T22:00:00+00:00",
            "calculated_at": "2026-08-31T22:30:00+00:00",
            "raw_response_id": raw_id,
            "warnings": [],
        },
    }


def projection(*, mode="valid"):
    snapshot = {
        "match_id": point(501),
        "feature_set_version": "stage3.v1",
        "player_a": {"id": point(11), "surface_elo": point(1650, future=mode == "future")},
        "player_b": {"id": point(22), "surface_elo": point(1550)},
        "match_context": {"tour": point("ATP"), "level": point("ATP 250")},
        "market": {
            "player_a_odds": point(1.8, 902),
            "player_b_odds": point(2.1, 902),
        },
        "entity_mapping_complete": True,
    }
    inputs = [
        {"path": ["player_a", "surface_elo"], "value_sha256": _hash(1650),
         "raw_response_ids": [901]},
        {"path": ["player_b", "surface_elo"], "value_sha256": _hash(1550),
         "raw_response_ids": [901]},
    ]
    components = [
        {"name": name, "active": name == "surface_elo_edge",
         "warnings": [] if name == "surface_elo_edge" else ["neutral_fixture"],
         "inputs": inputs if name == "surface_elo_edge" else []}
        for name in COMPONENTS
    ]
    if mode == "component":
        components.pop()
    if mode == "neutral":
        components[0].update(active=False, warnings=["neutral_fixture"], inputs=[])
    if mode == "value_digest":
        components[0]["inputs"][0]["value_sha256"] = "f" * 64
    if mode == "source":
        snapshot["player_a"]["surface_elo"]["provenance"]["source_provider"] = "wrong"
    raw_inputs = []
    for raw_id, response in RAW_RESPONSES.items():
        raw = {
            "raw_response_id": raw_id,
            "source_provider": "sportsbet" if raw_id == 902 else "tennismylife",
            "source_endpoint": "/odds" if raw_id == 902 else "/ratings",
            "fetched_at": "2026-08-31T22:00:00+00:00",
            "created_at": "2026-08-31T22:00:01+00:00",
            "artifact_name": "",
            "response_sha256": _hash(response),
        }
        if mode == "raw_digest" and raw_id == 901:
            raw["response_sha256"] = "f" * 64
        raw["artifact_name"] = (
            f"Tennis_Raw_Evidence_{EVENT}_{raw_id}_"
            f"{raw['response_sha256'][:12]}.json"
        )
        raw_inputs.append(raw)
    decision_inputs = {
        "tour": {"path": ["match_context", "tour"],
                 "value_sha256": _hash("ATP"), "raw_response_ids": [901]},
        "tournament_level": {"path": ["match_context", "level"],
                             "value_sha256": _hash("ATP 250"),
                             "raw_response_ids": [901]},
        "player_a_odds": {"path": ["market", "player_a_odds"],
                          "value_sha256": _hash(1.8), "raw_response_ids": [902]},
        "player_b_odds": {"path": ["market", "player_b_odds"],
                          "value_sha256": _hash(2.1), "raw_response_ids": [902]},
    }
    if mode == "decision_input":
        decision_inputs.pop("player_b_odds")
    prediction_id = 999 if mode == "wrong_id" else 101
    return {
        "schema_version": (
            "wong-choi-tennis-feature-evidence/v2"
            if mode == "legacy_schema"
            else "wong-choi-tennis-feature-evidence/v3"
        ),
        "event_id": EVENT,
        "generated_at": CUTOFF,
        "raw_inputs": raw_inputs,
        "rows": [{
            "prediction_id": prediction_id, "match_id": 501,
            "feature_set_version": "stage3.v1", "prediction_created_at": CUTOFF,
            "selection_player_id": 33 if mode == "participant" else 11,
            "model_probability": 0.62,
            "no_vig_market_probability": 0.54, "current_market_odds": 1.8,
            "edge": 0.08, "feature_snapshot": snapshot,
            "feature_snapshot_sha256": "f" * 64 if mode == "snapshot_digest" else _hash(snapshot),
            "components": components, "decision_inputs": decision_inputs,
            "raw_input_ids": [901, 902],
        }],
    }


def fixture(tmp_path, *, mode="valid", include_feature=True, include_raw=True,
            include_extra_raw=False, include_cohort=False, cohort_mode="valid"):
    evidence = tmp_path / "evidence"
    store = EvidenceStore(evidence)
    store.append(EvidenceRecord(
        "wc:tennis:model-release:feature", RecordKind.MODEL_RELEASE, Domain.TENNIS,
        "2026-08-01T00:00:00+00:00",
        {"release_stage": "shadow", "code_commit": "a" * 40,
         "evaluation_contract_version": "tennis-v1"},
    ))
    snapshot = tmp_path / "archive" / f"{EVENT} Tennis Analysis" / "_prediction_snapshots" / "feature"
    snapshot.mkdir(parents=True)
    report = snapshot / "Tennis_Daily_Report.txt"
    report.write_text("Tennis report\n", encoding="utf-8")
    files = [report]
    if include_feature:
        feature = snapshot / f"Tennis_Feature_Evidence_{EVENT}.json"
        feature_payload = projection(mode=mode)
        feature.write_text(json.dumps(feature_payload, sort_keys=True) + "\n", encoding="utf-8")
        files.append(feature)
        if include_raw:
            for raw in feature_payload["raw_inputs"]:
                raw_path = snapshot / raw["artifact_name"]
                raw_path.write_text(
                    json.dumps(RAW_RESPONSES[raw["raw_response_id"]], sort_keys=True)
                    + "\n",
                    encoding="utf-8",
                )
                files.append(raw_path)
        if include_extra_raw:
            extra_raw = snapshot / f"Tennis_Raw_Evidence_{EVENT}_902_deadbeefdead.json"
            extra_raw.write_text(json.dumps({"unused": True}, sort_keys=True) + "\n",
                                 encoding="utf-8")
            files.append(extra_raw)
    if include_cohort:
        cohort = snapshot / f"Tennis_Cohort_Evidence_{EVENT}.json"
        family = "match_winner_wta" if cohort_mode == "family" else "match_winner_atp"
        cohort.write_text(json.dumps({
            "schema_version": "wong-choi-tennis-cohort-evidence/v1",
            "event_id": EVENT,
            "generated_at": CUTOFF,
            "rows": [{
                "prediction_id": 101,
                "family": family,
                "tour": "ATP",
                "surface": "hard",
                "tournament_level": "grand_slam",
                "odds_bucket": "1.50-1.99",
            }],
        }, sort_keys=True) + "\n", encoding="utf-8")
        files.append(cohort)
    manifest = snapshot / "manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": "wong-choi-prediction-snapshot/v1", "append_only": True,
        "domain": "tennis", "event_id": EVENT, "created_at": CUTOFF,
        "files": [{"name": path.name, "bytes": path.stat().st_size, "sha256": digest(path)}
                  for path in files],
    }) + "\n", encoding="utf-8")
    record_prediction_decision(
        domain=Domain.TENNIS, event_id=EVENT, snapshot=snapshot, evidence_root=evidence,
        decision_state=DecisionState.SHADOW,
        recommendations=[{"id": 101, "decision": "BET", "final_decision": "BET", "edge": 0.08}],
        model_release_id="wc:tennis:model-release:feature", created_at=AS_OF,
        source_cutoff_at=CUTOFF,
    )
    return evidence, snapshot


def inspect(evidence):
    return inspect_tennis_feature_provenance(root=evidence, as_of=AS_OF)


def test_hash_pinned_snapshot_components_and_raw_inputs_verify_feature_availability(tmp_path):
    report = inspect(fixture(tmp_path)[0])
    assert (report["records_seen"], report["verified_predictions"],
            report["active_components"], report["raw_inputs"]) == (1, 1, 1, 2)
    assert report["feature_availability_verified"] is True
    assert report["verified_monitoring_samples"] is None
    assert report["model_promotion_allowed"] is False


@pytest.mark.parametrize(
    ("mode", "blocker"),
    [("wrong_id", "prediction_id_set_mismatch"),
     ("future", "feature_source_after_cutoff"),
     ("component", "component_contract_incomplete"),
     ("neutral", "component_contract_incomplete"),
     ("value_digest", "feature_value_digest_mismatch"),
     ("source", "feature_source_mismatch"),
     ("raw_digest", "raw_input_digest_mismatch"),
     ("decision_input", "decision_input_invalid"),
     ("legacy_schema", "feature_artifact_invalid"),
     ("participant", "feature_snapshot_invalid"),
     ("snapshot_digest", "feature_snapshot_digest_mismatch")],
)
def test_incomplete_or_non_pit_feature_projection_is_blocked(tmp_path, mode, blocker):
    report = inspect(fixture(tmp_path, mode=mode)[0])
    assert blocker in report["records"][0]["blockers"]
    assert report["verified_predictions"] == 0


def test_missing_feature_projection_is_not_inferred_from_mutable_database(tmp_path):
    report = inspect(fixture(tmp_path, include_feature=False)[0])
    assert report["records"][0]["blockers"] == ["feature_artifact_missing"]
    assert report["feature_availability_verified"] is False


def test_missing_referenced_raw_artifact_fails_closed(tmp_path):
    report = inspect(fixture(tmp_path, include_raw=False)[0])
    assert "raw_input_missing" in report["records"][0]["blockers"]
    assert report["verified_predictions"] == 0


def test_unreferenced_raw_artifact_fails_closed(tmp_path):
    report = inspect(fixture(tmp_path, include_extra_raw=True)[0])
    assert "raw_input_invalid" in report["records"][0]["blockers"]
    assert report["verified_predictions"] == 0


def test_mutated_feature_projection_fails_closed(tmp_path):
    evidence, snapshot = fixture(tmp_path)
    (snapshot / f"Tennis_Feature_Evidence_{EVENT}.json").write_text("{}\n", encoding="utf-8")
    report = inspect(evidence)
    assert report["records"][0]["blockers"] == ["prediction_bundle_unverified"]
    assert report["feature_availability_verified"] is False


def test_verifier_rejects_forged_sample_authority(tmp_path):
    evidence = fixture(tmp_path)[0]
    report = inspect(evidence)
    report["verified_monitoring_samples"] = 1
    report["content_hash"] = _hash({key: value for key, value in report.items()
                                    if key != "content_hash"})
    with pytest.raises((ValueError, RuntimeError)):
        verify_tennis_feature_provenance_report(report, root=evidence, as_of=AS_OF,
                                                relocation_roots=())


def test_no_prediction_is_not_feature_ready(tmp_path):
    evidence = tmp_path / "evidence"
    EvidenceStore(evidence).append(EvidenceRecord(
        "wc:tennis:model-release:feature", RecordKind.MODEL_RELEASE, Domain.TENNIS,
        "2026-08-01T00:00:00+00:00",
        {"release_stage": "shadow", "code_commit": "a" * 40,
         "evaluation_contract_version": "tennis-v1"},
    ))
    report = inspect(evidence)
    assert report["records_seen"] == 0
    assert report["feature_availability_verified"] is False
