"""Supervised native racing label pages; never qualified sample authority."""
import json
import re
from pathlib import Path

from .contracts import Domain
from .research_evaluation import _write_report
from .research_index import _Reader, _at, _encoded, _hash, _hashed, _safe
from .research_prediction_artifacts import MAX_ARTIFACTS
from .research_prediction_page_runtime import (
    _corpus_scope, _inputs, reconcile_prediction_corpus, run_prediction_corpus_request,
    verify_prediction_corpus_receipt, verify_prediction_page_receipt,
)
from .research_prediction_pages import MAX_INVENTORY_BYTES, MAX_PAGE_RECORDS, inspect_prediction_page, plan_prediction_pages
from .research_racing_settlement_inventory import (
    run_racing_settlement_inventory_request, verify_racing_settlement_inventory, verify_racing_settlement_inventory_receipt,
)
from .research_racing_settlement_pages import (
    COUNTS, COVERAGE_SCHEMA, SCHEMA, _selected_labels, aggregate_racing_settlement_pages, inspect_racing_settlement_page,
)
from .research_runner import ResearchDisposition


def _label_inputs(payload, runtime, checkpoint=lambda: None):
    base = {k: v for k, v in payload.items() if k not in {"settlement_inventory_path", "settlement_inventory_sha256"}}
    inventory, page, domain, root, end = _inputs(base, runtime, checkpoint)
    if domain not in (Domain.AU, Domain.HKJC):
        raise ValueError("native racing domain required")
    path = _safe(Path(payload["settlement_inventory_path"]))
    witness = payload["settlement_inventory_sha256"]
    if (not path.is_relative_to(_safe(runtime.warm_root)) or not isinstance(witness, str)
            or not re.fullmatch("[0-9a-f]{64}", witness)):
        raise ValueError("pinned WARM settlement inventory required")
    reader = _Reader(checkpoint, max_records=1, max_record_bytes=MAX_INVENTORY_BYTES,
                     max_total_bytes=MAX_INVENTORY_BYTES * 2)
    settlement, digest = reader.read(path)
    if digest != witness:
        raise ValueError("settlement inventory byte digest mismatch")
    verify_racing_settlement_inventory_receipt(
        payload={"domain": domain.value, "evidence_root": str(root), "as_of": end.isoformat()},
        runtime=runtime, report_path=path, receipt={"content_hash": settlement["content_hash"]})
    reader.recheck()
    return base, inventory, page, domain, root, end, settlement


class RacingSettlementCorpusInspectionRunner:
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
            self.runtime, self.registry, None, action="racing-settlement-corpus", payload=payload,
            estimated_bytes=estimated_bytes, timeout_seconds=timeout_seconds,
        )
        valid = receipt if disposition is ResearchDisposition.SUCCEEDED else {}
        return SourceInspectionResult(disposition, status, attempt,
                                      Path(valid["report_path"]) if valid.get("report_path") else None,
                                      valid.get("content_hash"))


def run_racing_settlement_corpus_request(request, *, runtime, workspace, checkpoint):
    payload = request["payload"]
    domain, root, end = _corpus_scope(payload)
    if domain not in (Domain.AU, Domain.HKJC):
        raise ValueError("native racing domain required")
    run_racing_settlement_inventory_request(
        {"payload": {"domain": domain.value, "evidence_root": str(root), "as_of": end.isoformat()}},
        runtime=runtime, workspace=workspace, checkpoint=checkpoint)
    run_prediction_corpus_request(request, runtime=runtime, workspace=workspace, checkpoint=checkpoint)
    reader = _Reader(checkpoint, max_record_bytes=MAX_INVENTORY_BYTES)
    inventory, prediction_digest = reader.read(workspace / "prediction-inventory.json")
    settlement, settlement_digest = reader.read(workspace / "settlement-inventory.json")
    plans = plan_prediction_pages(inventory, max_refs=payload["max_refs"], max_records=payload["max_records"])
    results = []
    for page in plans:
        checkpoint()
        page_payload = {**payload, "inventory_path": str(workspace / "prediction-inventory.json"),
                        "inventory_sha256": prediction_digest, "page_index": page["page_index"],
                        "settlement_inventory_path": str(workspace / "settlement-inventory.json"),
                        "settlement_inventory_sha256": settlement_digest}
        output = run_racing_settlement_page_request({"payload": page_payload}, runtime=runtime,
                                                    workspace=workspace, checkpoint=checkpoint)
        bounded = _Reader(checkpoint, max_record_bytes=262144, max_total_bytes=524288)
        value, _ = bounded.read(Path(output["report_path"]))
        bounded.recheck()
        results.append(value)
    common = dict(results=results, inventory=inventory, settlement_inventory=settlement,
                  root=root, domain=domain, as_of=end, relocation_roots=tuple(Path(p) for p in payload["relocation_roots"]),
                  max_refs=payload["max_refs"], max_records=payload["max_records"], checkpoint=checkpoint)
    proof = aggregate_racing_settlement_pages(**common)
    path = workspace / "racing-settlement-coverage.json"
    if len((json.dumps(proof, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()) > 131072:
        raise ValueError("persisted label coverage exceeds read bound")
    _write_report(path, proof, resource_checkpoint=checkpoint, create_parents=False)
    if _encoded(aggregate_racing_settlement_pages(**common)) != _encoded(proof):
        raise ValueError("label corpus source changed during final publication")
    reader.recheck()
    checkpoint()
    return {"disposition": "succeeded", "status": "racing_settlement_corpus_inventory_only",
            "report_path": str(path), "content_hash": proof["content_hash"],
            "normalized_source_verified": False, "verified_monitoring_samples": None,
            "model_promotion_allowed": False}


def verify_racing_settlement_corpus_receipt(*, payload, runtime, report_path, receipt):
    """Complete bounded page-set checks; fresh source reconstruction stays in child."""
    domain, root, end = _corpus_scope(payload)
    report_path = _safe(Path(report_path))
    if (domain not in (Domain.AU, Domain.HKJC) or report_path.name != "racing-settlement-coverage.json"
            or not report_path.is_relative_to(_safe(runtime.warm_root))):
        raise ValueError("invalid label corpus output scope")
    workspace = report_path.parent
    reader = _Reader(lambda: None, max_record_bytes=MAX_INVENTORY_BYTES)
    inventory, prediction_digest = reader.read(workspace / "prediction-inventory.json")
    settlement, settlement_digest = reader.read(workspace / "settlement-inventory.json")
    prediction, _ = reader.read(workspace / "prediction-coverage.json")
    verify_prediction_corpus_receipt(payload=payload, runtime=runtime,
                                     report_path=workspace / "prediction-coverage.json",
                                     receipt={"content_hash": prediction["content_hash"]})
    verify_racing_settlement_inventory_receipt(
        payload={"domain": domain.value, "evidence_root": str(root), "as_of": end.isoformat()},
        runtime=runtime, report_path=workspace / "settlement-inventory.json", receipt={"content_hash": settlement["content_hash"]})
    plans = plan_prediction_pages(inventory, max_refs=payload["max_refs"], max_records=payload["max_records"])
    reports, candidates, hashes = [], [], []
    pages_reader = _Reader(lambda: None, max_record_bytes=262144)
    for page in plans:
        path = workspace / f"racing-settlement-page-{page['content_hash']}.json"
        report, _ = pages_reader.read(path)
        page_payload = {**payload, "inventory_path": str(workspace / "prediction-inventory.json"),
                        "inventory_sha256": prediction_digest, "page_index": page["page_index"],
                        "settlement_inventory_path": str(workspace / "settlement-inventory.json"),
                        "settlement_inventory_sha256": settlement_digest}
        verify_racing_settlement_page_receipt(payload=page_payload, runtime=runtime, report_path=path,
                                              receipt={"content_hash": report["content_hash"]})
        reports.append(report)
        candidates.extend(report["settlement_report"]["candidates"])
        hashes.append(report["content_hash"])
    if sorted(c["settlement_id"] for c in candidates) != [r["settlement_id"] for r in settlement["settlements"]
                                                          if r["settlement_state"] in {"settled", "hit", "miss"}]:
        raise ValueError("label corpus missing or duplicating settlements")
    expected = {"schema_version": COVERAGE_SCHEMA, "domain": domain.value,
                "inventory_hash": inventory["content_hash"], "settlement_inventory_hash": settlement["content_hash"],
                "page_hashes": hashes, "page_coverage_complete": True,
                **{key: sum(r["settlement_report"][key] for r in reports) for key in COUNTS},
                "label_source_verified": bool(candidates) and all(c["label_source_verified"] for c in candidates),
                "feature_availability_verified": False, "source_coverage_complete": False,
                "verified_monitoring_samples": None, "model_promotion_allowed": False}
    expected["content_hash"] = _hash(expected)
    final = _Reader(lambda: None, max_record_bytes=131072, max_total_bytes=262144)
    proof, _ = final.read(report_path)
    _hashed(proof, COVERAGE_SCHEMA)
    if _encoded(proof) != _encoded(expected) or proof["content_hash"] != receipt["content_hash"]:
        raise ValueError("label coverage differs from complete bounded page set")
    reader.recheck()
    pages_reader.recheck()
    final.recheck()


class RacingSettlementPageInspectionRunner:
    def __init__(self, runtime, registry):
        self.runtime, self.registry = runtime, registry

    def run(self, *, domain, evidence_root, as_of, inventory_path, inventory_sha256,
            settlement_inventory_path, settlement_inventory_sha256, page_index,
            estimated_bytes, timeout_seconds, relocation_roots=(),
            max_refs=MAX_ARTIFACTS, max_records=MAX_PAGE_RECORDS):
        from .research_supervision import _phase, SourceInspectionResult
        if not isinstance(domain, Domain) or domain not in (Domain.AU, Domain.HKJC) or not isinstance(relocation_roots, tuple):
            raise ValueError("native racing domain and tuple relocation roots required")
        payload = {"domain": domain.value, "evidence_root": str(Path(evidence_root).absolute()),
                   "as_of": _at(as_of).isoformat(), "inventory_path": str(Path(inventory_path).absolute()),
                   "inventory_sha256": inventory_sha256, "page_index": page_index,
                   "settlement_inventory_path": str(Path(settlement_inventory_path).absolute()),
                   "settlement_inventory_sha256": settlement_inventory_sha256,
                   "relocation_roots": [str(Path(p).absolute()) for p in relocation_roots],
                   "max_refs": max_refs, "max_records": max_records}
        disposition, status, attempt, receipt = _phase(
            self.runtime, self.registry, None, action="racing-settlement-page", payload=payload,
            estimated_bytes=estimated_bytes, timeout_seconds=timeout_seconds,
        )
        valid = receipt if disposition is ResearchDisposition.SUCCEEDED else {}
        return SourceInspectionResult(disposition, status, attempt,
                                      Path(valid["report_path"]) if valid.get("report_path") else None,
                                      valid.get("content_hash"))


def run_racing_settlement_page_request(request, *, runtime, workspace, checkpoint, evidence_snapshot=None):
    payload = request["payload"]
    _, inventory, page, domain, root, end, settlement = _label_inputs(payload, runtime, checkpoint)
    options = dict(inventory=inventory, page=page, domain=domain, root=root, as_of=end,
                   relocation_roots=tuple(Path(p) for p in payload["relocation_roots"]),
                   max_refs=payload["max_refs"], max_records=payload["max_records"], checkpoint=checkpoint)
    prediction = inspect_prediction_page(**options)
    label = inspect_racing_settlement_page(settlement_inventory=settlement,
                                          evidence_snapshot=evidence_snapshot, **options)
    if label["prediction_page_hash"] != prediction["content_hash"]:
        raise ValueError("label page differs from companion prediction proof")
    outputs = ((f"prediction-page-{page['content_hash']}.json", prediction, 131072),
               (f"racing-settlement-page-{page['content_hash']}.json", label, 262144))
    for name, value, limit in outputs:
        if len((json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()) > limit:
            raise ValueError("persisted label/prediction page exceeds read bound")
        _write_report(workspace / name, value, resource_checkpoint=checkpoint, create_parents=False)
    after = inspect_racing_settlement_page(settlement_inventory=settlement,
                                          evidence_snapshot=evidence_snapshot, **options)
    if _encoded(after) != _encoded(label):
        raise ValueError("label source changed during publication")
    _label_inputs(payload, runtime, checkpoint)
    checkpoint()
    return {"disposition": "succeeded", "status": "racing_settlement_page_inventory_only",
            "report_path": str(workspace / outputs[1][0]), "content_hash": label["content_hash"],
            "normalized_source_verified": False, "verified_monitoring_samples": None,
            "model_promotion_allowed": False}


def verify_racing_settlement_page_receipt(*, payload, runtime, report_path, receipt):
    """Bounded parent metadata checks, not fresh source/blob reconstruction."""
    base, inventory, page, domain, root, end, settlement = _label_inputs(payload, runtime)
    if report_path.name != f"racing-settlement-page-{page['content_hash']}.json":
        raise ValueError("label output identity mismatch")
    reader = _Reader(lambda: None, max_record_bytes=262144, max_total_bytes=1048576)
    report, _ = reader.read(report_path)
    _hashed(report, SCHEMA)
    expected = {"schema_version", "domain", "inventory_hash", "settlement_inventory_hash", "page_plan_hash",
                "prediction_page_hash", "settlement_report", "source_coverage_complete",
                "verified_monitoring_samples", "model_promotion_allowed", "content_hash"}
    if (set(report) != expected or report["domain"] != domain.value
            or report["inventory_hash"] != inventory["content_hash"]
            or report["settlement_inventory_hash"] != settlement["content_hash"]
            or report["page_plan_hash"] != page["content_hash"] or report["content_hash"] != receipt["content_hash"]
            or report["source_coverage_complete"] is not False or report["verified_monitoring_samples"] is not None
            or report["model_promotion_allowed"] is not False):
        raise ValueError("label page identity or authority mismatch")
    path = report_path.parent / f"prediction-page-{page['content_hash']}.json"
    verify_prediction_page_receipt(payload=base, runtime=runtime, report_path=path,
                                   receipt={"content_hash": report["prediction_page_hash"]})
    if domain is Domain.AU:
        from .research_au_settlement_source import verify_au_settlement_candidate_report as native
    else:
        from .research_hkjc_settlement_source import verify_hkjc_settlement_candidate_report as native
    label = report["settlement_report"]
    native(label, root=root, as_of=end, relocation_roots=tuple(Path(p) for p in payload["relocation_roots"]))
    selected = _selected_labels(settlement, set(page["record_ids"]))
    if (label["prediction_report_hash"] != report["prediction_page_hash"]
            or [r["settlement_id"] for r in label["candidates"]] != [r["settlement_id"] for r in selected]):
        raise ValueError("label page coverage differs from frozen parent links")
    for candidate, metadata in zip(label["candidates"], selected):
        if any(candidate[k] != metadata[k] for k in ("settlement_id", "decision_id", "prediction_id", "event_id", "created_at")):
            raise ValueError("label record differs from frozen metadata")
    reader.recheck()


_LABEL_WITNESSES = {
    "inventory_sha256": "prediction-inventory.json",
    "prediction_coverage_sha256": "prediction-coverage.json",
    "settlement_inventory_sha256": "settlement-inventory.json",
    "label_coverage_sha256": "racing-settlement-coverage.json",
}


def _read_label_corpus_outputs(base, workspace, witnesses, checkpoint):
    metadata = _Reader(checkpoint, max_record_bytes=MAX_INVENTORY_BYTES)
    coverage = _Reader(checkpoint, max_record_bytes=131072)
    pages = _Reader(checkpoint, max_record_bytes=262144)
    values = {}
    for key, name in _LABEL_WITNESSES.items():
        witness = witnesses[key]
        if not isinstance(witness, str) or not re.fullmatch("[0-9a-f]{64}", witness):
            raise ValueError("explicit prior label corpus byte witnesses required")
        reader = metadata if name.endswith("inventory.json") else coverage
        value, digest = reader.read(workspace / name)
        if digest != witness:
            raise ValueError("prior label corpus byte witness mismatch")
        values[name] = value
    plans = plan_prediction_pages(values["prediction-inventory.json"], max_refs=base["max_refs"], max_records=base["max_records"])
    for page in plans:
        for prefix, limit in (("prediction-page", 131072), ("racing-settlement-page", 262144)):
            name = f"{prefix}-{page['content_hash']}.json"
            path = _safe(workspace / name)
            if path.stat().st_size > limit:
                raise ValueError("oversized prior label/prediction page")
            values[name], _ = pages.read(path)
    return values, plans, (metadata, coverage, pages)


def reconcile_racing_settlement_corpus(*, payload, runtime, workspace, inventory_sha256,
                                       prediction_coverage_sha256, settlement_inventory_sha256,
                                       label_coverage_sha256, checkpoint=lambda: None):
    """Read-only complete source reconstruction, never repair or retry authority.

    Operational calls require the existing supervisor/heavy lock/WARM guard.
    Pins every existing proof before source reads and rechecks all before return.
    """
    domain, root, end = _corpus_scope(payload)
    workspace = _safe(Path(workspace))
    if (domain not in (Domain.AU, Domain.HKJC) or not workspace.is_dir()
            or not workspace.is_relative_to(_safe(runtime.warm_root))):
        raise ValueError("prior native label corpus must be existing WARM input")
    witnesses = dict(inventory_sha256=inventory_sha256, prediction_coverage_sha256=prediction_coverage_sha256,
                     settlement_inventory_sha256=settlement_inventory_sha256, label_coverage_sha256=label_coverage_sha256)
    values, plans, readers = _read_label_corpus_outputs(payload, workspace, witnesses, checkpoint)
    reconcile_prediction_corpus(payload=payload, runtime=runtime, workspace=workspace,
                                inventory_sha256=inventory_sha256, coverage_sha256=prediction_coverage_sha256,
                                checkpoint=checkpoint)
    settlement = values["settlement-inventory.json"]
    verify_racing_settlement_inventory(settlement, root=root, domain=domain, as_of=end, checkpoint=checkpoint)
    actual = aggregate_racing_settlement_pages(
        results=[values[f"racing-settlement-page-{p['content_hash']}.json"] for p in plans],
        inventory=values["prediction-inventory.json"], settlement_inventory=settlement,
        root=root, domain=domain, as_of=end, relocation_roots=tuple(Path(p) for p in payload["relocation_roots"]),
        max_refs=payload["max_refs"], max_records=payload["max_records"], checkpoint=checkpoint)
    if _encoded(actual) != _encoded(values["racing-settlement-coverage.json"]):
        raise ValueError("prior label coverage differs from complete current source")
    for reader in readers:
        reader.recheck()
    checkpoint()
    return {"status": "verified_existing_label_corpus", "content_hash": actual["content_hash"],
            "retry_allowed": False, "model_promotion_allowed": False}


def _label_reconciliation_scope(payload):
    extra = {"prior_workspace", *_LABEL_WITNESSES}
    base = {key: value for key, value in payload.items() if key not in extra}
    domain, _, _ = _corpus_scope(base)
    if set(payload) != set(base) | extra or domain not in (Domain.AU, Domain.HKJC):
        raise ValueError("invalid label reconciliation scope")
    return base


class RacingSettlementCorpusReconciliationRunner:
    def __init__(self, runtime, registry):
        self.runtime, self.registry = runtime, registry

    def run(self, *, domain, evidence_root, as_of, prior_workspace, inventory_sha256,
            prediction_coverage_sha256, settlement_inventory_sha256, label_coverage_sha256,
            estimated_bytes, timeout_seconds, relocation_roots=(), max_refs=MAX_ARTIFACTS,
            max_records=MAX_PAGE_RECORDS):
        from .research_supervision import _phase, SourceInspectionResult
        if not isinstance(domain, Domain) or domain not in (Domain.AU, Domain.HKJC) or not isinstance(relocation_roots, tuple):
            raise ValueError("native racing domain and tuple relocation roots required")
        payload = {"domain": domain.value, "evidence_root": str(Path(evidence_root).absolute()),
                   "as_of": _at(as_of).isoformat(), "relocation_roots": [str(Path(p).absolute()) for p in relocation_roots],
                   "max_refs": max_refs, "max_records": max_records, "prior_workspace": str(Path(prior_workspace).absolute()),
                   "inventory_sha256": inventory_sha256, "prediction_coverage_sha256": prediction_coverage_sha256,
                   "settlement_inventory_sha256": settlement_inventory_sha256, "label_coverage_sha256": label_coverage_sha256}
        disposition, status, attempt, receipt = _phase(
            self.runtime, self.registry, None, action="racing-settlement-corpus-reconcile", payload=payload,
            estimated_bytes=estimated_bytes, timeout_seconds=timeout_seconds)
        valid = receipt if disposition is ResearchDisposition.SUCCEEDED else {}
        return SourceInspectionResult(disposition, status, attempt,
                                      Path(valid["report_path"]) if valid.get("report_path") else None,
                                      valid.get("content_hash"))


def run_racing_settlement_corpus_reconciliation_request(request, *, runtime, workspace, checkpoint):
    payload = request["payload"]
    base = _label_reconciliation_scope(payload)
    prior = _safe(Path(payload["prior_workspace"]))
    witnesses = {key: payload[key] for key in _LABEL_WITNESSES}
    reconcile_racing_settlement_corpus(payload=base, runtime=runtime, workspace=prior, checkpoint=checkpoint, **witnesses)
    values, _, readers = _read_label_corpus_outputs(base, prior, witnesses, checkpoint)
    for name, value in values.items():
        _write_report(workspace / name, value, resource_checkpoint=checkpoint, create_parents=False)
    for reader in readers:
        reader.recheck()
    proof = reconcile_racing_settlement_corpus(payload=base, runtime=runtime, workspace=workspace,
                                              checkpoint=checkpoint, **witnesses)
    return {"disposition": "succeeded", "status": "racing_settlement_corpus_reconciled_inventory_only",
            "report_path": str(workspace / "racing-settlement-coverage.json"), "content_hash": proof["content_hash"],
            "normalized_source_verified": False, "verified_monitoring_samples": None,
            "model_promotion_allowed": False}


def verify_racing_settlement_corpus_reconciliation_receipt(*, payload, runtime, report_path, receipt):
    base = _label_reconciliation_scope(payload)
    reader = _Reader(lambda: None, max_record_bytes=MAX_INVENTORY_BYTES)
    for key, name in _LABEL_WITNESSES.items():
        _, digest = reader.read(report_path.parent / name)
        if digest != payload[key]:
            raise ValueError("label reconciliation output differs from pinned prior bytes")
    verify_racing_settlement_corpus_receipt(payload=base, runtime=runtime, report_path=report_path, receipt=receipt)
    reader.recheck()
