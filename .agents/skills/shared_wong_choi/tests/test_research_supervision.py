from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared_wong_choi.artifact_archive import artifact_digest
from shared_wong_choi.contracts import Domain
from shared_wong_choi.research_dataset import DatasetSource, SplitPolicy, StorageTier, load_dataset_snapshot
from shared_wong_choi.research_registry import ExperimentRegistry
from shared_wong_choi.research_runner import (
    ResearchJob,
    ResearchDisposition,
    ResearchRuntime,
    SubprocessResearchExecutor,
    create_research_adapter,
)
from shared_wong_choi.research_supervision import (
    AuFeatureProvenanceInspectionRunner,
    AuSettlementCandidateInspectionRunner,
    HkjcFeatureProvenanceInspectionRunner,
    HkjcSettlementCandidateInspectionRunner,
    NbaFeatureProvenanceInspectionRunner,
    NbaMonitoringSampleInspectionRunner,
    NbaSettlementCandidateInspectionRunner,
    PredictionArtifactInspectionRunner,
    RacingMonitoringSampleInspectionRunner,
    PowerDevEngineRunner,
    PowerDevProducerRunner,
    PowerProjectionRunner,
    PowerVarianceInspectionRunner,
    ResearchPreparationRunner,
    ResearchScoringRunner,
    ResearchStorageEvidenceInspectionRunner,
    ResearchLivenessInspectionRunner,
    ResearchProductionDayInspectionRunner,
    ResearchLiveDriftInspectionRunner,
    TennisFeatureProvenanceInspectionRunner,
    TennisMonitoringSampleInspectionRunner,
    TennisSettlementCandidateInspectionRunner,
    TennisSourceInspectionRunner,
)
from shared_wong_choi.research_resources import ResearchWorkflow
from test_research_postflight import real_checkout_fixture
from test_research_runner import configured_queue, job, spec, snapshot
from shared_wong_choi.research_liveness import (
    probe_process_start_token,
    record_research_liveness_lease,
)
from test_research_tennis_source import fixture as source_fixture
from test_research_tennis_witness import fixture as witness_fixture
from test_research_prediction_artifacts import NOW as ARTIFACT_NOW
from test_research_prediction_artifacts import fixture as prediction_artifact_fixture
from test_research_au_settlement_source import END as AU_SETTLEMENT_END
from test_research_au_settlement_source import settled_fixture as au_settled_fixture
from test_research_au_feature_provenance import AS_OF as AU_FEATURE_AS_OF
from test_research_au_feature_provenance import fixture as au_feature_fixture
from test_research_nba_settlement_source import END as NBA_SETTLEMENT_END
from test_research_nba_settlement_source import settled_fixture as nba_settled_fixture
from test_research_nba_feature_provenance import AS_OF as NBA_FEATURE_AS_OF
from test_research_nba_feature_provenance import fixture as nba_feature_fixture
from test_research_hkjc_settlement_source import END as HKJC_SETTLEMENT_END
from test_research_hkjc_settlement_source import settled_fixture as hkjc_settled_fixture
from test_research_hkjc_feature_provenance import AS_OF as HKJC_FEATURE_AS_OF
from test_research_hkjc_feature_provenance import fixture as hkjc_feature_fixture
from test_research_tennis_settlement_source import END as TENNIS_SETTLEMENT_END
from test_research_tennis_settlement_source import settled_fixture as tennis_settled_fixture
from test_research_tennis_feature_provenance import AS_OF as TENNIS_FEATURE_AS_OF
from test_research_tennis_feature_provenance import fixture as tennis_feature_fixture
from test_research_power_variance import AS_OF as POWER_VARIANCE_AS_OF
from test_research_power_variance import _payload as power_variance_payload
from test_research_power_variance import _write as write_power_variance
from test_research_power_projection import AS_OF as POWER_PROJECTION_AS_OF
from test_research_power_projection import write_artifacts as write_power_projection_artifacts
from test_research_power_dev_producer import AS_OF as POWER_DEV_AS_OF
from test_research_power_dev_producer import setup_inputs as power_dev_inputs
from test_research_racing_monitoring_samples import _au_source as racing_au_source
from test_research_racing_monitoring_samples import _hkjc_source as racing_hkjc_source
from test_research_tennis_monitoring_samples import settled_source as tennis_sample_source
from test_research_production_day import (
    AS_OF as PRODUCTION_DAY_AS_OF,
    DAY as PRODUCTION_DAY,
    _attestation as production_day_attestation,
    _terminal_runs as production_day_runs,
)


def fixture(tmp_path, command_script=None):
    dataset = snapshot(tmp_path)
    current_job = job(tmp_path, dataset.path)
    commits = []
    for folder in (current_job.baseline_checkout, current_job.candidate_checkout):
        (folder / "evaluate.py").write_text(
            command_script
            or "import os,json; from pathlib import Path; "
            "Path(os.environ['WC_RESEARCH_METRICS_PATH']).write_text(json.dumps({'metric': .5}))\n"
        )
        for command in (
            ["init", "-q"],
            ["add", "evaluate.py"],
            [
                "-c",
                "user.name=Research Test",
                "-c",
                "user.email=research@example.invalid",
                "commit",
                "-qm",
                folder.name,
            ],
        ):
            subprocess.run(["git", "-C", str(folder), *command], check=True, capture_output=True)
        commits.append(subprocess.check_output(["git", "-C", str(folder), "rev-parse", "HEAD"], text=True).strip())
    current_spec = replace(spec(), baseline_commit=commits[0], candidate_commit=commits[1])
    registry = ExperimentRegistry(tmp_path / "registry")
    registry.append(current_spec)
    warm = tmp_path / "warm"
    warm.mkdir()
    runtime = ResearchRuntime(
        state_root=tmp_path / "state",
        warm_root=warm,
        production_lock_paths=(tmp_path / "production.lock",),
        executor=SubprocessResearchExecutor(poll_seconds=0.02, terminate_grace=0.1),
    )
    from research_test_support import pin_review
    pin_review(runtime, registry, current_spec)
    return current_spec, current_job, runtime, registry


def source_runtime(tmp_path):
    warm = tmp_path / "warm"
    warm.mkdir()
    return ResearchRuntime(
        state_root=tmp_path / "state",
        warm_root=warm,
        production_lock_paths=(tmp_path / "production.lock",),
        executor=SubprocessResearchExecutor(poll_seconds=0.02, terminate_grace=0.1),
    )


def test_live_drift_projection_runs_under_parent_supervision(tmp_path):
    runtime = source_runtime(tmp_path)
    registry = ExperimentRegistry(tmp_path / "registry")
    evidence = tmp_path / "evidence"
    (evidence / "records").mkdir(parents=True)

    result = ResearchLiveDriftInspectionRunner(runtime, registry).run(
        domain=Domain.AU,
        evidence_root=evidence,
        baseline_as_of=datetime(2026, 9, 1, tzinfo=timezone.utc),
        as_of=datetime(2026, 9, 4, tzinfo=timezone.utc),
        estimated_bytes=1024,
        timeout_seconds=10,
    )

    assert result.disposition is ResearchDisposition.SUCCEEDED
    assert result.status == "research_live_drift_projection"
    payload = json.loads(result.report_path.read_text())
    assert payload["status"] == "insufficient_data"
    assert payload["live_drift_verified"] is False
    assert payload["metric_drift_verified"] is False
    assert payload["market_drift_verified"] is False
    assert payload["model_promotion_allowed"] is False


def test_live_drift_defers_before_source_read_when_production_active(tmp_path):
    runtime = source_runtime(tmp_path)
    registry = ExperimentRegistry(tmp_path / "registry")
    handle = runtime.production_lock_paths[0].open("a")
    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        result = ResearchLiveDriftInspectionRunner(runtime, registry).run(
            domain=Domain.TENNIS,
            evidence_root=tmp_path / "must-not-open",
            baseline_as_of=datetime(2026, 9, 1, tzinfo=timezone.utc),
            as_of=datetime(2026, 9, 4, tzinfo=timezone.utc),
            estimated_bytes=1024,
            timeout_seconds=10,
        )
    finally:
        handle.close()

    assert result.disposition is ResearchDisposition.DEFERRED
    assert result.report_path is None


def test_power_variance_runs_supervised_without_writing_profile_or_sample(tmp_path):
    source = write_power_variance(tmp_path, power_variance_payload())
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    result = PowerVarianceInspectionRunner(runtime, registry).run(
        domain=Domain.AU,
        input_path=source,
        as_of=POWER_VARIANCE_AS_OF,
        estimated_bytes=1024,
        timeout_seconds=10,
    )
    assert result.disposition is ResearchDisposition.SUCCEEDED
    assert result.status == "power_variance_description_only"
    payload = json.loads(result.report_path.read_text())
    assert payload["variance_input_contract_verified"] is True
    assert payload["power_profile_write_allowed"] is False
    assert payload["verified_monitoring_samples"] is None
    assert payload["model_promotion_allowed"] is False
    assert result.content_hash == payload["content_hash"]
    assert not registry.root.exists(), "variance evidence cannot fabricate research records"


def test_power_projection_runs_supervised_inside_owned_attempt_without_registry_writes(tmp_path):
    baseline, comparator = write_power_projection_artifacts(tmp_path)
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    result = PowerProjectionRunner(runtime, registry).run(
        domain=Domain.AU,
        baseline_path=baseline,
        comparator_path=comparator,
        as_of=POWER_PROJECTION_AS_OF,
        estimated_bytes=1024,
        timeout_seconds=10,
    )
    assert result.disposition is ResearchDisposition.SUCCEEDED
    assert result.status == "power_projection_dev_only"
    assert result.report_path.is_relative_to(result.attempt_path)
    payload = json.loads(result.report_path.read_text())
    assert payload["source_role"] == "development_only"
    assert payload["engine_evidence"]["baseline_artifact_sha256"]
    assert result.content_hash
    assert not registry.root.exists(), "projection cannot fabricate research records"


def test_power_dev_producer_blocks_unattested_external_metrics(tmp_path):
    _spec, snapshot, _metrics, metrics_path, _variant, variant_path, protocol_path = (
        power_dev_inputs(tmp_path)
    )
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "producer-registry")
    result = PowerDevProducerRunner(runtime, registry).run(
        domain=Domain.AU,
        role="baseline",
        metrics_path=metrics_path,
        dataset_snapshot=snapshot.path,
        variant_manifest_path=variant_path,
        protocol_path=protocol_path,
        engine_commit="a" * 40,
        command_argv=("python3", "reviewed-domain-adapter.py"),
        generated_at=POWER_DEV_AS_OF,
        estimated_bytes=1024,
        timeout_seconds=10,
    )
    assert result.disposition is ResearchDisposition.BLOCKED
    assert result.status == "label_safe_domain_callback_required"
    assert result.report_path is None
    assert not (result.attempt_path / "phase-work" / "baseline-dev-observations.json").exists()
    assert not registry.root.exists(), "producer cannot fabricate research records"


def test_power_dev_producer_defers_before_metrics_or_dataset_read_when_production_active(tmp_path):
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    handle = runtime.production_lock_paths[0].open("a")
    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        result = PowerDevProducerRunner(runtime, registry).run(
            domain=Domain.HKJC,
            role="baseline",
            metrics_path=tmp_path / "must-not-open-metrics",
            dataset_snapshot=tmp_path / "must-not-open-dataset",
            variant_manifest_path=tmp_path / "must-not-open-variant",
            protocol_path=tmp_path / "must-not-open-protocol",
            engine_commit="a" * 40,
            command_argv=("python3", "reviewed-domain-adapter.py"),
            generated_at=POWER_DEV_AS_OF,
            estimated_bytes=1024,
            timeout_seconds=10,
        )
    finally:
        handle.close()
    assert result.disposition is ResearchDisposition.DEFERRED
    assert result.report_path is None


@pytest.mark.parametrize("action", ["engine", "producer"])
def test_parent_rejects_forged_legacy_power_success_receipt(tmp_path, action):
    class ForgedSuccess(SubprocessResearchExecutor):
        def run(self, invocation, *, timeout_seconds, production_active):
            execution = super().run(
                invocation,
                timeout_seconds=timeout_seconds,
                production_active=production_active,
            )
            invocation.metrics_path.write_text(
                json.dumps({"disposition": "succeeded", "status": "forged"}) + "\n"
            )
            return execution

    runtime = replace(
        source_runtime(tmp_path),
        executor=ForgedSuccess(poll_seconds=0.02, terminate_grace=0.1),
    )
    registry = ExperimentRegistry(tmp_path / "forged-registry")
    if action == "engine":
        snapshot, checkout, commit, variant_path, protocol_path = power_engine_fixture(
            tmp_path / "fixture"
        )
        result = PowerDevEngineRunner(runtime, registry).run(
            domain=Domain.AU,
            role="baseline",
            checkout=checkout,
            engine_commit=commit,
            command_argv=(sys.executable, "emit_dev.py"),
            dataset_snapshot=snapshot.path,
            variant_manifest_path=variant_path,
            protocol_path=protocol_path,
            generated_at=POWER_DEV_AS_OF,
            estimated_bytes=1024,
            timeout_seconds=10,
        )
    else:
        _, snapshot, _, metrics_path, _, variant_path, protocol_path = power_dev_inputs(
            tmp_path / "fixture"
        )
        result = PowerDevProducerRunner(runtime, registry).run(
            domain=Domain.AU,
            role="baseline",
            metrics_path=metrics_path,
            dataset_snapshot=snapshot.path,
            variant_manifest_path=variant_path,
            protocol_path=protocol_path,
            engine_commit="a" * 40,
            command_argv=("python3", "reviewed-domain-adapter.py"),
            generated_at=POWER_DEV_AS_OF,
            estimated_bytes=1024,
            timeout_seconds=10,
        )
    assert result.disposition is ResearchDisposition.FAILED
    outcome = json.loads((result.attempt_path / "phase-outcome.json").read_text())
    assert result.status == "ValueError: legacy power dev automation is disabled"
    assert outcome["result"] is None


def power_engine_fixture(tmp_path, domain=Domain.AU, *, mutate_variant=False):
    source = tmp_path / "source"
    _spec, snapshot, _metrics, _metrics_path, variant, variant_path, protocol_path = (
        power_dev_inputs(source, domain=domain)
    )
    checkout = tmp_path / "engine"
    checkout.mkdir()
    script = '''
import json, os
from pathlib import Path
assert "WC_POWER_DATASET_SNAPSHOT" not in os.environ
rows = [json.loads(line) for line in Path(os.environ["WC_POWER_DEV_ROWS"]).read_text().splitlines()]
assert rows and all(row["split"] == "dev" for row in rows)
values = {
    "gold": 0.0, "good_positional": 1.0, "top3_capture_at5": 0.6,
    "mean_top3_model_rank": 3.0, "competitive_recall_at5": 0.5,
    "ndcg_at5": 0.7, "top5_pairwise_auc": 0.65,
}
payload = {
    "schema_version": "wong-choi-evaluation-observations/v1",
    "domain": os.environ["WC_POWER_DOMAIN"],
    "sample_hash": os.environ["WC_POWER_SAMPLE_HASH"],
    "dataset_manifest_id": os.environ["WC_POWER_DATASET_MANIFEST_ID"],
    "dataset_artifact_digest": os.environ["WC_POWER_DATASET_ARTIFACT_DIGEST"],
    "observations": [
        {"row_id": row["row_id"], "event_at": row["event_at"], "split": "dev",
         "fold": row["payload"]["fold"], "cohorts": row["payload"]["cohorts"],
         "metrics": values}
        for row in rows
    ],
}
Path(os.environ["WC_POWER_METRICS_PATH"]).write_text(json.dumps(payload, sort_keys=True) + "\\n")
'''
    if mutate_variant:
        script = script.replace(
            'assert "WC_POWER_DATASET_SNAPSHOT" not in os.environ',
            'Path(os.environ["WC_POWER_VARIANT_MANIFEST"]).write_text("{}\\n")\n'
            'assert "WC_POWER_DATASET_SNAPSHOT" not in os.environ',
        )
    (checkout / "emit_dev.py").write_text(script)
    for command in (
        ["init", "-q"],
        ["add", "emit_dev.py"],
        ["-c", "user.name=Research Test", "-c", "user.email=research@example.invalid",
         "commit", "-qm", "frozen dev adapter"],
    ):
        subprocess.run(["git", "-C", str(checkout), *command], check=True, capture_output=True)
    commit = subprocess.check_output(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True
    ).strip()
    variant["engine_commit"] = commit
    variant_path.write_text(json.dumps(variant, sort_keys=True) + "\n")
    return snapshot, checkout, commit, variant_path, protocol_path


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
def test_power_dev_engine_blocks_until_domain_label_safe_callback_exists(tmp_path, domain):
    snapshot, checkout, commit, variant_path, protocol_path = power_engine_fixture(
        tmp_path, domain
    )
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "engine-registry")
    result = PowerDevEngineRunner(runtime, registry).run(
        domain=domain,
        role="baseline",
        checkout=checkout,
        engine_commit=commit,
        command_argv=(sys.executable, "emit_dev.py"),
        dataset_snapshot=snapshot.path,
        variant_manifest_path=variant_path,
        protocol_path=protocol_path,
        generated_at=POWER_DEV_AS_OF,
        estimated_bytes=4096,
        timeout_seconds=10,
    )
    assert result.disposition is ResearchDisposition.BLOCKED
    assert result.status == "label_safe_domain_callback_required"
    assert result.report_path is None
    assert not (result.attempt_path / "phase-work" / "engine-command").exists()
    assert not registry.root.exists()


def test_power_dev_engine_blocks_before_checkout_or_dataset_access(tmp_path):
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "engine-registry")
    result = PowerDevEngineRunner(runtime, registry).run(
        domain=Domain.AU,
        role="baseline",
        checkout=tmp_path / "must-not-open-checkout",
        engine_commit="f" * 40,
        command_argv=(sys.executable, "emit_dev.py"),
        dataset_snapshot=tmp_path / "must-not-open-dataset",
        variant_manifest_path=tmp_path / "must-not-open-variant",
        protocol_path=tmp_path / "must-not-open-protocol",
        generated_at=POWER_DEV_AS_OF,
        estimated_bytes=4096,
        timeout_seconds=10,
    )
    assert result.disposition is ResearchDisposition.BLOCKED
    assert result.status == "label_safe_domain_callback_required"
    assert result.report_path is None


def test_power_dev_engine_defers_before_checkout_or_dataset_when_production_active(tmp_path):
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    handle = runtime.production_lock_paths[0].open("a")
    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        result = PowerDevEngineRunner(runtime, registry).run(
            domain=Domain.AU,
            role="baseline",
            checkout=tmp_path / "must-not-open-checkout",
            engine_commit="a" * 40,
            command_argv=(sys.executable, "emit_dev.py"),
            dataset_snapshot=tmp_path / "must-not-open-dataset",
            variant_manifest_path=tmp_path / "must-not-open-variant",
            protocol_path=tmp_path / "must-not-open-protocol",
            generated_at=POWER_DEV_AS_OF,
            estimated_bytes=4096,
            timeout_seconds=10,
        )
    finally:
        handle.close()
    assert result.disposition is ResearchDisposition.DEFERRED
    assert result.report_path is None


def test_power_dev_engine_never_runs_legacy_mutating_command(tmp_path):
    snapshot, checkout, commit, variant_path, protocol_path = power_engine_fixture(
        tmp_path, mutate_variant=True
    )
    original_variant = variant_path.read_bytes()
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "engine-registry")
    result = PowerDevEngineRunner(runtime, registry).run(
        domain=Domain.AU,
        role="baseline",
        checkout=checkout,
        engine_commit=commit,
        command_argv=(sys.executable, "emit_dev.py"),
        dataset_snapshot=snapshot.path,
        variant_manifest_path=variant_path,
        protocol_path=protocol_path,
        generated_at=POWER_DEV_AS_OF,
        estimated_bytes=4096,
        timeout_seconds=10,
    )
    assert result.disposition is ResearchDisposition.BLOCKED
    assert result.status == "label_safe_domain_callback_required"
    assert not (result.attempt_path / "phase-work" / "engine-command").exists()
    assert variant_path.read_bytes() == original_variant


def test_power_projection_defers_before_source_read_when_production_active(tmp_path):
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    handle = runtime.production_lock_paths[0].open("a")
    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        result = PowerProjectionRunner(runtime, registry).run(
            domain=Domain.AU,
            baseline_path=tmp_path / "must-not-open-baseline",
            comparator_path=tmp_path / "must-not-open-comparator",
            as_of=POWER_PROJECTION_AS_OF,
            estimated_bytes=1024,
            timeout_seconds=10,
        )
    finally:
        handle.close()
    assert result.disposition is ResearchDisposition.DEFERRED
    assert result.report_path is None


def test_power_variance_defers_before_source_read_when_production_active(tmp_path):
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    handle = runtime.production_lock_paths[0].open("a")
    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        result = PowerVarianceInspectionRunner(runtime, registry).run(
            domain=Domain.AU,
            input_path=tmp_path / "must-not-open",
            as_of=POWER_VARIANCE_AS_OF,
            estimated_bytes=1024,
            timeout_seconds=10,
        )
    finally:
        handle.close()
    assert result.disposition is ResearchDisposition.DEFERRED
    assert result.report_path is None


def test_source_inventory_runs_before_spec_without_registering_any_experiment(tmp_path):
    db, policy = source_fixture(tmp_path)
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    result = TennisSourceInspectionRunner(runtime, registry).run(db, policy, estimated_bytes=1024, timeout_seconds=10)
    assert result.disposition is ResearchDisposition.SUCCEEDED
    assert result.report_path.is_relative_to(runtime.warm_root)
    payload = json.loads(result.report_path.read_text())
    assert len(payload["rows"]) == 1 and payload["pit_dataset_ready"] is False
    assert result.content_hash == payload["content_hash"]
    assert not registry.root.exists(), "inventory cannot fabricate spec/dataset/run/decision records"


def test_prediction_bundle_resolution_runs_supervised_without_registering_experiment(tmp_path):
    evidence, meeting, snapshot, _ = prediction_artifact_fixture(tmp_path)
    archive = tmp_path / "archive"
    relocated = archive / meeting.name / snapshot.relative_to(meeting)
    relocated.parent.mkdir(parents=True)
    snapshot.rename(relocated)
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    result = PredictionArtifactInspectionRunner(runtime, registry).run(
        domain=Domain.AU,
        evidence_root=evidence, as_of=ARTIFACT_NOW, relocation_roots=(archive,),
        estimated_bytes=1024, timeout_seconds=10,
    )
    assert result.disposition is ResearchDisposition.SUCCEEDED
    assert result.status == "prediction_artifact_inventory_only"
    payload = json.loads(result.report_path.read_text())
    assert payload["artifact_contents_verified"] is True
    assert payload["relocated_verified"] == 3 and payload["normalized_source_verified"] is False
    assert result.content_hash == payload["content_hash"] and not registry.root.exists()


def test_au_settlement_candidate_inventory_is_supervised_and_never_registers_sample(tmp_path):
    evidence, _meeting, _snapshot, _result = au_settled_fixture(tmp_path, evidence_result=True)
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    result = AuSettlementCandidateInspectionRunner(runtime, registry).run(
        evidence_root=evidence,
        as_of=AU_SETTLEMENT_END,
        estimated_bytes=1024,
        timeout_seconds=10,
    )
    assert result.disposition is ResearchDisposition.SUCCEEDED
    assert result.status == "au_settlement_candidate_inventory_only"
    payload = json.loads(result.report_path.read_text())
    assert payload["label_verified_settlements"] == 1
    assert payload["verified_monitoring_samples"] is None
    assert result.content_hash == payload["content_hash"]
    assert not registry.root.exists(), "label inventory cannot fabricate research records"


def test_au_settlement_candidate_inventory_defers_before_source_read_when_production_active(tmp_path):
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    handle = runtime.production_lock_paths[0].open("a")
    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        result = AuSettlementCandidateInspectionRunner(runtime, registry).run(
            evidence_root=tmp_path / "must-not-open",
            as_of=AU_SETTLEMENT_END,
            estimated_bytes=1024,
            timeout_seconds=10,
        )
    finally:
        handle.close()
    assert result.disposition is ResearchDisposition.DEFERRED
    assert result.report_path is None


@pytest.mark.parametrize(
    ("domain", "source"),
    [(Domain.AU, racing_au_source), (Domain.HKJC, racing_hkjc_source)],
)
def test_racing_monitoring_samples_run_supervised_and_only_register_clock_units(
        tmp_path, domain, source):
    evidence, as_of, _result = source(tmp_path)
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    result = RacingMonitoringSampleInspectionRunner(runtime, registry).run(
        domain=domain,
        evidence_root=evidence,
        as_of=as_of,
        estimated_bytes=1024,
        timeout_seconds=10,
    )

    assert result.disposition is ResearchDisposition.SUCCEEDED
    assert result.status == "racing_monitoring_sample_projection"
    payload = json.loads(result.report_path.read_text())
    assert payload["verified_monitoring_samples"] == 1
    assert payload["terminal_labels_emitted"] is False
    assert payload["model_promotion_allowed"] is False
    assert result.content_hash == payload["content_hash"]
    assert not registry.root.exists(), "sample clock projection cannot fabricate research records"


def test_racing_monitoring_samples_defer_before_source_read_when_production_active(tmp_path):
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    handle = runtime.production_lock_paths[0].open("a")
    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        result = RacingMonitoringSampleInspectionRunner(runtime, registry).run(
            domain=Domain.AU,
            evidence_root=tmp_path / "must-not-open",
            as_of=AU_SETTLEMENT_END,
            estimated_bytes=1024,
            timeout_seconds=10,
        )
    finally:
        handle.close()
    assert result.disposition is ResearchDisposition.DEFERRED
    assert result.report_path is None


def test_nba_monitoring_samples_run_supervised_without_registering_model_authority(tmp_path):
    evidence, _day, _snapshot, _verification = nba_settled_fixture(
        tmp_path, research_projection=True,
    )
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    result = NbaMonitoringSampleInspectionRunner(runtime, registry).run(
        evidence_root=evidence,
        as_of=NBA_SETTLEMENT_END,
        estimated_bytes=1024,
        timeout_seconds=10,
    )

    assert result.disposition is ResearchDisposition.SUCCEEDED
    assert result.status == "nba_monitoring_sample_projection"
    payload = json.loads(result.report_path.read_text())
    assert payload["verified_monitoring_samples"] == 1
    assert payload["terminal_labels_emitted"] is False
    assert payload["model_promotion_allowed"] is False
    assert result.content_hash == payload["content_hash"]
    assert not registry.root.exists()


def test_nba_monitoring_samples_defer_before_source_read_when_production_active(tmp_path):
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    handle = runtime.production_lock_paths[0].open("a")
    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        result = NbaMonitoringSampleInspectionRunner(runtime, registry).run(
            evidence_root=tmp_path / "must-not-open",
            as_of=NBA_SETTLEMENT_END,
            estimated_bytes=1024,
            timeout_seconds=10,
        )
    finally:
        handle.close()
    assert result.disposition is ResearchDisposition.DEFERRED
    assert result.report_path is None


def test_tennis_monitoring_samples_run_supervised_and_keep_family_scope(tmp_path):
    evidence, _snapshot, _outcome = tennis_sample_source(tmp_path)
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    result = TennisMonitoringSampleInspectionRunner(runtime, registry).run(
        evidence_root=evidence,
        as_of=TENNIS_SETTLEMENT_END,
        estimated_bytes=1024,
        timeout_seconds=10,
    )

    assert result.disposition is ResearchDisposition.SUCCEEDED
    assert result.status == "tennis_monitoring_sample_projection"
    payload = json.loads(result.report_path.read_text())
    assert payload["families"] == ["match_winner_atp"]
    assert payload["verified_monitoring_samples"] == 1
    assert payload["terminal_labels_emitted"] is False
    assert payload["model_promotion_allowed"] is False
    assert result.content_hash == payload["content_hash"]
    assert not registry.root.exists()


def test_tennis_monitoring_samples_defer_before_source_read_when_production_active(tmp_path):
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    handle = runtime.production_lock_paths[0].open("a")
    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        result = TennisMonitoringSampleInspectionRunner(runtime, registry).run(
            evidence_root=tmp_path / "must-not-open",
            as_of=TENNIS_SETTLEMENT_END,
            estimated_bytes=1024,
            timeout_seconds=10,
        )
    finally:
        handle.close()
    assert result.disposition is ResearchDisposition.DEFERRED
    assert result.report_path is None


def test_storage_evidence_runs_supervised_and_keeps_other_health_unknown(
        tmp_path, monkeypatch):
    repo, storage_state = tmp_path / "repo", tmp_path / "storage-state"
    hot, warm = tmp_path / "hot", tmp_path / "warm-archive"
    for path in (repo, storage_state, hot, warm):
        path.mkdir()
    monkeypatch.setenv("WC_HOT_DATA_ROOT", str(hot))
    monkeypatch.setenv("WC_WARM_ARCHIVE_ROOT", str(warm))
    monkeypatch.delenv("WC_COLD_MIRROR_ROOT", raising=False)
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")

    result = ResearchStorageEvidenceInspectionRunner(runtime, registry).run(
        domain=Domain.HKJC, repo_root=repo, storage_state_root=storage_state,
        as_of=HKJC_SETTLEMENT_END, estimated_bytes=1024, timeout_seconds=10,
    )

    assert result.disposition is ResearchDisposition.SUCCEEDED
    assert result.status == "research_storage_evidence_projection"
    payload = json.loads(result.report_path.read_text())
    assert payload["storage_health"] == "attention"
    assert payload["dashboard_d1"]["service_available"] is None
    assert payload["historical_availability_verified"] is False
    assert payload["process_liveness_verified"] is False
    assert payload["live_drift_verified"] is False
    assert payload["model_promotion_allowed"] is False
    assert result.content_hash == payload["content_hash"]
    assert not registry.root.exists()


def test_storage_evidence_defers_before_roots_are_read_when_production_active(
        tmp_path):
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    handle = runtime.production_lock_paths[0].open("a")
    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        result = ResearchStorageEvidenceInspectionRunner(runtime, registry).run(
            domain=Domain.NBA,
            repo_root=tmp_path / "must-not-open-repo",
            storage_state_root=tmp_path / "must-not-open-state",
            as_of=NBA_SETTLEMENT_END,
            estimated_bytes=1024,
            timeout_seconds=10,
        )
    finally:
        handle.close()
    assert result.disposition is ResearchDisposition.DEFERRED
    assert result.report_path is None


def test_research_liveness_projection_runs_under_parent_supervision(tmp_path):
    as_of = datetime(2026, 9, 4, 3, 30, tzinfo=timezone.utc)
    registry = ExperimentRegistry(tmp_path / "registry")
    current_spec = spec(Domain.AU)
    queue = configured_queue(
        tmp_path, clock=lambda: as_of - timedelta(minutes=1),
        current_spec=current_spec, registry=registry,
    )
    queue.enqueue(ResearchJob(
        "wc:au:research-job:supervised-live", Domain.AU,
        current_spec.record_id, tmp_path / "dataset", tmp_path / "baseline",
        tmp_path / "candidate", 1024, 600,
    ))
    claim = queue.claim_next("supervised-worker")
    leases = tmp_path / "leases"
    leases.mkdir()
    token = probe_process_start_token(os.getpid())
    assert token is not None
    record_research_liveness_lease(
        lease_root=leases, claim=claim, pid=os.getpid(),
        process_start_token=token,
        observed_at=as_of - timedelta(seconds=30),
        valid_until=as_of + timedelta(minutes=5),
    )
    (tmp_path / "supervisor").mkdir()

    result = ResearchLivenessInspectionRunner(
        source_runtime(tmp_path / "supervisor"), registry,
    ).run(
        domain=Domain.AU, queue_root=queue.root, lease_root=leases,
        as_of=as_of, estimated_bytes=1024, timeout_seconds=10,
    )

    assert result.disposition is ResearchDisposition.SUCCEEDED
    assert result.status == "research_liveness_evidence_projection"
    payload = json.loads(result.report_path.read_text())
    assert payload["counts"]["running_verified"] == 1
    assert payload["process_liveness_verified"] is True
    assert payload["model_promotion_allowed"] is False
    assert result.content_hash == payload["content_hash"]


def test_production_day_projection_runs_under_parent_supervision(tmp_path):
    runs = tmp_path / "production-runs"
    expected = production_day_runs(runs, Domain.AU)
    attestation = production_day_attestation(tmp_path, Domain.AU)
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")

    result = ResearchProductionDayInspectionRunner(runtime, registry).run(
        domain=Domain.AU,
        run_root=runs,
        attestation_path=attestation,
        production_day=PRODUCTION_DAY,
        as_of=PRODUCTION_DAY_AS_OF,
        estimated_bytes=1024,
        timeout_seconds=10,
    )

    assert result.disposition is ResearchDisposition.SUCCEEDED
    assert result.status == "research_production_day_evidence_projection"
    payload = json.loads(result.report_path.read_text())
    assert payload["production_day_closed"] is True
    assert payload["counts"]["terminal"] == len(expected)
    assert payload["model_promotion_allowed"] is False
    assert result.content_hash == payload["content_hash"]


def test_production_day_projection_defers_before_source_read_when_production_active(tmp_path):
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    handle = runtime.production_lock_paths[0].open("a")
    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        result = ResearchProductionDayInspectionRunner(runtime, registry).run(
            domain=Domain.AU,
            run_root=tmp_path / "must-not-open-runs",
            attestation_path=tmp_path / "must-not-open-attestation.json",
            production_day=PRODUCTION_DAY,
            as_of=PRODUCTION_DAY_AS_OF,
            estimated_bytes=1024,
            timeout_seconds=10,
        )
    finally:
        handle.close()

    assert result.disposition is ResearchDisposition.DEFERRED
    assert result.report_path is None
    assert not registry.root.exists()


def test_production_day_parent_rejects_source_changed_after_child_receipt(tmp_path):
    runs = tmp_path / "production-runs"
    production_day_runs(runs, Domain.AU)
    attestation = production_day_attestation(tmp_path, Domain.AU)

    class MutateAfterChild(SubprocessResearchExecutor):
        def run(self, invocation, *, timeout_seconds, production_active):
            execution = super().run(
                invocation,
                timeout_seconds=timeout_seconds,
                production_active=production_active,
            )
            manifest = next(runs.rglob("attempt-1.json"))
            payload = json.loads(manifest.read_text())
            payload["errors"].append("mutated-after-child")
            manifest.write_text(json.dumps(payload, sort_keys=True) + "\n")
            return execution

    runtime = replace(
        source_runtime(tmp_path),
        executor=MutateAfterChild(poll_seconds=0.02, terminate_grace=0.1),
    )
    registry = ExperimentRegistry(tmp_path / "registry")
    result = ResearchProductionDayInspectionRunner(runtime, registry).run(
        domain=Domain.AU,
        run_root=runs,
        attestation_path=attestation,
        production_day=PRODUCTION_DAY,
        as_of=PRODUCTION_DAY_AS_OF,
        estimated_bytes=1024,
        timeout_seconds=10,
    )

    assert result.disposition is ResearchDisposition.FAILED
    assert "source changed" in result.status
    assert result.report_path is None
    assert not registry.root.exists()


def test_nba_settlement_candidate_inventory_is_supervised_and_never_registers_sample(tmp_path):
    evidence, _day, _snapshot, _verification = nba_settled_fixture(tmp_path)
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    result = NbaSettlementCandidateInspectionRunner(runtime, registry).run(
        evidence_root=evidence,
        as_of=NBA_SETTLEMENT_END,
        estimated_bytes=1024,
        timeout_seconds=10,
    )
    assert result.disposition is ResearchDisposition.SUCCEEDED
    assert result.status == "nba_settlement_candidate_inventory_only"
    payload = json.loads(result.report_path.read_text())
    assert payload["label_verified_settlements"] == 1
    assert payload["verified_monitoring_samples"] is None
    assert result.content_hash == payload["content_hash"]
    assert not registry.root.exists(), "label inventory cannot fabricate research records"


def test_nba_settlement_candidate_inventory_defers_before_source_read_when_production_active(tmp_path):
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    handle = runtime.production_lock_paths[0].open("a")
    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        result = NbaSettlementCandidateInspectionRunner(runtime, registry).run(
            evidence_root=tmp_path / "must-not-open",
            as_of=NBA_SETTLEMENT_END,
            estimated_bytes=1024,
            timeout_seconds=10,
        )
    finally:
        handle.close()
    assert result.disposition is ResearchDisposition.DEFERRED
    assert result.report_path is None


def test_hkjc_settlement_candidate_inventory_is_supervised_and_never_registers_sample(tmp_path):
    evidence, _meeting, _snapshot, _results = hkjc_settled_fixture(tmp_path)
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    result = HkjcSettlementCandidateInspectionRunner(runtime, registry).run(
        evidence_root=evidence,
        as_of=HKJC_SETTLEMENT_END,
        estimated_bytes=1024,
        timeout_seconds=10,
    )
    assert result.disposition is ResearchDisposition.SUCCEEDED
    assert result.status == "hkjc_settlement_candidate_inventory_only"
    payload = json.loads(result.report_path.read_text())
    assert payload["label_verified_settlements"] == 1
    assert payload["verified_monitoring_samples"] is None
    assert result.content_hash == payload["content_hash"]
    assert not registry.root.exists(), "label inventory cannot fabricate research records"


def test_hkjc_settlement_candidate_inventory_defers_before_source_read_when_production_active(tmp_path):
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    handle = runtime.production_lock_paths[0].open("a")
    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        result = HkjcSettlementCandidateInspectionRunner(runtime, registry).run(
            evidence_root=tmp_path / "must-not-open",
            as_of=HKJC_SETTLEMENT_END,
            estimated_bytes=1024,
            timeout_seconds=10,
        )
    finally:
        handle.close()
    assert result.disposition is ResearchDisposition.DEFERRED
    assert result.report_path is None


def test_tennis_settlement_candidate_inventory_is_supervised_and_never_registers_sample(tmp_path):
    evidence, _day, _snapshot, _outcome = tennis_settled_fixture(tmp_path)
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    result = TennisSettlementCandidateInspectionRunner(runtime, registry).run(
        evidence_root=evidence,
        as_of=TENNIS_SETTLEMENT_END,
        estimated_bytes=1024,
        timeout_seconds=10,
    )
    assert result.disposition is ResearchDisposition.SUCCEEDED
    assert result.status == "tennis_settlement_candidate_inventory_only"
    payload = json.loads(result.report_path.read_text())
    assert payload["label_verified_settlements"] == 1
    assert payload["verified_monitoring_samples"] is None
    assert result.content_hash == payload["content_hash"]
    assert not registry.root.exists(), "label inventory cannot fabricate research records"


def test_tennis_settlement_candidate_inventory_defers_before_source_read_when_production_active(tmp_path):
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    handle = runtime.production_lock_paths[0].open("a")
    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        result = TennisSettlementCandidateInspectionRunner(runtime, registry).run(
            evidence_root=tmp_path / "must-not-open",
            as_of=TENNIS_SETTLEMENT_END,
            estimated_bytes=1024,
            timeout_seconds=10,
        )
    finally:
        handle.close()
    assert result.disposition is ResearchDisposition.DEFERRED
    assert result.report_path is None


def test_tennis_feature_provenance_inventory_is_supervised_without_registering_sample(tmp_path):
    evidence, _snapshot = tennis_feature_fixture(tmp_path)
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    result = TennisFeatureProvenanceInspectionRunner(runtime, registry).run(
        evidence_root=evidence,
        as_of=TENNIS_FEATURE_AS_OF,
        estimated_bytes=1024,
        timeout_seconds=10,
    )
    assert result.disposition is ResearchDisposition.SUCCEEDED
    assert result.status == "tennis_feature_provenance_inventory_only"
    payload = json.loads(result.report_path.read_text())
    assert payload["feature_availability_verified"] is True
    assert payload["verified_monitoring_samples"] is None
    assert result.content_hash == payload["content_hash"]
    assert not registry.root.exists(), "feature inventory cannot fabricate research records"


def test_tennis_feature_provenance_defers_before_source_read_when_production_active(tmp_path):
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    handle = runtime.production_lock_paths[0].open("a")
    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        result = TennisFeatureProvenanceInspectionRunner(runtime, registry).run(
            evidence_root=tmp_path / "must-not-open",
            as_of=TENNIS_FEATURE_AS_OF,
            estimated_bytes=1024,
            timeout_seconds=10,
        )
    finally:
        handle.close()
    assert result.disposition is ResearchDisposition.DEFERRED
    assert result.report_path is None


def test_hkjc_feature_provenance_inventory_is_supervised_without_registering_sample(tmp_path):
    evidence, _snapshot = hkjc_feature_fixture(tmp_path)
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    result = HkjcFeatureProvenanceInspectionRunner(runtime, registry).run(
        evidence_root=evidence,
        as_of=HKJC_FEATURE_AS_OF,
        estimated_bytes=1024,
        timeout_seconds=10,
    )
    assert result.disposition is ResearchDisposition.SUCCEEDED
    assert result.status == "hkjc_feature_provenance_inventory_only"
    payload = json.loads(result.report_path.read_text())
    assert payload["feature_availability_verified"] is True
    assert payload["verified_monitoring_samples"] is None
    assert result.content_hash == payload["content_hash"]
    assert not registry.root.exists(), "feature inventory cannot fabricate research records"


def test_hkjc_feature_provenance_defers_before_source_read_when_production_active(tmp_path):
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    handle = runtime.production_lock_paths[0].open("a")
    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        result = HkjcFeatureProvenanceInspectionRunner(runtime, registry).run(
            evidence_root=tmp_path / "must-not-open",
            as_of=HKJC_FEATURE_AS_OF,
            estimated_bytes=1024,
            timeout_seconds=10,
        )
    finally:
        handle.close()
    assert result.disposition is ResearchDisposition.DEFERRED
    assert result.report_path is None


def test_nba_feature_provenance_inventory_is_supervised_without_registering_sample(tmp_path):
    evidence, _snapshot = nba_feature_fixture(tmp_path)
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    result = NbaFeatureProvenanceInspectionRunner(runtime, registry).run(
        evidence_root=evidence,
        as_of=NBA_FEATURE_AS_OF,
        estimated_bytes=1024,
        timeout_seconds=10,
    )
    assert result.disposition is ResearchDisposition.SUCCEEDED
    assert result.status == "nba_feature_provenance_inventory_only"
    payload = json.loads(result.report_path.read_text())
    assert payload["feature_availability_verified"] is True
    assert payload["verified_monitoring_samples"] is None
    assert result.content_hash == payload["content_hash"]
    assert not registry.root.exists(), "feature inventory cannot fabricate research records"


def test_nba_feature_provenance_defers_before_source_read_when_production_active(tmp_path):
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    handle = runtime.production_lock_paths[0].open("a")
    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        result = NbaFeatureProvenanceInspectionRunner(runtime, registry).run(
            evidence_root=tmp_path / "must-not-open",
            as_of=NBA_FEATURE_AS_OF,
            estimated_bytes=1024,
            timeout_seconds=10,
        )
    finally:
        handle.close()
    assert result.disposition is ResearchDisposition.DEFERRED
    assert result.report_path is None


def test_au_feature_provenance_inventory_is_supervised_without_registering_sample(tmp_path):
    evidence = au_feature_fixture(tmp_path)
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    result = AuFeatureProvenanceInspectionRunner(runtime, registry).run(
        evidence_root=evidence,
        as_of=AU_FEATURE_AS_OF,
        estimated_bytes=1024,
        timeout_seconds=10,
    )
    assert result.disposition is ResearchDisposition.SUCCEEDED
    assert result.status == "au_feature_provenance_inventory_only"
    payload = json.loads(result.report_path.read_text())
    assert payload["feature_availability_verified"] is True
    assert payload["verified_monitoring_samples"] is None
    assert result.content_hash == payload["content_hash"]
    assert not registry.root.exists(), "feature inventory cannot fabricate research records"


def test_au_feature_provenance_defers_before_source_read_when_production_active(tmp_path):
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    handle = runtime.production_lock_paths[0].open("a")
    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        result = AuFeatureProvenanceInspectionRunner(runtime, registry).run(
            evidence_root=tmp_path / "must-not-open",
            as_of=AU_FEATURE_AS_OF,
            estimated_bytes=1024,
            timeout_seconds=10,
        )
    finally:
        handle.close()
    assert result.disposition is ResearchDisposition.DEFERRED
    assert result.report_path is None


def test_prediction_bundle_inventory_respects_production_priority_before_source_read(tmp_path):
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    handle = runtime.production_lock_paths[0].open("a")
    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        result = PredictionArtifactInspectionRunner(runtime, registry).run(
            domain=Domain.AU,
            evidence_root=tmp_path / "must-not-open", as_of=ARTIFACT_NOW,
            estimated_bytes=1024, timeout_seconds=10,
        )
    finally:
        handle.close()
    assert result.disposition is ResearchDisposition.DEFERRED
    assert result.report_path is None


@pytest.mark.parametrize("preempt", [False, True])
def test_prediction_artifact_hashing_is_externally_supervised(tmp_path, preempt):
    evidence, _meeting, _snapshot, _ = prediction_artifact_fixture(tmp_path)
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    fifo, ready = tmp_path / "blocked-prediction-artifact", tmp_path / "artifact-ready"
    os.mkfifo(fifo)
    handles = []

    class BlockedArtifact(SubprocessResearchExecutor):
        def run(self, invocation, *, timeout_seconds, production_active):
            program = (
                "from pathlib import Path; import sys; import shared_wong_choi.research_prediction_artifacts as a; "
                "import shared_wong_choi.research_supervision as r; "
                f"a.inspect_prediction_artifacts=lambda *x,**k: (Path({str(ready)!r}).touch(),open({str(fifo)!r}).read())[1]; "
                "r._worker(Path(sys.argv[1]))"
            )
            invocation = replace(invocation, argv=(sys.executable, "-c", program, invocation.argv[-1]))

            def check():
                if preempt and ready.exists() and not handles:
                    handle = runtime.production_lock_paths[0].open("a")
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    handles.append(handle)
                return production_active()

            return super().run(invocation, timeout_seconds=1, production_active=check)

    runtime = replace(runtime, executor=BlockedArtifact(poll_seconds=0.02, terminate_grace=0.1))
    try:
        result = PredictionArtifactInspectionRunner(runtime, registry).run(
            domain=Domain.AU, evidence_root=evidence, as_of=ARTIFACT_NOW,
            estimated_bytes=1024, timeout_seconds=10,
        )
    finally:
        for handle in handles:
            handle.close()
    assert ready.exists()
    assert result.disposition is (ResearchDisposition.PREEMPTED if preempt else ResearchDisposition.TIMED_OUT)
    assert result.report_path is None and not registry.root.exists()


def witness_setup(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    inventory, witness, snapshot = witness_fixture(source)
    from shared_wong_choi.research_tennis_source import TennisSourcePolicy

    policy = TennisSourcePolicy(
        **{**inventory["policy"], "feature_fields": tuple(inventory["policy"]["feature_fields"])}
    )
    return source / "tennis.db", policy, witness, snapshot


def test_witness_bundle_is_hash_linked_and_never_registers_or_qualifies_samples(tmp_path):
    from shared_wong_choi.research_tennis_source import _digest

    db, policy, witness, snapshot = witness_setup(tmp_path)
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    before = artifact_digest(snapshot)
    result = TennisSourceInspectionRunner(runtime, registry).run(
        db, policy, witnesses=(witness,), estimated_bytes=1024, timeout_seconds=10
    )
    assert result.disposition is ResearchDisposition.SUCCEEDED
    assert result.status == "availability_inventory_with_witnesses_only"
    payload = json.loads(result.report_path.read_text())
    assert payload["schema_version"] == "wong-choi-tennis-source-witness-bundle/v1"
    inventory, reports = payload["inventory"], payload["snapshot_witnesses"]
    assert reports[0]["inventory_hash"] == inventory["content_hash"]
    assert [row["status"] for row in reports[0]["rows"]] == ["catalog_predecision_value_match"] * 2
    for report in (payload, inventory, *reports):
        assert report["content_hash"] == _digest({k: v for k, v in report.items() if k != "content_hash"})
        assert report["pit_dataset_ready"] is False and report["proposal_ready"] is False
    assert result.content_hash == payload["content_hash"]
    assert not registry.root.exists() and artifact_digest(snapshot) == before


def test_invalid_requested_witness_does_not_publish_an_inventory_only_success(tmp_path):
    db, policy, witness, snapshot = witness_setup(tmp_path)
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    witness = replace(witness, catalog_sha256="a" * 64)
    result = TennisSourceInspectionRunner(runtime, registry).run(
        db, policy, witnesses=(witness,), estimated_bytes=1024, timeout_seconds=10
    )
    assert result.disposition is ResearchDisposition.FAILED
    assert result.report_path is None and not registry.root.exists()
    assert not list(result.attempt_path.glob("work/*.json"))


def test_duplicate_witness_rejected_before_any_attempt(tmp_path):
    db, policy, witness, _ = witness_setup(tmp_path)
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    with pytest.raises(ValueError, match="duplicate"):
        TennisSourceInspectionRunner(runtime, registry).run(
            db, policy, witnesses=(witness, witness), estimated_bytes=1024, timeout_seconds=10
        )
    assert not list(runtime.warm_root.iterdir()) and not registry.root.exists()


@pytest.mark.parametrize("preempt", [False, True])
def test_full_archive_hash_is_inside_external_timeout_and_production_supervision(tmp_path, preempt):
    db, policy, witness, _ = witness_setup(tmp_path)
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    fifo, ready = tmp_path / "blocked-hash", tmp_path / "hash-ready"
    os.mkfifo(fifo)
    handles = []

    class BlockedHash(SubprocessResearchExecutor):
        def run(self, invocation, *, timeout_seconds, production_active):
            program = (
                "from pathlib import Path; import sys; import shared_wong_choi.research_tennis_witness as w; "
                "import shared_wong_choi.research_supervision as r; "
                f"w.artifact_digest=lambda *a,**k: (Path({str(ready)!r}).touch(),open({str(fifo)!r}).read())[1]; "
                "r._worker(Path(sys.argv[1]))"
            )
            invocation = replace(invocation, argv=(sys.executable, "-c", program, invocation.argv[-1]))

            def check():
                if preempt and ready.exists() and not handles:
                    handle = runtime.production_lock_paths[0].open("a")
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    handles.append(handle)
                return production_active()

            return super().run(invocation, timeout_seconds=1, production_active=check)

    runtime = replace(runtime, executor=BlockedHash(poll_seconds=0.02, terminate_grace=0.1))
    try:
        result = TennisSourceInspectionRunner(runtime, registry).run(
            db, policy, witnesses=(witness,), estimated_bytes=1024, timeout_seconds=10
        )
    finally:
        for handle in handles:
            handle.close()
    assert ready.exists(), "must reach the full archive hash in the supervised worker"
    assert result.disposition is (ResearchDisposition.PREEMPTED if preempt else ResearchDisposition.TIMED_OUT)
    assert result.report_path is None and not registry.root.exists()
    outcome = json.loads((result.attempt_path / "phase-outcome.json").read_text())
    assert outcome["publication"] == "unconfirmed_reconcile_before_retry"


@pytest.mark.parametrize("fault", ["production", "heavy", "offline", "capacity", "unconfigured"])
def test_source_inspection_respects_shared_resources_before_opening_source(tmp_path, fault):
    db, policy = source_fixture(tmp_path)
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    handle = None
    if fault in ("production", "heavy"):
        lock = (
            runtime.production_lock_paths[0]
            if fault == "production"
            else runtime.state_root / "locks/research-heavy-worker.lock"
        )
        lock.parent.mkdir(parents=True, exist_ok=True)
        handle = lock.open("a")
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if fault == "offline":
        runtime = replace(runtime, warm_root=tmp_path / "missing")
    if fault == "capacity":
        runtime = replace(runtime, free_space_probe=lambda _: 0)
    if fault == "unconfigured":
        runtime = replace(runtime, production_lock_paths=())
    try:
        result = TennisSourceInspectionRunner(runtime, registry).run(
            tmp_path / "nonexistent.db", policy, estimated_bytes=1024, timeout_seconds=10
        )
    finally:
        if handle:
            handle.close()
    assert result.disposition is ResearchDisposition.DEFERRED
    assert result.report_path is None
    assert not registry.root.exists()


@pytest.mark.parametrize("preempt", [False, True])
def test_stalled_source_read_is_externally_supervised(tmp_path, preempt):
    db, policy = source_fixture(tmp_path)
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    fifo, ready = tmp_path / "blocked-source", tmp_path / "worker-ready"
    os.mkfifo(fifo)
    handles = []

    class BlockedSource(SubprocessResearchExecutor):
        def run(self, invocation, *, timeout_seconds, production_active):
            program = (
                "from pathlib import Path; import sys; import shared_wong_choi.research_supervision as r; "
                f"r.inspect_tennis_sources=lambda *a,**k: (Path({str(ready)!r}).touch(),open({str(fifo)!r}).read())[1]; "
                "r._worker(Path(sys.argv[1]))"
            )
            invocation = replace(invocation, argv=(sys.executable, "-c", program, invocation.argv[-1]))

            def check():
                if preempt and ready.exists() and not handles:
                    handle = runtime.production_lock_paths[0].open("a")
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    handles.append(handle)
                return production_active()

            return super().run(invocation, timeout_seconds=1, production_active=check)

    runtime = replace(runtime, executor=BlockedSource(poll_seconds=0.02, terminate_grace=0.1))
    try:
        result = TennisSourceInspectionRunner(runtime, registry).run(
            db, policy, estimated_bytes=1024, timeout_seconds=10
        )
    finally:
        for handle in handles:
            handle.close()
    assert ready.exists(), "must actually enter the source reader"
    assert result.disposition is (ResearchDisposition.PREEMPTED if preempt else ResearchDisposition.TIMED_OUT)
    assert result.report_path is None and not registry.root.exists()
    assert len(list(runtime.warm_root.rglob("phase-outcome.json"))) == 1


@pytest.mark.parametrize(
    "reason,expected",
    [("production_active", "preempted"), ("phase_timeout", "timed_out"), ("warm_offline", "preempted")],
)
def test_worker_checkpoint_interruptions_are_classified_not_general_failures(tmp_path, reason, expected):
    db, policy = source_fixture(tmp_path)
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")

    class WorkerInterrupt(SubprocessResearchExecutor):
        def run(self, invocation, **kwargs):
            program = (
                "from pathlib import Path; import sys; import shared_wong_choi.research_supervision as r; "
                f"r.inspect_tennis_sources=lambda *a,**k: (_ for _ in ()).throw(r.ResourceInterrupted({reason!r})); "
                "r._worker(Path(sys.argv[1]))"
            )
            return super().run(replace(invocation, argv=(sys.executable, "-c", program, invocation.argv[-1])), **kwargs)

    runtime = replace(runtime, executor=WorkerInterrupt(poll_seconds=0.02, terminate_grace=0.1))
    result = TennisSourceInspectionRunner(runtime, registry).run(db, policy, estimated_bytes=1024, timeout_seconds=10)
    assert result.disposition.value == expected
    assert result.status == reason and result.report_path is None
    outcome = json.loads((result.attempt_path / "phase-outcome.json").read_text())
    assert outcome["publication"] == "unconfirmed_reconcile_before_retry"


def test_preempted_scoring_kills_nested_command_descendants(tmp_path):
    import time

    ready, leaked = tmp_path / "child-ready", tmp_path / "leaked-write"
    descendant = (
        "import signal,time; from pathlib import Path; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        f"Path({str(ready)!r}).touch(); time.sleep(.6); Path({str(leaked)!r}).touch()"
    )
    script = f"import subprocess,sys,time; subprocess.Popen([sys.executable, '-c', {descendant!r}]); time.sleep(60)"
    current_spec, current_job, runtime, registry = fixture(tmp_path, script)
    handles = []

    class PreemptAfterChildStarts(SubprocessResearchExecutor):
        def run(self, invocation, *, timeout_seconds, production_active):
            def check():
                if ready.exists() and not handles:
                    handle = runtime.production_lock_paths[0].open("a")
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    handles.append(handle)
                return production_active()

            return super().run(invocation, timeout_seconds=timeout_seconds, production_active=check)

    runtime = replace(runtime, executor=PreemptAfterChildStarts(poll_seconds=0.02, terminate_grace=0.1))
    try:
        result = ResearchScoringRunner(runtime, registry).run(current_job, current_spec, create_research_adapter("au"))
    finally:
        for handle in handles:
            handle.close()
    assert ready.exists(), "test must actually reach the nested command"
    assert result.disposition is ResearchDisposition.PREEMPTED
    time.sleep(0.7)
    assert not leaked.exists(), "descendant survived supervised group termination"


def test_scoring_supervisor_uses_real_clean_checkouts_and_registers_run(tmp_path):
    current_spec, current_job, runtime, registry = fixture(tmp_path)
    result = ResearchScoringRunner(runtime, registry).run(current_job, current_spec, create_research_adapter("au"))
    assert result.disposition is ResearchDisposition.SUCCEEDED
    registered = registry.load(result.experiment_run_id)
    assert registered["baseline_commit"] == current_spec.baseline_commit
    assert registered["candidate_commit"] == current_spec.candidate_commit
    assert registered["artifact_digest"] == artifact_digest(result.artifact_path)["sha256"]


def test_preparation_runs_resolver_in_worker_under_shared_lock(tmp_path):
    current_spec, current_job, runtime, registry = fixture(tmp_path)
    root = tmp_path / "dataset-source/artifact"
    sources = (
        DatasetSource(
            "au-fixture", StorageTier.HOT, root, root / "rows.jsonl", "2026-08-28T00:00:00+00:00", artifact_digest(root)
        ),
    )
    result = ResearchPreparationRunner(runtime, registry).run(
        current_spec,
        sources=sources,
        split_policy=SplitPolicy("2026-08-10T23:59:00+00:00", "2026-08-20T23:59:00+00:00", "2026-08-29T23:59:00+00:00"),
        estimated_bytes=1024,
        timeout_seconds=10,
    )
    assert result.disposition is ResearchDisposition.SUCCEEDED
    manifest = load_dataset_snapshot(result.snapshot_path).manifest
    assert registry.load(manifest.record_id) == manifest.to_payload()
    assert result.snapshot_path.is_relative_to(runtime.warm_root)


def test_one_entry_prepares_then_scores_and_publishes_with_real_checkouts(tmp_path):
    current_spec, args = real_checkout_fixture(tmp_path)
    runtime = ResearchRuntime(
        state_root=tmp_path / "state",
        warm_root=tmp_path / "warm",
        production_lock_paths=(tmp_path / "production.lock",),
        executor=SubprocessResearchExecutor(poll_seconds=0.02, terminate_grace=0.1),
    )
    from shared_wong_choi.research_runner import ResearchJob

    current_job = ResearchJob(
        "wc:au:research-job:full-supervision",
        current_spec.domain,
        current_spec.record_id,
        tmp_path / "unprepared",
        tmp_path / "baseline",
        tmp_path / "candidate",
        1024,
        30,
    )
    root = tmp_path / "raw"
    result = ResearchWorkflow(runtime, args["registry"]).prepare_and_run(
        current_job,
        current_spec,
        create_research_adapter("au"),
        evidence=args["evidence"],
        sources=(
            DatasetSource(
                "settled",
                StorageTier.HOT,
                root,
                root / "rows.jsonl",
                "2026-08-29T00:00:00+00:00",
                artifact_digest(root),
            ),
        ),
        split_policy=SplitPolicy("2026-08-11T23:59:00+00:00", "2026-08-13T23:59:00+00:00", "2026-08-29T23:59:00+00:00"),
    )
    assert result.preparation.disposition is ResearchDisposition.SUCCEEDED
    assert result.workflow.scoring.disposition is ResearchDisposition.SUCCEEDED
    assert result.workflow.postflight.disposition is ResearchDisposition.SUCCEEDED
    manifest = load_dataset_snapshot(result.preparation.snapshot_path).manifest
    record = args["registry"].load(result.workflow.scoring.experiment_run_id)
    assert record["links"]["dataset_manifest_id"] == manifest.record_id


@pytest.mark.parametrize("phase", ["prepare", "scoring"])
@pytest.mark.parametrize("preempt", [False, True])
def test_supervisor_terminates_blocked_parent_io_before_any_run_publication(tmp_path, phase, preempt):
    current_spec, current_job, runtime, registry = fixture(tmp_path)
    fifo = tmp_path / "blocked-read"
    os.mkfifo(fifo)
    locks = []

    class BlockedReader(SubprocessResearchExecutor):
        def run(self, invocation, *, timeout_seconds, production_active):
            # The real worker is entered, then a source/checkout read stalls.
            patch = (
                "r.build_dataset_snapshot=lambda *a,**k: open(FIFO).read(); "
                if phase == "prepare"
                else "r._git_checkout_probe=lambda *a,**k: open(FIFO).read(); "
            )
            program = (
                "from pathlib import Path; import sys; import shared_wong_choi.research_supervision as r; "
                f"FIFO={str(fifo)!r}; {patch}r._worker(Path(sys.argv[1]))"
            )
            invocation = replace(invocation, argv=(sys.executable, "-c", program, invocation.argv[-1]))
            polls = 0

            def check():
                nonlocal polls
                polls += 1
                if preempt and polls == 8:
                    handle = runtime.production_lock_paths[0].open("a")
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    locks.append(handle)
                return production_active()

            return super().run(invocation, timeout_seconds=min(timeout_seconds, 1), production_active=check)

    runtime = replace(runtime, executor=BlockedReader(poll_seconds=0.05, terminate_grace=0.1))
    try:
        if phase == "scoring":
            result = ResearchScoringRunner(runtime, registry).run(
                current_job, current_spec, create_research_adapter("au")
            )
        else:
            root = tmp_path / "dataset-source/artifact"
            result = ResearchPreparationRunner(runtime, registry).run(
                current_spec,
                sources=(
                    DatasetSource(
                        "source",
                        StorageTier.HOT,
                        root,
                        root / "rows.jsonl",
                        "2026-08-28T00:00:00+00:00",
                        artifact_digest(root),
                    ),
                ),
                split_policy=SplitPolicy(
                    "2026-08-10T23:59:00+00:00", "2026-08-20T23:59:00+00:00", "2026-08-29T23:59:00+00:00"
                ),
                estimated_bytes=1024,
                timeout_seconds=10,
            )
    finally:
        for handle in locks:
            handle.close()
    assert result.disposition is (ResearchDisposition.PREEMPTED if preempt else ResearchDisposition.TIMED_OUT)
    assert not registry.root.joinpath("records/experiment_run").exists()
    outcomes = list(runtime.warm_root.rglob("phase-outcome.json"))
    assert len(outcomes) == 1
    assert json.loads(outcomes[0].read_text())["publication"] == "unconfirmed_reconcile_before_retry"
