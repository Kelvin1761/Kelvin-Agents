from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared_wong_choi.contracts import Domain
from shared_wong_choi.research_registry import ExperimentRegistry
from shared_wong_choi.research_runner import (
    ResearchDisposition, ResearchJob, SubprocessResearchExecutor,
)
from shared_wong_choi.research_liveness import (
    probe_process_start_token,
    record_research_liveness_lease,
)
from shared_wong_choi.research_review_runtime import ResearchReviewRunner
from shared_wong_choi.research_index import completed_review_request_ids, load_review_receipt
from test_research_index import fixture as registry_fixture, clock_args
from test_research_supervision import source_runtime
from test_research_racing_monitoring_samples import _au_source as racing_au_source
from shared_wong_choi.research_supervision import (
    NbaMonitoringSampleInspectionRunner,
    RacingMonitoringSampleInspectionRunner,
    ResearchLivenessInspectionRunner,
    ResearchProductionDayInspectionRunner,
    ResearchLiveDriftInspectionRunner,
    ResearchStorageEvidenceInspectionRunner,
    TennisMonitoringSampleInspectionRunner,
)
from test_research_nba_monitoring_samples import settled_source as nba_sample_source
from test_research_nba_settlement_source import END as NBA_SAMPLE_END
from test_research_tennis_monitoring_samples import settled_source as tennis_sample_source
from test_research_tennis_settlement_source import END as TENNIS_SAMPLE_END
from test_research_runner import configured_queue, spec as runner_spec
from test_research_production_day import (
    AS_OF as PRODUCTION_DAY_AS_OF,
    DAY as PRODUCTION_DAY,
    _attestation as production_day_attestation,
    _terminal_runs as production_day_runs,
)
from test_research_au_feature_provenance import (
    AS_OF as AU_FEATURE_AS_OF,
    fixture as au_feature_fixture,
)


def setup(tmp_path):
    return source_runtime(tmp_path), registry_fixture(tmp_path)


def run_review(runtime, registry, **kwargs):
    return ResearchReviewRunner(runtime, registry).run(**clock_args(), estimated_bytes=1048576, timeout_seconds=15, **kwargs)


def read_summary(result):
    assert result.disposition is ResearchDisposition.SUCCEEDED, result
    return json.loads(result.report_path.read_bytes())


def liveness_fixture(tmp_path, runtime, registry, as_of, *, worker_pid=None):
    queue_home = tmp_path / "queue-source"
    queue_home.mkdir()
    current_spec = runner_spec(Domain.AU)
    queue = configured_queue(
        queue_home, clock=lambda: as_of - timedelta(minutes=1),
        current_spec=current_spec, registry=registry,
    )
    queue.enqueue(ResearchJob(
        "wc:au:research-job:review-live", Domain.AU,
        current_spec.record_id, tmp_path / "dataset", tmp_path / "baseline",
        tmp_path / "candidate", 1024, 600,
    ))
    claim = queue.claim_next("review-worker")
    leases = tmp_path / "liveness-leases"
    leases.mkdir()
    worker_pid = os.getpid() if worker_pid is None else worker_pid
    token = probe_process_start_token(worker_pid)
    assert token is not None
    record_research_liveness_lease(
        lease_root=leases, claim=claim, pid=worker_pid,
        process_start_token=token,
        observed_at=as_of - timedelta(seconds=30),
        valid_until=as_of + timedelta(minutes=5),
    )
    result = ResearchLivenessInspectionRunner(runtime, registry).run(
        domain=Domain.AU, queue_root=queue.root, lease_root=leases,
        as_of=as_of, estimated_bytes=1048576, timeout_seconds=15,
    )
    assert result.disposition is ResearchDisposition.SUCCEEDED
    return queue, leases, result


def test_supervised_review_records_registry_event_and_calendar_then_dedups(tmp_path):
    runtime, registry = setup(tmp_path)
    before = {str(path): path.read_bytes() for path in registry.root.rglob("*.json")}
    result = run_review(runtime, registry)
    summary = read_summary(result)
    assert summary["created_reviews"] == 2
    assert summary["remaining_requests"] == 0
    assert summary["run_completion_events"] == 1
    assert summary["sample_evidence_status"] == "not_integrated"
    assert summary["production_day_evidence_status"] == "not_integrated"
    assert not summary["model_promotion_allowed"] and not summary["telegram_delivery_confirmed"]
    receipt_root = runtime.warm_root / "research-reviews"
    kinds = set()
    for request_id in completed_review_request_ids(receipt_root, Domain.AU):
        receipt = load_review_receipt(receipt_root / "au" / (request_id + ".json"))
        kinds.add(next(item["kind"] for item in receipt["plan"]["requests"] if item["request_id"] == request_id))
    assert kinds == {"run_postflight", "weekly"}
    repeated = read_summary(run_review(runtime, registry))
    assert repeated["created_reviews"] == 0
    assert repeated["already_recorded_reviews"] == 2
    assert before == {str(path): path.read_bytes() for path in registry.root.rglob("*.json")}


def test_supervised_review_reverifies_descriptive_live_drift_without_threshold_authority(
        tmp_path):
    runtime, registry = setup(tmp_path)
    evidence = au_feature_fixture(tmp_path / "feature-source")
    baseline = AU_FEATURE_AS_OF - timedelta(days=1)
    drift = ResearchLiveDriftInspectionRunner(runtime, registry).run(
        domain=Domain.AU,
        evidence_root=evidence,
        baseline_as_of=baseline,
        as_of=AU_FEATURE_AS_OF,
        estimated_bytes=1048576,
        timeout_seconds=15,
    )
    assert drift.disposition is ResearchDisposition.SUCCEEDED

    result = ResearchReviewRunner(runtime, registry).run(
        domain=Domain.AU,
        window_start=AU_FEATURE_AS_OF - timedelta(days=1),
        now=AU_FEATURE_AS_OF,
        ruler_digest="1" * 64,
        ruler_released_at=AU_FEATURE_AS_OF - timedelta(days=30),
        estimated_bytes=1048576,
        timeout_seconds=15,
        drift_report=drift.report_path,
        drift_evidence_root=evidence,
        drift_baseline_as_of=baseline,
    )

    summary = read_summary(result)
    assert summary["live_drift_evidence_status"] == "verified_insufficient_data"
    assert summary["live_drift_verified"] is False
    assert summary["live_drift"]["current_records"] == 1
    assert summary["live_drift"]["metric_drift_verified"] is False
    assert summary["live_drift"]["market_drift_verified"] is False
    assert summary["model_promotion_allowed"] is False


def test_supervised_review_reverifies_racing_sample_and_first_baseline_is_progress_only(tmp_path):
    runtime, registry = setup(tmp_path)
    evidence, as_of, _result = racing_au_source(tmp_path / "source")
    sample = RacingMonitoringSampleInspectionRunner(runtime, registry).run(
        domain=Domain.AU,
        evidence_root=evidence,
        as_of=as_of,
        estimated_bytes=1048576,
        timeout_seconds=15,
    )
    assert sample.disposition is ResearchDisposition.SUCCEEDED

    result = ResearchReviewRunner(runtime, registry).run(
        domain=Domain.AU,
        window_start=as_of - timedelta(days=1),
        now=as_of,
        ruler_digest="1" * 64,
        ruler_released_at=as_of - timedelta(days=30),
        estimated_bytes=1048576,
        timeout_seconds=15,
        racing_sample_report=sample.report_path,
        racing_sample_evidence_root=evidence,
    )
    summary = read_summary(result)
    assert summary["sample_evidence_status"] == "verified_complete"
    assert summary["sample_growth_observed"] is False
    assert summary["progress_only"] is True
    assert summary["racing_sample_current"]["content_hash"] == sample.content_hash
    assert summary["racing_sample_previous"] is None
    assert summary["model_promotion_allowed"] is False
    receipt = load_review_receipt(Path(summary["processed"][0]["path"]))
    assert len(receipt["clock_inputs"]["samples"][0]["unit_ids"]) == 1
    assert receipt["clock_inputs"]["previous_samples"] == []
    assert all(item["kind"] != "sample" for item in receipt["plan"]["requests"])


def test_supervised_review_unchanged_verified_sample_never_redecides_promotion(tmp_path):
    runtime, registry = setup(tmp_path)
    evidence, as_of, _result = racing_au_source(tmp_path / "source")
    sample = RacingMonitoringSampleInspectionRunner(runtime, registry).run(
        domain=Domain.AU,
        evidence_root=evidence,
        as_of=as_of,
        estimated_bytes=1048576,
        timeout_seconds=15,
    )
    result = ResearchReviewRunner(runtime, registry).run(
        domain=Domain.AU,
        window_start=as_of - timedelta(minutes=1),
        now=as_of,
        ruler_digest="1" * 64,
        ruler_released_at=as_of - timedelta(days=30),
        estimated_bytes=1048576,
        timeout_seconds=15,
        racing_sample_report=sample.report_path,
        previous_racing_sample_report=sample.report_path,
        racing_sample_evidence_root=evidence,
    )
    summary = read_summary(result)
    assert summary["sample_evidence_status"] == "verified_complete"
    assert summary["sample_growth_observed"] is False
    assert summary["progress_only"] is True
    assert summary["reevaluate_promotion_allowed"] is False


@pytest.mark.parametrize(
    ("domain", "source", "runner_type", "as_of", "scope"),
    [
        (Domain.NBA, nba_sample_source, NbaMonitoringSampleInspectionRunner,
         NBA_SAMPLE_END, "all"),
        (Domain.TENNIS, tennis_sample_source, TennisMonitoringSampleInspectionRunner,
         TENNIS_SAMPLE_END, "match_winner_atp"),
    ],
)
def test_supervised_review_accepts_domain_specific_sample_scopes(
        tmp_path, domain, source, runner_type, as_of, scope):
    runtime, registry = setup(tmp_path)
    evidence, *_rest = source(tmp_path / "source")
    sample = runner_type(runtime, registry).run(
        evidence_root=evidence,
        as_of=as_of,
        estimated_bytes=1048576,
        timeout_seconds=15,
    )
    assert sample.disposition is ResearchDisposition.SUCCEEDED

    result = ResearchReviewRunner(runtime, registry).run(
        domain=domain,
        window_start=as_of - timedelta(days=1),
        now=as_of,
        ruler_digest="1" * 64,
        ruler_released_at=as_of - timedelta(days=30),
        estimated_bytes=1048576,
        timeout_seconds=15,
        racing_sample_report=sample.report_path,
        racing_sample_evidence_root=evidence,
    )
    summary = read_summary(result)
    assert summary["racing_sample_current"]["scope_counts"] == {scope: 1}
    assert summary["racing_sample_current"]["observed_at"] == as_of.isoformat()
    assert summary["progress_only"] is True


def test_supervised_review_reverifies_storage_without_inventing_other_health(
        tmp_path, monkeypatch):
    runtime, registry = setup(tmp_path)
    repo, storage_state = tmp_path / "repo", tmp_path / "storage-state"
    hot, warm = tmp_path / "hot", tmp_path / "warm-archive"
    for path in (repo, storage_state, hot, warm):
        path.mkdir()
    monkeypatch.setenv("WC_HOT_DATA_ROOT", str(hot))
    monkeypatch.setenv("WC_WARM_ARCHIVE_ROOT", str(warm))
    monkeypatch.delenv("WC_COLD_MIRROR_ROOT", raising=False)
    clock = clock_args()
    storage = ResearchStorageEvidenceInspectionRunner(runtime, registry).run(
        domain=Domain.AU, repo_root=repo, storage_state_root=storage_state,
        as_of=clock["now"], estimated_bytes=1048576, timeout_seconds=15,
    )
    assert storage.disposition is ResearchDisposition.SUCCEEDED

    result = run_review(
        runtime, registry,
        storage_report=storage.report_path,
        storage_repo_root=repo,
        storage_state_root=storage_state,
    )
    summary = read_summary(result)
    assert summary["storage_evidence_status"] == "verified_attention"
    assert summary["storage_evidence"]["content_hash"] == storage.content_hash
    assert summary["storage_evidence"]["storage_health"] == "attention"
    assert summary["process_liveness_verified"] is False
    assert summary["live_drift_verified"] is False
    assert summary["model_promotion_allowed"] is False


def test_supervised_review_reverifies_process_liveness_without_granting_authority(
        tmp_path):
    runtime, registry = setup(tmp_path)
    clock = clock_args()
    queue, leases, liveness = liveness_fixture(
        tmp_path, runtime, registry, clock["now"],
    )

    result = run_review(
        runtime, registry,
        queue_root=queue.root,
        liveness_report=liveness.report_path,
        liveness_lease_root=leases,
    )

    summary = read_summary(result)
    assert summary["process_liveness_evidence_status"] == "verified_complete"
    assert summary["process_liveness_verified"] is True
    assert summary["process_liveness"]["content_hash"] == liveness.content_hash
    assert summary["process_liveness"]["queue_index_hash"] == summary["index_hash"]
    assert summary["process_liveness"]["counts"]["running_verified"] == 1
    assert summary["live_drift_verified"] is False
    assert summary["model_promotion_allowed"] is False


def test_supervised_review_reverifies_closed_production_day_and_emits_daily_event(
        tmp_path):
    runtime, registry = setup(tmp_path)
    runs = tmp_path / "production-runs"
    production_day_runs(runs, Domain.AU)
    attestation = production_day_attestation(tmp_path, Domain.AU)
    evidence = ResearchProductionDayInspectionRunner(runtime, registry).run(
        domain=Domain.AU,
        run_root=runs,
        attestation_path=attestation,
        production_day=PRODUCTION_DAY,
        as_of=PRODUCTION_DAY_AS_OF,
        estimated_bytes=1048576,
        timeout_seconds=15,
    )
    assert evidence.disposition is ResearchDisposition.SUCCEEDED

    result = ResearchReviewRunner(runtime, registry).run(
        domain=Domain.AU,
        window_start=PRODUCTION_DAY_AS_OF - timedelta(days=2),
        now=PRODUCTION_DAY_AS_OF,
        ruler_digest="1" * 64,
        ruler_released_at=PRODUCTION_DAY_AS_OF - timedelta(days=30),
        estimated_bytes=1048576,
        timeout_seconds=15,
        production_day_report=evidence.report_path,
        production_day_run_root=runs,
        production_day_attestation_path=attestation,
        production_day=PRODUCTION_DAY,
    )

    summary = read_summary(result)
    assert summary["production_day_evidence_status"] == "verified_closed"
    assert summary["production_day_evidence"]["content_hash"] == evidence.content_hash
    assert summary["production_day_evidence"]["production_day"] == PRODUCTION_DAY.isoformat()
    receipts = [load_review_receipt(Path(item["path"])) for item in summary["processed"]]
    assert any(
        request["kind"] == "daily"
        for receipt in receipts for request in receipt["plan"]["requests"]
    )
    assert summary["model_promotion_allowed"] is False


def test_supervised_review_accepts_verified_incomplete_day_without_daily_event(tmp_path):
    runtime, registry = setup(tmp_path)
    runs = tmp_path / "production-runs"
    evidence = ResearchProductionDayInspectionRunner(runtime, registry).run(
        domain=Domain.AU,
        run_root=runs,
        attestation_path=None,
        production_day=PRODUCTION_DAY,
        as_of=PRODUCTION_DAY_AS_OF,
        estimated_bytes=1048576,
        timeout_seconds=15,
    )

    result = ResearchReviewRunner(runtime, registry).run(
        domain=Domain.AU,
        window_start=PRODUCTION_DAY_AS_OF - timedelta(days=2),
        now=PRODUCTION_DAY_AS_OF,
        ruler_digest="1" * 64,
        ruler_released_at=PRODUCTION_DAY_AS_OF - timedelta(days=30),
        estimated_bytes=1048576,
        timeout_seconds=15,
        production_day_report=evidence.report_path,
        production_day_run_root=runs,
        production_day_attestation_path=None,
        production_day=PRODUCTION_DAY,
    )

    summary = read_summary(result)
    assert summary["production_day_evidence_status"] == "verified_incomplete"
    receipts = [load_review_receipt(Path(item["path"])) for item in summary["processed"]]
    assert all(
        request["kind"] != "daily"
        for receipt in receipts for request in receipt["plan"]["requests"]
    )


def test_supervised_review_rejects_production_day_after_run_source_changes(tmp_path):
    runtime, registry = setup(tmp_path)
    runs = tmp_path / "production-runs"
    production_day_runs(runs, Domain.AU)
    attestation = production_day_attestation(tmp_path, Domain.AU)
    evidence = ResearchProductionDayInspectionRunner(runtime, registry).run(
        domain=Domain.AU,
        run_root=runs,
        attestation_path=attestation,
        production_day=PRODUCTION_DAY,
        as_of=PRODUCTION_DAY_AS_OF,
        estimated_bytes=1048576,
        timeout_seconds=15,
    )
    manifest = next(runs.rglob("attempt-1.json"))
    payload = json.loads(manifest.read_text())
    payload["errors"].append("changed-before-review")
    manifest.write_text(json.dumps(payload, sort_keys=True) + "\n")

    result = ResearchReviewRunner(runtime, registry).run(
        domain=Domain.AU,
        window_start=PRODUCTION_DAY_AS_OF - timedelta(days=2),
        now=PRODUCTION_DAY_AS_OF,
        ruler_digest="1" * 64,
        ruler_released_at=PRODUCTION_DAY_AS_OF - timedelta(days=30),
        estimated_bytes=1048576,
        timeout_seconds=15,
        production_day_report=evidence.report_path,
        production_day_run_root=runs,
        production_day_attestation_path=attestation,
        production_day=PRODUCTION_DAY,
    )

    assert result.disposition is ResearchDisposition.FAILED
    assert result.report_path is None


def test_supervised_review_rejects_liveness_after_process_identity_changes(
        tmp_path):
    runtime, registry = setup(tmp_path)
    clock = clock_args()
    process = subprocess.Popen(["sleep", "30"])
    try:
        queue, leases, liveness = liveness_fixture(
            tmp_path, runtime, registry, clock["now"],
            worker_pid=process.pid,
        )
    finally:
        process.terminate()
        process.wait(timeout=5)

    result = run_review(
        runtime, registry,
        queue_root=queue.root,
        liveness_report=liveness.report_path,
        liveness_lease_root=leases,
    )

    assert result.disposition is ResearchDisposition.FAILED
    assert result.report_path is None


def test_supervised_review_rejects_storage_report_after_source_changes(
        tmp_path, monkeypatch):
    runtime, registry = setup(tmp_path)
    repo, storage_state = tmp_path / "repo", tmp_path / "storage-state"
    hot, warm = tmp_path / "hot", tmp_path / "warm-archive"
    for path in (repo, storage_state, hot, warm):
        path.mkdir()
    monkeypatch.setenv("WC_HOT_DATA_ROOT", str(hot))
    monkeypatch.setenv("WC_WARM_ARCHIVE_ROOT", str(warm))
    clock = clock_args()
    storage = ResearchStorageEvidenceInspectionRunner(runtime, registry).run(
        domain=Domain.AU, repo_root=repo, storage_state_root=storage_state,
        as_of=clock["now"], estimated_bytes=1048576, timeout_seconds=15,
    )
    warm.rmdir()

    result = run_review(
        runtime, registry,
        storage_report=storage.report_path,
        storage_repo_root=repo,
        storage_state_root=storage_state,
    )
    assert result.disposition is ResearchDisposition.FAILED
    assert result.report_path is None


def test_bounded_batch_replays_pending_window_without_losing_request(tmp_path):
    runtime, registry = setup(tmp_path)
    first = read_summary(run_review(runtime, registry, max_reviews=1))
    assert first["created_reviews"] == 1 and first["remaining_requests"] == 1
    assert first["next_window_start"] == first["window_start"]
    second = read_summary(run_review(runtime, registry, max_reviews=1))
    assert second["created_reviews"] == 1 and second["remaining_requests"] == 0
    assert second["next_window_start"] == second["as_of"]


@pytest.mark.parametrize("fault", ["production", "heavy", "offline", "capacity", "unconfigured"])
def test_review_defers_without_registry_io_when_resources_unavailable(tmp_path, fault):
    runtime = source_runtime(tmp_path)
    registry = ExperimentRegistry(tmp_path / "missing-registry")
    handle = None
    if fault in {"production", "heavy"}:
        lock = runtime.production_lock_paths[0] if fault == "production" else runtime.state_root / "locks/research-heavy-worker.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        handle = lock.open("a")
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if fault == "offline":
        runtime = replace(runtime, warm_root=tmp_path / "unmounted")
    if fault == "capacity":
        runtime = replace(runtime, free_space_probe=lambda _: 0)
    if fault == "unconfigured":
        runtime = replace(runtime, production_lock_paths=())
    try:
        result = run_review(runtime, registry)
    finally:
        if handle:
            handle.close()
    assert result.disposition is ResearchDisposition.DEFERRED
    assert result.report_path is None
    assert not registry.root.exists()
    assert not (runtime.warm_root / "research-reviews").exists()


def test_missing_registry_does_not_fabricate_empty_healthy_review(tmp_path):
    runtime = source_runtime(tmp_path)
    registry = ExperimentRegistry(tmp_path / "missing")
    result = run_review(runtime, registry)
    assert result.disposition is ResearchDisposition.FAILED
    assert result.report_path is None and not registry.root.exists()


@pytest.mark.parametrize("preempt", [False, True])
def test_blocked_index_read_is_killed_by_outer_supervisor(tmp_path, preempt):
    runtime, registry = setup(tmp_path)
    fifo, ready = tmp_path / "blocked-index", tmp_path / "ready"
    os.mkfifo(fifo)
    handles = []

    class Blocked(SubprocessResearchExecutor):
        def run(self, invocation, *, timeout_seconds, production_active):
            program = (
                "from pathlib import Path; import sys; import shared_wong_choi.research_review_runtime as r; "
                "import shared_wong_choi.research_supervision as s; "
                f"r.build_research_index=lambda **k: (Path({str(ready)!r}).touch(),open({str(fifo)!r}).read())[1]; "
                "s._worker(Path(sys.argv[1]))"
            )
            def check():
                if preempt and ready.exists() and not handles:
                    handle = runtime.production_lock_paths[0].open("a")
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    handles.append(handle)
                return production_active()
            return super().run(replace(invocation, argv=(sys.executable, "-c", program, invocation.argv[-1])),
                               timeout_seconds=1, production_active=check)

    runtime = replace(runtime, executor=Blocked(poll_seconds=0.02, terminate_grace=0.1))
    try:
        result = run_review(runtime, registry)
    finally:
        for handle in handles:
            handle.close()
    assert ready.exists()
    assert result.disposition is (ResearchDisposition.PREEMPTED if preempt else ResearchDisposition.TIMED_OUT)
    assert result.report_path is None
    assert not (runtime.warm_root / "research-reviews").exists()


def test_worker_exit_after_first_receipt_recovers_from_durable_review_ids(tmp_path):
    runtime, registry = setup(tmp_path)

    class Crash(SubprocessResearchExecutor):
        def run(self, invocation, **kwargs):
            program = (
                "from pathlib import Path; import os,sys; import shared_wong_choi.research_review_runtime as r; "
                "import shared_wong_choi.research_supervision as s; original=r.record_review; "
                "r.record_review=lambda **k: (original(**k),os._exit(77)); s._worker(Path(sys.argv[1]))"
            )
            return super().run(replace(invocation, argv=(sys.executable, "-c", program, invocation.argv[-1])), **kwargs)

    failed = run_review(replace(runtime, executor=Crash(poll_seconds=0.02, terminate_grace=0.1)), registry)
    assert failed.disposition is ResearchDisposition.FAILED
    outcome = json.loads((failed.attempt_path / "phase-outcome.json").read_bytes())
    assert outcome["execution"]["returncode"] == 77
    assert outcome["publication"] == "unconfirmed_reconcile_before_retry"
    root = runtime.warm_root / "research-reviews"
    ids = completed_review_request_ids(root, Domain.AU)
    assert len(ids) == 1
    original = {str(path): path.read_bytes() for path in root.rglob("*.json")}
    resumed = read_summary(run_review(runtime, registry))
    assert resumed["created_reviews"] == 1 and resumed["already_recorded_reviews"] == 1
    assert len(completed_review_request_ids(root, Domain.AU)) == 2
    for path, raw in original.items():
        assert Path(path).read_bytes() == raw


def test_ruler_freeze_survives_recorded_review_and_new_worker(tmp_path):
    runtime, registry = setup(tmp_path)
    options = {**clock_args(), "ruler_released_at": clock_args()["now"] - timedelta(days=91)}
    runner = ResearchReviewRunner(runtime, registry)
    first = read_summary(runner.run(**options, estimated_bytes=1048576, timeout_seconds=15))
    assert first["freeze_research_required"]
    second = read_summary(runner.run(**options, estimated_bytes=1048576, timeout_seconds=15))
    assert second["created_reviews"] == 0 and second["freeze_research_required"]


@pytest.mark.parametrize("fault", ["domain", "promotion", "count"])
def test_parent_rejects_forged_summary_even_after_rehash(tmp_path, fault):
    from shared_wong_choi.research_index import _hash
    runtime, registry = setup(tmp_path)
    class Forged(SubprocessResearchExecutor):
        def run(self, invocation, **kwargs):
            execution = super().run(invocation, **kwargs)
            receipt = json.loads(invocation.metrics_path.read_bytes())
            path = Path(receipt["report_path"])
            summary = json.loads(path.read_bytes())
            if fault == "domain":
                summary["domain"] = "nba"
            elif fault == "promotion":
                summary["model_promotion_allowed"] = True
            else:
                summary["created_reviews"] = 999
            summary.pop("content_hash")
            summary["content_hash"] = _hash(summary)
            path.write_text(json.dumps(summary))
            receipt["content_hash"] = summary["content_hash"]
            invocation.metrics_path.write_text(json.dumps(receipt))
            return execution
    result = run_review(replace(runtime, executor=Forged()), registry)
    assert result.disposition is ResearchDisposition.FAILED
    assert result.report_path is None


@pytest.mark.parametrize("reason,expected", [("production_active", ResearchDisposition.PREEMPTED), ("phase_timeout", ResearchDisposition.TIMED_OUT)])
def test_index_checkpoint_interruptions_preserve_resource_reason(tmp_path, reason, expected):
    runtime, registry = setup(tmp_path)
    class Interrupted(SubprocessResearchExecutor):
        def run(self, invocation, **kwargs):
            program = (
                "from pathlib import Path; import sys; import shared_wong_choi.research_index as i; "
                "import shared_wong_choi.research_supervision as s; "
                "from shared_wong_choi.research_resources import ResourceInterrupted; "
                f"i._Reader.read=lambda *a,**k: (_ for _ in ()).throw(ResourceInterrupted({reason!r})); "
                "s._worker(Path(sys.argv[1]))"
            )
            return super().run(replace(invocation, argv=(sys.executable, "-c", program, invocation.argv[-1])), **kwargs)
    result = run_review(replace(runtime, executor=Interrupted()), registry)
    assert result.disposition is expected
    assert result.status == reason
    assert result.report_path is None


def test_lost_warm_does_not_recreate_archive_for_review_outcome(tmp_path):
    runtime, registry = setup(tmp_path)
    disconnected = tmp_path / "disconnected"
    class LostWarm(SubprocessResearchExecutor):
        def run(self, invocation, **kwargs):
            result = super().run(invocation, **kwargs)
            runtime.warm_root.rename(disconnected)
            return result
    result = run_review(replace(runtime, executor=LostWarm()), registry)
    assert result.disposition is ResearchDisposition.FAILED
    assert result.report_path is None and not runtime.warm_root.exists()
    assert len(list(disconnected.glob("research-reviews/au/*.json"))) == 2
    fallbacks = list(runtime.state_root.glob("research-interruptions/*.json"))
    assert len(fallbacks) == 1
    assert json.loads(fallbacks[0].read_bytes())["outcome_storage"] == "hot_fallback"


def test_review_completion_from_other_registry_cannot_suppress_current_review(tmp_path):
    from test_research_registry import append_chain
    runtime, registry = setup(tmp_path)
    assert read_summary(run_review(runtime, registry))["created_reviews"] == 2
    other = ExperimentRegistry(tmp_path / "other-registry")
    append_chain(other)
    result = run_review(runtime, other)
    assert result.disposition is ResearchDisposition.FAILED
    assert result.report_path is None
