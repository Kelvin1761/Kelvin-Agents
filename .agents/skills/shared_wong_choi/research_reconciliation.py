"""Read-only postflight publication reconciliation; no retries or promotion.

Operational entry is PostflightReconciliationRunner, which holds the heavy lock
and supervises all artifact/evaluation reads in a terminable child process.
An absent matching record is an observation, never proof that no writer exists.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .research_evaluation import _decision_for_evaluation, _strict_json, evaluate_run_artifact
from .research_postflight import SafetyEvidence
from .research_registry import ResearchKind


def _read(path: Path, limit=16_000_000):
    if any(item.is_symlink() for item in (path, *path.parents)) or not path.is_file():
        raise ValueError("reconciliation requires regular non-symlink evidence")
    if not 0 < path.stat().st_size <= limit:
        raise ValueError("reconciliation evidence byte limit")
    raw = path.read_bytes()
    if not 0 < len(raw) <= limit:
        raise ValueError("reconciliation evidence byte limit")
    return raw


def _encode(payload):
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def verify_reconciliation_receipt(spec, *, registry, report_path, receipt, request_sha256):
    """Bounded parent-side cross-check, not another corpus/evaluation pass."""
    payload = _strict_json(_read(report_path, 65536).decode())
    digest = hashlib.sha256(
        _encode({key: value for key, value in payload.items() if key != "content_hash"})
    ).hexdigest()
    decision_id = payload.get("verified_decision_id")
    if (
        payload.get("schema_version") != "wong-choi-postflight-reconciliation/v1"
        or digest != payload.get("content_hash")
        or digest != receipt.get("content_hash")
        or payload.get("spec_id") != spec.record_id
        or payload.get("request_sha256") != request_sha256
        or payload.get("publication_status") != receipt.get("status")
        or payload.get("publication_status")
        not in {
            "verified_existing_decision",
            "report_without_matching_decision",
            "no_matching_publication_observed",
        }
        or decision_id != receipt.get("decision_id")
        or (payload["publication_status"] == "verified_existing_decision") != bool(decision_id)
        or any(
            payload.get(key) is not False
            for key in (
                "rerun_scoring_allowed",
                "retry_publication_allowed",
                "model_promotion_allowed",
            )
        )
    ):
        raise ValueError("reconciliation report does not match receipt/request")
    run = registry.load(payload["run_id"])
    if run["links"]["spec_id"] != spec.record_id:
        raise ValueError("reconciliation report has wrong spec/run")
    if decision_id:
        decision = registry.load(decision_id)
        if (
            decision["links"]["run_id"] != payload["run_id"]
            or decision["artifact_digest"] != payload["evaluation_artifact_digest"]
            or decision_id != payload["expected_decision_id"]
        ):
            raise ValueError("reconciliation report has wrong decision")


def reconcile_postflight(spec, *, attempt_path, request_sha256, registry, warm_root, state_root, checkpoint):
    """Recompute the existing frozen run's evaluation; never execute model code."""
    checkpoint()
    if not isinstance(request_sha256, str) or not re.fullmatch("[0-9a-f]{64}", request_sha256):
        raise ValueError("pinned request SHA-256 required")
    attempt = Path(attempt_path)
    if (
        not attempt.is_absolute()
        or ".." in attempt.parts
        or attempt.parent != warm_root / "research-postflight" / spec.domain.value
        or not attempt.name.startswith("attempt-")
    ):
        raise ValueError("postflight attempt is outside configured WARM layout")
    request_path = attempt / "request.json"
    raw = _read(request_path, 65536)
    if hashlib.sha256(raw).hexdigest() != request_sha256:
        raise ValueError("postflight request does not match pinned hash")
    request = _strict_json(raw.decode())
    if (
        request.get("schema_version") != "wong-choi-research-postflight-request/v1"
        or request.get("spec_id") != spec.record_id
        or request.get("registry") != str(registry.root)
        or request.get("warm_root") != str(warm_root)
        or request.get("state_root") != str(state_root)
    ):
        raise ValueError("postflight request context mismatch")
    # Historical request deadlines/PIDs are evidence only; never execute them.
    run_id = request["run_id"]
    run = registry.load(run_id)
    spec_record = registry.load(spec.record_id)
    if spec_record != spec.to_payload() or run["links"]["spec_id"] != spec.record_id:
        raise ValueError("postflight request does not match registered spec/run")
    raw_evidence = request["evidence"]
    evidence = SafetyEvidence(
        Path(raw_evidence["input_protocol"]),
        Path(raw_evidence["postflight_protocol"]),
        {key: Path(value) for key, value in raw_evidence["source_paths"].items()},
    )
    report = evaluate_run_artifact(
        spec,
        dataset_snapshot=Path(request["dataset_snapshot"]),
        run_artifact=Path(request["run_artifact"]),
        run_id=run_id,
        registry=registry,
        evidence=evidence,
    )
    checkpoint()
    report_payload = report.to_payload()
    encoded_report = (json.dumps(report_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    report_digest = hashlib.sha256(encoded_report).hexdigest()
    report_path = (
        warm_root / "research-evaluations" / spec.domain.value / report_payload["content_hash"] / "report.json"
    )
    expected = _decision_for_evaluation(report, run_id, report_digest, run["completed_at"])
    decision_path = registry.path_for(ResearchKind.EXPERIMENT_DECISION, expected.record_id)
    exists = report_path.exists() or report_path.is_symlink()
    if exists and _read(report_path) != encoded_report:
        raise ValueError("existing evaluation report differs from frozen evidence")
    decision = None
    if registry.find(expected.record_id) is not None:
        _read(decision_path)
        decision = registry.load(expected.record_id)
        expected = _decision_for_evaluation(report, run_id, report_digest, decision["decided_at"])
        if not exists or decision != expected.to_payload():
            raise ValueError("existing decision/report conflicts with frozen evidence")
        status = "verified_existing_decision"
    else:
        status = "report_without_matching_decision" if exists else "no_matching_publication_observed"
    checkpoint()
    if (
        _read(request_path, 65536) != raw
        or registry.load(run_id) != run
        or registry.load(spec.record_id) != spec_record
        or (decision is not None and registry.load(expected.record_id) != decision)
        or (decision is None and registry.find(expected.record_id) is not None)
        or ((report_path.exists() or report_path.is_symlink()) != exists)
        or (exists and _read(report_path) != encoded_report)
    ):
        raise ValueError("publication changed during reconciliation")
    payload = {
        "schema_version": "wong-choi-postflight-reconciliation/v1",
        "request_sha256": request_sha256,
        "spec_id": spec.record_id,
        "run_id": run_id,
        "publication_status": status,
        "expected_decision_id": expected.record_id,
        "verified_decision_id": expected.record_id if decision else None,
        "evaluation_content_hash": report_payload["content_hash"],
        "evaluation_artifact_digest": report_digest,
        "evaluation_report_path": str(report_path) if exists else None,
        "rerun_scoring_allowed": False,
        "retry_publication_allowed": False,
        "model_promotion_allowed": False,
    }
    return {**payload, "content_hash": hashlib.sha256(_encode(payload)).hexdigest()}
