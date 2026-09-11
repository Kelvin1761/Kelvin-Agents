from __future__ import annotations

import fcntl
import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared_wong_choi.control import single_run_lock
from shared_wong_choi.contracts import Domain
from shared_wong_choi.research_evaluation import (
    EvaluationVerification,
    evaluate_run_artifact,
    publish_evaluation_decision,
)
from shared_wong_choi.research_resources import ResearchPostflightRunner, ResearchWorkflow, ResourceInterrupted
from shared_wong_choi.research_supervision import ResearchScoringRunner
from shared_wong_choi.research_runner import (
    CommandExecution,
    CommandState,
    ResearchDisposition,
    ResearchRuntime,
    SubprocessResearchExecutor,
    ResearchJob,
    ResearchRunResult,
    ResearchRunner,
    create_research_adapter,
)
from test_research_postflight import evidence_fixture, real_checkout_fixture


def fixture(tmp_path):
    spec, arguments = evidence_fixture(tmp_path, use_harness=True)
    runtime = ResearchRuntime(
        state_root=tmp_path / "state",
        warm_root=tmp_path / "warm",
        production_lock_paths=(tmp_path / "production.lock",),
        executor=SubprocessResearchExecutor(poll_seconds=0.02, terminate_grace=0.1),
    )
    registry = arguments.pop("registry")
    from research_test_support import pin_review
    pin_review(runtime, registry, spec)
    return spec, arguments, runtime, registry


def test_real_postflight_worker_publishes_verified_idempotent_decision(tmp_path):
    spec, args, runtime, registry = fixture(tmp_path)
    runner = ResearchPostflightRunner(runtime, registry)
    result = runner.run(spec, **args, estimated_bytes=1024, timeout_seconds=30)
    assert result.disposition is ResearchDisposition.SUCCEEDED
    decision = registry.load(result.decision_id)
    assert decision["links"]["run_id"] == args["run_id"]
    assert result.report_path.is_relative_to(runtime.warm_root)
    assert json.loads(result.attempt_path.joinpath("outcome.json").read_text())["execution"]["returncode"] == 0
    retried = runner.run(spec, **args, estimated_bytes=1024, timeout_seconds=30)
    assert retried.decision_id == result.decision_id
    assert retried.status == "duplicate"


@pytest.mark.parametrize("phase", ["postflight", "scoring"])
def test_lost_warm_never_recreates_mount_path_for_outcome(tmp_path, phase):
    spec, args, runtime, registry = fixture(tmp_path)

    class LostWarm:
        def run(self, invocation, **kwargs):
            runtime.warm_root.rename(tmp_path / "disconnected-warm")
            return CommandExecution(CommandState.PREEMPTED, -15, "", "warm lost", 0.1, 0, 0, 0)

    runtime = replace(runtime, executor=LostWarm())
    if phase == "postflight":
        result = ResearchPostflightRunner(runtime, registry).run(spec, **args, estimated_bytes=1024, timeout_seconds=30)
    else:
        job = ResearchJob(
            "wc:au:research-job:lost-warm",
            spec.domain,
            spec.record_id,
            args["dataset_snapshot"],
            tmp_path / "baseline",
            tmp_path / "candidate",
            1024,
            30,
        )
        result = ResearchScoringRunner(runtime, registry).run(job, spec, create_research_adapter("au"))
    assert result.disposition is ResearchDisposition.PREEMPTED
    assert not runtime.warm_root.exists(), "outcome logging recreated offline WARM on HOT disk"
    fallback = list((runtime.state_root / "research-interruptions").glob("*.json"))
    assert len(fallback) == 1
    assert json.loads(fallback[0].read_text())["outcome_storage"] == "hot_fallback"


@pytest.mark.parametrize("fault,status", [("warm", "warm_offline"), ("space", "insufficient_capacity")])
def test_postflight_resources_fail_closed_before_worker(tmp_path, fault, status):
    spec, args, runtime, registry = fixture(tmp_path)
    runtime = replace(
        runtime, **({"warm_root": tmp_path / "offline"} if fault == "warm" else {"free_space_probe": lambda _: 0})
    )
    result = ResearchPostflightRunner(runtime, registry).run(spec, **args, estimated_bytes=1024, timeout_seconds=30)
    assert result.status == status
    assert not registry.root.joinpath("records/experiment_decision").exists()


@pytest.mark.parametrize("production", [False, True])
def test_postflight_uses_same_heavy_lock_and_yields_to_production(tmp_path, production):
    spec, args, runtime, registry = fixture(tmp_path)
    lock = runtime.production_lock_paths[0] if production else runtime.state_root / "locks/research-heavy-worker.lock"
    with single_run_lock(lock) as acquired:
        assert acquired
        result = ResearchPostflightRunner(runtime, registry).run(spec, **args, estimated_bytes=1024, timeout_seconds=30)
    assert result.disposition is ResearchDisposition.DEFERRED
    assert result.status == ("production_active" if production else "heavy_worker_busy")
    assert result.attempt_path is None


def test_expired_budget_never_launches_postflight(tmp_path):
    spec, args, runtime, registry = fixture(tmp_path)
    with pytest.raises(ValueError, match="timeout"):
        ResearchPostflightRunner(runtime, registry).run(spec, **args, estimated_bytes=1024, timeout_seconds=0)
    assert not runtime.warm_root.joinpath("research-postflight").exists()


@pytest.mark.parametrize("fault", ["missing_locks", "nan_space", "symlink"])
def test_unknown_or_redirected_resource_configuration_cannot_run(tmp_path, fault):
    spec, args, runtime, registry = fixture(tmp_path)
    if fault == "missing_locks":
        runtime = replace(runtime, production_lock_paths=())
    elif fault == "nan_space":
        runtime = replace(runtime, free_space_probe=lambda _: float("nan"))
    else:
        (runtime.warm_root / "research-evaluations").symlink_to(tmp_path, target_is_directory=True)
    result = ResearchPostflightRunner(runtime, registry).run(spec, **args, estimated_bytes=1024, timeout_seconds=30)
    assert result.disposition is not ResearchDisposition.SUCCEEDED
    assert not registry.root.joinpath("records/experiment_decision").exists()


@pytest.mark.parametrize("expired", [False, True])
def test_workflow_shares_one_time_budget_and_wires_registered_run(tmp_path, monkeypatch, expired):
    spec, args, runtime, registry = fixture(tmp_path)
    scoring = ResearchRunResult("job", ResearchDisposition.SUCCEEDED, "succeeded", args["run_artifact"], args["run_id"])
    monkeypatch.setattr(ResearchScoringRunner, "run", lambda *a, **k: scoring)
    budget_clock = iter([100, 140 if expired else 110])
    workflow = ResearchWorkflow(runtime, registry, monotonic=lambda: next(budget_clock))
    job = ResearchJob(
        "wc:au:research-job:workflow",
        spec.domain,
        spec.record_id,
        args["dataset_snapshot"],
        tmp_path / "baseline",
        tmp_path / "candidate",
        1024,
        30,
    )
    result = workflow.run(job, spec, create_research_adapter(spec.domain), evidence=args["evidence"])
    assert result.scoring is scoring
    assert result.postflight.disposition is (
        ResearchDisposition.TIMED_OUT if expired else ResearchDisposition.SUCCEEDED
    )
    if expired:
        assert not runtime.warm_root.joinpath("research-postflight").exists()
    else:
        request = json.loads(result.postflight.attempt_path.joinpath("request.json").read_text())
        assert request["run_id"] == args["run_id"]


def test_failed_scoring_never_enters_evaluation(tmp_path, monkeypatch):
    spec, args, runtime, registry = fixture(tmp_path)
    scoring = ResearchRunResult("job", ResearchDisposition.BLOCKED, "dataset_unverified")
    monkeypatch.setattr(ResearchScoringRunner, "run", lambda *a, **k: scoring)
    job = ResearchJob(
        "wc:au:research-job:workflow",
        spec.domain,
        spec.record_id,
        args["dataset_snapshot"],
        tmp_path / "baseline",
        tmp_path / "candidate",
        1024,
        30,
    )
    result = ResearchWorkflow(runtime, registry).run(
        job, spec, create_research_adapter(spec.domain), evidence=args["evidence"]
    )
    assert result.scoring is scoring and result.postflight is None


def test_workflow_rejects_missing_production_configuration_before_scoring(tmp_path, monkeypatch):
    spec, args, runtime, registry = fixture(tmp_path)

    def unexpected(*args, **kwargs):
        pytest.fail("scoring started without production lock configuration")

    monkeypatch.setattr(ResearchScoringRunner, "run", unexpected)
    job = ResearchJob(
        "wc:au:research-job:workflow",
        spec.domain,
        spec.record_id,
        args["dataset_snapshot"],
        tmp_path / "baseline",
        tmp_path / "candidate",
        1024,
        30,
    )
    result = ResearchWorkflow(replace(runtime, production_lock_paths=()), registry).run(
        job, spec, create_research_adapter(spec.domain), evidence=args["evidence"]
    )
    assert result.scoring.status == "production_locks_unconfigured"
    assert result.postflight is None


@pytest.mark.parametrize("domain", list(Domain))
def test_real_commands_harness_and_postflight_complete_one_workflow(tmp_path, domain):
    spec, args = real_checkout_fixture(tmp_path, domain=domain)
    runtime = ResearchRuntime(
        state_root=tmp_path / "state",
        warm_root=tmp_path / "warm",
        production_lock_paths=(tmp_path / "production.lock",),
        checkout_probe=lambda path: spec.baseline_commit if path.name == "baseline" else spec.candidate_commit,
        executor=SubprocessResearchExecutor(poll_seconds=0.05, terminate_grace=0.1),
    )
    job = ResearchJob(
        f"wc:{domain.value}:research-job:real-workflow",
        domain,
        spec.record_id,
        args["dataset_snapshot"],
        tmp_path / "baseline",
        tmp_path / "candidate",
        1024,
        30,
    )
    result = ResearchWorkflow(runtime, args["registry"]).run(
        job, spec, create_research_adapter(domain), evidence=args["evidence"]
    )
    assert result.scoring.disposition is ResearchDisposition.SUCCEEDED
    assert result.postflight.disposition is ResearchDisposition.SUCCEEDED
    report = json.loads(result.postflight.report_path.read_text())
    assert report["safety_passed"]
    decision = args["registry"].load(result.postflight.decision_id)
    assert decision["links"]["run_id"] == result.scoring.experiment_run_id
    if domain is Domain.NBA:
        assert decision["state"] == "inconclusive"


def test_publication_rechecks_resources_after_expensive_verification(tmp_path):
    spec, args, runtime, registry = fixture(tmp_path)
    report = evaluate_run_artifact(spec, registry=registry, **args)
    calls = []

    def preempted():
        calls.append(1)
        raise ResourceInterrupted("production_active")

    with pytest.raises(ResourceInterrupted, match="production_active"):
        publish_evaluation_decision(
            report,
            registry=registry,
            run_id=args["run_id"],
            report_root=runtime.warm_root / "reports",
            decided_at="2026-08-31T01:00:00+00:00",
            verification=EvaluationVerification(spec, args["dataset_snapshot"], args["run_artifact"], args["evidence"]),
            resource_checkpoint=preempted,
        )
    assert calls
    assert not registry.root.joinpath("records/experiment_decision").exists()
    assert not runtime.warm_root.joinpath("reports").exists()


@pytest.mark.parametrize("preempt", [False, True])
def test_real_worker_is_terminated_during_evaluation_without_publishing(tmp_path, preempt):
    spec, args, runtime, registry = fixture(tmp_path)
    handles = []

    class SlowEvaluationExecutor(SubprocessResearchExecutor):
        def run(self, invocation, *, timeout_seconds, production_active):
            # Exercise the real worker, but stall only its expensive evaluation.
            code = (
                "import sys,time; from pathlib import Path; "
                "import shared_wong_choi.research_resources as r; "
                "r.evaluate_run_artifact=lambda *a,**k: time.sleep(60); "
                "r._worker(Path(sys.argv[1]))"
            )
            invocation = replace(invocation, argv=(sys.executable, "-c", code, invocation.argv[-1]))
            polls = 0

            def check():
                nonlocal polls
                polls += 1
                if preempt and polls == 5:
                    handle = runtime.production_lock_paths[0].open("a")
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    handles.append(handle)
                return production_active()

            return super().run(invocation, timeout_seconds=min(timeout_seconds, 1), production_active=check)

    runtime = replace(runtime, executor=SlowEvaluationExecutor(poll_seconds=0.05, terminate_grace=0.1))
    try:
        result = ResearchPostflightRunner(runtime, registry).run(spec, **args, estimated_bytes=1024, timeout_seconds=30)
    finally:
        for handle in handles:
            handle.close()
    assert result.disposition is (ResearchDisposition.PREEMPTED if preempt else ResearchDisposition.TIMED_OUT)
    assert not registry.root.joinpath("records/experiment_decision").exists()
    assert result.attempt_path.joinpath("outcome.json").is_file()
    with single_run_lock(runtime.state_root / "locks/research-heavy-worker.lock") as acquired:
        assert acquired


@pytest.mark.parametrize("reason,expected", [("production_active", "preempted"), ("timeout", "timed_out")])
def test_postflight_worker_checkpoint_interruptions_preserve_uncertain_publication(tmp_path, reason, expected):
    spec, args, runtime, registry = fixture(tmp_path)

    class WorkerInterrupt(SubprocessResearchExecutor):
        def run(self, invocation, **kwargs):
            program = (
                "from pathlib import Path; import sys; import shared_wong_choi.research_resources as r; "
                f"r.evaluate_run_artifact=lambda *a,**k: (_ for _ in ()).throw(r.ResourceInterrupted({reason!r})); "
                "r._worker(Path(sys.argv[1]))"
            )
            return super().run(replace(invocation, argv=(sys.executable, "-c", program, invocation.argv[-1])), **kwargs)

    runtime = replace(runtime, executor=WorkerInterrupt(poll_seconds=0.02, terminate_grace=0.1))
    result = ResearchPostflightRunner(runtime, registry).run(spec, **args, estimated_bytes=1024, timeout_seconds=10)
    assert result.disposition.value == expected
    assert result.status == reason and result.decision_id is None
    assert (
        json.loads((result.attempt_path / "outcome.json").read_text())["publication"]
        == "unconfirmed_reconcile_before_retry"
    )
