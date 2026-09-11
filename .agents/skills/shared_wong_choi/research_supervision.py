"""Supervised dataset preparation and scoring, including parent-side I/O.

Trusted command descendants remain in the supervisor-owned process group.
This is not containment of hostile code deliberately creating new sessions.
Interrupted work is quarantined in its WARM attempt, never silently retried.
"""

from __future__ import annotations

import hashlib
import math
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

from .control import single_run_lock
from .contracts import Domain
from .research_dataset import (
    DatasetSource,
    SplitPolicy,
    StorageTier,
    build_dataset_snapshot,
    load_dataset_snapshot,
)
from .research_evaluation import _strict_json, _write_report
from .research_registry import ExperimentRegistry, ExperimentSpec, _record_from_payload
from .research_reconciliation import reconcile_postflight, verify_reconciliation_receipt
from .research_phase_reconciliation import reconcile_phase, verify_phase_reconciliation_receipt
from .research_resources import (
    DEADLINE_CLOCK,
    ResourceInterrupted,
    _deadline_now,
    _validate_deadline,
    _resource_status,
    _record_attempt_outcome,
    _interruption_receipt,
    _read_interruption,
)
from .research_tennis_source import TennisSourcePolicy, inspect_tennis_sources, _digest
from .research_tennis_witness import SnapshotWitness, verify_tennis_snapshot_witness
from .research_runner import (
    CommandInvocation,
    CommandState,
    ResearchDisposition,
    ResearchDomainAdapter,
    ResearchJob,
    ResearchRunner,
    ResearchRunResult,
    ResearchRuntime,
    SubprocessResearchExecutor,
    _git_checkout_probe,
    create_research_adapter,
)


class _InheritedGroupExecutor(SubprocessResearchExecutor):
    """Only constructed inside the independently supervised session leader."""

    def _spawn(self, invocation):
        if os.getpid() != os.getpgrp():
            raise RuntimeError("scoring worker does not own the supervised process group")
        return subprocess.Popen(
            list(invocation.argv),
            cwd=invocation.cwd,
            env={**os.environ, **dict(invocation.env)},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=False,
        )

    def _cleanup_group(self, process):
        # The outer supervisor owns group cleanup, including our descendants.
        pass

    def _terminate(self, process):
        if process.poll() is None:
            process.terminate()
        try:
            return process.communicate(timeout=self.terminate_grace)
        except subprocess.TimeoutExpired:
            process.kill()
            return process.communicate(timeout=self.terminate_grace)


@dataclass(frozen=True)
class PreparationResult:
    disposition: ResearchDisposition
    status: str
    attempt_path: Path | None = None
    snapshot_path: Path | None = None
    dataset_manifest_id: str | None = None


def _phase(runtime, registry, spec, *, action, payload, estimated_bytes, timeout_seconds, notification_route=None):
    if type(estimated_bytes) is not int or estimated_bytes <= 0:
        raise ValueError("estimated_bytes must be positive")
    if type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be finite and positive")
    deadline = _deadline_now() + timeout_seconds
    source_inventory = action == "tennis-source"
    metadata_only = action in {
        "tennis-source", "prediction-artifacts", "au-settlement-candidates",
        "nba-settlement-candidates", "hkjc-settlement-candidates",
        "tennis-settlement-candidates", "au-feature-provenance",
        "tennis-feature-provenance", "hkjc-feature-provenance",
        "nba-feature-provenance", "racing-monitoring-samples",
        "nba-monitoring-samples", "tennis-monitoring-samples",
        "research-storage-evidence", "research-liveness-evidence",
        "research-production-day-evidence", "research-live-drift",
        "power-dev-engine", "power-dev-producer", "power-projection",
        "power-variance", "review", "notify",
    }
    if action not in {
        "prepare", "scoring", "tennis-source", "prediction-artifacts",
        "au-settlement-candidates", "nba-settlement-candidates",
        "hkjc-settlement-candidates", "tennis-settlement-candidates", "au-feature-provenance",
        "tennis-feature-provenance", "hkjc-feature-provenance",
        "nba-feature-provenance", "racing-monitoring-samples",
        "nba-monitoring-samples", "tennis-monitoring-samples",
        "research-storage-evidence", "research-liveness-evidence",
        "research-production-day-evidence", "research-live-drift",
        "power-dev-engine", "power-dev-producer", "power-projection",
        "power-variance", "reconcile", "review", "notify",
    } or (spec is None) != metadata_only:
        raise ValueError("only source inventory or metadata review may run without a registered spec")
    private_env = {}
    if action == "notify":
        from .research_notification_runtime import notification_environment
        private_env = notification_environment(notification_route, payload)
    elif notification_route is not None:
        raise ValueError("notification credentials forbidden on other research phases")
    if spec is not None:
        spec.validate()
    from .research_guard import research_gate_status

    def status_probe():
        return _resource_status(runtime, registry, estimated_bytes) or (
            research_gate_status(runtime, registry, spec.domain, spec.evaluation_ruler_digest)
            if action in {"prepare", "scoring"} else None)

    status = status_probe()
    if status:
        disposition = ResearchDisposition.BLOCKED if status.startswith("research_") else ResearchDisposition.DEFERRED
        return disposition, status, None, None
    if spec is not None and registry.load(spec.record_id) != spec.to_payload():
        return ResearchDisposition.BLOCKED, "spec_registry_mismatch", None, None
    root = (
        runtime.warm_root.expanduser().absolute()
        / "research-phases"
        / (Domain(payload["domain"]).value if action in {
            "prediction-artifacts", "au-settlement-candidates",
            "nba-settlement-candidates", "hkjc-settlement-candidates",
            "tennis-settlement-candidates", "au-feature-provenance",
            "tennis-feature-provenance", "hkjc-feature-provenance",
            "nba-feature-provenance", "racing-monitoring-samples",
            "nba-monitoring-samples", "tennis-monitoring-samples",
            "research-storage-evidence", "research-liveness-evidence",
            "research-production-day-evidence", "research-live-drift",
            "power-dev-engine", "power-dev-producer", "power-projection",
            "power-variance", "review", "notify",
        }
           else ("tennis" if source_inventory else spec.domain.value))
    )
    lock = runtime.state_root.expanduser().absolute() / "locks/research-heavy-worker.lock"
    if any(path.is_symlink() for base in (root, lock) for path in (base, *base.parents)):
        return ResearchDisposition.BLOCKED, "unsafe_phase_path", None, None
    root.mkdir(parents=True, exist_ok=True)
    attempt = Path(tempfile.mkdtemp(prefix=action + "-", dir=root))
    request = {
        "schema_version": "wong-choi-supervised-research-phase/v1",
        "action": action,
        "spec_id": spec.record_id if spec else None,
        "registry": str(registry.root),
        "state_root": str(runtime.state_root.expanduser().absolute()),
        "warm_root": str(runtime.warm_root.expanduser().absolute()),
        "production_locks": [str(path.expanduser().absolute()) for path in runtime.production_lock_paths],
        "reserve_bytes": runtime.reserve_bytes,
        "estimated_bytes": estimated_bytes,
        "deadline": deadline,
        "deadline_clock": DEADLINE_CLOCK,
        "parent_pid": os.getpid(),
        "payload": payload,
    }
    request_path = attempt / "request.json"
    _write_report(request_path, request)
    invocation = CommandInvocation(
        action,
        0,
        (sys.executable, "-m", "shared_wong_choi.research_supervision", str(request_path)),
        attempt,
        {
            "PYTHONPATH": str(Path(__file__).resolve().parent.parent),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": str(spec.seed if spec else 0),
            "TZ": "UTC",
            "LC_ALL": "C",
            "LANG": "C",
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            **private_env,
        },
        attempt,
        attempt / "completed.json",
    )
    outcome: dict[str, Any] = {
        "action": action,
        "spec_id": spec.record_id if spec else None,
        "publication": "unconfirmed_reconcile_before_retry",
    }
    completed = None
    interruption = None

    def interrupted():
        nonlocal interruption
        interruption = status_probe()
        return interruption is not None

    try:
        remaining = deadline - _deadline_now()
        if remaining <= 0:
            raise ResourceInterrupted("phase_timeout")
        execution = runtime.executor.run(
            invocation,
            timeout_seconds=remaining,
            production_active=interrupted,
        )
        outcome["execution"] = asdict(execution)
        if action == "notify":
            # Environment-carried credentials can appear in an unexpected worker
            # traceback. Keep timing/state, but never persist notification stdout.
            outcome["execution"].update(stdout="[redacted]", stderr="[redacted]")
        if execution.state is not CommandState.SUCCEEDED or execution.returncode != 0:
            disposition = {
                CommandState.TIMED_OUT: ResearchDisposition.TIMED_OUT,
                CommandState.PREEMPTED: ResearchDisposition.PREEMPTED,
            }.get(execution.state, ResearchDisposition.FAILED)
            status = interruption or execution.state.value
        else:
            info = invocation.metrics_path.stat()
            if not stat.S_ISREG(info.st_mode) or info.st_size > 65536 or invocation.metrics_path.is_symlink():
                raise ValueError("invalid or oversized phase completion receipt")
            completed = _strict_json(invocation.metrics_path.read_text())
            disposition = ResearchDisposition(completed["disposition"])
            status = completed["status"]
            if disposition is ResearchDisposition.SUCCEEDED:
                if action in {"review", "notify"}:
                    path_key = "report_path"
                elif action == "reconcile":
                    if (
                        completed.get("rerun_scoring_allowed") is not False
                        or completed.get("retry_publication_allowed") is not False
                        or completed.get("model_promotion_allowed") is not False
                        or completed.get("request_sha256") != payload["request_sha256"]
                        or not re.fullmatch("[0-9a-f]{64}", completed.get("content_hash", ""))
                    ):
                        raise ValueError("invalid reconciliation receipt")
                    path_key = "report_path"
                elif source_inventory:
                    if (
                        completed.get("proposal_ready") is not False
                        or completed.get("pit_dataset_ready") is not False
                        or not isinstance(completed.get("content_hash"), str)
                        or len(completed["content_hash"]) != 64
                    ):
                        raise ValueError("invalid source inventory receipt")
                    path_key = "report_path"
                elif action == "prediction-artifacts":
                    if (set(completed) != {
                            "disposition", "status", "report_path", "content_hash",
                            "normalized_source_verified", "verified_monitoring_samples",
                            "model_promotion_allowed",
                        }
                            or completed.get("normalized_source_verified") is not False
                            or completed.get("verified_monitoring_samples") is not None
                            or completed.get("model_promotion_allowed") is not False
                            or not re.fullmatch("[0-9a-f]{64}", completed.get("content_hash", ""))):
                        raise ValueError("invalid prediction artifact inventory receipt")
                    path_key = "report_path"
                elif action == "au-settlement-candidates":
                    if (set(completed) != {
                            "disposition", "status", "report_path", "content_hash",
                            "feature_availability_verified", "verified_monitoring_samples",
                            "model_promotion_allowed",
                        }
                            or completed.get("feature_availability_verified") is not False
                            or completed.get("verified_monitoring_samples") is not None
                            or completed.get("model_promotion_allowed") is not False
                            or not re.fullmatch("[0-9a-f]{64}", completed.get("content_hash", ""))):
                        raise ValueError("invalid AU settlement candidate receipt")
                    path_key = "report_path"
                elif action == "nba-settlement-candidates":
                    if (set(completed) != {
                            "disposition", "status", "report_path", "content_hash",
                            "feature_availability_verified", "verified_monitoring_samples",
                            "model_promotion_allowed",
                        }
                            or completed.get("feature_availability_verified") is not False
                            or completed.get("verified_monitoring_samples") is not None
                            or completed.get("model_promotion_allowed") is not False
                            or not re.fullmatch("[0-9a-f]{64}", completed.get("content_hash", ""))):
                        raise ValueError("invalid NBA settlement candidate receipt")
                    path_key = "report_path"
                elif action == "hkjc-settlement-candidates":
                    if (set(completed) != {
                            "disposition", "status", "report_path", "content_hash",
                            "feature_availability_verified", "verified_monitoring_samples",
                            "model_promotion_allowed",
                        }
                            or completed.get("feature_availability_verified") is not False
                            or completed.get("verified_monitoring_samples") is not None
                            or completed.get("model_promotion_allowed") is not False
                            or not re.fullmatch("[0-9a-f]{64}", completed.get("content_hash", ""))):
                        raise ValueError("invalid HKJC settlement candidate receipt")
                    path_key = "report_path"
                elif action == "tennis-settlement-candidates":
                    if (set(completed) != {
                            "disposition", "status", "report_path", "content_hash",
                            "feature_availability_verified", "verified_monitoring_samples",
                            "model_promotion_allowed",
                        }
                            or completed.get("feature_availability_verified") is not False
                            or completed.get("verified_monitoring_samples") is not None
                            or completed.get("model_promotion_allowed") is not False
                            or not re.fullmatch("[0-9a-f]{64}", completed.get("content_hash", ""))):
                        raise ValueError("invalid Tennis settlement candidate receipt")
                    path_key = "report_path"
                elif action == "au-feature-provenance":
                    if (set(completed) != {
                            "disposition", "status", "report_path", "content_hash",
                            "feature_availability_verified", "verified_monitoring_samples",
                            "model_promotion_allowed",
                        }
                            or type(completed.get("feature_availability_verified")) is not bool
                            or completed.get("verified_monitoring_samples") is not None
                            or completed.get("model_promotion_allowed") is not False
                            or not re.fullmatch("[0-9a-f]{64}", completed.get("content_hash", ""))):
                        raise ValueError("invalid AU feature provenance receipt")
                    path_key = "report_path"
                elif action == "tennis-feature-provenance":
                    if (set(completed) != {
                            "disposition", "status", "report_path", "content_hash",
                            "feature_availability_verified", "verified_monitoring_samples",
                            "model_promotion_allowed",
                        }
                            or type(completed.get("feature_availability_verified")) is not bool
                            or completed.get("verified_monitoring_samples") is not None
                            or completed.get("model_promotion_allowed") is not False
                            or not re.fullmatch("[0-9a-f]{64}", completed.get("content_hash", ""))):
                        raise ValueError("invalid Tennis feature provenance receipt")
                    path_key = "report_path"
                elif action == "hkjc-feature-provenance":
                    if (set(completed) != {
                            "disposition", "status", "report_path", "content_hash",
                            "feature_availability_verified", "verified_monitoring_samples",
                            "model_promotion_allowed",
                        }
                            or type(completed.get("feature_availability_verified")) is not bool
                            or completed.get("verified_monitoring_samples") is not None
                            or completed.get("model_promotion_allowed") is not False
                            or not re.fullmatch("[0-9a-f]{64}", completed.get("content_hash", ""))):
                        raise ValueError("invalid HKJC feature provenance receipt")
                    path_key = "report_path"
                elif action == "nba-feature-provenance":
                    if (set(completed) != {
                            "disposition", "status", "report_path", "content_hash",
                            "feature_availability_verified", "verified_monitoring_samples",
                            "model_promotion_allowed",
                        }
                            or type(completed.get("feature_availability_verified")) is not bool
                            or completed.get("verified_monitoring_samples") is not None
                            or completed.get("model_promotion_allowed") is not False
                            or not re.fullmatch("[0-9a-f]{64}", completed.get("content_hash", ""))):
                        raise ValueError("invalid NBA feature provenance receipt")
                    path_key = "report_path"
                elif action == "racing-monitoring-samples":
                    if (set(completed) != {
                            "disposition", "status", "report_path", "content_hash",
                            "verified_monitoring_samples", "terminal_labels_emitted",
                            "model_promotion_allowed", "reevaluate_promotion_allowed",
                        }
                            or type(completed.get("verified_monitoring_samples")) is not int
                            or not 0 <= completed["verified_monitoring_samples"] <= 10000
                            or completed.get("terminal_labels_emitted") is not False
                            or completed.get("model_promotion_allowed") is not False
                            or completed.get("reevaluate_promotion_allowed") is not False
                            or not re.fullmatch("[0-9a-f]{64}", completed.get("content_hash", ""))):
                        raise ValueError("invalid racing monitoring sample receipt")
                    path_key = "report_path"
                elif action == "nba-monitoring-samples":
                    if (set(completed) != {
                            "disposition", "status", "report_path", "content_hash",
                            "verified_monitoring_samples", "terminal_labels_emitted",
                            "model_promotion_allowed", "reevaluate_promotion_allowed",
                        }
                            or type(completed.get("verified_monitoring_samples")) is not int
                            or not 0 <= completed["verified_monitoring_samples"] <= 10000
                            or completed.get("terminal_labels_emitted") is not False
                            or completed.get("model_promotion_allowed") is not False
                            or completed.get("reevaluate_promotion_allowed") is not False
                            or not re.fullmatch("[0-9a-f]{64}", completed.get("content_hash", ""))):
                        raise ValueError("invalid NBA monitoring sample receipt")
                    path_key = "report_path"
                elif action == "tennis-monitoring-samples":
                    if (set(completed) != {
                            "disposition", "status", "report_path", "content_hash",
                            "verified_monitoring_samples", "terminal_labels_emitted",
                            "model_promotion_allowed", "reevaluate_promotion_allowed",
                        }
                            or type(completed.get("verified_monitoring_samples")) is not int
                            or not 0 <= completed["verified_monitoring_samples"] <= 100000
                            or completed.get("terminal_labels_emitted") is not False
                            or completed.get("model_promotion_allowed") is not False
                            or completed.get("reevaluate_promotion_allowed") is not False
                            or not re.fullmatch("[0-9a-f]{64}", completed.get("content_hash", ""))):
                        raise ValueError("invalid Tennis monitoring sample receipt")
                    path_key = "report_path"
                elif action == "research-storage-evidence":
                    if (set(completed) != {
                            "disposition", "status", "report_path", "content_hash",
                            "storage_health", "historical_availability_verified",
                            "process_liveness_verified", "live_drift_verified",
                            "model_promotion_allowed",
                        }
                            or completed.get("storage_health") not in {"ok", "attention"}
                            or completed.get("historical_availability_verified") is not False
                            or completed.get("process_liveness_verified") is not False
                            or completed.get("live_drift_verified") is not False
                            or completed.get("model_promotion_allowed") is not False
                            or not re.fullmatch("[0-9a-f]{64}", completed.get("content_hash", ""))):
                        raise ValueError("invalid research storage evidence receipt")
                    path_key = "report_path"
                elif action == "research-liveness-evidence":
                    if (set(completed) != {
                            "disposition", "status", "report_path", "content_hash",
                            "process_liveness_verified", "all_claimed_processes_verified",
                            "running_verified", "unverified_claims",
                            "model_promotion_allowed", "queue_mutation_allowed",
                        }
                            or completed.get("process_liveness_verified") is not True
                            or type(completed.get("all_claimed_processes_verified")) is not bool
                            or type(completed.get("running_verified")) is not int
                            or not 0 <= completed["running_verified"] <= 1000
                            or type(completed.get("unverified_claims")) is not int
                            or not 0 <= completed["unverified_claims"] <= 1000
                            or completed.get("model_promotion_allowed") is not False
                            or completed.get("queue_mutation_allowed") is not False
                            or not re.fullmatch("[0-9a-f]{64}", completed.get("content_hash", ""))):
                        raise ValueError("invalid research liveness evidence receipt")
                    path_key = "report_path"
                elif action == "research-production-day-evidence":
                    if (set(completed) != {
                            "disposition", "status", "report_path", "content_hash",
                            "production_day_closed", "schedule_attestation_verified",
                            "expected_runs", "terminal_runs", "model_promotion_allowed",
                            "schedule_mutation_allowed",
                        }
                            or type(completed.get("production_day_closed")) is not bool
                            or type(completed.get("schedule_attestation_verified")) is not bool
                            or type(completed.get("expected_runs")) is not int
                            or not 0 <= completed["expected_runs"] <= 1000
                            or type(completed.get("terminal_runs")) is not int
                            or not 0 <= completed["terminal_runs"] <= completed["expected_runs"]
                            or completed.get("model_promotion_allowed") is not False
                            or completed.get("schedule_mutation_allowed") is not False
                            or not re.fullmatch("[0-9a-f]{64}", completed.get("content_hash", ""))):
                        raise ValueError("invalid research production-day evidence receipt")
                    path_key = "report_path"
                elif action == "research-live-drift":
                    if (set(completed) != {
                            "disposition", "status", "report_path", "content_hash",
                            "live_drift_verified", "feature_health", "direction",
                            "metric_drift_verified", "market_drift_verified",
                            "model_promotion_allowed",
                        }
                            or type(completed.get("live_drift_verified")) is not bool
                            or completed.get("feature_health")
                            not in {"ok", "attention", "unknown"}
                            or completed.get("direction")
                            not in {"improved", "degraded", "unchanged", "unknown"}
                            or completed.get("metric_drift_verified") is not False
                            or completed.get("market_drift_verified") is not False
                            or completed.get("model_promotion_allowed") is not False
                            or not re.fullmatch(
                                "[0-9a-f]{64}", completed.get("content_hash", "")
                            )):
                        raise ValueError("invalid research live drift receipt")
                    path_key = "report_path"
                elif action in {"power-dev-engine", "power-dev-producer"}:
                    raise ValueError("legacy power dev automation is disabled")
                elif action == "power-projection":
                    if (set(completed) != {
                            "disposition", "status", "report_path", "content_hash",
                            "source_role", "power_profile_write_allowed",
                            "verified_monitoring_samples", "model_promotion_allowed",
                        }
                            or completed.get("source_role") != "development_only"
                            or completed.get("power_profile_write_allowed") is not False
                            or completed.get("verified_monitoring_samples") is not None
                            or completed.get("model_promotion_allowed") is not False
                            or not re.fullmatch("[0-9a-f]{64}", completed.get("content_hash", ""))):
                        raise ValueError("invalid power projection receipt")
                    path_key = "report_path"
                elif action == "power-variance":
                    if (set(completed) != {
                            "disposition", "status", "report_path", "content_hash",
                            "variance_input_contract_verified", "power_profile_write_allowed",
                            "verified_monitoring_samples", "model_promotion_allowed",
                        }
                            or completed.get("variance_input_contract_verified") is not True
                            or completed.get("power_profile_write_allowed") is not False
                            or completed.get("verified_monitoring_samples") is not None
                            or completed.get("model_promotion_allowed") is not False
                            or not re.fullmatch("[0-9a-f]{64}", completed.get("content_hash", ""))):
                        raise ValueError("invalid power variance receipt")
                    path_key = "report_path"
                else:
                    record_id = completed["run_id"] if action == "scoring" else completed["dataset_manifest_id"]
                    record = registry.load(record_id)
                    if record["links"]["spec_id"] != spec.record_id:
                        raise ValueError("phase receipt has wrong registered spec")
                    path_key = "artifact_path" if action == "scoring" else "snapshot_path"
                returned_path = Path(completed[path_key])
                if not returned_path.is_relative_to(attempt) or any(
                    path.is_symlink() for path in (returned_path, *returned_path.parents)
                ):
                    raise ValueError("phase output is outside owned attempt")
                if action == "reconcile":
                    verifier = (
                        verify_phase_reconciliation_receipt
                        if payload["kind"] == "phase"
                        else verify_reconciliation_receipt
                    )
                    verifier(
                        spec,
                        registry=registry,
                        report_path=returned_path,
                        receipt=completed,
                        request_sha256=payload["request_sha256"],
                    )
                elif action == "review":
                    from .research_review_runtime import verify_review_summary
                    verify_review_summary(request=request, runtime=runtime, report_path=returned_path, receipt=completed,
                                          require_current_freeze=True,
                                          require_current_storage=True,
                                          require_current_liveness=True,
                                          require_current_production_day=True,
                                          require_current_drift=True)
                elif action == "prediction-artifacts":
                    from .research_prediction_artifacts import verify_prediction_artifact_report
                    if returned_path.stat().st_size > 131072:
                        raise ValueError("oversized prediction artifact report")
                    stored_report = _strict_json(returned_path.read_text())
                    verify_prediction_artifact_report(
                        stored_report, root=Path(payload["evidence_root"]),
                        domain=Domain(payload["domain"]), as_of=payload["as_of"],
                        relocation_roots=tuple(Path(item) for item in payload["relocation_roots"]),
                    )
                    if stored_report["content_hash"] != completed["content_hash"]:
                        raise ValueError("prediction artifact report/receipt mismatch")
                elif action == "au-settlement-candidates":
                    from .research_au_settlement_source import verify_au_settlement_candidate_report
                    if returned_path.stat().st_size > 262144:
                        raise ValueError("oversized AU settlement candidate report")
                    stored_report = _strict_json(returned_path.read_text())
                    verify_au_settlement_candidate_report(
                        stored_report, root=Path(payload["evidence_root"]),
                        as_of=payload["as_of"],
                        relocation_roots=tuple(Path(item) for item in payload["relocation_roots"]),
                    )
                    if stored_report["content_hash"] != completed["content_hash"]:
                        raise ValueError("AU settlement candidate report/receipt mismatch")
                elif action == "nba-settlement-candidates":
                    from .research_nba_settlement_source import verify_nba_settlement_candidate_report
                    if returned_path.stat().st_size > 262144:
                        raise ValueError("oversized NBA settlement candidate report")
                    stored_report = _strict_json(returned_path.read_text())
                    verify_nba_settlement_candidate_report(
                        stored_report, root=Path(payload["evidence_root"]),
                        as_of=payload["as_of"],
                        relocation_roots=tuple(Path(item) for item in payload["relocation_roots"]),
                    )
                    if stored_report["content_hash"] != completed["content_hash"]:
                        raise ValueError("NBA settlement candidate report/receipt mismatch")
                elif action == "hkjc-settlement-candidates":
                    from .research_hkjc_settlement_source import verify_hkjc_settlement_candidate_report
                    if returned_path.stat().st_size > 262144:
                        raise ValueError("oversized HKJC settlement candidate report")
                    stored_report = _strict_json(returned_path.read_text())
                    verify_hkjc_settlement_candidate_report(
                        stored_report, root=Path(payload["evidence_root"]),
                        as_of=payload["as_of"],
                        relocation_roots=tuple(Path(item) for item in payload["relocation_roots"]),
                    )
                    if stored_report["content_hash"] != completed["content_hash"]:
                        raise ValueError("HKJC settlement candidate report/receipt mismatch")
                elif action == "tennis-settlement-candidates":
                    from .research_tennis_settlement_source import verify_tennis_settlement_candidate_report
                    if returned_path.stat().st_size > 262144:
                        raise ValueError("oversized Tennis settlement candidate report")
                    stored_report = _strict_json(returned_path.read_text())
                    verify_tennis_settlement_candidate_report(
                        stored_report, root=Path(payload["evidence_root"]),
                        as_of=payload["as_of"],
                        relocation_roots=tuple(Path(item) for item in payload["relocation_roots"]),
                    )
                    if stored_report["content_hash"] != completed["content_hash"]:
                        raise ValueError("Tennis settlement candidate report/receipt mismatch")
                elif action == "au-feature-provenance":
                    from .research_au_feature_provenance import verify_au_feature_provenance_report
                    if returned_path.stat().st_size > 262144:
                        raise ValueError("oversized AU feature provenance report")
                    stored_report = _strict_json(returned_path.read_text())
                    verify_au_feature_provenance_report(
                        stored_report, root=Path(payload["evidence_root"]),
                        as_of=payload["as_of"],
                        relocation_roots=tuple(Path(item) for item in payload["relocation_roots"]),
                    )
                    if (stored_report["content_hash"] != completed["content_hash"]
                            or stored_report["feature_availability_verified"]
                            is not completed["feature_availability_verified"]):
                        raise ValueError("AU feature provenance report/receipt mismatch")
                elif action == "tennis-feature-provenance":
                    from .research_tennis_feature_provenance import verify_tennis_feature_provenance_report
                    if returned_path.stat().st_size > 262144:
                        raise ValueError("oversized Tennis feature provenance report")
                    stored_report = _strict_json(returned_path.read_text())
                    verify_tennis_feature_provenance_report(
                        stored_report, root=Path(payload["evidence_root"]),
                        as_of=payload["as_of"],
                        relocation_roots=tuple(Path(item) for item in payload["relocation_roots"]),
                    )
                    if (stored_report["content_hash"] != completed["content_hash"]
                            or stored_report["feature_availability_verified"]
                            is not completed["feature_availability_verified"]):
                        raise ValueError("Tennis feature provenance report/receipt mismatch")
                elif action == "hkjc-feature-provenance":
                    from .research_hkjc_feature_provenance import verify_hkjc_feature_provenance_report
                    if returned_path.stat().st_size > 262144:
                        raise ValueError("oversized HKJC feature provenance report")
                    stored_report = _strict_json(returned_path.read_text())
                    verify_hkjc_feature_provenance_report(
                        stored_report, root=Path(payload["evidence_root"]),
                        as_of=payload["as_of"],
                        relocation_roots=tuple(Path(item) for item in payload["relocation_roots"]),
                    )
                    if (stored_report["content_hash"] != completed["content_hash"]
                            or stored_report["feature_availability_verified"]
                            is not completed["feature_availability_verified"]):
                        raise ValueError("HKJC feature provenance report/receipt mismatch")
                elif action == "nba-feature-provenance":
                    from .research_nba_feature_provenance import verify_nba_feature_provenance_report
                    if returned_path.stat().st_size > 262144:
                        raise ValueError("oversized NBA feature provenance report")
                    stored_report = _strict_json(returned_path.read_text())
                    verify_nba_feature_provenance_report(
                        stored_report, root=Path(payload["evidence_root"]),
                        as_of=payload["as_of"],
                        relocation_roots=tuple(Path(item) for item in payload["relocation_roots"]),
                    )
                    if (stored_report["content_hash"] != completed["content_hash"]
                            or stored_report["feature_availability_verified"]
                            is not completed["feature_availability_verified"]):
                        raise ValueError("NBA feature provenance report/receipt mismatch")
                elif action == "racing-monitoring-samples":
                    from .research_racing_monitoring_samples import (
                        verify_racing_monitoring_sample_report,
                    )
                    if returned_path.stat().st_size > 1048576:
                        raise ValueError("oversized racing monitoring sample report")
                    stored_report = _strict_json(returned_path.read_text())
                    verify_racing_monitoring_sample_report(
                        stored_report,
                        root=Path(payload["evidence_root"]),
                        domain=Domain(payload["domain"]),
                        as_of=payload["as_of"],
                        relocation_roots=tuple(
                            Path(item) for item in payload["relocation_roots"]
                        ),
                    )
                    if (stored_report["content_hash"] != completed["content_hash"]
                            or stored_report["verified_monitoring_samples"]
                            != completed["verified_monitoring_samples"]):
                        raise ValueError("racing monitoring sample report/receipt mismatch")
                elif action == "nba-monitoring-samples":
                    from .research_nba_monitoring_samples import (
                        verify_nba_monitoring_sample_report,
                    )
                    if returned_path.stat().st_size > 1048576:
                        raise ValueError("oversized NBA monitoring sample report")
                    stored_report = _strict_json(returned_path.read_text())
                    verify_nba_monitoring_sample_report(
                        stored_report,
                        root=Path(payload["evidence_root"]),
                        as_of=payload["as_of"],
                        relocation_roots=tuple(
                            Path(item) for item in payload["relocation_roots"]
                        ),
                    )
                    if (stored_report["content_hash"] != completed["content_hash"]
                            or stored_report["verified_monitoring_samples"]
                            != completed["verified_monitoring_samples"]):
                        raise ValueError("NBA monitoring sample report/receipt mismatch")
                elif action == "tennis-monitoring-samples":
                    from .research_tennis_monitoring_samples import (
                        verify_tennis_monitoring_sample_report,
                    )
                    if returned_path.stat().st_size > 1048576:
                        raise ValueError("oversized Tennis monitoring sample report")
                    stored_report = _strict_json(returned_path.read_text())
                    verify_tennis_monitoring_sample_report(
                        stored_report,
                        root=Path(payload["evidence_root"]),
                        as_of=payload["as_of"],
                        relocation_roots=tuple(
                            Path(item) for item in payload["relocation_roots"]
                        ),
                    )
                    if (stored_report["content_hash"] != completed["content_hash"]
                            or stored_report["verified_monitoring_samples"]
                            != completed["verified_monitoring_samples"]):
                        raise ValueError("Tennis monitoring sample report/receipt mismatch")
                elif action == "research-storage-evidence":
                    from .research_storage_evidence import verify_research_storage_evidence
                    if returned_path.stat().st_size > 32768:
                        raise ValueError("oversized research storage evidence report")
                    stored_report = _strict_json(returned_path.read_text())
                    verify_research_storage_evidence(
                        stored_report,
                        repo_root=Path(payload["repo_root"]),
                        state_root=Path(payload["storage_state_root"]),
                        domain=Domain(payload["domain"]),
                        as_of=payload["as_of"],
                        reverify_source=True,
                    )
                    if (stored_report["content_hash"] != completed["content_hash"]
                            or stored_report["storage_health"]
                            != completed["storage_health"]):
                        raise ValueError("research storage evidence report/receipt mismatch")
                elif action == "research-liveness-evidence":
                    from .research_liveness import verify_research_liveness_evidence
                    if returned_path.stat().st_size > 1048576:
                        raise ValueError("oversized research liveness evidence report")
                    stored_report = _strict_json(returned_path.read_text())
                    verify_research_liveness_evidence(
                        stored_report,
                        registry_root=registry.root,
                        queue_root=Path(payload["queue_root"]),
                        lease_root=Path(payload["lease_root"]),
                        domain=Domain(payload["domain"]),
                        as_of=payload["as_of"],
                        reverify_source=True,
                    )
                    if (stored_report["content_hash"] != completed["content_hash"]
                            or stored_report["process_liveness_verified"]
                            != completed["process_liveness_verified"]
                            or stored_report["all_claimed_processes_verified"]
                            != completed["all_claimed_processes_verified"]
                            or stored_report["counts"]["running_verified"]
                            != completed["running_verified"]
                            or stored_report["counts"]["claimed_liveness_unverified"]
                            != completed["unverified_claims"]):
                        raise ValueError("research liveness evidence report/receipt mismatch")
                elif action == "research-production-day-evidence":
                    from .research_production_day import verify_production_day_evidence
                    if returned_path.stat().st_size > 1048576:
                        raise ValueError("oversized research production-day evidence report")
                    stored_report = _strict_json(returned_path.read_text())
                    verify_production_day_evidence(
                        stored_report,
                        run_root=Path(payload["run_root"]),
                        attestation_path=(
                            Path(payload["attestation_path"])
                            if payload["attestation_path"] is not None else None
                        ),
                        domain=Domain(payload["domain"]),
                        production_day=date.fromisoformat(payload["production_day"]),
                        as_of=payload["as_of"],
                        reverify_source=True,
                    )
                    if (stored_report["content_hash"] != completed["content_hash"]
                            or stored_report["production_day_closed"]
                            != completed["production_day_closed"]
                            or stored_report["schedule_attestation_verified"]
                            != completed["schedule_attestation_verified"]
                            or stored_report["counts"]["expected"]
                            != completed["expected_runs"]
                            or stored_report["counts"]["terminal"]
                            != completed["terminal_runs"]):
                        raise ValueError("research production-day evidence report/receipt mismatch")
                elif action == "research-live-drift":
                    from .research_live_drift import verify_live_feature_drift_report
                    if returned_path.stat().st_size > 32768:
                        raise ValueError("oversized research live drift report")
                    stored_report = _strict_json(returned_path.read_text())
                    verify_live_feature_drift_report(
                        stored_report,
                        root=Path(payload["evidence_root"]),
                        domain=Domain(payload["domain"]),
                        baseline_as_of=payload["baseline_as_of"],
                        as_of=payload["as_of"],
                        relocation_roots=tuple(
                            Path(item) for item in payload["relocation_roots"]
                        ),
                        reverify_source=True,
                    )
                    if (stored_report["content_hash"] != completed["content_hash"]
                            or stored_report["live_drift_verified"]
                            is not completed["live_drift_verified"]
                            or stored_report["feature_health"]
                            != completed["feature_health"]
                            or stored_report["direction"] != completed["direction"]):
                        raise ValueError("research live drift report/receipt mismatch")
                elif action == "power-projection":
                    from .research_index import _hash
                    from .research_power_projection import verify_power_variance_projection
                    if returned_path.stat().st_size > 16777216:
                        raise ValueError("oversized power projection")
                    stored_report = _strict_json(returned_path.read_text())
                    verify_power_variance_projection(
                        output_path=returned_path,
                        baseline_path=Path(payload["baseline_path"]),
                        comparator_path=Path(payload["comparator_path"]),
                        domain=Domain(payload["domain"]),
                        as_of=payload["as_of"],
                        ruler_root=Path(payload["ruler_root"]),
                    )
                    if _hash(stored_report) != completed["content_hash"]:
                        raise ValueError("power projection/receipt mismatch")
                elif action == "power-variance":
                    from .research_power_variance import verify_power_variance_report
                    if returned_path.stat().st_size > 131072:
                        raise ValueError("oversized power variance report")
                    stored_report = _strict_json(returned_path.read_text())
                    verify_power_variance_report(
                        stored_report,
                        input_path=Path(payload["input_path"]),
                        domain=Domain(payload["domain"]),
                        as_of=payload["as_of"],
                        ruler_root=Path(payload["ruler_root"]),
                    )
                    if stored_report["content_hash"] != completed["content_hash"]:
                        raise ValueError("power variance report/receipt mismatch")
                elif action == "notify":
                    from .research_notification_runtime import verify_notification_summary
                    verify_notification_summary(request=request, runtime=runtime, report_path=returned_path, receipt=completed)
            elif action == "notify" and not completed.get("interrupted"):
                if completed not in ({"disposition": "deferred", "status": "heavy_worker_busy"},
                                     {"disposition": "failed", "status": "notification_worker_failed"}):
                    raise ValueError("invalid non-success notification completion")
            if completed.get("interrupted") is True:
                disposition = _read_interruption(completed)
                outcome["publication"] = "unconfirmed_reconcile_before_retry"
            else:
                outcome["publication"] = "receipt_verified"
    except Exception as exc:
        disposition = (
            ResearchDisposition.TIMED_OUT if isinstance(exc, ResourceInterrupted) else ResearchDisposition.FAILED
        )
        status = "notification_phase_failed" if action == "notify" else f"{type(exc).__name__}: {exc}"
        completed = None
    outcome.update({"disposition": disposition.value, "status": status, "result": completed})
    _record_attempt_outcome(runtime, attempt, "phase-outcome.json", outcome)
    return disposition, status, attempt, completed


@dataclass(frozen=True)
class SourceInspectionResult:
    disposition: ResearchDisposition
    status: str
    attempt_path: Path | None = None
    report_path: Path | None = None
    content_hash: str | None = None


@dataclass(frozen=True)
class ReconciliationResult:
    disposition: ResearchDisposition
    status: str
    attempt_path: Path | None = None
    report_path: Path | None = None
    decision_id: str | None = None
    content_hash: str | None = None
    record_id: str | None = None


class PostflightReconciliationRunner:
    """Inspect an explicitly pinned prior attempt; never rerun or auto-publish."""

    kind = "postflight"

    def __init__(self, runtime: ResearchRuntime, registry: ExperimentRegistry):
        self.runtime, self.registry = runtime, registry

    def run(self, spec, *, attempt_path, request_sha256, estimated_bytes, timeout_seconds):
        if not isinstance(request_sha256, str) or not re.fullmatch("[0-9a-f]{64}", request_sha256):
            raise ValueError("pinned request SHA-256 required")
        disposition, status, attempt, receipt = _phase(
            self.runtime,
            self.registry,
            spec,
            action="reconcile",
            payload={"attempt_path": str(attempt_path.absolute()), "request_sha256": request_sha256, "kind": self.kind},
            estimated_bytes=estimated_bytes,
            timeout_seconds=timeout_seconds,
        )
        valid = receipt if disposition is ResearchDisposition.SUCCEEDED else {}
        return ReconciliationResult(
            disposition,
            status,
            attempt,
            Path(valid["report_path"]) if valid.get("report_path") else None,
            valid.get("decision_id"),
            valid.get("content_hash"),
            valid.get("record_id"),
        )


class PhaseReconciliationRunner(PostflightReconciliationRunner):
    """Preparation/scoring evidence only; never evaluation/promotion authority."""

    kind = "phase"


class TennisSourceInspectionRunner:
    """Pre-spec inventory only: no registry append or evaluation authority."""

    def __init__(self, runtime: ResearchRuntime, registry: ExperimentRegistry):
        self.runtime, self.registry = runtime, registry

    def run(
        self,
        db_path: Path,
        policy: TennisSourcePolicy,
        *,
        estimated_bytes: int,
        timeout_seconds: float,
        witnesses: tuple[SnapshotWitness, ...] = (),
    ):
        policy.validate()
        witness_payloads = [witness.to_payload() for witness in witnesses]
        if len({item["artifact_id"] for item in witness_payloads}) != len(witness_payloads):
            raise ValueError("duplicate snapshot witness")
        disposition, status, attempt, receipt = _phase(
            self.runtime,
            self.registry,
            None,
            action="tennis-source",
            payload={
                "db_path": str(db_path.expanduser().absolute()),
                "policy": asdict(policy),
                "witnesses": witness_payloads,
            },
            estimated_bytes=estimated_bytes,
            timeout_seconds=timeout_seconds,
        )
        return SourceInspectionResult(
            disposition,
            status,
            attempt,
            Path(receipt["report_path"]) if receipt and receipt.get("report_path") else None,
            receipt.get("content_hash") if receipt else None,
        )


class PredictionArtifactInspectionRunner:
    """Supervised read-only bundle integrity; never a normalized dataset grant."""

    def __init__(self, runtime: ResearchRuntime, registry: ExperimentRegistry):
        self.runtime, self.registry = runtime, registry

    def run(self, *, domain: Domain, evidence_root: Path, as_of,
            relocation_roots: tuple[Path, ...] = (), estimated_bytes: int,
            timeout_seconds: float):
        from .research_index import _at
        if not isinstance(domain, Domain) or not isinstance(relocation_roots, tuple):
            raise ValueError("known domain and tuple relocation roots required")
        payload = {"domain": domain.value, "evidence_root": str(evidence_root.expanduser().absolute()),
                   "as_of": _at(as_of).isoformat(),
                   "relocation_roots": [str(path.expanduser().absolute()) for path in relocation_roots]}
        disposition, status, attempt, receipt = _phase(
            self.runtime, self.registry, None, action="prediction-artifacts", payload=payload,
            estimated_bytes=estimated_bytes, timeout_seconds=timeout_seconds,
        )
        valid = receipt if disposition is ResearchDisposition.SUCCEEDED else {}
        return SourceInspectionResult(disposition, status, attempt,
                                      Path(valid["report_path"]) if valid.get("report_path") else None,
                                      valid.get("content_hash"))


class AuSettlementCandidateInspectionRunner:
    """Supervised label applicability inventory; never sample authority."""

    def __init__(self, runtime: ResearchRuntime, registry: ExperimentRegistry):
        self.runtime, self.registry = runtime, registry

    def run(self, *, evidence_root: Path, as_of, relocation_roots: tuple[Path, ...] = (),
            estimated_bytes: int, timeout_seconds: float):
        from .research_index import _at
        if not isinstance(relocation_roots, tuple):
            raise ValueError("tuple relocation roots required")
        payload = {
            "domain": Domain.AU.value,
            "evidence_root": str(evidence_root.expanduser().absolute()),
            "as_of": _at(as_of).isoformat(),
            "relocation_roots": [str(path.expanduser().absolute()) for path in relocation_roots],
        }
        disposition, status, attempt, receipt = _phase(
            self.runtime, self.registry, None, action="au-settlement-candidates", payload=payload,
            estimated_bytes=estimated_bytes, timeout_seconds=timeout_seconds,
        )
        valid = receipt if disposition is ResearchDisposition.SUCCEEDED else {}
        return SourceInspectionResult(
            disposition, status, attempt,
            Path(valid["report_path"]) if valid.get("report_path") else None,
            valid.get("content_hash"),
        )


class NbaSettlementCandidateInspectionRunner:
    """Supervised NBA label applicability inventory; never sample authority."""

    def __init__(self, runtime: ResearchRuntime, registry: ExperimentRegistry):
        self.runtime, self.registry = runtime, registry

    def run(self, *, evidence_root: Path, as_of, relocation_roots: tuple[Path, ...] = (),
            estimated_bytes: int, timeout_seconds: float):
        from .research_index import _at
        if not isinstance(relocation_roots, tuple):
            raise ValueError("tuple relocation roots required")
        payload = {
            "domain": Domain.NBA.value,
            "evidence_root": str(evidence_root.expanduser().absolute()),
            "as_of": _at(as_of).isoformat(),
            "relocation_roots": [str(path.expanduser().absolute()) for path in relocation_roots],
        }
        disposition, status, attempt, receipt = _phase(
            self.runtime, self.registry, None, action="nba-settlement-candidates", payload=payload,
            estimated_bytes=estimated_bytes, timeout_seconds=timeout_seconds,
        )
        valid = receipt if disposition is ResearchDisposition.SUCCEEDED else {}
        return SourceInspectionResult(
            disposition, status, attempt,
            Path(valid["report_path"]) if valid.get("report_path") else None,
            valid.get("content_hash"),
        )


class HkjcSettlementCandidateInspectionRunner:
    """Supervised HKJC label applicability inventory; never sample authority."""

    def __init__(self, runtime: ResearchRuntime, registry: ExperimentRegistry):
        self.runtime, self.registry = runtime, registry

    def run(self, *, evidence_root: Path, as_of, relocation_roots: tuple[Path, ...] = (),
            estimated_bytes: int, timeout_seconds: float):
        from .research_index import _at
        if not isinstance(relocation_roots, tuple):
            raise ValueError("tuple relocation roots required")
        payload = {
            "domain": Domain.HKJC.value,
            "evidence_root": str(evidence_root.expanduser().absolute()),
            "as_of": _at(as_of).isoformat(),
            "relocation_roots": [str(path.expanduser().absolute()) for path in relocation_roots],
        }
        disposition, status, attempt, receipt = _phase(
            self.runtime, self.registry, None, action="hkjc-settlement-candidates", payload=payload,
            estimated_bytes=estimated_bytes, timeout_seconds=timeout_seconds,
        )
        valid = receipt if disposition is ResearchDisposition.SUCCEEDED else {}
        return SourceInspectionResult(
            disposition, status, attempt,
            Path(valid["report_path"]) if valid.get("report_path") else None,
            valid.get("content_hash"),
        )


class RacingMonitoringSampleInspectionRunner:
    """Supervised AU/HKJC settled-race sample projection; no model authority."""

    def __init__(self, runtime: ResearchRuntime, registry: ExperimentRegistry):
        self.runtime, self.registry = runtime, registry

    def run(self, *, domain: Domain, evidence_root: Path, as_of,
            relocation_roots: tuple[Path, ...] = (), estimated_bytes: int,
            timeout_seconds: float):
        from .research_index import _at
        if domain not in {Domain.AU, Domain.HKJC} or not isinstance(relocation_roots, tuple):
            raise ValueError("AU/HKJC domain and tuple relocation roots required")
        payload = {
            "domain": domain.value,
            "evidence_root": str(evidence_root.expanduser().absolute()),
            "as_of": _at(as_of).isoformat(),
            "relocation_roots": [
                str(path.expanduser().absolute()) for path in relocation_roots
            ],
        }
        disposition, status, attempt, receipt = _phase(
            self.runtime, self.registry, None, action="racing-monitoring-samples",
            payload=payload, estimated_bytes=estimated_bytes,
            timeout_seconds=timeout_seconds,
        )
        valid = receipt if disposition is ResearchDisposition.SUCCEEDED else {}
        return SourceInspectionResult(
            disposition, status, attempt,
            Path(valid["report_path"]) if valid.get("report_path") else None,
            valid.get("content_hash"),
        )


class NbaMonitoringSampleInspectionRunner:
    """Supervised NBA forward-settled sample projection; no model authority."""

    def __init__(self, runtime: ResearchRuntime, registry: ExperimentRegistry):
        self.runtime, self.registry = runtime, registry

    def run(self, *, evidence_root: Path, as_of,
            relocation_roots: tuple[Path, ...] = (), estimated_bytes: int,
            timeout_seconds: float):
        from .research_index import _at
        if not isinstance(relocation_roots, tuple):
            raise ValueError("tuple relocation roots required")
        payload = {
            "domain": Domain.NBA.value,
            "evidence_root": str(evidence_root.expanduser().absolute()),
            "as_of": _at(as_of).isoformat(),
            "relocation_roots": [
                str(path.expanduser().absolute()) for path in relocation_roots
            ],
        }
        disposition, status, attempt, receipt = _phase(
            self.runtime, self.registry, None, action="nba-monitoring-samples",
            payload=payload, estimated_bytes=estimated_bytes,
            timeout_seconds=timeout_seconds,
        )
        valid = receipt if disposition is ResearchDisposition.SUCCEEDED else {}
        return SourceInspectionResult(
            disposition, status, attempt,
            Path(valid["report_path"]) if valid.get("report_path") else None,
            valid.get("content_hash"),
        )


class TennisMonitoringSampleInspectionRunner:
    """Supervised Tennis family sample projection; no model authority."""

    def __init__(self, runtime: ResearchRuntime, registry: ExperimentRegistry):
        self.runtime, self.registry = runtime, registry

    def run(self, *, evidence_root: Path, as_of,
            relocation_roots: tuple[Path, ...] = (), estimated_bytes: int,
            timeout_seconds: float):
        from .research_index import _at
        if not isinstance(relocation_roots, tuple):
            raise ValueError("tuple relocation roots required")
        payload = {
            "domain": Domain.TENNIS.value,
            "evidence_root": str(evidence_root.expanduser().absolute()),
            "as_of": _at(as_of).isoformat(),
            "relocation_roots": [
                str(path.expanduser().absolute()) for path in relocation_roots
            ],
        }
        disposition, status, attempt, receipt = _phase(
            self.runtime, self.registry, None, action="tennis-monitoring-samples",
            payload=payload, estimated_bytes=estimated_bytes,
            timeout_seconds=timeout_seconds,
        )
        valid = receipt if disposition is ResearchDisposition.SUCCEEDED else {}
        return SourceInspectionResult(
            disposition, status, attempt,
            Path(valid["report_path"]) if valid.get("report_path") else None,
            valid.get("content_hash"),
        )


class ResearchStorageEvidenceInspectionRunner:
    """Supervised point-in-time storage projection; no liveness/model authority."""

    def __init__(self, runtime: ResearchRuntime, registry: ExperimentRegistry):
        self.runtime, self.registry = runtime, registry

    def run(self, *, domain: Domain, repo_root: Path, storage_state_root: Path,
            as_of, estimated_bytes: int, timeout_seconds: float):
        from .research_index import _at
        if not isinstance(domain, Domain):
            raise ValueError("known domain required")
        payload = {
            "domain": domain.value,
            "repo_root": str(repo_root.expanduser().absolute()),
            "storage_state_root": str(storage_state_root.expanduser().absolute()),
            "as_of": _at(as_of).isoformat(),
        }
        disposition, status, attempt, receipt = _phase(
            self.runtime, self.registry, None, action="research-storage-evidence",
            payload=payload, estimated_bytes=estimated_bytes,
            timeout_seconds=timeout_seconds,
        )
        valid = receipt if disposition is ResearchDisposition.SUCCEEDED else {}
        return SourceInspectionResult(
            disposition, status, attempt,
            Path(valid["report_path"]) if valid.get("report_path") else None,
            valid.get("content_hash"),
        )


class ResearchLivenessInspectionRunner:
    """Supervised queue liveness projection; cannot mutate queue or model."""

    def __init__(self, runtime: ResearchRuntime, registry: ExperimentRegistry):
        self.runtime, self.registry = runtime, registry

    def run(self, *, domain: Domain, queue_root: Path, lease_root: Path,
            as_of, estimated_bytes: int, timeout_seconds: float):
        from .research_index import _at
        if not isinstance(domain, Domain):
            raise ValueError("known domain required")
        payload = {
            "domain": domain.value,
            "queue_root": str(queue_root.expanduser().absolute()),
            "lease_root": str(lease_root.expanduser().absolute()),
            "as_of": _at(as_of).isoformat(),
        }
        disposition, status, attempt, receipt = _phase(
            self.runtime, self.registry, None,
            action="research-liveness-evidence", payload=payload,
            estimated_bytes=estimated_bytes, timeout_seconds=timeout_seconds,
        )
        valid = receipt if disposition is ResearchDisposition.SUCCEEDED else {}
        return SourceInspectionResult(
            disposition, status, attempt,
            Path(valid["report_path"]) if valid.get("report_path") else None,
            valid.get("content_hash"),
        )


class ResearchProductionDayInspectionRunner:
    """Supervised production-day coverage; cannot mutate schedule or model."""

    def __init__(self, runtime: ResearchRuntime, registry: ExperimentRegistry):
        self.runtime, self.registry = runtime, registry

    def run(self, *, domain: Domain, run_root: Path,
            attestation_path: Path | None, production_day: date, as_of,
            estimated_bytes: int, timeout_seconds: float):
        from .research_index import _at
        if not isinstance(domain, Domain) or type(production_day) is not date:
            raise ValueError("known domain and production date required")
        payload = {
            "domain": domain.value,
            "run_root": str(run_root.expanduser().absolute()),
            "attestation_path": (
                str(attestation_path.expanduser().absolute())
                if attestation_path is not None else None
            ),
            "production_day": production_day.isoformat(),
            "as_of": _at(as_of).isoformat(),
        }
        disposition, status, attempt, receipt = _phase(
            self.runtime, self.registry, None,
            action="research-production-day-evidence", payload=payload,
            estimated_bytes=estimated_bytes, timeout_seconds=timeout_seconds,
        )
        valid = receipt if disposition is ResearchDisposition.SUCCEEDED else {}
        return SourceInspectionResult(
            disposition, status, attempt,
            Path(valid["report_path"]) if valid.get("report_path") else None,
            valid.get("content_hash"),
        )


class ResearchLiveDriftInspectionRunner:
    """Supervised descriptive feature drift; no threshold/model authority."""

    def __init__(self, runtime: ResearchRuntime, registry: ExperimentRegistry):
        self.runtime, self.registry = runtime, registry

    def run(self, *, domain: Domain, evidence_root: Path,
            baseline_as_of, as_of, relocation_roots: tuple[Path, ...] = (),
            estimated_bytes: int, timeout_seconds: float):
        from .research_index import _at
        if not isinstance(domain, Domain) or not isinstance(relocation_roots, tuple):
            raise ValueError("known domain and tuple relocation roots required")
        payload = {
            "domain": domain.value,
            "evidence_root": str(evidence_root.expanduser().absolute()),
            "baseline_as_of": _at(baseline_as_of).isoformat(),
            "as_of": _at(as_of).isoformat(),
            "relocation_roots": [
                str(path.expanduser().absolute()) for path in relocation_roots
            ],
        }
        disposition, status, attempt, receipt = _phase(
            self.runtime, self.registry, None,
            action="research-live-drift", payload=payload,
            estimated_bytes=estimated_bytes, timeout_seconds=timeout_seconds,
        )
        valid = receipt if disposition is ResearchDisposition.SUCCEEDED else {}
        return SourceInspectionResult(
            disposition, status, attempt,
            Path(valid["report_path"]) if valid.get("report_path") else None,
            valid.get("content_hash"),
        )


class TennisSettlementCandidateInspectionRunner:
    """Supervised Tennis label applicability inventory; never sample authority."""

    def __init__(self, runtime: ResearchRuntime, registry: ExperimentRegistry):
        self.runtime, self.registry = runtime, registry

    def run(self, *, evidence_root: Path, as_of, relocation_roots: tuple[Path, ...] = (),
            estimated_bytes: int, timeout_seconds: float):
        from .research_index import _at
        if not isinstance(relocation_roots, tuple):
            raise ValueError("tuple relocation roots required")
        payload = {
            "domain": Domain.TENNIS.value,
            "evidence_root": str(evidence_root.expanduser().absolute()),
            "as_of": _at(as_of).isoformat(),
            "relocation_roots": [str(path.expanduser().absolute()) for path in relocation_roots],
        }
        disposition, status, attempt, receipt = _phase(
            self.runtime, self.registry, None, action="tennis-settlement-candidates", payload=payload,
            estimated_bytes=estimated_bytes, timeout_seconds=timeout_seconds,
        )
        valid = receipt if disposition is ResearchDisposition.SUCCEEDED else {}
        return SourceInspectionResult(
            disposition, status, attempt,
            Path(valid["report_path"]) if valid.get("report_path") else None,
            valid.get("content_hash"),
        )


class AuFeatureProvenanceInspectionRunner:
    """Supervised feature/source inventory; never label or sample authority."""

    def __init__(self, runtime: ResearchRuntime, registry: ExperimentRegistry):
        self.runtime, self.registry = runtime, registry

    def run(self, *, evidence_root: Path, as_of, relocation_roots: tuple[Path, ...] = (),
            estimated_bytes: int, timeout_seconds: float):
        from .research_index import _at
        if not isinstance(relocation_roots, tuple):
            raise ValueError("tuple relocation roots required")
        payload = {
            "domain": Domain.AU.value,
            "evidence_root": str(evidence_root.expanduser().absolute()),
            "as_of": _at(as_of).isoformat(),
            "relocation_roots": [str(path.expanduser().absolute()) for path in relocation_roots],
        }
        disposition, status, attempt, receipt = _phase(
            self.runtime, self.registry, None, action="au-feature-provenance", payload=payload,
            estimated_bytes=estimated_bytes, timeout_seconds=timeout_seconds,
        )
        valid = receipt if disposition is ResearchDisposition.SUCCEEDED else {}
        return SourceInspectionResult(
            disposition, status, attempt,
            Path(valid["report_path"]) if valid.get("report_path") else None,
            valid.get("content_hash"),
        )


class TennisFeatureProvenanceInspectionRunner:
    """Supervised Tennis feature/source inventory; never sample authority."""

    def __init__(self, runtime: ResearchRuntime, registry: ExperimentRegistry):
        self.runtime, self.registry = runtime, registry

    def run(self, *, evidence_root: Path, as_of, relocation_roots: tuple[Path, ...] = (),
            estimated_bytes: int, timeout_seconds: float):
        from .research_index import _at
        if not isinstance(relocation_roots, tuple):
            raise ValueError("tuple relocation roots required")
        payload = {
            "domain": Domain.TENNIS.value,
            "evidence_root": str(evidence_root.expanduser().absolute()),
            "as_of": _at(as_of).isoformat(),
            "relocation_roots": [str(path.expanduser().absolute()) for path in relocation_roots],
        }
        disposition, status, attempt, receipt = _phase(
            self.runtime, self.registry, None, action="tennis-feature-provenance", payload=payload,
            estimated_bytes=estimated_bytes, timeout_seconds=timeout_seconds,
        )
        valid = receipt if disposition is ResearchDisposition.SUCCEEDED else {}
        return SourceInspectionResult(
            disposition, status, attempt,
            Path(valid["report_path"]) if valid.get("report_path") else None,
            valid.get("content_hash"),
        )


class HkjcFeatureProvenanceInspectionRunner:
    """Supervised HKJC feature/source inventory; never sample authority."""

    def __init__(self, runtime: ResearchRuntime, registry: ExperimentRegistry):
        self.runtime, self.registry = runtime, registry

    def run(self, *, evidence_root: Path, as_of, relocation_roots: tuple[Path, ...] = (),
            estimated_bytes: int, timeout_seconds: float):
        from .research_index import _at
        if not isinstance(relocation_roots, tuple):
            raise ValueError("tuple relocation roots required")
        payload = {
            "domain": Domain.HKJC.value,
            "evidence_root": str(evidence_root.expanduser().absolute()),
            "as_of": _at(as_of).isoformat(),
            "relocation_roots": [str(path.expanduser().absolute()) for path in relocation_roots],
        }
        disposition, status, attempt, receipt = _phase(
            self.runtime, self.registry, None, action="hkjc-feature-provenance", payload=payload,
            estimated_bytes=estimated_bytes, timeout_seconds=timeout_seconds,
        )
        valid = receipt if disposition is ResearchDisposition.SUCCEEDED else {}
        return SourceInspectionResult(
            disposition, status, attempt,
            Path(valid["report_path"]) if valid.get("report_path") else None,
            valid.get("content_hash"),
        )


class NbaFeatureProvenanceInspectionRunner:
    """Supervised NBA feature/source inventory; never sample authority."""

    def __init__(self, runtime: ResearchRuntime, registry: ExperimentRegistry):
        self.runtime, self.registry = runtime, registry

    def run(self, *, evidence_root: Path, as_of, relocation_roots: tuple[Path, ...] = (),
            estimated_bytes: int, timeout_seconds: float):
        from .research_index import _at
        if not isinstance(relocation_roots, tuple):
            raise ValueError("tuple relocation roots required")
        payload = {
            "domain": Domain.NBA.value,
            "evidence_root": str(evidence_root.expanduser().absolute()),
            "as_of": _at(as_of).isoformat(),
            "relocation_roots": [str(path.expanduser().absolute()) for path in relocation_roots],
        }
        disposition, status, attempt, receipt = _phase(
            self.runtime, self.registry, None, action="nba-feature-provenance", payload=payload,
            estimated_bytes=estimated_bytes, timeout_seconds=timeout_seconds,
        )
        valid = receipt if disposition is ResearchDisposition.SUCCEEDED else {}
        return SourceInspectionResult(
            disposition, status, attempt,
            Path(valid["report_path"]) if valid.get("report_path") else None,
            valid.get("content_hash"),
        )


class PowerDevEngineRunner:
    """Fail-closed placeholder until each domain has a label-safe callback."""

    def __init__(self, runtime: ResearchRuntime, registry: ExperimentRegistry):
        self.runtime, self.registry = runtime, registry

    def run(self, *, domain: Domain, role: str, checkout: Path, engine_commit: str,
            command_argv, dataset_snapshot: Path, variant_manifest_path: Path,
            protocol_path: Path, generated_at, estimated_bytes: int,
            timeout_seconds: float, ruler_root: Path | None = None):
        from .evaluation_rulers import DEFAULT_RULER_ROOT
        from .research_index import _at
        if domain not in {Domain.AU, Domain.HKJC}:
            raise ValueError("power dev engine supervision supports AU or HKJC only")
        if role not in {"baseline", "neutral_comparator"}:
            raise ValueError("invalid power dev engine role")
        if not command_argv or any(not isinstance(item, str) or not item for item in command_argv):
            raise ValueError("power dev engine command argv required")
        selected_root = Path(ruler_root) if ruler_root is not None else DEFAULT_RULER_ROOT
        payload = {
            "domain": domain.value,
            "role": role,
            "checkout": str(checkout.expanduser().absolute()),
            "engine_commit": engine_commit,
            "command_argv": list(command_argv),
            "dataset_snapshot": str(dataset_snapshot.expanduser().absolute()),
            "variant_manifest_path": str(variant_manifest_path.expanduser().absolute()),
            "protocol_path": str(protocol_path.expanduser().absolute()),
            "generated_at": _at(generated_at).isoformat(),
            "ruler_root": str(selected_root.expanduser().absolute()),
        }
        disposition, status, attempt, receipt = _phase(
            self.runtime, self.registry, None, action="power-dev-engine", payload=payload,
            estimated_bytes=estimated_bytes, timeout_seconds=timeout_seconds,
        )
        valid = receipt if disposition is ResearchDisposition.SUCCEEDED else {}
        return SourceInspectionResult(
            disposition, status, attempt,
            Path(valid["report_path"]) if valid.get("report_path") else None,
            valid.get("content_hash"),
        )


class PowerDevProducerRunner:
    """Fail-closed placeholder for future attested domain metrics packaging."""

    def __init__(self, runtime: ResearchRuntime, registry: ExperimentRegistry):
        self.runtime, self.registry = runtime, registry

    def run(self, *, domain: Domain, role: str, metrics_path: Path,
            dataset_snapshot: Path, variant_manifest_path: Path, protocol_path: Path,
            engine_commit: str, command_argv, generated_at, estimated_bytes: int,
            timeout_seconds: float, ruler_root: Path | None = None):
        from .evaluation_rulers import DEFAULT_RULER_ROOT
        from .research_index import _at
        if domain not in {Domain.AU, Domain.HKJC}:
            raise ValueError("power dev producer supervision supports AU or HKJC only")
        if role not in {"baseline", "neutral_comparator"}:
            raise ValueError("invalid power dev producer role")
        selected_root = Path(ruler_root) if ruler_root is not None else DEFAULT_RULER_ROOT
        payload = {
            "domain": domain.value,
            "role": role,
            "metrics_path": str(metrics_path.expanduser().absolute()),
            "dataset_snapshot": str(dataset_snapshot.expanduser().absolute()),
            "variant_manifest_path": str(variant_manifest_path.expanduser().absolute()),
            "protocol_path": str(protocol_path.expanduser().absolute()),
            "engine_commit": engine_commit,
            "command_argv": list(command_argv),
            "generated_at": _at(generated_at).isoformat(),
            "ruler_root": str(selected_root.expanduser().absolute()),
        }
        disposition, status, attempt, receipt = _phase(
            self.runtime, self.registry, None, action="power-dev-producer", payload=payload,
            estimated_bytes=estimated_bytes, timeout_seconds=timeout_seconds,
        )
        valid = receipt if disposition is ResearchDisposition.SUCCEEDED else {}
        return SourceInspectionResult(
            disposition, status, attempt,
            Path(valid["report_path"]) if valid.get("report_path") else None,
            valid.get("content_hash"),
        )


class PowerProjectionRunner:
    """Supervised dev-only engine pairing; creates no profile or sample."""

    def __init__(self, runtime: ResearchRuntime, registry: ExperimentRegistry):
        self.runtime, self.registry = runtime, registry

    def run(self, *, domain: Domain, baseline_path: Path, comparator_path: Path, as_of,
            estimated_bytes: int, timeout_seconds: float, ruler_root: Path | None = None):
        from .evaluation_rulers import DEFAULT_RULER_ROOT
        from .research_index import _at
        if domain not in {Domain.AU, Domain.HKJC}:
            raise ValueError("power projection supervision supports AU or HKJC only")
        selected_root = Path(ruler_root) if ruler_root is not None else DEFAULT_RULER_ROOT
        payload = {
            "domain": domain.value,
            "baseline_path": str(baseline_path.expanduser().absolute()),
            "comparator_path": str(comparator_path.expanduser().absolute()),
            "as_of": _at(as_of).isoformat(),
            "ruler_root": str(selected_root.expanduser().absolute()),
        }
        disposition, status, attempt, receipt = _phase(
            self.runtime, self.registry, None, action="power-projection", payload=payload,
            estimated_bytes=estimated_bytes, timeout_seconds=timeout_seconds,
        )
        valid = receipt if disposition is ResearchDisposition.SUCCEEDED else {}
        return SourceInspectionResult(
            disposition, status, attempt,
            Path(valid["report_path"]) if valid.get("report_path") else None,
            valid.get("content_hash"),
        )


class PowerVarianceInspectionRunner:
    """Supervised racing dev-variance description; never profile/sample authority."""

    def __init__(self, runtime: ResearchRuntime, registry: ExperimentRegistry):
        self.runtime, self.registry = runtime, registry

    def run(self, *, domain: Domain, input_path: Path, as_of,
            estimated_bytes: int, timeout_seconds: float, ruler_root: Path | None = None):
        from .evaluation_rulers import DEFAULT_RULER_ROOT
        from .research_index import _at
        if domain not in {Domain.AU, Domain.HKJC}:
            raise ValueError("power variance supervision supports AU or HKJC only")
        selected_root = Path(ruler_root) if ruler_root is not None else DEFAULT_RULER_ROOT
        payload = {
            "domain": domain.value,
            "input_path": str(input_path.expanduser().absolute()),
            "as_of": _at(as_of).isoformat(),
            "ruler_root": str(selected_root.expanduser().absolute()),
        }
        disposition, status, attempt, receipt = _phase(
            self.runtime, self.registry, None, action="power-variance", payload=payload,
            estimated_bytes=estimated_bytes, timeout_seconds=timeout_seconds,
        )
        valid = receipt if disposition is ResearchDisposition.SUCCEEDED else {}
        return SourceInspectionResult(
            disposition, status, attempt,
            Path(valid["report_path"]) if valid.get("report_path") else None,
            valid.get("content_hash"),
        )


class ResearchPreparationRunner:
    def __init__(self, runtime: ResearchRuntime, registry: ExperimentRegistry):
        self.runtime, self.registry = runtime, registry

    def run(self, spec, *, sources, split_policy, estimated_bytes, timeout_seconds, previous_snapshot=None):
        split_policy.validate()
        payload = {
            "sources": [
                {
                    "source_id": source.source_id,
                    "tier": source.tier.value,
                    "artifact_path": str(source.artifact_path.expanduser().absolute()),
                    "rows_path": str(source.rows_path.expanduser().absolute()),
                    "available_at": source.available_at,
                    "expected_digest": dict(source.expected_digest),
                    "catalog_record": str(source.catalog_record.expanduser().absolute())
                    if source.catalog_record
                    else None,
                }
                for source in sources
            ],
            "split_policy": split_policy.to_dict(),
            "previous_snapshot": str(previous_snapshot.expanduser().absolute()) if previous_snapshot else None,
        }
        disposition, status, attempt, receipt = _phase(
            self.runtime,
            self.registry,
            spec,
            action="prepare",
            payload=payload,
            estimated_bytes=estimated_bytes,
            timeout_seconds=timeout_seconds,
        )
        return PreparationResult(
            disposition,
            status,
            attempt,
            Path(receipt["snapshot_path"]) if receipt and receipt.get("snapshot_path") else None,
            receipt.get("dataset_manifest_id") if receipt else None,
        )


class ResearchScoringRunner:
    def __init__(self, runtime: ResearchRuntime, registry: ExperimentRegistry):
        self.runtime, self.registry = runtime, registry

    def run(self, job: ResearchJob, spec: ExperimentSpec, adapter: ResearchDomainAdapter) -> ResearchRunResult:
        job.validate()
        if type(adapter) is not ResearchDomainAdapter or adapter.domain is not spec.domain:
            return ResearchRunResult(job.job_id, ResearchDisposition.BLOCKED, "unsupported_command_adapter")
        disposition, status, attempt, receipt = _phase(
            self.runtime,
            self.registry,
            spec,
            action="scoring",
            payload={"job": job.to_payload()},
            estimated_bytes=job.estimated_bytes,
            timeout_seconds=job.timeout_seconds,
        )
        return ResearchRunResult(
            job.job_id,
            disposition,
            status,
            artifact_path=Path(receipt["artifact_path"]) if receipt and receipt.get("artifact_path") else attempt,
            experiment_run_id=receipt.get("run_id") if receipt else None,
            reproducibility_digest=receipt.get("reproducibility_digest") if receipt else None,
        )


def _worker_body(request_path: Path):
    request = _strict_json(request_path.read_text())
    if request["schema_version"] != "wong-choi-supervised-research-phase/v1" or request["action"] not in {
        "prepare",
        "scoring",
        "tennis-source",
        "prediction-artifacts",
        "au-settlement-candidates",
        "nba-settlement-candidates",
        "hkjc-settlement-candidates",
        "tennis-settlement-candidates",
        "au-feature-provenance",
        "tennis-feature-provenance",
        "hkjc-feature-provenance",
        "nba-feature-provenance",
        "racing-monitoring-samples",
        "nba-monitoring-samples", "tennis-monitoring-samples",
        "research-storage-evidence", "research-liveness-evidence",
        "research-production-day-evidence", "research-live-drift",
        "power-dev-engine",
        "power-dev-producer",
        "power-projection",
        "power-variance",
        "reconcile",
        "review",
        "notify",
    }:
        raise ValueError("unsupported supervised research request")
    _validate_deadline(request)
    registry = ExperimentRegistry(Path(request["registry"]))
    outer = ResearchRuntime(
        state_root=Path(request["state_root"]),
        warm_root=Path(request["warm_root"]),
        production_lock_paths=tuple(Path(path) for path in request["production_locks"]),
        reserve_bytes=request["reserve_bytes"],
    )
    spec = None

    def checkpoint():
        if os.getppid() != request["parent_pid"]:
            raise ResourceInterrupted("supervisor_unavailable")
        if _deadline_now() >= request["deadline"]:
            raise ResourceInterrupted("phase_timeout")
        status = _resource_status(outer, registry, request["estimated_bytes"])
        if not status and spec is not None and request["action"] in {"prepare", "scoring"}:
            from .research_guard import research_gate_status
            status = research_gate_status(outer, registry, spec.domain, spec.evaluation_ruler_digest)
        if status:
            raise ResourceInterrupted(status)

    checkpoint()
    source_inventory = request["action"] == "tennis-source"
    metadata_only = request["action"] in {
        "tennis-source", "prediction-artifacts", "au-settlement-candidates",
        "nba-settlement-candidates", "hkjc-settlement-candidates",
        "tennis-settlement-candidates", "au-feature-provenance",
        "tennis-feature-provenance", "hkjc-feature-provenance",
        "nba-feature-provenance", "racing-monitoring-samples",
        "nba-monitoring-samples", "tennis-monitoring-samples",
        "research-storage-evidence", "research-liveness-evidence",
        "research-production-day-evidence", "research-live-drift",
        "power-dev-engine", "power-dev-producer", "power-projection",
        "power-variance", "review", "notify",
    }
    spec = None if metadata_only else _record_from_payload(registry.load(request["spec_id"]))
    if (metadata_only and request["spec_id"] is not None) or (
        not metadata_only and not isinstance(spec, ExperimentSpec)
    ):
        raise ValueError("only source inventory or metadata review may run without a registered spec")
    checkpoint()
    workspace = request_path.parent / "work"
    workspace.mkdir()
    payload = request["payload"]
    if request["action"] == "notify":
        from .research_notification_runtime import run_notification_request
        with single_run_lock(outer.state_root / "locks/research-heavy-worker.lock") as acquired:
            if not acquired:
                result = {"disposition": "deferred", "status": "heavy_worker_busy"}
            else:
                result = run_notification_request(request, registry=registry, runtime=outer, workspace=workspace, checkpoint=checkpoint)
    elif request["action"] == "review":
        from .research_review_runtime import run_review_request
        with single_run_lock(outer.state_root / "locks/research-heavy-worker.lock") as acquired:
            if not acquired:
                result = {"disposition": "deferred", "status": "heavy_worker_busy"}
            else:
                result = run_review_request(request, registry=registry, runtime=outer, workspace=workspace, checkpoint=checkpoint)
    elif request["action"] == "prediction-artifacts":
        from .research_prediction_artifacts import inspect_prediction_artifacts
        with single_run_lock(outer.state_root / "locks/research-heavy-worker.lock") as acquired:
            if not acquired:
                result = {"disposition": "deferred", "status": "heavy_worker_busy"}
            else:
                if set(payload) != {"domain", "evidence_root", "as_of", "relocation_roots"}:
                    raise ValueError("unsupported prediction artifact request fields")
                report = inspect_prediction_artifacts(
                    root=Path(payload["evidence_root"]), domain=Domain(payload["domain"]),
                    as_of=payload["as_of"], relocation_roots=tuple(Path(item) for item in payload["relocation_roots"]),
                    checkpoint=checkpoint,
                )
                path = workspace / "prediction-artifacts.json"
                _write_report(path, report, resource_checkpoint=checkpoint, create_parents=False)
                result = {"disposition": "succeeded", "status": "prediction_artifact_inventory_only",
                          "report_path": str(path), "content_hash": report["content_hash"],
                          "normalized_source_verified": False, "verified_monitoring_samples": None,
                          "model_promotion_allowed": False}
    elif request["action"] == "au-settlement-candidates":
        from .research_au_settlement_source import inspect_au_settlement_candidates
        with single_run_lock(outer.state_root / "locks/research-heavy-worker.lock") as acquired:
            if not acquired:
                result = {"disposition": "deferred", "status": "heavy_worker_busy"}
            else:
                if set(payload) != {"domain", "evidence_root", "as_of", "relocation_roots"} \
                        or payload["domain"] != Domain.AU.value:
                    raise ValueError("unsupported AU settlement candidate request fields")
                report = inspect_au_settlement_candidates(
                    root=Path(payload["evidence_root"]), as_of=payload["as_of"],
                    relocation_roots=tuple(Path(item) for item in payload["relocation_roots"]),
                    checkpoint=checkpoint,
                )
                path = workspace / "au-settlement-candidates.json"
                _write_report(path, report, resource_checkpoint=checkpoint, create_parents=False)
                result = {
                    "disposition": "succeeded",
                    "status": "au_settlement_candidate_inventory_only",
                    "report_path": str(path),
                    "content_hash": report["content_hash"],
                    "feature_availability_verified": False,
                    "verified_monitoring_samples": None,
                    "model_promotion_allowed": False,
                }
    elif request["action"] == "nba-settlement-candidates":
        from .research_nba_settlement_source import inspect_nba_settlement_candidates
        with single_run_lock(outer.state_root / "locks/research-heavy-worker.lock") as acquired:
            if not acquired:
                result = {"disposition": "deferred", "status": "heavy_worker_busy"}
            else:
                if set(payload) != {"domain", "evidence_root", "as_of", "relocation_roots"} \
                        or payload["domain"] != Domain.NBA.value:
                    raise ValueError("unsupported NBA settlement candidate request fields")
                report = inspect_nba_settlement_candidates(
                    root=Path(payload["evidence_root"]), as_of=payload["as_of"],
                    relocation_roots=tuple(Path(item) for item in payload["relocation_roots"]),
                    checkpoint=checkpoint,
                )
                path = workspace / "nba-settlement-candidates.json"
                _write_report(path, report, resource_checkpoint=checkpoint, create_parents=False)
                result = {
                    "disposition": "succeeded",
                    "status": "nba_settlement_candidate_inventory_only",
                    "report_path": str(path),
                    "content_hash": report["content_hash"],
                    "feature_availability_verified": False,
                    "verified_monitoring_samples": None,
                    "model_promotion_allowed": False,
                }
    elif request["action"] == "hkjc-settlement-candidates":
        from .research_hkjc_settlement_source import inspect_hkjc_settlement_candidates
        with single_run_lock(outer.state_root / "locks/research-heavy-worker.lock") as acquired:
            if not acquired:
                result = {"disposition": "deferred", "status": "heavy_worker_busy"}
            else:
                if set(payload) != {"domain", "evidence_root", "as_of", "relocation_roots"} \
                        or payload["domain"] != Domain.HKJC.value:
                    raise ValueError("unsupported HKJC settlement candidate request fields")
                report = inspect_hkjc_settlement_candidates(
                    root=Path(payload["evidence_root"]), as_of=payload["as_of"],
                    relocation_roots=tuple(Path(item) for item in payload["relocation_roots"]),
                    checkpoint=checkpoint,
                )
                path = workspace / "hkjc-settlement-candidates.json"
                _write_report(path, report, resource_checkpoint=checkpoint, create_parents=False)
                result = {
                    "disposition": "succeeded",
                    "status": "hkjc_settlement_candidate_inventory_only",
                    "report_path": str(path),
                    "content_hash": report["content_hash"],
                    "feature_availability_verified": False,
                    "verified_monitoring_samples": None,
                    "model_promotion_allowed": False,
                }
    elif request["action"] == "tennis-settlement-candidates":
        from .research_tennis_settlement_source import inspect_tennis_settlement_candidates
        with single_run_lock(outer.state_root / "locks/research-heavy-worker.lock") as acquired:
            if not acquired:
                result = {"disposition": "deferred", "status": "heavy_worker_busy"}
            else:
                if set(payload) != {"domain", "evidence_root", "as_of", "relocation_roots"} \
                        or payload["domain"] != Domain.TENNIS.value:
                    raise ValueError("unsupported Tennis settlement candidate request fields")
                report = inspect_tennis_settlement_candidates(
                    root=Path(payload["evidence_root"]), as_of=payload["as_of"],
                    relocation_roots=tuple(Path(item) for item in payload["relocation_roots"]),
                    checkpoint=checkpoint,
                )
                path = workspace / "tennis-settlement-candidates.json"
                _write_report(path, report, resource_checkpoint=checkpoint, create_parents=False)
                result = {
                    "disposition": "succeeded",
                    "status": "tennis_settlement_candidate_inventory_only",
                    "report_path": str(path),
                    "content_hash": report["content_hash"],
                    "feature_availability_verified": False,
                    "verified_monitoring_samples": None,
                    "model_promotion_allowed": False,
                }
    elif request["action"] == "au-feature-provenance":
        from .research_au_feature_provenance import inspect_au_feature_provenance
        with single_run_lock(outer.state_root / "locks/research-heavy-worker.lock") as acquired:
            if not acquired:
                result = {"disposition": "deferred", "status": "heavy_worker_busy"}
            else:
                if set(payload) != {"domain", "evidence_root", "as_of", "relocation_roots"} \
                        or payload["domain"] != Domain.AU.value:
                    raise ValueError("unsupported AU feature provenance request fields")
                report = inspect_au_feature_provenance(
                    root=Path(payload["evidence_root"]), as_of=payload["as_of"],
                    relocation_roots=tuple(Path(item) for item in payload["relocation_roots"]),
                    checkpoint=checkpoint,
                )
                path = workspace / "au-feature-provenance.json"
                _write_report(path, report, resource_checkpoint=checkpoint, create_parents=False)
                result = {
                    "disposition": "succeeded",
                    "status": "au_feature_provenance_inventory_only",
                    "report_path": str(path),
                    "content_hash": report["content_hash"],
                    "feature_availability_verified": report["feature_availability_verified"],
                    "verified_monitoring_samples": None,
                    "model_promotion_allowed": False,
                }
    elif request["action"] == "tennis-feature-provenance":
        from .research_tennis_feature_provenance import inspect_tennis_feature_provenance
        with single_run_lock(outer.state_root / "locks/research-heavy-worker.lock") as acquired:
            if not acquired:
                result = {"disposition": "deferred", "status": "heavy_worker_busy"}
            else:
                if set(payload) != {"domain", "evidence_root", "as_of", "relocation_roots"} \
                        or payload["domain"] != Domain.TENNIS.value:
                    raise ValueError("unsupported Tennis feature provenance request fields")
                report = inspect_tennis_feature_provenance(
                    root=Path(payload["evidence_root"]), as_of=payload["as_of"],
                    relocation_roots=tuple(Path(item) for item in payload["relocation_roots"]),
                    checkpoint=checkpoint,
                )
                path = workspace / "tennis-feature-provenance.json"
                _write_report(path, report, resource_checkpoint=checkpoint, create_parents=False)
                result = {
                    "disposition": "succeeded",
                    "status": "tennis_feature_provenance_inventory_only",
                    "report_path": str(path),
                    "content_hash": report["content_hash"],
                    "feature_availability_verified": report["feature_availability_verified"],
                    "verified_monitoring_samples": None,
                    "model_promotion_allowed": False,
                }
    elif request["action"] == "hkjc-feature-provenance":
        from .research_hkjc_feature_provenance import inspect_hkjc_feature_provenance
        with single_run_lock(outer.state_root / "locks/research-heavy-worker.lock") as acquired:
            if not acquired:
                result = {"disposition": "deferred", "status": "heavy_worker_busy"}
            else:
                if set(payload) != {"domain", "evidence_root", "as_of", "relocation_roots"} \
                        or payload["domain"] != Domain.HKJC.value:
                    raise ValueError("unsupported HKJC feature provenance request fields")
                report = inspect_hkjc_feature_provenance(
                    root=Path(payload["evidence_root"]), as_of=payload["as_of"],
                    relocation_roots=tuple(Path(item) for item in payload["relocation_roots"]),
                    checkpoint=checkpoint,
                )
                path = workspace / "hkjc-feature-provenance.json"
                _write_report(path, report, resource_checkpoint=checkpoint, create_parents=False)
                result = {
                    "disposition": "succeeded",
                    "status": "hkjc_feature_provenance_inventory_only",
                    "report_path": str(path),
                    "content_hash": report["content_hash"],
                    "feature_availability_verified": report["feature_availability_verified"],
                    "verified_monitoring_samples": None,
                    "model_promotion_allowed": False,
                }
    elif request["action"] == "nba-feature-provenance":
        from .research_nba_feature_provenance import inspect_nba_feature_provenance
        with single_run_lock(outer.state_root / "locks/research-heavy-worker.lock") as acquired:
            if not acquired:
                result = {"disposition": "deferred", "status": "heavy_worker_busy"}
            else:
                if set(payload) != {"domain", "evidence_root", "as_of", "relocation_roots"} \
                        or payload["domain"] != Domain.NBA.value:
                    raise ValueError("unsupported NBA feature provenance request fields")
                report = inspect_nba_feature_provenance(
                    root=Path(payload["evidence_root"]), as_of=payload["as_of"],
                    relocation_roots=tuple(Path(item) for item in payload["relocation_roots"]),
                    checkpoint=checkpoint,
                )
                path = workspace / "nba-feature-provenance.json"
                _write_report(path, report, resource_checkpoint=checkpoint, create_parents=False)
                result = {
                    "disposition": "succeeded",
                    "status": "nba_feature_provenance_inventory_only",
                    "report_path": str(path),
                    "content_hash": report["content_hash"],
                    "feature_availability_verified": report["feature_availability_verified"],
                    "verified_monitoring_samples": None,
                    "model_promotion_allowed": False,
                }
    elif request["action"] == "racing-monitoring-samples":
        from .research_racing_monitoring_samples import (
            inspect_racing_monitoring_samples,
        )
        with single_run_lock(outer.state_root / "locks/research-heavy-worker.lock") as acquired:
            if not acquired:
                result = {"disposition": "deferred", "status": "heavy_worker_busy"}
            else:
                if (set(payload) != {"domain", "evidence_root", "as_of", "relocation_roots"}
                        or Domain(payload["domain"]) not in {Domain.AU, Domain.HKJC}):
                    raise ValueError("unsupported racing monitoring sample request fields")
                report = inspect_racing_monitoring_samples(
                    root=Path(payload["evidence_root"]),
                    domain=Domain(payload["domain"]),
                    as_of=payload["as_of"],
                    relocation_roots=tuple(
                        Path(item) for item in payload["relocation_roots"]
                    ),
                    checkpoint=checkpoint,
                )
                path = workspace / "racing-monitoring-samples.json"
                _write_report(
                    path, report, resource_checkpoint=checkpoint,
                    create_parents=False,
                )
                result = {
                    "disposition": "succeeded",
                    "status": "racing_monitoring_sample_projection",
                    "report_path": str(path),
                    "content_hash": report["content_hash"],
                    "verified_monitoring_samples": report["verified_monitoring_samples"],
                    "terminal_labels_emitted": False,
                    "model_promotion_allowed": False,
                    "reevaluate_promotion_allowed": False,
                }
    elif request["action"] == "nba-monitoring-samples":
        from .research_nba_monitoring_samples import inspect_nba_monitoring_samples
        with single_run_lock(outer.state_root / "locks/research-heavy-worker.lock") as acquired:
            if not acquired:
                result = {"disposition": "deferred", "status": "heavy_worker_busy"}
            else:
                if (set(payload) != {
                        "domain", "evidence_root", "as_of", "relocation_roots"
                    } or Domain(payload["domain"]) is not Domain.NBA):
                    raise ValueError("unsupported NBA monitoring sample request fields")
                report = inspect_nba_monitoring_samples(
                    root=Path(payload["evidence_root"]),
                    as_of=payload["as_of"],
                    relocation_roots=tuple(
                        Path(item) for item in payload["relocation_roots"]
                    ),
                    checkpoint=checkpoint,
                )
                path = workspace / "nba-monitoring-samples.json"
                _write_report(
                    path, report, resource_checkpoint=checkpoint,
                    create_parents=False,
                )
                result = {
                    "disposition": "succeeded",
                    "status": "nba_monitoring_sample_projection",
                    "report_path": str(path),
                    "content_hash": report["content_hash"],
                    "verified_monitoring_samples": report["verified_monitoring_samples"],
                    "terminal_labels_emitted": False,
                    "model_promotion_allowed": False,
                    "reevaluate_promotion_allowed": False,
                }
    elif request["action"] == "tennis-monitoring-samples":
        from .research_tennis_monitoring_samples import inspect_tennis_monitoring_samples
        with single_run_lock(outer.state_root / "locks/research-heavy-worker.lock") as acquired:
            if not acquired:
                result = {"disposition": "deferred", "status": "heavy_worker_busy"}
            else:
                if (set(payload) != {
                        "domain", "evidence_root", "as_of", "relocation_roots"
                    } or Domain(payload["domain"]) is not Domain.TENNIS):
                    raise ValueError("unsupported Tennis monitoring sample request fields")
                report = inspect_tennis_monitoring_samples(
                    root=Path(payload["evidence_root"]),
                    as_of=payload["as_of"],
                    relocation_roots=tuple(
                        Path(item) for item in payload["relocation_roots"]
                    ),
                    checkpoint=checkpoint,
                )
                path = workspace / "tennis-monitoring-samples.json"
                _write_report(
                    path, report, resource_checkpoint=checkpoint,
                    create_parents=False,
                )
                result = {
                    "disposition": "succeeded",
                    "status": "tennis_monitoring_sample_projection",
                    "report_path": str(path),
                    "content_hash": report["content_hash"],
                    "verified_monitoring_samples": report["verified_monitoring_samples"],
                    "terminal_labels_emitted": False,
                    "model_promotion_allowed": False,
                    "reevaluate_promotion_allowed": False,
                }
    elif request["action"] == "research-storage-evidence":
        from .research_storage_evidence import collect_research_storage_evidence
        with single_run_lock(outer.state_root / "locks/research-heavy-worker.lock") as acquired:
            if not acquired:
                result = {"disposition": "deferred", "status": "heavy_worker_busy"}
            else:
                if set(payload) != {
                        "domain", "repo_root", "storage_state_root", "as_of"
                    }:
                    raise ValueError("unsupported research storage evidence request fields")
                report = collect_research_storage_evidence(
                    repo_root=Path(payload["repo_root"]),
                    state_root=Path(payload["storage_state_root"]),
                    domain=Domain(payload["domain"]), as_of=payload["as_of"],
                    checkpoint=checkpoint,
                )
                path = workspace / "research-storage-evidence.json"
                _write_report(
                    path, report, resource_checkpoint=checkpoint,
                    create_parents=False,
                )
                result = {
                    "disposition": "succeeded",
                    "status": "research_storage_evidence_projection",
                    "report_path": str(path),
                    "content_hash": report["content_hash"],
                    "storage_health": report["storage_health"],
                    "historical_availability_verified": False,
                    "process_liveness_verified": False,
                    "live_drift_verified": False,
                    "model_promotion_allowed": False,
                }
    elif request["action"] == "research-liveness-evidence":
        from .research_liveness import collect_research_liveness_evidence
        with single_run_lock(outer.state_root / "locks/research-heavy-worker.lock") as acquired:
            if not acquired:
                result = {"disposition": "deferred", "status": "heavy_worker_busy"}
            else:
                if set(payload) != {"domain", "queue_root", "lease_root", "as_of"}:
                    raise ValueError("unsupported research liveness evidence request fields")
                report = collect_research_liveness_evidence(
                    registry_root=registry.root,
                    queue_root=Path(payload["queue_root"]),
                    lease_root=Path(payload["lease_root"]),
                    domain=Domain(payload["domain"]), as_of=payload["as_of"],
                    checkpoint=checkpoint,
                )
                path = workspace / "research-liveness-evidence.json"
                _write_report(
                    path, report, resource_checkpoint=checkpoint,
                    create_parents=False,
                )
                result = {
                    "disposition": "succeeded",
                    "status": "research_liveness_evidence_projection",
                    "report_path": str(path),
                    "content_hash": report["content_hash"],
                    "process_liveness_verified": True,
                    "all_claimed_processes_verified": report["all_claimed_processes_verified"],
                    "running_verified": report["counts"]["running_verified"],
                    "unverified_claims": report["counts"]["claimed_liveness_unverified"],
                    "model_promotion_allowed": False,
                    "queue_mutation_allowed": False,
                }
    elif request["action"] == "research-production-day-evidence":
        from .research_production_day import inspect_production_day
        with single_run_lock(outer.state_root / "locks/research-heavy-worker.lock") as acquired:
            if not acquired:
                result = {"disposition": "deferred", "status": "heavy_worker_busy"}
            else:
                if set(payload) != {
                        "domain", "run_root", "attestation_path",
                        "production_day", "as_of",
                    }:
                    raise ValueError("unsupported research production-day evidence request fields")
                report = inspect_production_day(
                    run_root=Path(payload["run_root"]),
                    attestation_path=(
                        Path(payload["attestation_path"])
                        if payload["attestation_path"] is not None else None
                    ),
                    domain=Domain(payload["domain"]),
                    production_day=date.fromisoformat(payload["production_day"]),
                    as_of=payload["as_of"],
                    checkpoint=checkpoint,
                )
                path = workspace / "research-production-day-evidence.json"
                _write_report(
                    path, report, resource_checkpoint=checkpoint,
                    create_parents=False,
                )
                result = {
                    "disposition": "succeeded",
                    "status": "research_production_day_evidence_projection",
                    "report_path": str(path),
                    "content_hash": report["content_hash"],
                    "production_day_closed": report["production_day_closed"],
                    "schedule_attestation_verified": report["schedule_attestation_verified"],
                    "expected_runs": report["counts"]["expected"],
                    "terminal_runs": report["counts"]["terminal"],
                    "model_promotion_allowed": False,
                    "schedule_mutation_allowed": False,
                }
    elif request["action"] == "research-live-drift":
        from .research_live_drift import inspect_live_feature_drift
        with single_run_lock(outer.state_root / "locks/research-heavy-worker.lock") as acquired:
            if not acquired:
                result = {"disposition": "deferred", "status": "heavy_worker_busy"}
            else:
                if set(payload) != {
                        "domain", "evidence_root", "baseline_as_of", "as_of",
                        "relocation_roots",
                    }:
                    raise ValueError("unsupported research live drift request fields")
                report = inspect_live_feature_drift(
                    root=Path(payload["evidence_root"]),
                    domain=Domain(payload["domain"]),
                    baseline_as_of=payload["baseline_as_of"],
                    as_of=payload["as_of"],
                    relocation_roots=tuple(
                        Path(item) for item in payload["relocation_roots"]
                    ),
                    checkpoint=checkpoint,
                )
                path = workspace / "research-live-drift.json"
                _write_report(
                    path, report, resource_checkpoint=checkpoint,
                    create_parents=False,
                )
                result = {
                    "disposition": "succeeded",
                    "status": "research_live_drift_projection",
                    "report_path": str(path),
                    "content_hash": report["content_hash"],
                    "live_drift_verified": report["live_drift_verified"],
                    "feature_health": report["feature_health"],
                    "direction": report["direction"],
                    "metric_drift_verified": False,
                    "market_drift_verified": False,
                    "model_promotion_allowed": False,
                }
    elif request["action"] == "power-dev-engine":
        with single_run_lock(outer.state_root / "locks/research-heavy-worker.lock") as acquired:
            if not acquired:
                result = {"disposition": "deferred", "status": "heavy_worker_busy"}
            else:
                # The legacy command received complete development rows and
                # returned self-reported metrics.  Until AU and HKJC each have
                # a reviewed adapter that separates scorer inputs from labels
                # and lets the measurement layer verify the seven metrics, no
                # command may run or create power evidence through this route.
                result = {
                    "disposition": "blocked",
                    "status": "label_safe_domain_callback_required",
                    "report_path": None,
                    "label_separation_verified": False,
                    "terminal_metrics_emitted": False,
                    "power_profile_write_allowed": False,
                    "verified_monitoring_samples": None,
                    "model_promotion_allowed": False,
                }
    elif request["action"] == "power-dev-producer":
        with single_run_lock(outer.state_root / "locks/research-heavy-worker.lock") as acquired:
            if not acquired:
                result = {"disposition": "deferred", "status": "heavy_worker_busy"}
            else:
                result = {
                    "disposition": "blocked",
                    "status": "label_safe_domain_callback_required",
                    "report_path": None,
                    "label_separation_verified": False,
                    "terminal_metrics_emitted": False,
                    "power_profile_write_allowed": False,
                    "verified_monitoring_samples": None,
                    "model_promotion_allowed": False,
                }
    elif request["action"] == "power-projection":
        from .research_index import _hash
        from .research_power_projection import build_power_variance_projection
        with single_run_lock(outer.state_root / "locks/research-heavy-worker.lock") as acquired:
            if not acquired:
                result = {"disposition": "deferred", "status": "heavy_worker_busy"}
            else:
                if (set(payload) != {
                        "domain", "baseline_path", "comparator_path", "as_of", "ruler_root"
                    } or Domain(payload["domain"]) not in {Domain.AU, Domain.HKJC}):
                    raise ValueError("unsupported power projection request fields")
                path = workspace / "power-variance-input.json"
                report = build_power_variance_projection(
                    baseline_path=Path(payload["baseline_path"]),
                    comparator_path=Path(payload["comparator_path"]),
                    output_path=path,
                    domain=Domain(payload["domain"]),
                    as_of=payload["as_of"],
                    ruler_root=Path(payload["ruler_root"]),
                    checkpoint=checkpoint,
                )
                result = {
                    "disposition": "succeeded",
                    "status": "power_projection_dev_only",
                    "report_path": str(path),
                    "content_hash": _hash(report),
                    "source_role": "development_only",
                    "power_profile_write_allowed": False,
                    "verified_monitoring_samples": None,
                    "model_promotion_allowed": False,
                }
    elif request["action"] == "power-variance":
        from .research_power_variance import inspect_power_variance
        with single_run_lock(outer.state_root / "locks/research-heavy-worker.lock") as acquired:
            if not acquired:
                result = {"disposition": "deferred", "status": "heavy_worker_busy"}
            else:
                if (set(payload) != {"domain", "input_path", "as_of", "ruler_root"}
                        or Domain(payload["domain"]) not in {Domain.AU, Domain.HKJC}):
                    raise ValueError("unsupported power variance request fields")
                report = inspect_power_variance(
                    input_path=Path(payload["input_path"]),
                    domain=Domain(payload["domain"]),
                    as_of=payload["as_of"],
                    ruler_root=Path(payload["ruler_root"]),
                    checkpoint=checkpoint,
                )
                path = workspace / "power-variance.json"
                _write_report(path, report, resource_checkpoint=checkpoint, create_parents=False)
                result = {
                    "disposition": "succeeded",
                    "status": "power_variance_description_only",
                    "report_path": str(path),
                    "content_hash": report["content_hash"],
                    "variance_input_contract_verified": True,
                    "power_profile_write_allowed": False,
                    "verified_monitoring_samples": None,
                    "model_promotion_allowed": False,
                }
    elif request["action"] == "reconcile":
        with single_run_lock(outer.state_root / "locks/research-heavy-worker.lock") as acquired:
            if not acquired:
                result = {"disposition": "deferred", "status": "heavy_worker_busy"}
            else:
                if payload["kind"] not in {"postflight", "phase"}:
                    raise ValueError("unsupported reconciliation kind")
                reconcile = reconcile_phase if payload["kind"] == "phase" else reconcile_postflight
                report = reconcile(
                    spec,
                    attempt_path=Path(payload["attempt_path"]),
                    request_sha256=payload["request_sha256"],
                    registry=registry,
                    warm_root=outer.warm_root,
                    state_root=outer.state_root,
                    checkpoint=checkpoint,
                )
                path = workspace / "reconciliation.json"
                _write_report(path, report, resource_checkpoint=checkpoint, create_parents=False)
                result = {
                    "disposition": "succeeded",
                    "status": report["publication_status"],
                    "report_path": str(path),
                    "content_hash": report["content_hash"],
                    "decision_id": report.get("verified_decision_id"),
                    "record_id": report.get("verified_record_id"),
                    "request_sha256": report["request_sha256"],
                    "rerun_scoring_allowed": False,
                    "retry_publication_allowed": False,
                    "model_promotion_allowed": False,
                }
    elif source_inventory:
        with single_run_lock(outer.state_root / "locks/research-heavy-worker.lock") as acquired:
            if not acquired:
                result = {"disposition": "deferred", "status": "heavy_worker_busy"}
            else:
                checkpoint()
                policy = TennisSourcePolicy(
                    **{**payload["policy"], "feature_fields": tuple(payload["policy"]["feature_fields"])}
                )
                report = inspect_tennis_sources(Path(payload["db_path"]), policy, checkpoint=checkpoint)
                checkpoint()
                path = workspace / "source-inventory.json"
                report_payload = report.to_payload()
                report_status = "availability_inventory_only"
                if payload.get("witnesses"):
                    # All archive hashing/SQLite reads stay inside this worker,
                    # after the active database's read transaction has closed.
                    witnesses = tuple(SnapshotWitness.from_payload(item) for item in payload["witnesses"])
                    if len({item.artifact_id for item in witnesses}) != len(witnesses):
                        raise ValueError("duplicate snapshot witness")
                    witness_reports = [
                        verify_tennis_snapshot_witness(report_payload, witness, checkpoint=checkpoint)
                        for witness in witnesses
                    ]
                    report_payload = {
                        "schema_version": "wong-choi-tennis-source-witness-bundle/v1",
                        "inventory": report_payload,
                        "snapshot_witnesses": witness_reports,
                        "pit_dataset_ready": False,
                        "proposal_ready": False,
                    }
                    report_payload["content_hash"] = _digest(report_payload)
                    path = workspace / "source-witness-bundle.json"
                    report_status = "availability_inventory_with_witnesses_only"
                _write_report(path, report_payload, resource_checkpoint=checkpoint, create_parents=False)
                result = {
                    "disposition": "succeeded",
                    "status": report_status,
                    "report_path": str(path),
                    "content_hash": report_payload["content_hash"],
                    "row_count": len(report.rows),
                    "excluded_count": len(report.exclusions),
                    "pit_dataset_ready": False,
                    "proposal_ready": False,
                }
    elif request["action"] == "prepare":
        with single_run_lock(outer.state_root / "locks/research-heavy-worker.lock") as acquired:
            if not acquired:
                result = {"disposition": "deferred", "status": "heavy_worker_busy"}
            else:
                checkpoint()
                sources = tuple(
                    DatasetSource(
                        item["source_id"],
                        StorageTier(item["tier"]),
                        Path(item["artifact_path"]),
                        Path(item["rows_path"]),
                        item["available_at"],
                        item["expected_digest"],
                        Path(item["catalog_record"]) if item["catalog_record"] else None,
                    )
                    for item in payload["sources"]
                )
                dataset = build_dataset_snapshot(
                    spec,
                    sources=sources,
                    split_policy=SplitPolicy(**payload["split_policy"]),
                    snapshot_root=workspace / "datasets",
                    previous_snapshot=Path(payload["previous_snapshot"]) if payload["previous_snapshot"] else None,
                )
                checkpoint()
                registry.append(dataset.manifest)
                result = {
                    "disposition": "succeeded",
                    "status": dataset.status,
                    "snapshot_path": str(dataset.path),
                    "dataset_manifest_id": dataset.manifest.record_id,
                }
    else:
        job = ResearchJob.from_payload(payload["job"])
        runtime = ResearchRuntime(
            state_root=outer.state_root,
            warm_root=workspace,
            production_lock_paths=outer.production_lock_paths,
            reserve_bytes=outer.reserve_bytes,
            checkout_probe=_git_checkout_probe,
            executor=_InheritedGroupExecutor(poll_seconds=0.1, terminate_grace=0.2),
            review_warm_root=outer.warm_root,
        )
        run = ResearchRunner(runtime, registry).run(job, spec, create_research_adapter(spec.domain))
        checkpoint()
        result = {
            "disposition": run.disposition.value,
            "status": run.status,
            "artifact_path": str(run.artifact_path) if run.artifact_path else None,
            "run_id": run.experiment_run_id,
            "reproducibility_digest": run.reproducibility_digest,
        }
    _write_report(request_path.parent / "completed.json", result)


def _worker(request_path: Path):
    try:
        _worker_body(request_path)
    except ResourceInterrupted as exc:
        _write_report(request_path.parent / "completed.json", _interruption_receipt(str(exc)), create_parents=False)
    except Exception:
        if _strict_json(request_path.read_text()).get("action") != "notify":
            raise
        _write_report(request_path.parent / "completed.json",
                      {"disposition": "failed", "status": "notification_worker_failed"}, create_parents=False)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m shared_wong_choi.research_supervision REQUEST.json")
    _worker(Path(sys.argv[1]))
