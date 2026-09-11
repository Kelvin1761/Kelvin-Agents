from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared_wong_choi.contracts import Domain
from shared_wong_choi.research_index import ResearchIndexError, record_review, load_review_receipt
from shared_wong_choi.research_presentation import prepare_review_presentation
from shared_wong_choi.research_registry import ExperimentRegistry, ExperimentDecisionState
from shared_wong_choi.research_review_clock import ReviewEvent, plan_reviews
from shared_wong_choi.research_runner import ResearchJob, ResearchQueue
from test_research_index import NOW, clock_args, rehash
from test_research_registry import spec, dataset, run, decision


def chain(store, domain, state=ExperimentDecisionState.INCONCLUSIVE):
    s = spec(domain=domain)
    d = dataset(domain=domain, spec_id=s.record_id)
    r = replace(run(domain=domain, spec_id=s.record_id, dataset_id=d.record_id),
                evaluation_ruler_id=s.evaluation_ruler_id)
    p = replace(decision(run_id=r.record_id, state=state), domain=domain,
                record_id=f"wc:{domain.value}:experiment-decision:test")
    for record in (s, d, r, p):
        store.append(record)


def receipt(tmp_path, domain=Domain.AU, *, state=ExperimentDecisionState.INCONCLUSIVE,
            events=(), queue=False):
    store = ExperimentRegistry(tmp_path / "registry")
    for item in Domain:
        chain(store, item, state)
    options = {**clock_args(events=events), "domain": domain}
    requests = plan_reviews(**options)["requests"]
    extra = {}
    if queue:
        from test_research_runner import configured_queue
        q = configured_queue(tmp_path, clock=lambda: NOW, current_spec=spec(), registry=store)
        for item in Domain:
            q.enqueue(ResearchJob(f"wc:{item.value}:research-job:test", item, spec(domain=item).record_id,
                                  tmp_path / "data", tmp_path / "base", tmp_path / "candidate", 10, 10))
        q.claim_next("worker")
        extra["queue_root"] = q.root
    return record_review(root=tmp_path / "reviews", registry_root=store.root,
                         clock_inputs=options, request_id=requests[0]["request_id"], **extra)["path"]


@pytest.mark.parametrize("domain", list(Domain))
def test_scopes_counts_and_rows_are_not_verified_samples(tmp_path, domain):
    path = receipt(tmp_path, domain)
    result = prepare_review_presentation(path)
    view = result["projection"]
    assert len(view["experiments"]) == 1
    assert view["experiments"][0]["domain"] == domain.value
    assert view["counts"]["experiments"] == 1
    assert view["counts"]["runs"] == 1
    assert view["counts"]["decisions"] == {"inconclusive": 1}
    assert view["experiments"][0]["datasets"][0]["manifest_rows"] == 100
    assert view["verified_monitoring_samples"] is None
    assert view["storage_health"] is None and view["live_drift"] is None
    assert view["queue_completeness_verified"] is False
    assert "合格監測樣本：未核實" in result["telegram"]["text"]
    assert "只報進度" in result["telegram"]["text"]


def test_shadow_proposal_requires_review_and_missing_report_is_visible(tmp_path):
    result = prepare_review_presentation(receipt(tmp_path, state=ExperimentDecisionState.SHADOW_REVIEW_PROPOSAL))
    view = result["projection"]
    choice = view["experiments"][0]["runs"][0]["registered_decisions"][0]
    assert choice["report_verification"] == "not_supplied" and choice["report"] is None
    assert view["counts"]["reports_not_supplied"] == 1
    assert "核對證據後再做 shadow review" in result["telegram"]["text"]
    assert "未附報告 1" in result["telegram"]["text"]
    assert view["model_promotion_allowed"] is False
    assert result["telegram"]["send_authorized"] is False


def test_freeze_is_not_hidden_by_an_existing_review(tmp_path):
    path = receipt(tmp_path, events=(ReviewEvent("incident", "feed-error", NOW, "a" * 64),))
    result = prepare_review_presentation(path)
    original = load_review_receipt(path)
    assert result["projection"]["freeze_reasons"] == original["plan"]["freeze_reasons"]
    assert result["projection"]["human_review_required"] is True
    assert "凍結研究／需要人手覆核" in result["telegram"]["text"]


def test_queue_claim_is_not_presented_as_running(tmp_path):
    result = prepare_review_presentation(receipt(tmp_path, queue=True))
    view = result["projection"]
    assert len(view["queue"]) == 1
    assert view["queue"][0]["status"] == "claimed_liveness_unverified"
    assert view["queue"][0]["process_alive"] is None
    assert "運行存活：未核實" in result["telegram"]["text"]


def storage_review(tmp_path, monkeypatch):
    from shared_wong_choi.research_supervision import (
        ResearchStorageEvidenceInspectionRunner,
    )
    from test_research_review_runtime import run_review, setup

    runtime, registry = setup(tmp_path)
    repo, storage_state = tmp_path / "repo", tmp_path / "storage-state"
    hot, warm = tmp_path / "hot", tmp_path / "warm-archive"
    for item in (repo, storage_state, hot, warm):
        item.mkdir()
    monkeypatch.setenv("WC_HOT_DATA_ROOT", str(hot))
    monkeypatch.setenv("WC_WARM_ARCHIVE_ROOT", str(warm))
    storage = ResearchStorageEvidenceInspectionRunner(runtime, registry).run(
        domain=Domain.AU, repo_root=repo, storage_state_root=storage_state,
        as_of=NOW, estimated_bytes=1048576, timeout_seconds=15,
    )
    review = run_review(
        runtime, registry,
        storage_report=storage.report_path,
        storage_repo_root=repo,
        storage_state_root=storage_state,
    )
    summary = json.loads(review.report_path.read_text())
    receipt_path = Path(summary["processed"][0]["path"])
    return runtime, registry, storage, review, receipt_path


def liveness_review(tmp_path):
    from test_research_review_runtime import (
        liveness_fixture, run_review, setup,
    )

    runtime, registry = setup(tmp_path)
    queue, leases, liveness = liveness_fixture(
        tmp_path, runtime, registry, NOW,
    )
    review = run_review(
        runtime, registry,
        queue_root=queue.root,
        liveness_report=liveness.report_path,
        liveness_lease_root=leases,
    )
    summary = json.loads(review.report_path.read_text())
    receipt_path = Path(summary["processed"][0]["path"])
    return runtime, registry, liveness, review, receipt_path


def production_day_review(tmp_path, *, complete=True):
    from datetime import timedelta

    from shared_wong_choi.research_supervision import (
        ResearchProductionDayInspectionRunner,
    )
    from test_research_production_day import (
        AS_OF, DAY, _attestation, _terminal_runs,
    )
    from test_research_review_runtime import setup
    from shared_wong_choi.research_review_runtime import ResearchReviewRunner

    runtime, registry = setup(tmp_path)
    runs = tmp_path / "production-runs"
    attestation = None
    if complete:
        _terminal_runs(runs, Domain.AU)
        attestation = _attestation(tmp_path, Domain.AU)
    evidence = ResearchProductionDayInspectionRunner(runtime, registry).run(
        domain=Domain.AU, run_root=runs, attestation_path=attestation,
        production_day=DAY, as_of=AS_OF,
        estimated_bytes=1048576, timeout_seconds=15,
    )
    review = ResearchReviewRunner(runtime, registry).run(
        domain=Domain.AU, window_start=AS_OF - timedelta(days=2), now=AS_OF,
        ruler_digest="1" * 64, ruler_released_at=AS_OF - timedelta(days=30),
        estimated_bytes=1048576, timeout_seconds=15,
        production_day_report=evidence.report_path,
        production_day_run_root=runs,
        production_day_attestation_path=attestation,
        production_day=DAY,
    )
    summary = json.loads(review.report_path.read_text())
    receipt_path = Path(summary["processed"][0]["path"])
    return evidence, review, receipt_path


def live_drift_review(tmp_path):
    from datetime import timedelta

    from shared_wong_choi.research_review_runtime import ResearchReviewRunner
    from shared_wong_choi.research_supervision import ResearchLiveDriftInspectionRunner
    from test_research_au_feature_provenance import AS_OF, fixture as feature_fixture
    from test_research_review_runtime import setup

    runtime, registry = setup(tmp_path)
    source = feature_fixture(tmp_path / "feature-source")
    baseline = AS_OF - timedelta(days=1)
    drift = ResearchLiveDriftInspectionRunner(runtime, registry).run(
        domain=Domain.AU, evidence_root=source,
        baseline_as_of=baseline, as_of=AS_OF,
        estimated_bytes=1048576, timeout_seconds=15,
    )
    review = ResearchReviewRunner(runtime, registry).run(
        domain=Domain.AU, window_start=baseline, now=AS_OF,
        ruler_digest="1" * 64, ruler_released_at=AS_OF - timedelta(days=30),
        estimated_bytes=1048576, timeout_seconds=15,
        drift_report=drift.report_path,
        drift_evidence_root=source,
        drift_baseline_as_of=baseline,
    )
    summary = json.loads(review.report_path.read_text())
    receipt_path = Path(summary["processed"][0]["path"])
    return drift, review, receipt_path


def test_verified_review_summary_exposes_storage_but_not_drift_or_liveness(
        tmp_path, monkeypatch):
    _, _, storage, review, receipt_path = storage_review(tmp_path, monkeypatch)

    result = prepare_review_presentation(
        receipt_path, review_summary_path=review.report_path,
    )
    view = result["projection"]
    assert view["storage_health"] == "attention"
    assert view["storage_evidence"]["content_hash"] == storage.content_hash
    assert view["storage_evidence"]["observed_at"] == NOW.isoformat()
    assert view["process_liveness_verified"] is False
    assert view["live_drift"] is None
    assert "儲存健康：需留意（已核實時間點快照）" in result["telegram"]["text"]
    assert str(storage.report_path) not in result["telegram"]["text"]


def test_verified_review_summary_exposes_bound_liveness_without_model_authority(
        tmp_path):
    _, _, liveness, review, receipt_path = liveness_review(tmp_path)

    result = prepare_review_presentation(
        receipt_path, review_summary_path=review.report_path,
    )

    view = result["projection"]
    assert view["process_liveness_verified"] is True
    assert view["queue_completeness_verified"] is True
    assert view["process_liveness"]["content_hash"] == liveness.content_hash
    assert view["process_liveness"]["counts"]["running_verified"] == 1
    assert view["process_liveness"]["queue_index_hash"] == view["index_hash"]
    assert view["model_promotion_allowed"] is False
    assert "運行存活：來源已核實" in result["telegram"]["text"]
    assert str(liveness.report_path) not in result["telegram"]["text"]


@pytest.mark.parametrize(
    ("complete", "status", "message"),
    [
        (True, "verified_closed", "生產日：已完整核實"),
        (False, "verified_incomplete", "生產日：證據未完整"),
    ],
)
def test_verified_review_summary_exposes_production_day_without_source_paths(
        tmp_path, complete, status, message):
    evidence, review, receipt_path = production_day_review(
        tmp_path, complete=complete,
    )

    result = prepare_review_presentation(
        receipt_path, review_summary_path=review.report_path,
    )

    view = result["projection"]
    assert view["production_day_evidence_status"] == status
    assert view["production_day_evidence"]["content_hash"] == evidence.content_hash
    assert view["production_day_evidence"]["production_day"] == "2026-09-03"
    assert message in result["telegram"]["text"]
    assert str(evidence.report_path) not in result["telegram"]["text"]
    assert str(tmp_path) not in result["telegram"]["text"]
    assert view["model_promotion_allowed"] is False


def test_verified_review_summary_exposes_descriptive_drift_without_source_paths(
        tmp_path):
    drift, review, receipt_path = live_drift_review(tmp_path)

    result = prepare_review_presentation(
        receipt_path, review_summary_path=review.report_path,
    )

    view = result["projection"]
    assert view["live_drift"]["content_hash"] == drift.content_hash
    assert view["live_drift"]["status"] == "insufficient_data"
    assert view["live_drift"]["current_records"] == 1
    assert view["live_drift"]["metric_drift_verified"] is False
    assert view["live_drift"]["market_drift_verified"] is False
    assert "特徵 drift：證據不足" in result["telegram"]["text"]
    assert str(drift.report_path) not in result["telegram"]["text"]
    assert str(tmp_path) not in result["telegram"]["text"]
    assert view["model_promotion_allowed"] is False


def test_repeatable_read_only_preview_has_dedup_identity_not_delivery(tmp_path, monkeypatch):
    path = receipt(tmp_path)
    original = {str(p): p.read_bytes() for p in tmp_path.rglob("*.json")}
    def forbidden(*args, **kwargs):
        raise AssertionError("presentation must not send, score or write")
    import socket
    import shared_wong_choi.research_evaluation as evaluation
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(evaluation, "evaluate_run_artifact", forbidden)
    monkeypatch.setattr(Path, "write_text", forbidden)
    first = prepare_review_presentation(path)
    assert first == prepare_review_presentation(path)
    assert first["telegram"]["delivery_confirmed"] is False
    assert first["telegram"]["status"] == "prepared_only"
    assert first["telegram"]["audience_requirement"] == "authorized_primary_only"
    assert first["telegram"]["parse_mode"] is None
    assert original == {str(p): p.read_bytes() for p in tmp_path.rglob("*.json")}


def test_storage_summary_must_pin_selected_receipt_hash(tmp_path, monkeypatch):
    _, _, _, review, path = storage_review(tmp_path, monkeypatch)
    payload = json.loads(review.report_path.read_text())
    payload["processed"][0]["receipt_id"] = "a" * 64
    rehash(payload)
    review.report_path.write_text(json.dumps(payload))
    completed_path = review.report_path.parent.parent / "completed.json"
    completed = json.loads(completed_path.read_text())
    completed["content_hash"] = payload["content_hash"]
    completed_path.write_text(json.dumps(completed))
    with pytest.raises(ValueError, match="selected receipt"):
        prepare_review_presentation(path, review_summary_path=review.report_path)


def test_two_registries_cannot_share_a_delivery_key(tmp_path):
    one = prepare_review_presentation(receipt(tmp_path / "one"))
    two = prepare_review_presentation(receipt(tmp_path / "two"))
    assert one["projection"]["request_id"] == two["projection"]["request_id"]
    assert one["telegram"]["dedup_key"] != two["telegram"]["dedup_key"]


def test_changed_snapshot_same_review_keeps_key_but_exposes_payload_conflict(tmp_path):
    path = receipt(tmp_path)
    one = prepare_review_presentation(path)
    store = ExperimentRegistry(tmp_path / "registry")
    store.append(replace(spec(), record_id=spec().record_id + "-new"))
    options = clock_args()
    second_path = record_review(root=tmp_path / "other-reviews", registry_root=store.root,
                                clock_inputs=options, request_id=one["projection"]["request_id"])["path"]
    two = prepare_review_presentation(second_path)
    assert one["telegram"]["dedup_key"] == two["telegram"]["dedup_key"]
    assert one["telegram"]["content_hash"] != two["telegram"]["content_hash"]


def test_historical_ruler_is_not_presented_as_current_ruler_evidence(tmp_path):
    receipt(tmp_path)
    options = {**clock_args(), "ruler_digest": "f" * 64}
    path = record_review(root=tmp_path / "other-reviews", registry_root=tmp_path / "registry",
                         clock_inputs=options, request_id=plan_reviews(**options)["requests"][0]["request_id"])["path"]
    result = prepare_review_presentation(path)
    assert result["projection"]["other_ruler_experiment_ids"] == [spec().record_id]
    assert "其他 ruler 嘅歷史實驗：1" in result["telegram"]["text"]


@pytest.mark.parametrize("fault", ["changed_hash", "rehash_fake_count", "approval"])
def test_corrupt_receipt_cannot_become_a_digest(tmp_path, fault):
    path = receipt(tmp_path)
    value = json.loads(path.read_text())
    if fault == "approval":
        value["model_promotion_allowed"] = True
    else:
        value["index"]["counts"]["experiment_run"] = 10000
    if fault != "changed_hash":
        rehash(value["index"])
        rehash(value)
    path.write_text(json.dumps(value))
    with pytest.raises(ResearchIndexError):
        prepare_review_presentation(path)


def test_digest_omits_free_text_paths_and_stays_bounded(tmp_path):
    path = receipt(tmp_path)
    result = prepare_review_presentation(path)
    text = result["telegram"]["text"]
    assert str(tmp_path) not in text
    assert spec().hypothesis not in text
    assert "confidence interval crosses" not in text
    assert len(text.encode("utf-16-le")) // 2 < 4096
    assert result["projection"]["receipt_hash"] == load_review_receipt(path)["content_hash"]


def test_hash_linked_ci_is_projected_exactly_without_rejudging(tmp_path, monkeypatch):
    from test_research_postflight import evidence_fixture
    import shared_wong_choi.research_evaluation as evaluation
    folder = tmp_path / "experiment"
    folder.mkdir()
    s, args = evidence_fixture(folder, use_harness=True)
    report = evaluation.evaluate_run_artifact(s, **args)
    publication = evaluation.publish_evaluation_decision(
        report, registry=args["registry"], run_id=args["run_id"], report_root=tmp_path / "reports",
        decided_at=NOW.isoformat(), verification=evaluation.EvaluationVerification(
            s, args["dataset_snapshot"], args["run_artifact"], args["evidence"]),
    )
    options = {**clock_args(), "ruler_digest": s.evaluation_ruler_digest}
    path = record_review(root=tmp_path / "reviews", registry_root=args["registry"].root,
                         clock_inputs=options, request_id=plan_reviews(**options)["requests"][0]["request_id"],
                         report_paths={publication.decision_id: publication.report_path})["path"]
    def forbidden(*args, **kwargs):
        raise AssertionError("must not reevaluate")
    monkeypatch.setattr(evaluation, "evaluate_run_artifact", forbidden)
    view = prepare_review_presentation(path)["projection"]
    choice = view["experiments"][0]["runs"][0]["registered_decisions"][0]
    assert choice["report"]["scopes"] == report.to_payload()["scopes"]
    assert choice["report_verification"] == "hash_and_lineage_verified_not_recomputed"
    assert view["safety_recomputed"] is False
