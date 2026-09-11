"""Read-only preparation/scoring reconciliation; not evaluation or retry authority."""

from __future__ import annotations

import hashlib
import re
import shlex
from pathlib import Path
from urllib.parse import quote

from .artifact_archive import artifact_digest
from .research_dataset import _aware, _load_snapshot, _enforce_previous_floor, load_dataset_snapshot, SplitPolicy
from .research_evaluation import _strict_json
from .research_reconciliation import _read, _encode
from .research_registry import ResearchKind
from .research_runner import ResearchJob, RUN_ARTIFACT_SCHEMA_VERSION, _digest


def _safe(path):
    if not path.is_absolute() or ".." in path.parts or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("unsafe phase evidence path")


def _children(path, limit=10000):
    _safe(path)
    if not path.exists():
        return []
    if not path.is_dir():
        raise ValueError("phase evidence directory required")
    result = []
    for item in path.iterdir():
        _safe(item)
        result.append(item)
        if len(result) > limit:
            raise ValueError("phase evidence entry limit exceeded")
    return sorted(result)


def _tree_digest(path):
    _safe(path)
    if not path.is_dir():
        raise ValueError("phase artifact directory required")
    for item in path.rglob("*"):
        if item.is_symlink() or not (item.is_dir() or item.is_file()):
            raise ValueError("non-regular phase artifact")
    return artifact_digest(path)


def _prepared(spec, request, attempt, registry):
    root = attempt / "work/datasets" / spec.domain.value
    entries = _children(root, 32)
    finals = [p for p in entries if re.fullmatch("[0-9a-f]{64}", p.name)]
    if len(finals) > 1 or any(not p.name.startswith(".") and p not in finals for p in entries):
        raise ValueError("ambiguous preparation output")
    if not finals:
        return None, None, None, "incomplete_artifact_observed" if entries else "no_final_artifact_observed", None
    path = finals[0]
    digest = _tree_digest(path)
    snapshot = load_dataset_snapshot(path)
    manifest, rows = _load_snapshot(path)
    policy = SplitPolicy(**request["payload"]["split_policy"])
    expected_sources = sorted(
        [
            {
                "source_id": s["source_id"],
                "tier": s["tier"],
                "artifact_path": str(Path(s["artifact_path"]).resolve()),
                "rows_path": str(Path(s["rows_path"]).resolve()),
                "available_at": _aware(s["available_at"], "source availability").isoformat(),
                "artifact_digest": s["expected_digest"],
                "catalog_record": str(Path(s["catalog_record"]).resolve())
                if s["tier"] == "warm" and s["catalog_record"]
                else None,
            }
            for s in request["payload"]["sources"]
        ],
        key=lambda s: s["source_id"],
    )
    if (
        snapshot.manifest.spec_id != spec.record_id
        or snapshot.manifest.domain is not spec.domain
        or manifest["split_policy"] != policy.to_dict()
        or manifest["sources"] != expected_sources
    ):
        raise ValueError("prepared snapshot differs from pinned request")
    previous = request["payload"]["previous_snapshot"]
    if previous:
        _tree_digest(Path(previous))
        _enforce_previous_floor(Path(previous), spec=spec, split_policy=policy, current_rows=rows)
    record = None
    if registry.find(snapshot.manifest.record_id) is not None:
        record = registry.load(snapshot.manifest.record_id)
        if record != snapshot.manifest.to_payload():
            raise ValueError("prepared snapshot registration mismatch")
    status = "verified_registered_dataset" if record else "artifact_without_matching_registration"
    return path, digest, record, status, snapshot.manifest.artifact_digest


def _scored(spec, request, attempt, registry, checkpoint):
    job = ResearchJob.from_payload(request["payload"]["job"])
    if job.spec_id != spec.record_id or job.domain is not spec.domain:
        raise ValueError("scoring job differs from pinned spec")
    root = attempt / "work/research-runs" / spec.domain.value
    entries = _children(root, 32)
    path = root / quote(job.job_id, safe="._-")
    if any(not p.name.startswith(".") and p != path for p in entries):
        raise ValueError("unexpected scoring artifact")
    if path not in entries:
        return None, None, None, "incomplete_artifact_observed" if entries else "no_final_artifact_observed", None
    digest = _tree_digest(path)
    dataset_before = _tree_digest(job.dataset_snapshot)
    dataset = load_dataset_snapshot(job.dataset_snapshot).manifest
    if dataset.spec_id != spec.record_id or registry.load(dataset.record_id) != dataset.to_payload():
        raise ValueError("scoring dataset registration mismatch")
    failed = (path / "cleanup.json").exists()
    if failed:
        result = _strict_json(_read(path / "cleanup.json").decode())
        if result.get("removed_partial") is not True or not result.get("status"):
            raise ValueError("invalid failed scoring artifact")
        runtime = result["executions"]
        metrics_digest = None
    else:
        result = _strict_json(_read(path / "result.json").decode())
        metrics = _strict_json(_read(path / "metrics.json").decode())
        runtime = _strict_json(_read(path / "runtime.json").decode())
        metrics_digest = _digest(metrics)
        if (
            set(metrics) != {"baseline", "candidate"}
            or any(not isinstance(metrics[r], list) or len(metrics[r]) != len(spec.commands) for r in metrics)
            or result
            != {
                "schema_version": RUN_ARTIFACT_SCHEMA_VERSION,
                "append_only": True,
                "job_id": job.job_id,
                "domain": spec.domain.value,
                "spec_id": spec.record_id,
                "dataset_manifest_id": dataset.record_id,
                "baseline_commit": spec.baseline_commit,
                "candidate_commit": spec.candidate_commit,
                "commands": list(spec.commands),
                "seed": spec.seed,
                "reproducibility_digest": metrics_digest,
            }
        ):
            raise ValueError("scoring output differs from pinned job/spec")
    if (
        result.get("schema_version") != RUN_ARTIFACT_SCHEMA_VERSION
        or result.get("append_only") is not True
        or result.get("job_id") != job.job_id
    ):
        raise ValueError("scoring artifact identity mismatch")
    expected_commands = [
        (role, index, shlex.split(command))
        for role in ("baseline", "candidate")
        for index, command in enumerate(spec.commands)
    ]
    if (
        not isinstance(runtime, list)
        or len(runtime) > len(expected_commands)
        or (not failed and len(runtime) != len(expected_commands))
    ):
        raise ValueError("scoring command coverage mismatch")
    for item, (role, index, argv) in zip(runtime, expected_commands):
        if (item["role"], item["index"], item["argv"]) != (role, index, argv) or (
            not failed and (item["state"] != "succeeded" or item["returncode"] != 0)
        ):
            raise ValueError("scoring runtime differs from pinned commands")
    stdout_digest = _digest([{"stdout": item["stdout"], "stderr": item["stderr"]} for item in runtime])
    matches = []
    for record_path in _children(registry.root / "records/experiment_run"):
        checkpoint()
        if record_path.name.startswith("."):
            continue
        raw = _strict_json(_read(record_path).decode())
        if record_path != registry.path_for(ResearchKind.EXPERIMENT_RUN, raw["record_id"]):
            raise ValueError("noncanonical run registry path")
        record = registry.load(raw["record_id"])
        if record["artifact_digest"] != digest["sha256"]:
            continue
        identity = _digest(
            {"job_id": job.job_id, "started_at": record["started_at"], "artifact_digest": digest["sha256"]}
        )[:24]
        if (
            record["record_id"] != f"wc:{spec.domain.value}:experiment-run:{identity}"
            or record["links"] != {"spec_id": spec.record_id, "dataset_manifest_id": dataset.record_id}
            or record["baseline_commit"] != spec.baseline_commit
            or record["candidate_commit"] != spec.candidate_commit
            or record["evaluation_ruler_id"] != spec.evaluation_ruler_id
            or record["evaluation_ruler_digest"] != spec.evaluation_ruler_digest
            or record["commands"] != list(spec.commands)
            or record["seed"] != spec.seed
            or record["stdout_digest"] != stdout_digest
            or (not failed and (record["state"] != "succeeded" or record["metrics_digest"] != metrics_digest))
            or (failed and record["state"] not in {"failed", "blocked"})
        ):
            raise ValueError("scoring registration differs from pinned artifact/spec")
        matches.append(record)
    if len(matches) > 1:
        raise ValueError("ambiguous scoring registrations")
    if _tree_digest(job.dataset_snapshot) != dataset_before:
        raise ValueError("scoring dataset changed during reconciliation")
    record = matches[0] if matches else None
    status = (
        ("verified_registered_failure" if failed else "verified_registered_run")
        if record
        else "artifact_without_matching_registration"
    )
    return path, digest, record, status, None


def reconcile_phase(spec, *, attempt_path, request_sha256, registry, warm_root, state_root, checkpoint):
    checkpoint()
    attempt = Path(attempt_path)
    _safe(attempt)
    request_path = attempt / "request.json"
    raw = _read(request_path, 65536)
    if hashlib.sha256(raw).hexdigest() != request_sha256:
        raise ValueError("phase request does not match pinned hash")
    request = _strict_json(raw.decode())
    phase = request.get("action")
    if (
        request.get("schema_version") != "wong-choi-supervised-research-phase/v1"
        or phase not in {"prepare", "scoring"}
        or attempt.parent != warm_root / "research-phases" / spec.domain.value
        or not attempt.name.startswith(phase + "-")
        or request.get("spec_id") != spec.record_id
        or request.get("registry") != str(registry.root)
        or request.get("warm_root") != str(warm_root)
        or request.get("state_root") != str(state_root)
        or registry.load(spec.record_id) != spec.to_payload()
    ):
        raise ValueError("phase request context mismatch")
    if phase == "prepare":
        path, digest, record, status, rows_digest = _prepared(spec, request, attempt, registry)
    else:
        path, digest, record, status, rows_digest = _scored(spec, request, attempt, registry, checkpoint)
    checkpoint()
    if (
        _read(request_path, 65536) != raw
        or registry.load(spec.record_id) != spec.to_payload()
        or (path is not None and _tree_digest(path) != digest)
        or (record is not None and registry.load(record["record_id"]) != record)
    ):
        raise ValueError("phase evidence changed during reconciliation")
    payload = {
        "schema_version": "wong-choi-phase-reconciliation/v1",
        "request_sha256": request_sha256,
        "spec_id": spec.record_id,
        "phase": phase,
        "publication_status": status,
        "artifact_path": str(path) if path else None,
        "artifact_digest": digest,
        "dataset_rows_digest": rows_digest,
        "verified_record_id": record["record_id"] if record else None,
        "record_hash": record["content_hash"] if record else None,
        "rerun_scoring_allowed": False,
        "retry_publication_allowed": False,
        "model_promotion_allowed": False,
    }
    return {**payload, "content_hash": hashlib.sha256(_encode(payload)).hexdigest()}


def verify_phase_reconciliation_receipt(spec, *, registry, report_path, receipt, request_sha256):
    payload = _strict_json(_read(report_path, 65536).decode())
    digest = hashlib.sha256(_encode({k: v for k, v in payload.items() if k != "content_hash"})).hexdigest()
    record_id = payload.get("verified_record_id")
    status = payload.get("publication_status")
    verified = status in {"verified_registered_dataset", "verified_registered_run", "verified_registered_failure"}
    if (
        payload.get("schema_version") != "wong-choi-phase-reconciliation/v1"
        or payload.get("phase") not in {"prepare", "scoring"}
        or payload.get("spec_id") != spec.record_id
        or payload.get("request_sha256") != request_sha256
        or digest != payload.get("content_hash")
        or digest != receipt.get("content_hash")
        or status != receipt.get("status")
        or status
        not in {
            "verified_registered_dataset",
            "verified_registered_run",
            "verified_registered_failure",
            "artifact_without_matching_registration",
            "incomplete_artifact_observed",
            "no_final_artifact_observed",
        }
        or bool(record_id) != verified
        or (verified and payload.get("phase") == "prepare" and status != "verified_registered_dataset")
        or (payload.get("phase") == "scoring" and status == "verified_registered_dataset")
        or record_id != receipt.get("record_id")
        or receipt.get("decision_id") is not None
        or any(
            payload.get(k) is not False
            for k in ("rerun_scoring_allowed", "retry_publication_allowed", "model_promotion_allowed")
        )
    ):
        raise ValueError("phase reconciliation receipt mismatch")
    if record_id:
        record = registry.load(record_id)
        expected_kind = "dataset_manifest" if payload["phase"] == "prepare" else "experiment_run"
        expected_digest = (
            payload["dataset_rows_digest"] if payload["phase"] == "prepare" else payload["artifact_digest"]["sha256"]
        )
        if (
            record["kind"] != expected_kind
            or record["links"]["spec_id"] != spec.record_id
            or record["content_hash"] != payload["record_hash"]
            or record["artifact_digest"] != expected_digest
            or (status == "verified_registered_run" and record.get("state") != "succeeded")
            or (status == "verified_registered_failure" and record.get("state") not in {"failed", "blocked"})
        ):
            raise ValueError("phase reconciliation record mismatch")
