from __future__ import annotations

import json
import hashlib
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared_wong_choi.contracts import Domain
from shared_wong_choi.research_registry import ExperimentRegistry, ExperimentRunState, ExperimentDecisionState
from shared_wong_choi.research_runner import ResearchJob, ResearchQueue, ResearchRunResult, ResearchDisposition
from shared_wong_choi.research_index import (
    ResearchIndexError, build_research_index, record_review,
    load_review_receipt, completed_review_request_ids,
)
from shared_wong_choi.research_review_clock import plan_reviews, ReviewEvent
from test_research_registry import spec, dataset, run, decision, append_chain


NOW = datetime(2026, 8, 31, tzinfo=timezone.utc)


def fixture(tmp_path):
    store = ExperimentRegistry(tmp_path / "registry")
    append_chain(store)
    return store


def clock_args(**changes):
    return dict(domain=Domain.AU, now=NOW,
                window_start=datetime(2026, 8, 30, tzinfo=timezone.utc),
                ruler_digest="1" * 64, ruler_released_at=datetime(2026, 8, 1, tzinfo=timezone.utc), **changes)


def test_index_is_read_only_repeatable_and_does_not_qualify_samples(tmp_path):
    store = fixture(tmp_path)
    before = {str(path): path.read_bytes() for path in store.root.rglob("*.json")}
    index = build_research_index(registry_root=store.root, as_of=NOW)
    assert index == build_research_index(registry_root=store.root, as_of=NOW)
    assert index["counts"]["experiment_run"] == 1
    entry = index["experiments"][0]
    assert entry["runs"][0]["registered_decisions"][0]["state"] == "inconclusive"
    assert entry["datasets"][0]["manifest_rows"] == 100
    assert index["verified_monitoring_samples"] is None
    assert not index["model_promotion_allowed"]
    assert before == {str(path): path.read_bytes() for path in store.root.rglob("*.json")}


@pytest.mark.parametrize("domain", list(Domain))
def test_four_domains_preserve_failure_and_registered_proposal_distinction(tmp_path, domain):
    store = ExperimentRegistry(tmp_path / "registry")
    s = spec(domain=domain)
    d = dataset(domain=domain, spec_id=s.record_id)
    r = replace(run(domain=domain, spec_id=s.record_id, dataset_id=d.record_id),
                evaluation_ruler_id=s.evaluation_ruler_id)
    p = replace(decision(run_id=r.record_id, state=ExperimentDecisionState.SHADOW_REVIEW_PROPOSAL),
                domain=domain, record_id=f"wc:{domain.value}:experiment-decision:proposal")
    f = replace(r, record_id=r.record_id + "-failed", state=ExperimentRunState.FAILED)
    for record in (s, d, r, p, f):
        store.append(record)
    index = build_research_index(registry_root=store.root, as_of=NOW)
    runs = index["experiments"][0]["runs"]
    assert {item["execution_state"] for item in runs} == {"succeeded", "failed"}
    registered = next(item for item in runs if item["registered_decisions"])["registered_decisions"][0]
    assert registered["report_verification"] == "not_supplied"
    assert registered["state"] == "shadow_review_proposal"
    assert registered["next_human_action"] == "verify_evidence_then_shadow_review"
    assert not index["model_promotion_allowed"]


@pytest.mark.parametrize("fault", ["hash", "parent", "wrong_filename", "future", "cycle", "symlink", "oversized", "duplicate_json_key"])
def test_invalid_registry_never_becomes_a_green_index(tmp_path, fault):
    store = fixture(tmp_path)
    path = store.path_for(spec())
    if fault == "hash":
        path.write_text(path.read_text().replace("pace feature", "invented feature"))
    elif fault == "parent":
        path.unlink()
    elif fault == "wrong_filename":
        path.rename(path.with_name("copied.json"))
    elif fault == "future":
        s = replace(spec(), record_id=spec().record_id + "-future", created_at="2027-01-01T00:00:00Z")
        store.append(s)
    elif fault == "cycle":
        path.write_text(json.dumps(replace(spec(), parent_spec_id=spec().record_id).to_payload()))
    elif fault == "symlink":
        moved = tmp_path / "moved.json"
        path.rename(moved)
        path.symlink_to(moved)
    elif fault == "oversized":
        path.write_bytes(b" " * 1_048_577)
    else:
        path.write_text(path.read_text().replace('"kind":', '"kind":"experiment_run","kind":', 1))
    with pytest.raises(ResearchIndexError):
        build_research_index(registry_root=store.root, as_of=NOW)


def test_failed_run_cannot_be_presented_as_shadow_candidate(tmp_path):
    store = fixture(tmp_path)
    store.path_for(run()).write_text(json.dumps(replace(run(), state=ExperimentRunState.FAILED).to_payload()))
    store.path_for(decision()).write_text(json.dumps(replace(decision(), state=ExperimentDecisionState.SHADOW_REVIEW_PROPOSAL).to_payload()))
    with pytest.raises(ResearchIndexError):
        build_research_index(registry_root=store.root, as_of=NOW)


def test_queue_claim_is_not_liveness_and_orphan_claim_is_rejected(tmp_path):
    store = fixture(tmp_path)
    from test_research_runner import configured_queue
    queue = configured_queue(tmp_path, clock=lambda: NOW, current_spec=spec(), registry=store)
    job = ResearchJob("wc:au:research-job:test", Domain.AU, spec().record_id,
                      tmp_path / "dataset", tmp_path / "base", tmp_path / "candidate", 1024, 10)
    queue.enqueue(job)
    index = build_research_index(registry_root=store.root, queue_root=queue.root, as_of=NOW)
    assert index["queue"][0]["status"] == "queued"
    claim = queue.claim_next("worker-one")
    index = build_research_index(registry_root=store.root, queue_root=queue.root, as_of=NOW)
    assert index["queue"][0]["status"] == "claimed_liveness_unverified"
    assert index["queue"][0]["process_alive"] is None
    (queue.root / "jobs" / claim.path.name).unlink()
    with pytest.raises(ResearchIndexError):
        build_research_index(registry_root=store.root, queue_root=queue.root, as_of=NOW)


def test_missing_root_is_not_an_empty_healthy_registry_and_bounds_fail_closed(tmp_path):
    with pytest.raises(ResearchIndexError):
        build_research_index(registry_root=tmp_path / "missing", as_of=NOW)
    store = fixture(tmp_path)
    with pytest.raises(ResearchIndexError):
        build_research_index(registry_root=store.root, as_of=NOW, max_records=3)


def test_index_checkpoint_can_interrupt_before_reading_corpus(tmp_path):
    store = fixture(tmp_path)
    def stop():
        raise InterruptedError("production priority")
    with pytest.raises(InterruptedError):
        build_research_index(registry_root=store.root, as_of=NOW, checkpoint=stop)


def test_real_published_report_projects_ci_without_reevaluation(tmp_path, monkeypatch):
    from test_research_postflight import evidence_fixture
    import shared_wong_choi.research_evaluation as evaluation
    (tmp_path / "experiment").mkdir()
    s, arguments = evidence_fixture(tmp_path / "experiment", use_harness=True)
    report = evaluation.evaluate_run_artifact(s, **arguments)
    publication = evaluation.publish_evaluation_decision(
        report, registry=arguments["registry"], run_id=arguments["run_id"],
        report_root=tmp_path / "reports", decided_at=NOW.isoformat(),
        verification=evaluation.EvaluationVerification(s, arguments["dataset_snapshot"], arguments["run_artifact"], arguments["evidence"]),
    )
    def forbidden(*args, **kwargs):
        raise AssertionError("index must not re-evaluate")
    monkeypatch.setattr(evaluation, "evaluate_run_artifact", forbidden)
    index = build_research_index(registry_root=arguments["registry"].root, as_of=NOW,
                                 report_paths={publication.decision_id: publication.report_path})
    projected = index["experiments"][0]["runs"][0]["registered_decisions"][0]
    assert projected["report_verification"] == "hash_and_lineage_verified_not_recomputed"
    assert projected["report"]["scopes"] == report.to_payload()["scopes"]
    clock = {**clock_args(), "ruler_digest": s.evaluation_ruler_digest}
    request = plan_reviews(**clock)["requests"][0]
    receipt = record_review(root=tmp_path / "reviews", registry_root=arguments["registry"].root,
                            clock_inputs=clock, request_id=request["request_id"],
                            report_paths={publication.decision_id: publication.report_path})
    assert load_review_receipt(receipt["path"])["index"]["experiments"] == index["experiments"]
    publication.report_path.write_bytes(publication.report_path.read_bytes() + b" ")
    with pytest.raises(ResearchIndexError):
        build_research_index(registry_root=arguments["registry"].root, as_of=NOW,
                             report_paths={publication.decision_id: publication.report_path})


def test_review_receipt_is_atomic_idempotent_and_not_delivery_or_approval(tmp_path):
    store = fixture(tmp_path)
    clock = clock_args()
    request_id = plan_reviews(**clock)["requests"][0]["request_id"]
    options = dict(root=tmp_path / "reviews", registry_root=store.root, clock_inputs=clock, request_id=request_id)
    first = record_review(**options)
    second = record_review(**options)
    assert first["status"] == "created" and second["status"] == "duplicate"
    receipt = load_review_receipt(first["path"])
    assert receipt["request_id"] == request_id
    assert receipt["telegram_delivery_confirmed"] is False
    assert receipt["model_promotion_allowed"] is False
    assert completed_review_request_ids(tmp_path / "reviews", Domain.AU) == frozenset({request_id})
    assert not plan_reviews(**clock, completed_request_ids={request_id})["requests"]


def test_changed_review_cannot_overwrite_original_and_tampering_is_rejected(tmp_path):
    store = fixture(tmp_path)
    clock = clock_args()
    request_id = plan_reviews(**clock)["requests"][0]["request_id"]
    options = dict(root=tmp_path / "reviews", registry_root=store.root, clock_inputs=clock, request_id=request_id)
    first = record_review(**options)
    original = first["path"].read_bytes()
    store.append(replace(spec(), record_id=spec().record_id + "-second"))
    with pytest.raises(ResearchIndexError, match="conflict"):
        record_review(**options)
    assert first["path"].read_bytes() == original
    first["path"].write_text(first["path"].read_text().replace('"model_promotion_allowed":false', '"model_promotion_allowed":true'))
    with pytest.raises(ResearchIndexError):
        completed_review_request_ids(tmp_path / "reviews", Domain.AU)


def test_completed_review_does_not_clear_incident_freeze(tmp_path):
    store = fixture(tmp_path)
    event = ReviewEvent("incident", "feed-1", NOW, "a" * 64)
    clock = clock_args(events=(event,))
    request = next(item for item in plan_reviews(**clock)["requests"] if item["kind"] == "incident")
    record_review(root=tmp_path / "reviews", registry_root=store.root, clock_inputs=clock, request_id=request["request_id"])
    ids = completed_review_request_ids(tmp_path / "reviews", Domain.AU)
    assert plan_reviews(**clock, completed_request_ids=ids)["freeze_research_required"]


def test_unknown_request_is_not_recorded(tmp_path):
    store = fixture(tmp_path)
    with pytest.raises(ResearchIndexError):
        record_review(root=tmp_path / "reviews", registry_root=store.root, clock_inputs=clock_args(), request_id="f" * 64)
    assert not (tmp_path / "reviews").exists()


def rehash(payload):
    payload.pop("content_hash", None)
    payload["content_hash"] = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                                       separators=(",", ":")).encode()).hexdigest()


def test_rehashed_receipt_cannot_invent_projection_counts(tmp_path):
    store = fixture(tmp_path)
    clock = clock_args()
    request_id = plan_reviews(**clock)["requests"][0]["request_id"]
    result = record_review(root=tmp_path / "reviews", registry_root=store.root, clock_inputs=clock, request_id=request_id)
    payload = json.loads(result["path"].read_bytes())
    payload["index"]["counts"]["experiment_run"] = 999
    rehash(payload["index"])
    rehash(payload)
    result["path"].write_text(json.dumps(payload))
    with pytest.raises(ResearchIndexError):
        load_review_receipt(result["path"])


def test_temporary_registry_entries_still_count_towards_scan_bound(tmp_path):
    store = fixture(tmp_path)
    folder = store.path_for(spec()).parent
    for i in range(6):
        (folder / f".leftover-{i}.tmp").write_text("partial")
    with pytest.raises(ResearchIndexError):
        build_research_index(registry_root=store.root, as_of=NOW, max_records=5)


@pytest.mark.parametrize("after_link", [False, True])
def test_interrupted_receipt_publication_is_recoverable_without_overwrite(tmp_path, monkeypatch, after_link):
    store = fixture(tmp_path)
    clock = clock_args()
    request_id = plan_reviews(**clock)["requests"][0]["request_id"]
    options = dict(root=tmp_path / "reviews", registry_root=store.root, clock_inputs=clock, request_id=request_id)
    original = os.link
    def interrupted(source, target):
        if after_link:
            original(source, target)
        raise InterruptedError("simulated publication interruption")
    monkeypatch.setattr(os, "link", interrupted)
    with pytest.raises(InterruptedError):
        record_review(**options)
    path = tmp_path / "reviews" / "au" / (request_id + ".json")
    assert path.exists() is after_link
    if after_link:
        assert load_review_receipt(path)["request_id"] == request_id
    monkeypatch.setattr(os, "link", original)
    result = record_review(**options)
    assert result["status"] == ("duplicate" if after_link else "created")


def test_concurrent_review_writers_publish_exactly_one_receipt(tmp_path):
    store = fixture(tmp_path)
    clock = clock_args()
    request_id = plan_reviews(**clock)["requests"][0]["request_id"]
    def write(_):
        return record_review(root=tmp_path / "reviews", registry_root=store.root, clock_inputs=clock, request_id=request_id)
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(write, range(4)))
    assert [item["status"] for item in results].count("created") == 1
    assert len({item["receipt_id"] for item in results}) == 1
    assert completed_review_request_ids(tmp_path / "reviews", Domain.AU) == frozenset({request_id})


@pytest.mark.parametrize("matching_job", [True, False])
def test_queue_completed_run_requires_its_job_identity(tmp_path, matching_job):
    store = fixture(tmp_path)
    from test_research_runner import configured_queue
    queue = configured_queue(tmp_path, clock=lambda: datetime(2026, 8, 30, tzinfo=timezone.utc), current_spec=spec(), registry=store)
    job = ResearchJob("wc:au:research-job:completed", Domain.AU, spec().record_id,
                      tmp_path / "dataset", tmp_path / "base", tmp_path / "candidate", 1024, 10)
    queue.enqueue(job)
    claim = queue.claim_next("worker-one")
    r = run()
    if matching_job:
        identity = hashlib.sha256(json.dumps(dict(job_id=job.job_id, started_at=r.started_at, artifact_digest=r.artifact_digest),
                                             sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:24]
        r = replace(r, record_id=f"wc:au:experiment-run:{identity}")
        store.append(r)
    queue.clock = lambda: NOW
    queue.finish(claim, ResearchRunResult(job.job_id, ResearchDisposition.SUCCEEDED, "succeeded", experiment_run_id=r.record_id))
    if matching_job:
        assert build_research_index(registry_root=store.root, queue_root=queue.root, as_of=NOW)["queue"][0]["status"] == "succeeded"
    else:
        with pytest.raises(ResearchIndexError):
            build_research_index(registry_root=store.root, queue_root=queue.root, as_of=NOW)


def test_review_receipt_roundtrips_explicit_production_day(tmp_path):
    store = fixture(tmp_path)
    event = ReviewEvent("production_day_closed", "late-close", NOW, "d" * 64, production_day=date(2026, 8, 30))
    clock = clock_args(events=(event,))
    request = next(item for item in plan_reviews(**clock)["requests"] if item["kind"] == "daily")
    result = record_review(root=tmp_path / "reviews", registry_root=store.root, clock_inputs=clock, request_id=request["request_id"])
    receipt = load_review_receipt(result["path"])
    assert receipt["clock_inputs"]["events"][0]["production_day"] == "2026-08-30"
    assert next(item for item in receipt["plan"]["requests"] if item["kind"] == "daily")["slot"] == "2026-08-30"
