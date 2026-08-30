from __future__ import annotations

import fcntl
import hashlib
import json
import os
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT.parent))

from shared_wong_choi.artifact_archive import artifact_digest
from shared_wong_choi.contracts import Domain
from shared_wong_choi.research_dataset import (
    DatasetSource,
    SplitPolicy,
    StorageTier,
    build_dataset_snapshot,
)
from shared_wong_choi.research_registry import (
    ExperimentRegistry,
    ExperimentSpec,
    ResearchKind,
)
from shared_wong_choi.research_runner import (
    CommandExecution,
    CommandState,
    QueueConflictError,
    ResearchDisposition,
    ResearchJob,
    ResearchQueue,
    ResearchRunResult,
    ResearchRunner,
    ResearchRuntime,
    SubprocessResearchExecutor,
    create_research_adapter,
)


BASELINE = "a" * 40
CANDIDATE = "b" * 40
CUTOFF = "2026-08-29T23:59:00+00:00"


def canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def spec(domain: Domain = Domain.AU) -> ExperimentSpec:
    return ExperimentSpec(
        record_id=f"wc:{domain.value}:experiment-spec:runner-v1",
        domain=domain,
        created_at="2026-08-30T00:00:00+00:00",
        hypothesis="runner contract fixture",
        evaluation_ruler_id=f"{domain.value}-v1",
        evaluation_ruler_digest="1" * 64,
        baseline_commit=BASELINE,
        candidate_commit=CANDIDATE,
        preregistered_metrics=("primary",),
        seed=7,
        commands=("python3 evaluate.py --frozen",),
        protocol_artifact_digest="2" * 64,
    )


def normalized_rows() -> list[dict]:
    return [
        {
            "row_id": "row-train",
            "event_at": "2026-08-01T00:00:00+00:00",
            "available_at": "2026-08-02T00:00:00+00:00",
            "payload": {"outcome": 1},
        },
        {
            "row_id": "row-dev",
            "event_at": "2026-08-15T00:00:00+00:00",
            "available_at": "2026-08-16T00:00:00+00:00",
            "payload": {"outcome": 0},
        },
        {
            "row_id": "row-terminal",
            "event_at": "2026-08-25T00:00:00+00:00",
            "available_at": "2026-08-26T00:00:00+00:00",
            "payload": {"outcome": 1},
        },
    ]


def snapshot(tmp_path: Path, domain: Domain = Domain.AU):
    artifact = tmp_path / "dataset-source" / "artifact"
    artifact.mkdir(parents=True)
    rows_path = artifact / "rows.jsonl"
    rows_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in normalized_rows()),
        encoding="utf-8",
    )
    source = DatasetSource(
        source_id=f"{domain.value}-fixture",
        tier=StorageTier.HOT,
        artifact_path=artifact,
        rows_path=rows_path,
        available_at="2026-08-28T00:00:00+00:00",
        expected_digest=artifact_digest(artifact),
    )
    return build_dataset_snapshot(
        spec(domain),
        sources=(source,),
        split_policy=SplitPolicy(
            train_end="2026-08-10T23:59:00+00:00",
            dev_end="2026-08-20T23:59:00+00:00",
            terminal_end=CUTOFF,
        ),
        snapshot_root=tmp_path / "snapshots",
    )


def job(tmp_path: Path, dataset_path: Path, domain: Domain = Domain.AU) -> ResearchJob:
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    baseline.mkdir(exist_ok=True)
    candidate.mkdir(exist_ok=True)
    return ResearchJob(
        job_id=f"wc:{domain.value}:research-job:fixture-001",
        domain=domain,
        spec_id=spec(domain).record_id,
        dataset_snapshot=dataset_path,
        baseline_checkout=baseline,
        candidate_checkout=candidate,
        estimated_bytes=1024,
        timeout_seconds=30,
    )


class DeterministicExecutor:
    def __init__(self) -> None:
        self.calls = []

    def run(self, invocation, *, timeout_seconds, production_active):
        self.calls.append(invocation)
        invocation.metrics_path.write_text(
            json.dumps(
                {"metric": 0.5, "role": invocation.role}, sort_keys=True
            )
            + "\n",
            encoding="utf-8",
        )
        return CommandExecution(
            state=CommandState.SUCCEEDED,
            returncode=0,
            stdout="deterministic\n",
            stderr="",
            wall_seconds=0.25,
            user_seconds=0.1,
            system_seconds=0.02,
            max_rss_kb=2048,
        )


class TimeoutExecutor:
    def run(self, invocation, *, timeout_seconds, production_active):
        (invocation.output_dir / "partial.bin").write_bytes(b"partial")
        return CommandExecution(
            state=CommandState.TIMED_OUT,
            returncode=None,
            stdout="started\n",
            stderr="timeout\n",
            wall_seconds=float(timeout_seconds),
            user_seconds=0.0,
            system_seconds=0.0,
            max_rss_kb=0,
        )


class PreemptedExecutor:
    def run(self, invocation, *, timeout_seconds, production_active):
        (invocation.output_dir / "partial.bin").write_bytes(b"partial")
        return CommandExecution(
            state=CommandState.PREEMPTED,
            returncode=-15,
            stdout="started\n",
            stderr="production started\n",
            wall_seconds=0.1,
            user_seconds=0.0,
            system_seconds=0.0,
            max_rss_kb=0,
        )


class ExplodingExecutor:
    def run(self, invocation, *, timeout_seconds, production_active):
        (invocation.output_dir / "partial.bin").write_bytes(b"partial")
        raise RuntimeError("executor exploded")


class DatasetMutatingExecutor(DeterministicExecutor):
    def run(self, invocation, *, timeout_seconds, production_active):
        result = super().run(
            invocation,
            timeout_seconds=timeout_seconds,
            production_active=production_active,
        )
        Path(invocation.env["WC_RESEARCH_DATASET"]).write_text(
            "tampered\n", encoding="utf-8"
        )
        return result


class SymlinkMetricsExecutor:
    def __init__(self, outside: Path) -> None:
        self.outside = outside

    def run(self, invocation, *, timeout_seconds, production_active):
        self.outside.write_text('{"metric": 1}\n', encoding="utf-8")
        invocation.metrics_path.symlink_to(self.outside)
        return CommandExecution(
            state=CommandState.SUCCEEDED,
            returncode=0,
            stdout="done\n",
            stderr="",
            wall_seconds=0.1,
            user_seconds=0.01,
            system_seconds=0.01,
            max_rss_kb=1024,
        )


def runtime(
    tmp_path: Path,
    *,
    executor=None,
    production_locks: tuple[Path, ...] = (),
    free_bytes: int = 10_000_000,
) -> ResearchRuntime:
    warm = tmp_path / "warm"
    warm.mkdir(exist_ok=True)
    return ResearchRuntime(
        state_root=tmp_path / "state",
        warm_root=warm,
        production_lock_paths=production_locks,
        reserve_bytes=1024,
        checkout_probe=lambda path: BASELINE
        if path.name == "baseline"
        else CANDIDATE,
        free_space_probe=lambda _path: free_bytes,
        executor=executor or DeterministicExecutor(),
        clock=lambda: datetime(2026, 8, 31, 0, 0, tzinfo=timezone.utc),
    )


def registered_runner(
    tmp_path: Path,
    run_runtime: ResearchRuntime,
    domain: Domain = Domain.AU,
) -> ResearchRunner:
    registry = ExperimentRegistry(tmp_path / "registry")
    registry.append(spec(domain))
    return ResearchRunner(run_runtime, registry)


def test_queue_is_append_only_idempotent_and_claims_in_order(tmp_path: Path) -> None:
    data = snapshot(tmp_path)
    first = job(tmp_path, data.path)
    second = replace(first, job_id="wc:au:research-job:fixture-002")
    queue = ResearchQueue(tmp_path / "queue")

    assert queue.enqueue(second).status == "created"
    assert queue.enqueue(first).status == "created"
    assert queue.enqueue(first).status == "duplicate"
    claim = queue.claim_next("worker-1")

    assert claim is not None
    assert claim.job.job_id == first.job_id
    assert queue.claim_next("worker-2").job.job_id == second.job_id


def test_queue_rejects_same_id_with_different_payload(tmp_path: Path) -> None:
    data = snapshot(tmp_path)
    queued = job(tmp_path, data.path)
    queue = ResearchQueue(tmp_path / "queue")
    queue.enqueue(queued)

    with pytest.raises(QueueConflictError, match="immutable queue conflict"):
        queue.enqueue(replace(queued, timeout_seconds=31))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("estimated_bytes", 0),
        ("estimated_bytes", True),
        ("timeout_seconds", 0),
        ("timeout_seconds", float("nan")),
        ("timeout_seconds", float("inf")),
    ],
)
def test_queue_rejects_invalid_resource_bounds(
    tmp_path: Path, field: str, value
) -> None:
    data = snapshot(tmp_path)

    with pytest.raises(ValueError, match="must be positive"):
        ResearchQueue(tmp_path / "queue").enqueue(
            replace(job(tmp_path, data.path), **{field: value})
        )


def test_queue_finish_verifies_claim_and_is_idempotent(tmp_path: Path) -> None:
    data = snapshot(tmp_path)
    queued = job(tmp_path, data.path)
    stamps = iter(
        (
            datetime(2026, 8, 31, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 8, 31, 0, 1, tzinfo=timezone.utc),
            datetime(2026, 8, 31, 0, 2, tzinfo=timezone.utc),
        )
    )
    queue = ResearchQueue(tmp_path / "queue", clock=lambda: next(stamps))
    queue.enqueue(queued)
    claim = queue.claim_next("worker-1")
    result = ResearchRunResult(
        job_id=queued.job_id,
        disposition=ResearchDisposition.DEFERRED,
        status="production_active",
    )

    with pytest.raises(QueueConflictError, match="claim verification"):
        queue.finish(replace(claim, worker_id="forged-worker"), result)
    assert queue.finish(claim, result).status == "created"
    assert queue.finish(claim, result).status == "duplicate"


@pytest.mark.parametrize("domain", list(Domain))
def test_four_domain_adapters_use_same_frozen_command_for_both_roles(
    tmp_path: Path, domain: Domain
) -> None:
    frozen = spec(domain)
    adapter = create_research_adapter(domain)
    baseline = adapter.invocations(
        frozen,
        role="baseline",
        checkout=tmp_path / "baseline",
        dataset_path=tmp_path / "dataset" / "rows.jsonl",
        output_dir=tmp_path / "output" / "baseline",
    )
    candidate = adapter.invocations(
        frozen,
        role="candidate",
        checkout=tmp_path / "candidate",
        dataset_path=tmp_path / "dataset" / "rows.jsonl",
        output_dir=tmp_path / "output" / "candidate",
    )

    assert [item.argv for item in baseline] == [item.argv for item in candidate]
    assert baseline[0].env["WC_RESEARCH_ROLE"] == "baseline"
    assert candidate[0].env["WC_RESEARCH_ROLE"] == "candidate"
    assert baseline[0].env["WC_RESEARCH_DATASET"] == candidate[0].env[
        "WC_RESEARCH_DATASET"
    ]
    assert baseline[0].env["PYTHONHASHSEED"] == str(frozen.seed)
    assert baseline[0].env["TZ"] == "UTC"


@pytest.mark.parametrize("domain", list(Domain))
def test_four_domain_contract_fixtures_run_end_to_end(
    tmp_path: Path, domain: Domain
) -> None:
    domain_root = tmp_path / domain.value
    domain_root.mkdir()
    data = snapshot(domain_root, domain)
    executor = DeterministicExecutor()
    run_runtime = runtime(domain_root, executor=executor)

    result = registered_runner(domain_root, run_runtime, domain).run(
        job(domain_root, data.path, domain),
        spec(domain),
        create_research_adapter(domain),
    )

    assert result.disposition is ResearchDisposition.SUCCEEDED
    assert [call.role for call in executor.calls] == ["baseline", "candidate"]


def test_successful_run_is_reproducible_and_registers_frozen_evidence(
    tmp_path: Path,
) -> None:
    data = snapshot(tmp_path)
    executor = DeterministicExecutor()
    run_runtime = runtime(tmp_path, executor=executor)
    runner = registered_runner(tmp_path, run_runtime)
    research_job = job(tmp_path, data.path)

    result = runner.run(research_job, spec(), create_research_adapter(Domain.AU))

    assert result.disposition is ResearchDisposition.SUCCEEDED
    assert result.artifact_path is not None and result.artifact_path.is_dir()
    assert not list(run_runtime.warm_root.rglob("*.partial-*"))
    assert [call.role for call in executor.calls] == ["baseline", "candidate"]
    expected_metrics = {
        "baseline": [{"metric": 0.5, "role": "baseline"}],
        "candidate": [{"metric": 0.5, "role": "candidate"}],
    }
    assert result.reproducibility_digest == canonical_digest(expected_metrics)
    registry = ExperimentRegistry(tmp_path / "registry")
    run_payload = registry.load(result.experiment_run_id)
    assert run_payload["kind"] == ResearchKind.EXPERIMENT_RUN.value
    assert run_payload["metrics_digest"] == result.reproducibility_digest
    assert run_payload["baseline_commit"] == BASELINE
    assert run_payload["candidate_commit"] == CANDIDATE


def test_two_jobs_with_same_spec_and_dataset_have_same_result_digest(
    tmp_path: Path,
) -> None:
    data = snapshot(tmp_path)
    run_runtime = runtime(tmp_path, executor=DeterministicExecutor())
    runner = registered_runner(tmp_path, run_runtime)
    first = job(tmp_path, data.path)
    second = replace(first, job_id="wc:au:research-job:fixture-002")

    first_result = runner.run(first, spec(), create_research_adapter("au"))
    second_result = runner.run(second, spec(), create_research_adapter("au"))

    assert first_result.disposition is ResearchDisposition.SUCCEEDED
    assert second_result.disposition is ResearchDisposition.SUCCEEDED
    assert first_result.reproducibility_digest == second_result.reproducibility_digest


def test_active_production_lock_defers_without_creating_scratch(tmp_path: Path) -> None:
    data = snapshot(tmp_path)
    lock_path = tmp_path / "production.lock"
    lock_path.touch()
    executor = DeterministicExecutor()
    with lock_path.open("a", encoding="utf-8") as held:
        fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        run_runtime = runtime(
            tmp_path, executor=executor, production_locks=(lock_path,)
        )
        runner = registered_runner(tmp_path, run_runtime)
        result = runner.run(job(tmp_path, data.path), spec(), create_research_adapter("au"))

    assert result.disposition is ResearchDisposition.DEFERRED
    assert result.status == "production_active"
    assert executor.calls == []
    assert not list(run_runtime.warm_root.iterdir())


def test_warm_offline_and_insufficient_capacity_defer(tmp_path: Path) -> None:
    data = snapshot(tmp_path)
    research_job = job(tmp_path, data.path)
    offline_runtime = runtime(tmp_path)
    offline_runtime.warm_root.rmdir()
    offline = registered_runner(tmp_path, offline_runtime).run(
        research_job, spec(), create_research_adapter("au")
    )

    low_space_root = tmp_path / "low-space"
    low_space_root.mkdir()
    low_space_runtime = runtime(low_space_root, free_bytes=1500)
    low_space = registered_runner(low_space_root, low_space_runtime).run(
        replace(
            research_job,
            baseline_checkout=low_space_root / "baseline",
            candidate_checkout=low_space_root / "candidate",
        ),
        spec(),
        create_research_adapter("au"),
    )

    assert offline.status == "warm_offline"
    assert low_space.status == "insufficient_capacity"
    assert offline.disposition is ResearchDisposition.DEFERRED
    assert low_space.disposition is ResearchDisposition.DEFERRED


def test_checkout_commit_mismatch_blocks_before_execution(tmp_path: Path) -> None:
    data = snapshot(tmp_path)
    executor = DeterministicExecutor()
    run_runtime = replace(
        runtime(tmp_path, executor=executor), checkout_probe=lambda _path: "c" * 40
    )
    result = registered_runner(tmp_path, run_runtime).run(
        job(tmp_path, data.path), spec(), create_research_adapter("au")
    )

    assert result.disposition is ResearchDisposition.BLOCKED
    assert result.status == "checkout_commit_mismatch"
    assert executor.calls == []


def test_timeout_cleans_partial_and_records_failed_run(tmp_path: Path) -> None:
    data = snapshot(tmp_path)
    run_runtime = runtime(tmp_path, executor=TimeoutExecutor())
    runner = registered_runner(tmp_path, run_runtime)

    result = runner.run(job(tmp_path, data.path), spec(), create_research_adapter("au"))

    assert result.disposition is ResearchDisposition.TIMED_OUT
    assert result.status == "command_timeout"
    assert not list(run_runtime.warm_root.rglob("*.partial-*"))
    assert result.artifact_path is not None
    cleanup = json.loads((result.artifact_path / "cleanup.json").read_text())
    assert cleanup["removed_partial"] is True
    run_payload = ExperimentRegistry(tmp_path / "registry").load(
        result.experiment_run_id
    )
    assert run_payload["state"] == "failed"


@pytest.mark.parametrize(
    ("executor", "disposition", "status", "run_state"),
    [
        (
            PreemptedExecutor(),
            ResearchDisposition.PREEMPTED,
            "production_preempted",
            "blocked",
        ),
        (
            ExplodingExecutor(),
            ResearchDisposition.FAILED,
            "executor_exception",
            "failed",
        ),
    ],
)
def test_preemption_and_executor_exception_cleanup_and_record_evidence(
    tmp_path: Path,
    executor,
    disposition: ResearchDisposition,
    status: str,
    run_state: str,
) -> None:
    data = snapshot(tmp_path)
    run_runtime = runtime(tmp_path, executor=executor)
    result = registered_runner(tmp_path, run_runtime).run(
        job(tmp_path, data.path), spec(), create_research_adapter("au")
    )

    assert result.disposition is disposition
    assert result.status == status
    assert not list(run_runtime.warm_root.rglob("*.partial-*"))
    assert result.artifact_path is not None
    assert (result.artifact_path / "cleanup.json").is_file()
    run_payload = ExperimentRegistry(tmp_path / "registry").load(
        result.experiment_run_id
    )
    assert run_payload["state"] == run_state


def test_checkout_change_during_run_fails_closed(tmp_path: Path) -> None:
    data = snapshot(tmp_path)
    executor = DeterministicExecutor()
    calls = {"baseline": 0, "candidate": 0}

    def changing_probe(path: Path) -> str:
        calls[path.name] += 1
        if calls[path.name] > 1:
            return "c" * 40
        return BASELINE if path.name == "baseline" else CANDIDATE

    run_runtime = replace(
        runtime(tmp_path, executor=executor), checkout_probe=changing_probe
    )
    result = registered_runner(tmp_path, run_runtime).run(
        job(tmp_path, data.path), spec(), create_research_adapter("au")
    )

    assert result.disposition is ResearchDisposition.BLOCKED
    assert result.status == "checkout_changed_during_run"
    assert not list(run_runtime.warm_root.rglob("*.partial-*"))


@pytest.mark.parametrize(
    ("executor_factory", "status"),
    [
        (lambda tmp: DatasetMutatingExecutor(), "dataset_changed_during_run"),
        (
            lambda tmp: SymlinkMetricsExecutor(tmp / "outside-metrics.json"),
            "unsafe_output_symlink",
        ),
    ],
)
def test_dataset_mutation_and_output_symlink_fail_closed(
    tmp_path: Path, executor_factory, status: str
) -> None:
    data = snapshot(tmp_path)
    run_runtime = runtime(tmp_path, executor=executor_factory(tmp_path))
    result = registered_runner(tmp_path, run_runtime).run(
        job(tmp_path, data.path), spec(), create_research_adapter("au")
    )

    assert result.disposition is ResearchDisposition.BLOCKED
    assert result.status == status
    assert not list(run_runtime.warm_root.rglob("*.partial-*"))
    assert result.artifact_path is not None
    assert (result.artifact_path / "cleanup.json").is_file()


def test_real_executor_terminates_timed_out_process_group(tmp_path: Path) -> None:
    adapter = create_research_adapter("au")
    frozen = replace(
        spec(),
        commands=(
            f"{sys.executable} -c 'import time; time.sleep(5)'",
        ),
    )
    invocation = adapter.invocations(
        frozen,
        role="baseline",
        checkout=tmp_path,
        dataset_path=tmp_path / "rows.jsonl",
        output_dir=tmp_path / "output",
    )[0]
    invocation.output_dir.mkdir(parents=True)
    executor = SubprocessResearchExecutor(poll_seconds=0.02, terminate_grace=0.05)

    result = executor.run(
        invocation, timeout_seconds=0.1, production_active=lambda: False
    )

    assert result.state is CommandState.TIMED_OUT
    assert result.returncode is not None
    assert result.wall_seconds < 2


def test_real_executor_preempts_when_production_starts(tmp_path: Path) -> None:
    adapter = create_research_adapter("au")
    frozen = replace(
        spec(), commands=(f"{sys.executable} -c 'import time; time.sleep(5)'",)
    )
    invocation = adapter.invocations(
        frozen,
        role="baseline",
        checkout=tmp_path,
        dataset_path=tmp_path / "rows.jsonl",
        output_dir=tmp_path / "output",
    )[0]
    invocation.output_dir.mkdir(parents=True)
    polls = {"count": 0}

    def production_active() -> bool:
        polls["count"] += 1
        return polls["count"] >= 2

    result = SubprocessResearchExecutor(
        poll_seconds=0.02, terminate_grace=0.05
    ).run(invocation, timeout_seconds=5, production_active=production_active)

    assert result.state is CommandState.PREEMPTED
    assert result.wall_seconds < 2


def test_real_executor_fails_closed_if_production_probe_errors(tmp_path: Path) -> None:
    adapter = create_research_adapter("au")
    frozen = replace(
        spec(), commands=(f"{sys.executable} -c 'import time; time.sleep(5)'",)
    )
    invocation = adapter.invocations(
        frozen,
        role="baseline",
        checkout=tmp_path,
        dataset_path=tmp_path / "rows.jsonl",
        output_dir=tmp_path / "output",
    )[0]
    invocation.output_dir.mkdir(parents=True)

    def broken_probe() -> bool:
        raise OSError("lock filesystem unavailable")

    result = SubprocessResearchExecutor(
        poll_seconds=0.02, terminate_grace=0.05
    ).run(invocation, timeout_seconds=5, production_active=broken_probe)

    assert result.state is CommandState.PREEMPTED
    assert result.wall_seconds < 2


def test_heavy_worker_lock_allows_only_one_runner(tmp_path: Path) -> None:
    data = snapshot(tmp_path)
    run_runtime = runtime(tmp_path)
    heavy_lock = run_runtime.state_root / "locks" / "research-heavy-worker.lock"
    heavy_lock.parent.mkdir(parents=True)
    heavy_lock.touch()
    with heavy_lock.open("a", encoding="utf-8") as held:
        fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = registered_runner(tmp_path, run_runtime).run(
            job(tmp_path, data.path), spec(), create_research_adapter("au")
        )

    assert result.disposition is ResearchDisposition.DEFERRED
    assert result.status == "heavy_worker_busy"


def test_shared_runner_does_not_import_any_domain_engine() -> None:
    module_path = PACKAGE_ROOT / "research_runner.py"
    source = module_path.read_text(encoding="utf-8")

    for forbidden in (
        "au_racing_engine",
        "hkjc_racing_engine",
        "tennis_wc",
        "nba_wong_choi",
        "MATRIX_WEIGHTS",
    ):
        assert forbidden not in source
