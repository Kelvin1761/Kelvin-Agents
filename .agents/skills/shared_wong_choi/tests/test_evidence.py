from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT.parent))

from shared_wong_choi.contracts import Domain
from shared_wong_choi.evidence import (
    ArtifactRef,
    EvidenceConflictError,
    EvidenceRecord,
    EvidenceStore,
    MissingEvidenceParentError,
    RecordKind,
)


NOW = "2026-08-26T12:00:00+00:00"
SHA = "a" * 64


def record(
    record_id: str,
    kind: RecordKind,
    *,
    links: dict[str, str] | None = None,
    body: dict | None = None,
) -> EvidenceRecord:
    defaults = {
        RecordKind.MODEL_RELEASE: {
            "release_stage": "production",
            "code_commit": "abcdef1",
            "evaluation_contract_version": "v1",
        },
        RecordKind.PREDICTION: {
            "event_id": "wc:au:event:2026-08-26:sportsbet:event-1",
            "source_cutoff_at": NOW,
            "recommendations": [],
        },
        RecordKind.DECISION: {"decision_state": "no_bet"},
        RecordKind.SETTLEMENT: {
            "settlement_state": "void",
            "settled_at": NOW,
        },
    }
    return EvidenceRecord(
        record_id=record_id,
        kind=kind,
        domain=Domain.AU,
        created_at=NOW,
        links=links or {},
        artifacts=(ArtifactRef("Race_1.json", SHA, NOW, "sportsbet"),),
        body=body or defaults[kind],
    )


def test_complete_evidence_chain_is_append_only_and_auditable(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path)
    release_id = "wc:au:model-release:v1"
    prediction_id = "wc:au:prediction:event-1:v1"
    decision_id = "wc:au:decision:event-1:v1"
    settlement_id = "wc:au:settlement:event-1:v1"

    assert store.append(record(release_id, RecordKind.MODEL_RELEASE)).status == "created"
    assert store.append(
        record(
            prediction_id,
            RecordKind.PREDICTION,
            links={"model_release_id": release_id},
        )
    ).status == "created"
    assert store.append(
        record(
            decision_id,
            RecordKind.DECISION,
            links={"prediction_id": prediction_id},
        )
    ).status == "created"
    assert store.append(
        record(
            settlement_id,
            RecordKind.SETTLEMENT,
            links={"decision_id": decision_id},
        )
    ).status == "created"

    assert store.append(record(release_id, RecordKind.MODEL_RELEASE)).status == "duplicate"
    audit = store.audit()
    assert audit["status"] == "ok"
    assert audit["counts"] == {
        "model_release": 1,
        "prediction": 1,
        "decision": 1,
        "settlement": 1,
    }


def test_conflicting_record_id_fails_closed(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path)
    record_id = "wc:au:model-release:v1"
    store.append(record(record_id, RecordKind.MODEL_RELEASE))
    with pytest.raises(EvidenceConflictError):
        store.append(
            record(
                record_id,
                RecordKind.MODEL_RELEASE,
                body={
                    "release_stage": "retired",
                    "code_commit": "abcdef1",
                    "evaluation_contract_version": "v1",
                },
            )
        )


def test_missing_parent_is_rejected(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path)
    with pytest.raises(MissingEvidenceParentError):
        store.append(
            record(
                "wc:au:prediction:event-1:v1",
                RecordKind.PREDICTION,
                links={"model_release_id": "wc:au:model-release:missing"},
            )
        )


def test_future_artifact_and_tampering_are_rejected(tmp_path: Path) -> None:
    future = EvidenceRecord(
        record_id="wc:au:model-release:v1",
        kind=RecordKind.MODEL_RELEASE,
        domain=Domain.AU,
        created_at=NOW,
        artifacts=(
            ArtifactRef(
                "future.json", SHA, "2026-08-26T12:00:01+00:00", "sportsbet"
            ),
        ),
        body={},
    )
    with pytest.raises(ValueError):
        future.to_dict()

    store = EvidenceStore(tmp_path)
    saved = store.append(record("wc:au:model-release:v1", RecordKind.MODEL_RELEASE))
    payload = json.loads(saved.path.read_text(encoding="utf-8"))
    payload["body"]["status"] = "tampered"
    saved.path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(EvidenceConflictError):
        store.load("wc:au:model-release:v1")
