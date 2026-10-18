"""Supervised, inventory-pinned page reads; no dataset/sample/model authority."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .contracts import Domain
from .research_index import _Reader, _at, _encoded, _hash, _hashed, _safe
from .research_evaluation import _write_report
from .research_prediction_artifacts import MAX_ARTIFACTS, SCHEMA, verify_prediction_artifact_report
from .research_prediction_pages import (
    MAX_INVENTORY_BYTES, MAX_PAGE_RECORDS, RESULT_SCHEMA, COVERAGE_SCHEMA,
    aggregate_prediction_pages, freeze_prediction_inventory,
    persist_prediction_page, plan_prediction_pages, verify_prediction_page_plan,
)
from .research_runner import ResearchDisposition


def _inputs(payload, runtime, checkpoint=lambda: None):
    if set(payload) != {
        "domain", "evidence_root", "as_of", "relocation_roots", "inventory_path",
        "inventory_sha256", "page_index", "max_refs", "max_records",
    }:
        raise ValueError("unsupported prediction page request fields")
    domain = Domain(payload["domain"])
    root = _safe(Path(payload["evidence_root"]))
    end = _at(payload["as_of"])
    path = _safe(Path(payload["inventory_path"]))
    if not path.is_relative_to(_safe(runtime.warm_root)):
        raise ValueError("prediction inventory must be a pinned WARM input")
    expected_digest = payload["inventory_sha256"]
    if not isinstance(expected_digest, str) or not re.fullmatch("[0-9a-f]{64}", expected_digest):
        raise ValueError("inventory byte digest required")
    reader = _Reader(checkpoint, max_records=1, max_record_bytes=MAX_INVENTORY_BYTES,
                     max_total_bytes=MAX_INVENTORY_BYTES * 2)
    inventory, digest = reader.read(path)
    if digest != expected_digest:
        raise ValueError("inventory input byte digest mismatch")
    plans = plan_prediction_pages(inventory, max_refs=payload["max_refs"], max_records=payload["max_records"])
    index = payload["page_index"]
    if type(index) is not int or not 0 <= index < len(plans):
        raise ValueError("invalid prediction page index")
    if (inventory["root"] != str(root) or inventory["domain"] != domain.value
            or inventory["as_of"] != end.isoformat()):
        raise ValueError("inventory request scope mismatch")
    reader.recheck()
    return inventory, plans[index], domain, root, end


def reconcile_prediction_corpus(*, payload, runtime, workspace, inventory_sha256,
                                coverage_sha256, checkpoint=lambda: None):
    """Read-only pinned prior-output reconstruction, not retry authorization.

    Operational calls must run inside the shared supervisor/heavy-worker lock.
    No missing page is written or replaced, and an existing final proof alone
    cannot establish completion. Every source page is reconstructed again.
    """
    domain, root, end = _corpus_scope(payload)
    workspace = _safe(Path(workspace))
    if not workspace.is_relative_to(_safe(runtime.warm_root)) or not workspace.is_dir():
        raise ValueError("prior corpus workspace must be existing WARM input")
    for digest in (inventory_sha256, coverage_sha256):
        if not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest):
            raise ValueError("prior corpus byte witnesses required")
    reader = _Reader(checkpoint, max_record_bytes=MAX_INVENTORY_BYTES)
    inventory, digest = reader.read(workspace / "prediction-inventory.json")
    if digest != inventory_sha256:
        raise ValueError("prior inventory byte digest mismatch")
    plans = plan_prediction_pages(inventory, max_refs=payload["max_refs"], max_records=payload["max_records"])
    path = workspace / "prediction-coverage.json"
    if path.stat().st_size > 131072:
        raise ValueError("oversized prior coverage proof")
    proof, digest = reader.read(path)
    if digest != coverage_sha256:
        raise ValueError("prior coverage byte digest mismatch")
    results = []
    for page in plans:
        checkpoint()
        page_path = workspace / f"prediction-page-{page['content_hash']}.json"
        if page_path.stat().st_size > 131072:
            raise ValueError("oversized prior page proof")
        report, _ = reader.read(page_path)
        results.append(report)
    actual = aggregate_prediction_pages(
        results=results, inventory=inventory, root=root, domain=domain, as_of=end,
        relocation_roots=tuple(Path(p) for p in payload["relocation_roots"]),
        max_refs=payload["max_refs"], max_records=payload["max_records"], checkpoint=checkpoint,
    )
    if _encoded(proof) != _encoded(actual):
        raise ValueError("prior corpus proof differs from current complete source")
    reader.recheck()
    checkpoint()
    return {"status": "verified_existing_corpus", "content_hash": actual["content_hash"],
            "retry_allowed": False, "model_promotion_allowed": False}


class PredictionPageInspectionRunner:
    def __init__(self, runtime, registry):
        self.runtime, self.registry = runtime, registry

    def run(self, *, domain, evidence_root, as_of, inventory_path, inventory_sha256,
            page_index, estimated_bytes, timeout_seconds, relocation_roots=(),
            max_refs=MAX_ARTIFACTS, max_records=MAX_PAGE_RECORDS):
        from .research_supervision import _phase, SourceInspectionResult
        if not isinstance(domain, Domain) or not isinstance(relocation_roots, tuple):
            raise ValueError("known domain and tuple relocation roots required")
        payload = {
            "domain": domain.value, "evidence_root": str(Path(evidence_root).absolute()),
            "as_of": _at(as_of).isoformat(), "inventory_path": str(Path(inventory_path).absolute()),
            "inventory_sha256": inventory_sha256, "page_index": page_index,
            "relocation_roots": [str(Path(p).absolute()) for p in relocation_roots],
            "max_refs": max_refs, "max_records": max_records,
        }
        disposition, status, attempt, receipt = _phase(
            self.runtime, self.registry, None, action="prediction-page", payload=payload,
            estimated_bytes=estimated_bytes, timeout_seconds=timeout_seconds,
        )
        valid = receipt if disposition is ResearchDisposition.SUCCEEDED else {}
        return SourceInspectionResult(disposition, status, attempt,
                                      Path(valid["report_path"]) if valid.get("report_path") else None,
                                      valid.get("content_hash"))


def run_prediction_page_request(request, *, runtime, workspace, checkpoint):
    payload = request["payload"]
    inventory, page, domain, root, end = _inputs(payload, runtime, checkpoint)
    saved = persist_prediction_page(
        inventory=inventory, page=page, root=root, domain=domain, as_of=end,
        output_root=workspace, relocation_roots=tuple(Path(p) for p in payload["relocation_roots"]),
        max_refs=payload["max_refs"], max_records=payload["max_records"], checkpoint=checkpoint,
    )
    return {"disposition": "succeeded", "status": "prediction_page_inventory_only",
            "report_path": str(saved["path"]), "content_hash": saved["content_hash"],
            "normalized_source_verified": False, "verified_monitoring_samples": None,
            "model_promotion_allowed": False}


def verify_prediction_page_receipt(*, payload, runtime, report_path, receipt):
    """Bounded parent verification; blob I/O stays in the supervised child."""
    inventory, page, domain, root, end = _inputs(payload, runtime)
    reader = _Reader(lambda: None, max_records=1, max_record_bytes=131072, max_total_bytes=262144)
    report, _ = reader.read(report_path)
    _hashed(report, RESULT_SCHEMA)
    expected = {
        "schema_version", "inventory_hash", "page_plan_hash", "page_index", "relocation_roots",
        "records", "source_coverage_complete", "model_promotion_allowed", "content_hash",
    }
    verify_prediction_page_plan(page, inventory, max_refs=payload["max_refs"], max_records=payload["max_records"])
    if (set(report) != expected or len(_encoded(report)) > 131072
            or report["inventory_hash"] != inventory["content_hash"]
            or report["page_plan_hash"] != page["content_hash"]
            or type(report["page_index"]) is not int or report["page_index"] != page["page_index"]
            or report["relocation_roots"] != payload["relocation_roots"]
            or report["source_coverage_complete"] is not False or report["model_promotion_allowed"] is not False
            or report["content_hash"] != receipt["content_hash"]):
        raise ValueError("prediction page receipt identity or authority mismatch")
    records = report["records"]
    if not isinstance(records, list) or [r["record_id"] for r in records] != page["record_ids"]:
        raise ValueError("prediction page record coverage mismatch")
    by_id = {r["record_id"]: r for r in inventory["records"]}
    if any(r["content_hash"] != by_id[r["record_id"]]["content_hash"]
           or r["artifact_refs"] != by_id[r["record_id"]]["artifact_refs"] for r in records):
        raise ValueError("page records do not bind frozen metadata")
    # Reuse the native bounded record-shape verifier without re-reading blobs.
    aggregate = {
        "schema_version": SCHEMA, "domain": domain.value, "root": str(root), "as_of": end.isoformat(),
        "relocation_roots": payload["relocation_roots"], "records": records, "records_seen": len(records),
        **{name: sum(r[name] for r in records) for name in (
            "artifact_refs", "direct_verified", "relocated_verified", "unavailable_refs", "direct_invalid_refs",
        )},
        "verified_bundles": sum(r["snapshot_bundle_verified"] for r in records),
        "artifact_contents_verified": bool(records) and all(r["snapshot_bundle_verified"] for r in records),
        "normalized_source_verified": False, "source_coverage_complete": False,
        "verified_monitoring_samples": None, "model_promotion_allowed": False,
    }
    aggregate["content_hash"] = _hash(aggregate)
    verify_prediction_artifact_report(aggregate, root=root, domain=domain, as_of=end,
                                      relocation_roots=tuple(Path(p) for p in payload["relocation_roots"]))
    reader.recheck()


class PredictionCorpusInspectionRunner:
    def __init__(self, runtime, registry):
        self.runtime, self.registry = runtime, registry

    def run(self, *, domain, evidence_root, as_of, estimated_bytes, timeout_seconds,
            relocation_roots=(), max_refs=MAX_ARTIFACTS, max_records=MAX_PAGE_RECORDS):
        from .research_supervision import _phase, SourceInspectionResult
        if not isinstance(domain, Domain) or not isinstance(relocation_roots, tuple):
            raise ValueError("known domain and tuple relocation roots required")
        payload = {
            "domain": domain.value, "evidence_root": str(Path(evidence_root).absolute()),
            "as_of": _at(as_of).isoformat(), "relocation_roots": [str(Path(p).absolute()) for p in relocation_roots],
            "max_refs": max_refs, "max_records": max_records,
        }
        disposition, status, attempt, receipt = _phase(
            self.runtime, self.registry, None, action="prediction-corpus", payload=payload,
            estimated_bytes=estimated_bytes, timeout_seconds=timeout_seconds,
        )
        valid = receipt if disposition is ResearchDisposition.SUCCEEDED else {}
        return SourceInspectionResult(disposition, status, attempt,
                                      Path(valid["report_path"]) if valid.get("report_path") else None,
                                      valid.get("content_hash"))


def _corpus_scope(payload):
    if set(payload) != {"domain", "evidence_root", "as_of", "relocation_roots", "max_refs", "max_records"}:
        raise ValueError("unsupported prediction corpus request fields")
    return Domain(payload["domain"]), _safe(Path(payload["evidence_root"])), _at(payload["as_of"])


def _reconciliation_scope(payload):
    extra = {"prior_workspace", "inventory_sha256", "coverage_sha256"}
    if set(payload) != {"domain", "evidence_root", "as_of", "relocation_roots", "max_refs", "max_records"} | extra:
        raise ValueError("unsupported corpus reconciliation request fields")
    base = {key: value for key, value in payload.items() if key not in extra}
    _corpus_scope(base)
    return base


class PredictionCorpusReconciliationRunner:
    def __init__(self, runtime, registry):
        self.runtime, self.registry = runtime, registry

    def run(self, *, domain, evidence_root, as_of, prior_workspace, inventory_sha256,
            coverage_sha256, estimated_bytes, timeout_seconds, relocation_roots=(),
            max_refs=MAX_ARTIFACTS, max_records=MAX_PAGE_RECORDS):
        from .research_supervision import _phase, SourceInspectionResult
        if not isinstance(domain, Domain) or not isinstance(relocation_roots, tuple):
            raise ValueError("known domain and tuple relocation roots required")
        payload = {"domain": domain.value, "evidence_root": str(Path(evidence_root).absolute()),
                   "as_of": _at(as_of).isoformat(), "prior_workspace": str(Path(prior_workspace).absolute()),
                   "inventory_sha256": inventory_sha256, "coverage_sha256": coverage_sha256,
                   "relocation_roots": [str(Path(p).absolute()) for p in relocation_roots],
                   "max_refs": max_refs, "max_records": max_records}
        disposition, status, attempt, receipt = _phase(
            self.runtime, self.registry, None, action="prediction-corpus-reconcile", payload=payload,
            estimated_bytes=estimated_bytes, timeout_seconds=timeout_seconds,
        )
        valid = receipt if disposition is ResearchDisposition.SUCCEEDED else {}
        return SourceInspectionResult(disposition, status, attempt,
                                      Path(valid["report_path"]) if valid.get("report_path") else None,
                                      valid.get("content_hash"))


def run_prediction_corpus_reconciliation_request(request, *, runtime, workspace, checkpoint):
    payload = request["payload"]
    base = _reconciliation_scope(payload)
    prior = _safe(Path(payload["prior_workspace"]))
    witnesses = {key: payload[key] for key in ("inventory_sha256", "coverage_sha256")}
    reconcile_prediction_corpus(payload=base, runtime=runtime, workspace=prior,
                                checkpoint=checkpoint, **witnesses)
    reader = _Reader(checkpoint, max_record_bytes=MAX_INVENTORY_BYTES)
    inventory, digest = reader.read(prior / "prediction-inventory.json")
    if digest != witnesses["inventory_sha256"]:
        raise ValueError("prior inventory changed after reconciliation")
    plans = plan_prediction_pages(inventory, max_refs=base["max_refs"], max_records=base["max_records"])
    files = ["prediction-inventory.json", *(f"prediction-page-{p['content_hash']}.json" for p in plans),
             "prediction-coverage.json"]
    for name in files:
        value, digest = reader.read(prior / name)
        if name == "prediction-coverage.json" and digest != witnesses["coverage_sha256"]:
            raise ValueError("prior coverage changed after reconciliation")
        _write_report(workspace / name, value, resource_checkpoint=checkpoint, create_parents=False)
    reader.recheck()
    # Rebuild the copied page set against sources again before acknowledging it.
    verified = reconcile_prediction_corpus(payload=base, runtime=runtime, workspace=workspace,
                                           checkpoint=checkpoint, **witnesses)
    return {"disposition": "succeeded", "status": "prediction_corpus_reconciled_inventory_only",
            "report_path": str(workspace / "prediction-coverage.json"), "content_hash": verified["content_hash"],
            "normalized_source_verified": False, "verified_monitoring_samples": None,
            "model_promotion_allowed": False}


def verify_prediction_corpus_reconciliation_receipt(*, payload, runtime, report_path, receipt):
    base = _reconciliation_scope(payload)
    reader = _Reader(lambda: None, max_record_bytes=MAX_INVENTORY_BYTES)
    for name, witness in (("prediction-inventory.json", "inventory_sha256"),
                          ("prediction-coverage.json", "coverage_sha256")):
        _, digest = reader.read(report_path.parent / name)
        if digest != payload[witness]:
            raise ValueError("reconciliation output does not match pinned prior bytes")
    verify_prediction_corpus_receipt(payload=base, runtime=runtime, report_path=report_path, receipt=receipt)
    reader.recheck()


def run_prediction_corpus_request(request, *, runtime, workspace, checkpoint):
    payload = request["payload"]
    domain, root, end = _corpus_scope(payload)
    inventory = freeze_prediction_inventory(root=root, domain=domain, as_of=end, checkpoint=checkpoint)
    plans = plan_prediction_pages(inventory, max_refs=payload["max_refs"], max_records=payload["max_records"])
    inventory_path = workspace / "prediction-inventory.json"
    if len((json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()) > MAX_INVENTORY_BYTES:
        raise ValueError("persisted inventory exceeds read bound")
    _write_report(inventory_path, inventory, resource_checkpoint=checkpoint, create_parents=False)
    results = []
    for page in plans:
        checkpoint()
        saved = persist_prediction_page(
            inventory=inventory, page=page, root=root, domain=domain, as_of=end,
            output_root=workspace, relocation_roots=tuple(Path(p) for p in payload["relocation_roots"]),
            max_refs=payload["max_refs"], max_records=payload["max_records"], checkpoint=checkpoint,
        )
        reader = _Reader(checkpoint, max_records=1, max_record_bytes=131072, max_total_bytes=262144)
        report, _ = reader.read(saved["path"])
        reader.recheck()
        results.append(report)
    proof = aggregate_prediction_pages(
        results=results, inventory=inventory, root=root, domain=domain, as_of=end,
        relocation_roots=tuple(Path(p) for p in payload["relocation_roots"]),
        max_refs=payload["max_refs"], max_records=payload["max_records"], checkpoint=checkpoint,
    )
    path = workspace / "prediction-coverage.json"
    _write_report(path, proof, resource_checkpoint=checkpoint, create_parents=False)
    checkpoint()
    return {"disposition": "succeeded", "status": "prediction_corpus_inventory_only",
            "report_path": str(path), "content_hash": proof["content_hash"],
            "normalized_source_verified": False, "verified_monitoring_samples": None,
            "model_promotion_allowed": False}


def verify_prediction_corpus_receipt(*, payload, runtime, report_path, receipt):
    """Parent checks the complete bounded page set, never reads source blobs."""
    domain, root, end = _corpus_scope(payload)
    workspace = _safe(report_path.parent)
    if report_path.name != "prediction-coverage.json" or not workspace.is_relative_to(_safe(runtime.warm_root)):
        raise ValueError("invalid prediction corpus output scope")
    reader = _Reader(lambda: None, max_record_bytes=MAX_INVENTORY_BYTES)
    inventory, inventory_digest = reader.read(workspace / "prediction-inventory.json")
    if (inventory["root"] != str(root) or inventory["domain"] != domain.value
            or inventory["as_of"] != end.isoformat()):
        raise ValueError("prediction inventory output scope mismatch")
    plans = plan_prediction_pages(inventory, max_refs=payload["max_refs"], max_records=payload["max_records"])
    records, hashes = [], []
    for page in plans:
        path = _safe(workspace / f"prediction-page-{page['content_hash']}.json")
        if path.stat().st_size > 131072:
            raise ValueError("oversized corpus page receipt")
        report, _ = reader.read(path)
        _hashed(report, RESULT_SCHEMA)
        page_payload = {
            **payload, "inventory_path": str(workspace / "prediction-inventory.json"),
            "inventory_sha256": inventory_digest, "page_index": page["page_index"],
        }
        verify_prediction_page_receipt(payload=page_payload, runtime=runtime, report_path=path,
                                       receipt={"content_hash": report["content_hash"]})
        hashes.append(report["content_hash"])
        records.extend(report["records"])
    if report_path.stat().st_size > 131072:
        raise ValueError("oversized prediction corpus coverage")
    proof, _ = reader.read(report_path)
    _hashed(proof, COVERAGE_SCHEMA)
    expected = {
        "schema_version": COVERAGE_SCHEMA, "inventory_hash": inventory["content_hash"],
        "page_hashes": hashes, "page_coverage_complete": True,
        "records_seen": len(records), "artifact_refs": sum(r["artifact_refs"] for r in records),
        "verified_bundles": sum(r["snapshot_bundle_verified"] for r in records),
        "unavailable_refs": sum(r["unavailable_refs"] for r in records),
        "artifact_contents_verified": bool(records) and all(r["snapshot_bundle_verified"] for r in records),
        "source_coverage_complete": False, "verified_monitoring_samples": None, "model_promotion_allowed": False,
    }
    expected["content_hash"] = _hash(expected)
    if _encoded(proof) != _encoded(expected) or proof["content_hash"] != receipt["content_hash"]:
        raise ValueError("prediction corpus coverage differs from complete page set")
    reader.recheck()
