from __future__ import annotations

import json
import sys
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT.parent))

from shared_wong_choi.contracts import Domain  # noqa: E402
from shared_wong_choi.domain_evidence import (  # noqa: E402
    record_prediction_decision,
    record_settlement_for_event,
)
from shared_wong_choi.evidence import DecisionState, EvidenceStore, ReleaseStage  # noqa: E402
from shared_wong_choi.model_registry import (  # noqa: E402
    ModelRegistry,
    ModelReleaseRequest,
)


def register_model(root: Path, domain: Domain) -> str:
    result = ModelRegistry(root).register(
        ModelReleaseRequest(
            domain=domain,
            model_id=f"{domain.value}-model",
            code_commit="a" * 40,
            evaluation_contract_version="v2",
            target_stage=ReleaseStage.RESEARCH,
            evaluation_verdict="BASELINE_MIGRATION",
            created_at="2026-08-26T09:00:00+00:00",
        )
    )
    return result["record_id"]


def test_scoring_snapshot_creates_prediction_and_decision_chain(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    model = register_model(evidence, Domain.AU)
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "manifest.json").write_text(
        json.dumps({"created_at": "2026-08-26T10:00:00+00:00"}),
        encoding="utf-8",
    )
    (snapshot / "Meeting_Auto_Scoring.csv").write_text(
        "race_number,rank,horse_number,horse_name,grade\n"
        "1,1,4,Fast Horse,A\n1,2,8,Other Horse,B\n",
        encoding="utf-8",
    )
    first = record_prediction_decision(
        domain=Domain.AU,
        event_id="2026-08-26|Randwick",
        snapshot=snapshot,
        evidence_root=evidence,
        decision_state=DecisionState.RECOMMEND,
        model_release_id=model,
    )
    second = record_prediction_decision(
        domain=Domain.AU,
        event_id="2026-08-26|Randwick",
        snapshot=snapshot,
        evidence_root=evidence,
        decision_state=DecisionState.RECOMMEND,
        model_release_id=model,
    )
    assert first["status"] == "created"
    assert first["recommendation_count"] == 2
    assert second["status"] == "duplicate"
    assert EvidenceStore(evidence).audit()["counts"] == {
        "model_release": 1,
        "prediction": 1,
        "decision": 1,
        "settlement": 0,
    }


def test_nba_snapshot_can_be_recorded_as_shadow(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    model = register_model(evidence, Domain.NBA)
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "manifest.json").write_text(
        json.dumps(
            {
                "created_at": "2026-08-26T10:00:00+00:00",
                "game_tags": ["BOS_LAL"],
            }
        ),
        encoding="utf-8",
    )
    result = record_prediction_decision(
        domain=Domain.NBA,
        event_id="2026-08-26",
        snapshot=snapshot,
        evidence_root=evidence,
        decision_state=DecisionState.SHADOW,
        model_release_id=model,
    )
    assert result["recommendation_count"] == 1


def test_event_settlement_links_decision_and_retries_idempotently(
    tmp_path: Path,
) -> None:
    evidence = tmp_path / "evidence"
    model = register_model(evidence, Domain.TENNIS)
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "manifest.json").write_text(
        json.dumps({"created_at": "2026-08-26T10:00:00+00:00"}),
        encoding="utf-8",
    )
    prediction = record_prediction_decision(
        domain=Domain.TENNIS,
        event_id="2026-08-27",
        snapshot=snapshot,
        evidence_root=evidence,
        decision_state=DecisionState.RECOMMEND,
        model_release_id=model,
    )
    report = tmp_path / "settlement.json"
    report.write_text('{"settled": 4}\n', encoding="utf-8")

    first = record_settlement_for_event(
        domain=Domain.TENNIS,
        event_id="2026-08-27",
        evidence_root=evidence,
        summary={"settled": 4},
        artifacts=[report],
    )
    second = record_settlement_for_event(
        domain=Domain.TENNIS,
        event_id="2026-08-27",
        evidence_root=evidence,
        summary={"settled": 4},
        artifacts=[report],
    )

    assert first["status"] == "created"
    assert second["status"] == "duplicate"
    assert first["decision_id"] == prediction["decision_id"]
    payload = EvidenceStore(evidence).load(first["settlement_id"])
    assert payload["body"]["settlement_state"] == "settled"
    assert payload["links"]["decision_id"] == prediction["decision_id"]
