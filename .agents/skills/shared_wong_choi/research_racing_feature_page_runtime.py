"""Supervised native racing feature-page receipts, never sample authority."""
from pathlib import Path
import json
import re

from .contracts import Domain
from .research_evaluation import _write_report
from .research_index import _Reader, _at, _encoded, _hash, _hashed, _safe
from .research_prediction_artifacts import MAX_ARTIFACTS
from .research_prediction_page_runtime import (
    _corpus_scope, _inputs, reconcile_prediction_corpus, run_prediction_corpus_request,
    verify_prediction_corpus_receipt, verify_prediction_page_receipt,
)
from .research_prediction_pages import (
    MAX_INVENTORY_BYTES, MAX_PAGE_RECORDS, inspect_prediction_page,
    plan_prediction_pages, verify_prediction_inventory,
)
from .research_racing_feature_pages import (
    COUNTS, COVERAGE_SCHEMA, SCHEMA, aggregate_racing_feature_pages, inspect_racing_feature_page,
)
from .research_runner import ResearchDisposition


class RacingFeaturePageInspectionRunner:
    def __init__(self, runtime, registry):
        self.runtime, self.registry = runtime, registry

    def run(self, *, domain, evidence_root, as_of, inventory_path, inventory_sha256,
            page_index, estimated_bytes, timeout_seconds, relocation_roots=(),
            max_refs=MAX_ARTIFACTS, max_records=MAX_PAGE_RECORDS):
        from .research_supervision import _phase, SourceInspectionResult
        if domain not in (Domain.AU, Domain.HKJC) or not isinstance(domain, Domain) or not isinstance(relocation_roots, tuple):
            raise ValueError("native racing domain and tuple relocation roots required")
        payload = {"domain": domain.value, "evidence_root": str(Path(evidence_root).absolute()),
                   "as_of": _at(as_of).isoformat(), "inventory_path": str(Path(inventory_path).absolute()),
                   "inventory_sha256": inventory_sha256, "page_index": page_index,
                   "relocation_roots": [str(Path(p).absolute()) for p in relocation_roots],
                   "max_refs": max_refs, "max_records": max_records}
        disposition, status, attempt, receipt = _phase(
            self.runtime, self.registry, None, action="racing-feature-page", payload=payload,
            estimated_bytes=estimated_bytes, timeout_seconds=timeout_seconds,
        )
        valid = receipt if disposition is ResearchDisposition.SUCCEEDED else {}
        return SourceInspectionResult(disposition, status, attempt,
                                      Path(valid["report_path"]) if valid.get("report_path") else None,
                                      valid.get("content_hash"))


def run_racing_feature_page_request(request, *, runtime, workspace, checkpoint):
    payload = request["payload"]
    inventory, page, domain, root, end = _inputs(payload, runtime, checkpoint)
    options = dict(inventory=inventory, page=page, domain=domain, root=root, as_of=end,
                   relocation_roots=tuple(Path(p) for p in payload["relocation_roots"]),
                   max_refs=payload["max_refs"], max_records=payload["max_records"], checkpoint=checkpoint)
    verify_prediction_inventory(inventory, root=root, domain=domain, as_of=end, checkpoint=checkpoint)
    prediction = inspect_prediction_page(**options)
    feature = inspect_racing_feature_page(**options)
    if feature["prediction_page_hash"] != prediction["content_hash"]:
        raise ValueError("prediction page changed before feature publication")
    verify_prediction_inventory(inventory, root=root, domain=domain, as_of=end, checkpoint=checkpoint)
    names = ((f"prediction-page-{page['content_hash']}.json", prediction, 131072),
             (f"racing-feature-page-{page['content_hash']}.json", feature, 262144))
    for name, value, limit in names:
        if len((json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()) > limit:
            raise ValueError("persisted feature/prediction page exceeds read bound")
        _write_report(workspace / name, value, resource_checkpoint=checkpoint, create_parents=False)
    checkpoint()
    return {"disposition": "succeeded", "status": "racing_feature_page_inventory_only",
            "report_path": str(workspace / names[1][0]), "content_hash": feature["content_hash"],
            "normalized_source_verified": False, "verified_monitoring_samples": None,
            "model_promotion_allowed": False}


def verify_racing_feature_page_receipt(*, payload, runtime, report_path, receipt):
    """Bounded parent metadata checks; heavy source reads stay in the child."""
    inventory, page, domain, root, end = _inputs(payload, runtime)
    if domain not in (Domain.AU, Domain.HKJC):
        raise ValueError("native racing domain required")
    if report_path.name != f"racing-feature-page-{page['content_hash']}.json":
        raise ValueError("feature page output identity mismatch")
    reader = _Reader(lambda: None, max_record_bytes=262144, max_total_bytes=1048576)
    report, _ = reader.read(report_path)
    _hashed(report, SCHEMA)
    expected = {"schema_version", "domain", "inventory_hash", "page_plan_hash", "prediction_page_hash",
                "feature_report", "source_coverage_complete", "verified_monitoring_samples",
                "model_promotion_allowed", "content_hash"}
    if (set(report) != expected or len(_encoded(report)) > 262144
            or report["domain"] != domain.value or report["inventory_hash"] != inventory["content_hash"]
            or report["page_plan_hash"] != page["content_hash"]
            or report["source_coverage_complete"] is not False or report["verified_monitoring_samples"] is not None
            or report["model_promotion_allowed"] is not False or report["content_hash"] != receipt["content_hash"]):
        raise ValueError("feature page identity or authority mismatch")
    prediction_path = report_path.parent / f"prediction-page-{page['content_hash']}.json"
    prediction, _ = reader.read(prediction_path)
    verify_prediction_page_receipt(payload=payload, runtime=runtime, report_path=prediction_path,
                                   receipt={"content_hash": report["prediction_page_hash"]})
    if domain is Domain.AU:
        from .research_au_feature_provenance import verify_au_feature_provenance_report as native
    else:
        from .research_hkjc_feature_provenance import verify_hkjc_feature_provenance_report as native
    feature = report["feature_report"]
    native(feature, root=root, as_of=end, relocation_roots=tuple(Path(p) for p in payload["relocation_roots"]))
    if (feature["prediction_report_hash"] != prediction["content_hash"]
            or [r["record_id"] for r in feature["records"]] != page["record_ids"]):
        raise ValueError("feature page does not bind prediction proof")
    for f, p in zip(feature["records"], prediction["records"]):
        if (f["event_id"] != p["event_id"] or f["source_cutoff_at"] != p["source_cutoff_at"]
                or f["snapshot_root"] != p["resolved_snapshot_root"]
                or f["bundle_verified"] != p["snapshot_bundle_verified"]):
            raise ValueError("feature record differs from verified prediction identity")
    reader.recheck()


class RacingFeatureCorpusInspectionRunner:
    def __init__(self, runtime, registry):
        self.runtime, self.registry = runtime, registry

    def run(self, *, domain, evidence_root, as_of, estimated_bytes, timeout_seconds,
            relocation_roots=(), max_refs=MAX_ARTIFACTS, max_records=MAX_PAGE_RECORDS):
        from .research_supervision import _phase, SourceInspectionResult
        if not isinstance(domain, Domain) or domain not in (Domain.AU, Domain.HKJC) or not isinstance(relocation_roots, tuple):
            raise ValueError("native racing domain and tuple relocation roots required")
        payload = {"domain": domain.value, "evidence_root": str(Path(evidence_root).absolute()),
                   "as_of": _at(as_of).isoformat(), "relocation_roots": [str(Path(p).absolute()) for p in relocation_roots],
                   "max_refs": max_refs, "max_records": max_records}
        disposition, status, attempt, receipt = _phase(
            self.runtime, self.registry, None, action="racing-feature-corpus", payload=payload,
            estimated_bytes=estimated_bytes, timeout_seconds=timeout_seconds,
        )
        valid = receipt if disposition is ResearchDisposition.SUCCEEDED else {}
        return SourceInspectionResult(disposition, status, attempt,
                                      Path(valid["report_path"]) if valid.get("report_path") else None,
                                      valid.get("content_hash"))


def run_racing_feature_corpus_request(request, *, runtime, workspace, checkpoint):
    payload = request["payload"]
    domain, root, end = _corpus_scope(payload)
    if domain not in (Domain.AU, Domain.HKJC):
        raise ValueError("native racing domain required")
    run_prediction_corpus_request(request, runtime=runtime, workspace=workspace, checkpoint=checkpoint)
    reader = _Reader(checkpoint, max_record_bytes=MAX_INVENTORY_BYTES)
    inventory, digest = reader.read(workspace / "prediction-inventory.json")
    plans = plan_prediction_pages(inventory, max_refs=payload["max_refs"], max_records=payload["max_records"])
    results = []
    for page in plans:
        checkpoint()
        page_payload = {**payload, "inventory_path": str(workspace / "prediction-inventory.json"),
                        "inventory_sha256": digest, "page_index": page["page_index"]}
        output = run_racing_feature_page_request({"payload": page_payload}, runtime=runtime,
                                                 workspace=workspace, checkpoint=checkpoint)
        bounded = _Reader(checkpoint, max_record_bytes=262144, max_total_bytes=524288)
        report, _ = bounded.read(Path(output["report_path"]))
        bounded.recheck()
        results.append(report)
    proof = aggregate_racing_feature_pages(
        results=results, inventory=inventory, root=root, domain=domain, as_of=end,
        relocation_roots=tuple(Path(p) for p in payload["relocation_roots"]),
        max_refs=payload["max_refs"], max_records=payload["max_records"], checkpoint=checkpoint,
    )
    reader.recheck()
    path = workspace / "racing-feature-coverage.json"
    if len((json.dumps(proof, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()) > 131072:
        raise ValueError("persisted feature coverage exceeds read bound")
    _write_report(path, proof, resource_checkpoint=checkpoint, create_parents=False)
    checkpoint()
    return {"disposition": "succeeded", "status": "racing_feature_corpus_inventory_only",
            "report_path": str(path), "content_hash": proof["content_hash"],
            "normalized_source_verified": False, "verified_monitoring_samples": None,
            "model_promotion_allowed": False}


def verify_racing_feature_corpus_receipt(*, payload, runtime, report_path, receipt):
    """Check the complete bounded proof set; source reconstruction stays in child."""
    domain, root, end = _corpus_scope(payload)
    if domain not in (Domain.AU, Domain.HKJC) or report_path.name != "racing-feature-coverage.json":
        raise ValueError("invalid native feature corpus scope")
    reader = _Reader(lambda: None, max_record_bytes=MAX_INVENTORY_BYTES)
    workspace = report_path.parent
    inventory, digest = reader.read(workspace / "prediction-inventory.json")
    prediction, _ = reader.read(workspace / "prediction-coverage.json")
    verify_prediction_corpus_receipt(payload=payload, runtime=runtime,
                                     report_path=workspace / "prediction-coverage.json",
                                     receipt={"content_hash": prediction["content_hash"]})
    plans = plan_prediction_pages(inventory, max_refs=payload["max_refs"], max_records=payload["max_records"])
    records, hashes = [], []
    for page in plans:
        path = workspace / f"racing-feature-page-{page['content_hash']}.json"
        bounded = _Reader(lambda: None, max_record_bytes=262144, max_total_bytes=524288)
        report, _ = bounded.read(path)
        page_payload = {**payload, "inventory_path": str(workspace / "prediction-inventory.json"),
                        "inventory_sha256": digest, "page_index": page["page_index"]}
        verify_racing_feature_page_receipt(payload=page_payload, runtime=runtime,
                                           report_path=path, receipt={"content_hash": report["content_hash"]})
        records.extend(report["feature_report"]["records"])
        hashes.append(report["content_hash"])
        bounded.recheck()
    final = _Reader(lambda: None, max_record_bytes=131072, max_total_bytes=262144)
    proof, _ = final.read(report_path)
    _hashed(proof, COVERAGE_SCHEMA)
    expected = {"schema_version": COVERAGE_SCHEMA, "domain": domain.value,
                "inventory_hash": inventory["content_hash"], "page_hashes": hashes,
                "records_seen": len(records), "verified_bundles": sum(r["bundle_verified"] for r in records),
                **{key: sum(r[key] for r in records) for key in COUNTS},
                "page_coverage_complete": True,
                "feature_availability_verified": bool(records) and all(r["feature_availability_verified"] for r in records),
                "source_coverage_complete": False, "verified_monitoring_samples": None,
                "model_promotion_allowed": False}
    expected["content_hash"] = _hash(expected)
    if _encoded(proof) != _encoded(expected) or proof["content_hash"] != receipt["content_hash"]:
        raise ValueError("feature corpus coverage differs from complete page set")
    reader.recheck()
    final.recheck()


def reconcile_racing_feature_corpus(*, payload, runtime, workspace, inventory_sha256,
                                    prediction_coverage_sha256, feature_coverage_sha256,
                                    checkpoint=lambda: None):
    """Read-only complete source reconstruction; operational use needs supervision.

    No missing page is created, no old outcome is changed, and no retry or model
    authority is granted. All three byte witnesses are required, not inferred.
    """
    domain, root, end = _corpus_scope(payload)
    if domain not in (Domain.AU, Domain.HKJC):
        raise ValueError("native racing domain required")
    workspace = _safe(Path(workspace))
    if not workspace.is_relative_to(_safe(runtime.warm_root)) or not workspace.is_dir():
        raise ValueError("prior feature corpus must be existing WARM input")
    for digest in (inventory_sha256, prediction_coverage_sha256, feature_coverage_sha256):
        if not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest):
            raise ValueError("prior feature corpus byte witnesses required")
    reader = _Reader(checkpoint, max_record_bytes=MAX_INVENTORY_BYTES)
    inventory, digest = reader.read(workspace / "prediction-inventory.json")
    if digest != inventory_sha256:
        raise ValueError("prior feature inventory byte digest mismatch")
    prediction_reader = _Reader(checkpoint, max_record_bytes=131072)
    _, prediction_digest = prediction_reader.read(workspace / "prediction-coverage.json")
    if prediction_digest != prediction_coverage_sha256:
        raise ValueError("prior prediction coverage byte digest mismatch")
    bounded = _Reader(checkpoint, max_record_bytes=131072, max_total_bytes=262144)
    proof, digest = bounded.read(workspace / "racing-feature-coverage.json")
    if digest != feature_coverage_sha256:
        raise ValueError("prior feature coverage byte digest mismatch")
    plans = plan_prediction_pages(inventory, max_refs=payload["max_refs"], max_records=payload["max_records"])
    for page in plans:
        prediction_reader.read(workspace / f"prediction-page-{page['content_hash']}.json")
    reconcile_prediction_corpus(payload=payload, runtime=runtime, workspace=workspace,
                                inventory_sha256=inventory_sha256,
                                coverage_sha256=prediction_coverage_sha256, checkpoint=checkpoint)
    page_reader = _Reader(checkpoint, max_record_bytes=262144)
    reports = []
    for page in plans:
        report, _ = page_reader.read(workspace / f"racing-feature-page-{page['content_hash']}.json")
        reports.append(report)
    actual = aggregate_racing_feature_pages(
        results=reports, inventory=inventory, root=root, domain=domain, as_of=end,
        relocation_roots=tuple(Path(p) for p in payload["relocation_roots"]),
        max_refs=payload["max_refs"], max_records=payload["max_records"], checkpoint=checkpoint,
    )
    if _encoded(proof) != _encoded(actual):
        raise ValueError("prior feature coverage differs from complete current source")
    reader.recheck()
    bounded.recheck()
    page_reader.recheck()
    prediction_reader.recheck()
    checkpoint()
    return {"status": "verified_existing_feature_corpus", "content_hash": actual["content_hash"],
            "retry_allowed": False, "model_promotion_allowed": False}


_RECONCILIATION_WITNESSES = {
    "inventory_sha256": "prediction-inventory.json",
    "prediction_coverage_sha256": "prediction-coverage.json",
    "feature_coverage_sha256": "racing-feature-coverage.json",
}


def _feature_reconciliation_scope(payload):
    extra = {"prior_workspace", *_RECONCILIATION_WITNESSES}
    base = {key: value for key, value in payload.items() if key not in extra}
    domain, _, _ = _corpus_scope(base)
    if set(payload) != set(base) | extra or domain not in (Domain.AU, Domain.HKJC):
        raise ValueError("invalid native feature reconciliation scope")
    return base


class RacingFeatureCorpusReconciliationRunner:
    def __init__(self, runtime, registry):
        self.runtime, self.registry = runtime, registry

    def run(self, *, domain, evidence_root, as_of, prior_workspace, inventory_sha256,
            prediction_coverage_sha256, feature_coverage_sha256, estimated_bytes,
            timeout_seconds, relocation_roots=(), max_refs=MAX_ARTIFACTS, max_records=MAX_PAGE_RECORDS):
        from .research_supervision import _phase, SourceInspectionResult
        if not isinstance(domain, Domain) or domain not in (Domain.AU, Domain.HKJC) or not isinstance(relocation_roots, tuple):
            raise ValueError("native racing domain and tuple relocation roots required")
        payload = {"domain": domain.value, "evidence_root": str(Path(evidence_root).absolute()),
                   "as_of": _at(as_of).isoformat(), "relocation_roots": [str(Path(p).absolute()) for p in relocation_roots],
                   "max_refs": max_refs, "max_records": max_records,
                   "prior_workspace": str(Path(prior_workspace).absolute()),
                   "inventory_sha256": inventory_sha256, "prediction_coverage_sha256": prediction_coverage_sha256,
                   "feature_coverage_sha256": feature_coverage_sha256}
        disposition, status, attempt, receipt = _phase(
            self.runtime, self.registry, None, action="racing-feature-corpus-reconcile", payload=payload,
            estimated_bytes=estimated_bytes, timeout_seconds=timeout_seconds,
        )
        valid = receipt if disposition is ResearchDisposition.SUCCEEDED else {}
        return SourceInspectionResult(disposition, status, attempt,
                                      Path(valid["report_path"]) if valid.get("report_path") else None,
                                      valid.get("content_hash"))


def run_racing_feature_corpus_reconciliation_request(request, *, runtime, workspace, checkpoint):
    payload = request["payload"]
    base = _feature_reconciliation_scope(payload)
    prior = _safe(Path(payload["prior_workspace"]))
    witnesses = {key: payload[key] for key in _RECONCILIATION_WITNESSES}
    reconcile_racing_feature_corpus(payload=base, runtime=runtime, workspace=prior,
                                    checkpoint=checkpoint, **witnesses)
    reader = _Reader(checkpoint, max_record_bytes=MAX_INVENTORY_BYTES)
    inventory, digest = reader.read(prior / "prediction-inventory.json")
    if digest != witnesses["inventory_sha256"]:
        raise ValueError("prior feature inventory changed before copy")
    plans = plan_prediction_pages(inventory, max_refs=base["max_refs"], max_records=base["max_records"])
    files = ["prediction-inventory.json", "prediction-coverage.json", "racing-feature-coverage.json"]
    files.extend(f"{prefix}-{p['content_hash']}.json" for p in plans
                 for prefix in ("prediction-page", "racing-feature-page"))
    for name in files:
        value, digest = reader.read(prior / name)
        for key, pinned in _RECONCILIATION_WITNESSES.items():
            if name == pinned and digest != witnesses[key]:
                raise ValueError("prior feature corpus bytes changed during copy")
        _write_report(workspace / name, value, resource_checkpoint=checkpoint, create_parents=False)
    reader.recheck()
    verified = reconcile_racing_feature_corpus(payload=base, runtime=runtime, workspace=workspace,
                                               checkpoint=checkpoint, **witnesses)
    return {"disposition": "succeeded", "status": "racing_feature_corpus_reconciled_inventory_only",
            "report_path": str(workspace / "racing-feature-coverage.json"), "content_hash": verified["content_hash"],
            "normalized_source_verified": False, "verified_monitoring_samples": None,
            "model_promotion_allowed": False}


def verify_racing_feature_corpus_reconciliation_receipt(*, payload, runtime, report_path, receipt):
    base = _feature_reconciliation_scope(payload)
    reader = _Reader(lambda: None, max_record_bytes=MAX_INVENTORY_BYTES)
    for key, name in _RECONCILIATION_WITNESSES.items():
        _, digest = reader.read(report_path.parent / name)
        if digest != payload[key]:
            raise ValueError("feature reconciliation output differs from pinned prior bytes")
    verify_racing_feature_corpus_receipt(payload=base, runtime=runtime,
                                         report_path=report_path, receipt=receipt)
    reader.recheck()
