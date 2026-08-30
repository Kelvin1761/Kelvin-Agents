from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT.parent))

from shared_wong_choi.contracts import Domain
from shared_wong_choi.research_registry import (
    DatasetManifest,
    DatasetSplit,
    ExperimentDecision,
    ExperimentDecisionState,
    ExperimentRegistry,
    ExperimentRun,
    ExperimentRunState,
    ExperimentSpec,
    MissingResearchParentError,
    ResearchConflictError,
    SourceWatermark,
)


SPEC_ID = "wc:au:experiment-spec:pace-v1"
DATASET_ID = "wc:au:dataset-manifest:pace-v1"
RUN_ID = "wc:au:experiment-run:pace-v1"
DECISION_ID = "wc:au:experiment-decision:pace-v1"
CREATED = "2026-08-30T00:00:00+00:00"
CUTOFF = "2026-08-29T23:59:00+00:00"
STARTED = "2026-08-30T00:01:00+00:00"
COMPLETED = "2026-08-30T00:02:00+00:00"
DECIDED = "2026-08-30T00:03:00+00:00"
BASELINE = "a" * 40
CANDIDATE = "b" * 40
RULER_DIGEST = "1" * 64
PROTOCOL_DIGEST = "2" * 64
SAMPLE_HASH = "3" * 64
DATASET_DIGEST = "4" * 64
METRICS_DIGEST = "5" * 64
RUN_DIGEST = "6" * 64
STDOUT_DIGEST = "7" * 64
DECISION_DIGEST = "8" * 64


def spec(*, domain: Domain = Domain.AU) -> ExperimentSpec:
    prefix = f"wc:{domain.value}"
    ruler_ids = {
        Domain.AU: "au-v2",
        Domain.HKJC: "hkjc-v2",
        Domain.TENNIS: "tennis-v1",
        Domain.NBA: "nba-v1",
    }
    return ExperimentSpec(
        record_id=SPEC_ID if domain is Domain.AU else f"{prefix}:experiment-spec:pace-v1",
        domain=domain,
        created_at=CREATED,
        hypothesis="pace feature improves top-five ranking without hurting Gold",
        evaluation_ruler_id=ruler_ids[domain],
        evaluation_ruler_digest=RULER_DIGEST,
        baseline_commit=BASELINE,
        candidate_commit=CANDIDATE,
        preregistered_metrics=("gold", "ndcg_at_5"),
        seed=7,
        commands=("python3 evaluate.py --platform au",),
        protocol_artifact_digest=PROTOCOL_DIGEST,
    )


def dataset(*, spec_id: str = SPEC_ID, domain: Domain = Domain.AU) -> DatasetManifest:
    prefix = f"wc:{domain.value}"
    return DatasetManifest(
        record_id=(
            DATASET_ID
            if domain is Domain.AU
            else f"{prefix}:dataset-manifest:pace-v1"
        ),
        domain=domain,
        created_at=CREATED,
        spec_id=spec_id,
        point_in_time_cutoff=CUTOFF,
        sample_hash=SAMPLE_HASH,
        row_count=100,
        source_watermarks=(
            SourceWatermark("racenet", CUTOFF, "9" * 64),
        ),
        splits=(
            DatasetSplit("train", 60, "a" * 64),
            DatasetSplit("dev", 20, "b" * 64),
            DatasetSplit("terminal", 20, "c" * 64),
        ),
        artifact_digest=DATASET_DIGEST,
    )


def run(
    *,
    spec_id: str = SPEC_ID,
    dataset_id: str = DATASET_ID,
    domain: Domain = Domain.AU,
    state: ExperimentRunState = ExperimentRunState.SUCCEEDED,
) -> ExperimentRun:
    prefix = f"wc:{domain.value}"
    return ExperimentRun(
        record_id=RUN_ID if domain is Domain.AU else f"{prefix}:experiment-run:pace-v1",
        domain=domain,
        created_at=COMPLETED,
        spec_id=spec_id,
        dataset_manifest_id=dataset_id,
        started_at=STARTED,
        completed_at=COMPLETED,
        state=state,
        evaluation_ruler_id="au-v2" if domain is Domain.AU else "hkjc-v2",
        evaluation_ruler_digest=RULER_DIGEST,
        baseline_commit=BASELINE,
        candidate_commit=CANDIDATE,
        seed=7,
        commands=("python3 evaluate.py --platform au",),
        metrics_digest=METRICS_DIGEST,
        artifact_digest=RUN_DIGEST,
        stdout_digest=STDOUT_DIGEST,
    )


def decision(
    *,
    run_id: str = RUN_ID,
    state: ExperimentDecisionState = ExperimentDecisionState.INCONCLUSIVE,
) -> ExperimentDecision:
    return ExperimentDecision(
        record_id=DECISION_ID,
        domain=Domain.AU,
        created_at=DECIDED,
        run_id=run_id,
        decided_at=DECIDED,
        state=state,
        rationale="confidence interval crosses the frozen no-change boundary",
        metrics_digest=METRICS_DIGEST,
        artifact_digest=DECISION_DIGEST,
    )


def append_chain(store: ExperimentRegistry) -> None:
    store.append(spec())
    store.append(dataset())
    store.append(run())
    store.append(decision())


def test_complete_chain_is_append_only_idempotent_and_auditable(tmp_path: Path) -> None:
    store = ExperimentRegistry(tmp_path)
    records = (spec(), dataset(), run(), decision())

    assert [store.append(item).status for item in records] == ["created"] * 4
    assert [store.append(item).status for item in records] == ["duplicate"] * 4

    audit = store.audit()
    assert audit["status"] == "ok"
    assert audit["counts"] == {
        "experiment_spec": 1,
        "dataset_manifest": 1,
        "experiment_run": 1,
        "experiment_decision": 1,
    }


@pytest.mark.parametrize("domain", tuple(Domain))
def test_experiment_spec_contract_is_shared_by_all_four_domains(
    tmp_path: Path, domain: Domain
) -> None:
    store = ExperimentRegistry(tmp_path)

    saved = store.append(spec(domain=domain))

    assert saved.status == "created"
    assert store.load(spec(domain=domain).record_id)["domain"] == domain.value


def test_parent_spec_lineage_is_typed_and_append_only(tmp_path: Path) -> None:
    store = ExperimentRegistry(tmp_path)
    parent = spec()
    child = replace(
        spec(),
        record_id="wc:au:experiment-spec:pace-v2",
        parent_spec_id=parent.record_id,
        candidate_commit="d" * 40,
    )
    store.append(parent)

    assert store.append(child).status == "created"
    assert store.load(child.record_id)["links"] == {"parent_spec_id": parent.record_id}


def test_same_id_with_different_content_fails_closed(tmp_path: Path) -> None:
    store = ExperimentRegistry(tmp_path)
    store.append(spec())

    with pytest.raises(ResearchConflictError, match="immutable research conflict"):
        store.append(replace(spec(), seed=8))


def test_missing_wrong_kind_and_cross_domain_parents_are_rejected(tmp_path: Path) -> None:
    store = ExperimentRegistry(tmp_path)
    with pytest.raises(MissingResearchParentError, match="missing parent"):
        store.append(dataset())

    store.append(spec())
    store.append(dataset())
    with pytest.raises(MissingResearchParentError, match="requires experiment_run"):
        store.append(decision(run_id=DATASET_ID))

    hkjc_spec = spec(domain=Domain.HKJC)
    store.append(hkjc_spec)
    with pytest.raises(MissingResearchParentError, match="cross-domain"):
        store.append(dataset(spec_id=hkjc_spec.record_id))


def test_run_must_match_its_frozen_spec_and_dataset_lineage(tmp_path: Path) -> None:
    store = ExperimentRegistry(tmp_path)
    store.append(spec())
    store.append(dataset())

    with pytest.raises(ResearchConflictError, match="candidate_commit"):
        store.append(replace(run(), candidate_commit="d" * 40))

    with pytest.raises(ResearchConflictError, match="seed"):
        store.append(replace(run(), seed=8))


def test_decision_must_match_run_metrics_and_follow_completion(tmp_path: Path) -> None:
    store = ExperimentRegistry(tmp_path)
    store.append(spec())
    store.append(dataset())
    store.append(run())

    with pytest.raises(ResearchConflictError, match="metrics_digest"):
        store.append(replace(decision(), metrics_digest="d" * 64))

    with pytest.raises(ValueError, match="decided_at cannot precede"):
        store.append(replace(decision(), decided_at=STARTED))


@pytest.mark.parametrize(
    ("candidate", "message"),
    [
        (replace(spec(), baseline_commit="not-a-sha"), "baseline_commit"),
        (replace(spec(), created_at="2026-08-30T00:00:00"), "timezone"),
        (replace(spec(), preregistered_metrics=("gold", "gold")), "unique"),
        (replace(dataset(), row_count=101), "split row counts"),
        (
            replace(
                dataset(),
                source_watermarks=(
                    SourceWatermark(
                        "racenet", "2026-08-30T00:00:01+00:00", "9" * 64
                    ),
                ),
            ),
            "availability after point-in-time cutoff",
        ),
    ],
)
def test_schema_validation_rejects_unreproducible_records(
    tmp_path: Path, candidate: object, message: str
) -> None:
    store = ExperimentRegistry(tmp_path)
    if not isinstance(candidate, ExperimentSpec):
        store.append(spec())
    with pytest.raises(ValueError, match=message):
        store.append(candidate)


def test_failed_and_inconclusive_records_cannot_be_rewritten(tmp_path: Path) -> None:
    store = ExperimentRegistry(tmp_path)
    store.append(spec())
    store.append(dataset())
    failed = run(state=ExperimentRunState.FAILED)
    store.append(failed)
    inconclusive = decision(state=ExperimentDecisionState.INCONCLUSIVE)
    store.append(inconclusive)

    with pytest.raises(ResearchConflictError):
        store.append(replace(failed, state=ExperimentRunState.SUCCEEDED))
    with pytest.raises(ResearchConflictError):
        store.append(
            replace(
                inconclusive,
                state=ExperimentDecisionState.SHADOW_REVIEW_PROPOSAL,
            )
        )


def test_tampering_is_detected_by_load_and_audit(tmp_path: Path) -> None:
    store = ExperimentRegistry(tmp_path)
    append_chain(store)
    saved = store.path_for(decision())
    payload = json.loads(saved.read_text(encoding="utf-8"))
    payload["rationale"] = "tampered"
    saved.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ResearchConflictError, match="content hash mismatch"):
        store.load(DECISION_ID)
    audit = store.audit()
    assert audit["status"] == "failed"
    assert any("content hash mismatch" in item for item in audit["errors"])


def test_audit_detects_parent_removed_outside_registry(tmp_path: Path) -> None:
    store = ExperimentRegistry(tmp_path)
    append_chain(store)
    store.path_for(spec()).unlink()

    audit = store.audit()

    assert audit["status"] == "failed"
    assert any("missing parent" in item for item in audit["errors"])


def test_v1_loader_rejects_unknown_fields_even_with_a_valid_hash(tmp_path: Path) -> None:
    store = ExperimentRegistry(tmp_path)
    saved = store.append(spec())
    payload = json.loads(saved.path.read_text(encoding="utf-8"))
    payload.pop("content_hash")
    payload["future_unregistered_field"] = "must not be silently ignored"
    payload["content_hash"] = hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    saved.path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )

    with pytest.raises(ResearchConflictError, match="unexpected fields"):
        store.load(SPEC_ID)
