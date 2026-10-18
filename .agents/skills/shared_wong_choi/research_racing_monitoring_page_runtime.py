"""Supervised bounded monitoring join: single pages grant no sample clock."""
import json
import re
from pathlib import Path

from .contracts import Domain
from .research_evaluation import _write_report
from .research_index import _Reader, _at, _encoded, _hashed, _safe
from .research_prediction_artifacts import MAX_ARTIFACTS
from .research_prediction_page_runtime import _corpus_scope, reconcile_prediction_corpus, run_prediction_corpus_request, verify_prediction_corpus_receipt
from .research_prediction_pages import MAX_INVENTORY_BYTES, MAX_PAGE_RECORDS, plan_prediction_pages
from .research_racing_feature_page_runtime import run_racing_feature_page_request, verify_racing_feature_page_receipt
from .research_racing_monitoring_pages import (
    COVERAGE_SCHEMA, SCHEMA, _coverage_projection, aggregate_racing_monitoring_pages, _inspect_racing_monitoring_page_once,
)
from .research_racing_monitoring_samples import BLOCKER_ORDER, _verify_shape
from .research_racing_settlement_page_runtime import (
    _label_inputs, run_racing_settlement_page_request, verify_racing_settlement_page_receipt,
)
from .research_runner import ResearchDisposition
from .research_racing_settlement_inventory import run_racing_settlement_inventory_request, verify_racing_settlement_inventory_receipt


class RacingMonitoringPageInspectionRunner:
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
            self.runtime, self.registry, None, action="racing-monitoring-page", payload=payload,
            estimated_bytes=estimated_bytes, timeout_seconds=timeout_seconds)
        valid = receipt if disposition is ResearchDisposition.SUCCEEDED else {}
        return SourceInspectionResult(disposition, status, attempt,
                                      Path(valid["report_path"]) if valid.get("report_path") else None,
                                      valid.get("content_hash"))


def run_racing_monitoring_page_request(request, *, runtime, workspace, checkpoint, evidence_snapshot=None):
    payload = request["payload"]
    base, inventory, page, domain, root, end, settlement = _label_inputs(payload, runtime, checkpoint)
    run_racing_settlement_page_request(request, runtime=runtime, workspace=workspace,
                                      checkpoint=checkpoint, evidence_snapshot=evidence_snapshot)
    run_racing_feature_page_request({"payload": base}, runtime=runtime, workspace=workspace, checkpoint=checkpoint)
    common = dict(inventory=inventory, settlement_inventory=settlement, page=page,
                  domain=domain, root=root, as_of=end,
                  relocation_roots=tuple(Path(p) for p in payload["relocation_roots"]),
                  max_refs=payload["max_refs"], max_records=payload["max_records"], checkpoint=checkpoint,
                  evidence_snapshot=evidence_snapshot)
    # The publication boundary retains two complete native rebuilds. Do not
    # nest the public inspector's two-pass pair inside each side of this pair.
    proof = _inspect_racing_monitoring_page_once(**common)
    reader = _Reader(checkpoint, max_record_bytes=262144)
    for prefix, key in (("prediction", "prediction_page_hash"),
                        ("racing-feature", "feature_page_hash"),
                        ("racing-settlement", "settlement_page_hash")):
        value, _ = reader.read(workspace / f"{prefix}-page-{page['content_hash']}.json")
        if value["content_hash"] != proof[key]:
            raise ValueError("monitoring page differs from published companion")
    path = workspace / f"racing-monitoring-page-{page['content_hash']}.json"
    if len((json.dumps(proof, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()) > 262144:
        raise ValueError("persisted monitoring page exceeds read bound")
    _write_report(path, proof, resource_checkpoint=checkpoint, create_parents=False)
    if _encoded(_inspect_racing_monitoring_page_once(**common)) != _encoded(proof):
        raise ValueError("monitoring source changed during publication")
    reader.recheck()
    _label_inputs(payload, runtime, checkpoint)
    checkpoint()
    return {"disposition": "succeeded", "status": "racing_monitoring_page_inventory_only",
            "report_path": str(path), "content_hash": proof["content_hash"],
            "normalized_source_verified": False, "verified_monitoring_samples": None,
            "model_promotion_allowed": False}


def verify_racing_monitoring_page_receipt(*, payload, runtime, report_path, receipt):
    """Bounded companion/identity checks; heavy source reconstruction stays in child."""
    base, inventory, page, domain, root, end, settlement = _label_inputs(payload, runtime)
    if report_path.name != f"racing-monitoring-page-{page['content_hash']}.json":
        raise ValueError("monitoring page output identity mismatch")
    reader = _Reader(lambda: None, max_record_bytes=262144)
    proof, _ = reader.read(report_path)
    _hashed(proof, SCHEMA)
    fields = {"schema_version", "domain", "inventory_hash", "settlement_inventory_hash",
              "page_plan_hash", "prediction_page_hash", "feature_page_hash", "settlement_page_hash",
              "monitoring_report", "source_coverage_complete", "verified_monitoring_samples",
              "model_promotion_allowed", "content_hash"}
    if (set(proof) != fields or proof["domain"] != domain.value
            or proof["inventory_hash"] != inventory["content_hash"]
            or proof["settlement_inventory_hash"] != settlement["content_hash"]
            or proof["page_plan_hash"] != page["content_hash"] or proof["content_hash"] != receipt["content_hash"]
            or proof["source_coverage_complete"] is not False
            or proof["verified_monitoring_samples"] is not None or proof["model_promotion_allowed"] is not False):
        raise ValueError("monitoring page scope or authority mismatch")
    feature_path = report_path.parent / f"racing-feature-page-{page['content_hash']}.json"
    label_path = report_path.parent / f"racing-settlement-page-{page['content_hash']}.json"
    verify_racing_feature_page_receipt(payload=base, runtime=runtime, report_path=feature_path,
                                       receipt={"content_hash": proof["feature_page_hash"]})
    verify_racing_settlement_page_receipt(payload=payload, runtime=runtime, report_path=label_path,
                                          receipt={"content_hash": proof["settlement_page_hash"]})
    feature, _ = reader.read(feature_path)
    label, _ = reader.read(label_path)
    monitoring = proof["monitoring_report"]
    _verify_shape(monitoring, root=root, domain=domain, as_of=end,
                  relocation_roots=tuple(Path(p) for p in payload["relocation_roots"]))
    if (feature["prediction_page_hash"] != proof["prediction_page_hash"]
            or label["prediction_page_hash"] != proof["prediction_page_hash"]
            or monitoring["prediction_report_hash"] != proof["prediction_page_hash"]
            or monitoring["feature_report_hash"] != feature["feature_report"]["content_hash"]
            or monitoring["settlement_report_hash"] != label["settlement_report"]["content_hash"]):
        raise ValueError("monitoring native companion hash mismatch")
    features = {item["record_id"]: item for item in feature["feature_report"]["records"]}
    labels = label["settlement_report"]["candidates"]
    if [item["settlement_id"] for item in monitoring["candidates"]] != [item["settlement_id"] for item in labels]:
        raise ValueError("monitoring settlement coverage mismatch")
    expected_units, blocked = [], 0
    for candidate, native in zip(monitoring["candidates"], labels):
        f = features.get(native["prediction_id"])
        flags = {"prediction_bundle_unverified": not native["prediction_bundle_verified"],
                 "label_source_unverified": not native["label_source_verified"],
                 "feature_record_missing": f is None,
                 "feature_availability_unverified": f is not None and not f["feature_availability_verified"]}
        blockers = [key for key in BLOCKER_ORDER if flags[key]]
        if (candidate["blockers"] != blockers or any(candidate[key] != native[key]
                for key in ("settlement_id", "prediction_id", "event_id"))):
            raise ValueError("monitoring eligibility or parent identity mismatch")
        blocked += bool(blockers)
        if not blockers:
            if len(candidate["race_numbers"]) != native["parsed_result_races"]:
                raise ValueError("monitoring race coverage differs from verified label")
            for number in candidate["race_numbers"]:
                expected_units.append({"unit_id": f"{native['prediction_id']}:race:{number}",
                                       "prediction_id": native["prediction_id"], "settlement_id": native["settlement_id"],
                                       "event_id": native["event_id"], "race_number": number,
                                       "settled_at": _at(native["created_at"]).isoformat(),
                                       "result_artifact_sha256": candidate["result_artifact_sha256"]})
    if (monitoring["units"] != sorted(expected_units, key=lambda item: item["unit_id"])
            or monitoring["blocked_settlements"] != blocked
            or monitoring["qualified_settlements"] != len(labels) - blocked):
        raise ValueError("monitoring units differ from verified parent identities")
    reader.recheck()


class RacingMonitoringCorpusInspectionRunner:
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
            self.runtime, self.registry, None, action="racing-monitoring-corpus", payload=payload,
            estimated_bytes=estimated_bytes, timeout_seconds=timeout_seconds)
        valid = receipt if disposition is ResearchDisposition.SUCCEEDED else {}
        return SourceInspectionResult(disposition, status, attempt,
                                      Path(valid["report_path"]) if valid.get("report_path") else None,
                                      valid.get("content_hash"))


def run_racing_monitoring_corpus_request(request, *, runtime, workspace, checkpoint):
    payload = request["payload"]
    domain, root, end = _corpus_scope(payload)
    if domain not in (Domain.AU, Domain.HKJC):
        raise ValueError("native racing domain required")
    from .research_native_evidence_snapshot import _NativeEvidenceSnapshot
    snapshot = _NativeEvidenceSnapshot(root=root, domain=domain, as_of=end, checkpoint=checkpoint)
    run_racing_settlement_inventory_request(
        {"payload": {"domain": domain.value, "evidence_root": str(root), "as_of": end.isoformat()}},
        runtime=runtime, workspace=workspace, checkpoint=checkpoint)
    run_prediction_corpus_request(request, runtime=runtime, workspace=workspace, checkpoint=checkpoint)
    reader = _Reader(checkpoint, max_record_bytes=MAX_INVENTORY_BYTES)
    inventory, prediction_digest = reader.read(workspace / "prediction-inventory.json")
    settlement, settlement_digest = reader.read(workspace / "settlement-inventory.json")
    plans = plan_prediction_pages(inventory, max_refs=payload["max_refs"], max_records=payload["max_records"])
    pages_reader = _Reader(checkpoint, max_record_bytes=262144)
    results = []
    for page in plans:
        checkpoint()
        page_payload = {**payload, "inventory_path": str(workspace / "prediction-inventory.json"),
                        "inventory_sha256": prediction_digest, "page_index": page["page_index"],
                        "settlement_inventory_path": str(workspace / "settlement-inventory.json"),
                        "settlement_inventory_sha256": settlement_digest}
        output = run_racing_monitoring_page_request({"payload": page_payload}, runtime=runtime,
                                                    workspace=workspace, checkpoint=checkpoint,
                                                    evidence_snapshot=snapshot)
        value, _ = pages_reader.read(Path(output["report_path"]))
        results.append(value)
    common = dict(results=results, inventory=inventory, settlement_inventory=settlement,
                  root=root, domain=domain, as_of=end, relocation_roots=tuple(Path(p) for p in payload["relocation_roots"]),
                  max_refs=payload["max_refs"], max_records=payload["max_records"], checkpoint=checkpoint,
                  evidence_snapshot=snapshot)
    proof = aggregate_racing_monitoring_pages(**common)
    path = workspace / "racing-monitoring-coverage.json"
    if len((json.dumps(proof, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()) > 1048576:
        raise ValueError("persisted monitoring coverage exceeds read bound")
    _write_report(path, proof, resource_checkpoint=checkpoint, create_parents=False)
    if _encoded(aggregate_racing_monitoring_pages(**common)) != _encoded(proof):
        raise ValueError("monitoring corpus source changed during final publication")
    reader.recheck()
    pages_reader.recheck()
    checkpoint()
    return {"disposition": "succeeded", "status": "racing_monitoring_corpus_sample_projection",
            "report_path": str(path), "content_hash": proof["content_hash"],
            "verified_monitoring_samples": proof["verified_monitoring_samples"], "terminal_labels_emitted": False,
            "model_promotion_allowed": False, "reevaluate_promotion_allowed": False}


def verify_racing_monitoring_corpus_receipt(*, payload, runtime, report_path, receipt):
    """Verify complete bounded companions; native source replay stays in child."""
    domain, root, end = _corpus_scope(payload)
    path = _safe(Path(report_path))
    if (domain not in (Domain.AU, Domain.HKJC) or path.name != "racing-monitoring-coverage.json"
            or not path.is_relative_to(_safe(runtime.warm_root))):
        raise ValueError("monitoring corpus output scope mismatch")
    workspace = path.parent
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
    pages_reader = _Reader(lambda: None, max_record_bytes=262144)
    results = []
    for page in plans:
        page_path = workspace / f"racing-monitoring-page-{page['content_hash']}.json"
        value, _ = pages_reader.read(page_path)
        page_payload = {**payload, "inventory_path": str(workspace / "prediction-inventory.json"),
                        "inventory_sha256": prediction_digest, "page_index": page["page_index"],
                        "settlement_inventory_path": str(workspace / "settlement-inventory.json"),
                        "settlement_inventory_sha256": settlement_digest}
        verify_racing_monitoring_page_receipt(payload=page_payload, runtime=runtime,
                                              report_path=page_path, receipt={"content_hash": value["content_hash"]})
        results.append(value)
    expected = _coverage_projection(
        results=results, inventory=inventory, settlement_inventory=settlement, root=root, domain=domain,
        as_of=end, relocation_roots=tuple(Path(p) for p in payload["relocation_roots"]),
        max_refs=payload["max_refs"], max_records=payload["max_records"])
    final = _Reader(lambda: None, max_record_bytes=1048576)
    proof, _ = final.read(path)
    _hashed(proof, COVERAGE_SCHEMA)
    if _encoded(proof) != _encoded(expected) or proof["content_hash"] != receipt["content_hash"]:
        raise ValueError("monitoring coverage differs from complete bounded pages")
    if "verified_monitoring_samples" in receipt and receipt["verified_monitoring_samples"] != proof["verified_monitoring_samples"]:
        raise ValueError("monitoring count differs from receipt")
    reader.recheck()
    pages_reader.recheck()
    final.recheck()


_MONITORING_WITNESSES = {
    "inventory_sha256": "prediction-inventory.json",
    "prediction_coverage_sha256": "prediction-coverage.json",
    "settlement_inventory_sha256": "settlement-inventory.json",
    "monitoring_coverage_sha256": "racing-monitoring-coverage.json",
}


def _read_monitoring_outputs(base, workspace, witnesses, checkpoint):
    metadata = _Reader(checkpoint, max_record_bytes=MAX_INVENTORY_BYTES)
    coverage = _Reader(checkpoint, max_record_bytes=1048576)
    pages = _Reader(checkpoint, max_record_bytes=262144)
    values = {}
    for key, name in _MONITORING_WITNESSES.items():
        witness = witnesses[key]
        if not isinstance(witness, str) or not re.fullmatch("[0-9a-f]{64}", witness):
            raise ValueError("explicit prior monitoring byte witnesses required")
        reader = metadata if name.endswith("inventory.json") else coverage
        value, digest = reader.read(workspace / name)
        if digest != witness:
            raise ValueError("prior monitoring byte witness mismatch")
        if name == "prediction-coverage.json" and (workspace / name).stat().st_size > 131072:
            raise ValueError("oversized prior prediction coverage")
        values[name] = value
    plans = plan_prediction_pages(values["prediction-inventory.json"], max_refs=base["max_refs"], max_records=base["max_records"])
    for page in plans:
        for prefix, limit in (("prediction", 131072), ("racing-feature", 262144),
                              ("racing-settlement", 262144), ("racing-monitoring", 262144)):
            name = f"{prefix}-page-{page['content_hash']}.json"
            path = _safe(workspace / name)
            if path.stat().st_size > limit:
                raise ValueError("oversized prior monitoring companion")
            values[name], _ = pages.read(path)
    return values, plans, (metadata, coverage, pages)


def reconcile_racing_monitoring_corpus(*, payload, runtime, workspace, inventory_sha256,
                                      prediction_coverage_sha256, settlement_inventory_sha256,
                                      monitoring_coverage_sha256, checkpoint=lambda: None):
    """Read-only all-source replay; never repair missing proofs or grant retry."""
    domain, root, end = _corpus_scope(payload)
    workspace = _safe(Path(workspace))
    if (domain not in (Domain.AU, Domain.HKJC) or not workspace.is_dir()
            or not workspace.is_relative_to(_safe(runtime.warm_root))):
        raise ValueError("prior monitoring corpus must be existing WARM input")
    witnesses = dict(inventory_sha256=inventory_sha256, prediction_coverage_sha256=prediction_coverage_sha256,
                     settlement_inventory_sha256=settlement_inventory_sha256, monitoring_coverage_sha256=monitoring_coverage_sha256)
    values, plans, readers = _read_monitoring_outputs(payload, workspace, witnesses, checkpoint)
    # All companion bytes are pinned BEFORE the first opaque-source replay.
    reconcile_prediction_corpus(payload=payload, runtime=runtime, workspace=workspace,
                                inventory_sha256=inventory_sha256, coverage_sha256=prediction_coverage_sha256,
                                checkpoint=checkpoint)
    from .research_native_evidence_snapshot import _NativeEvidenceSnapshot
    snapshot = _NativeEvidenceSnapshot(root=root, domain=domain, as_of=end, checkpoint=checkpoint)
    actual = aggregate_racing_monitoring_pages(
        results=[values[f"racing-monitoring-page-{page['content_hash']}.json"] for page in plans],
        inventory=values["prediction-inventory.json"], settlement_inventory=values["settlement-inventory.json"],
        root=root, domain=domain, as_of=end, relocation_roots=tuple(Path(p) for p in payload["relocation_roots"]),
        max_refs=payload["max_refs"], max_records=payload["max_records"], checkpoint=checkpoint,
        evidence_snapshot=snapshot)
    if _encoded(actual) != _encoded(values["racing-monitoring-coverage.json"]):
        raise ValueError("prior monitoring coverage differs from complete current source")
    verify_racing_monitoring_corpus_receipt(payload=payload, runtime=runtime,
                                           report_path=workspace / "racing-monitoring-coverage.json",
                                           receipt={"content_hash": actual["content_hash"]})
    for reader in readers:
        reader.recheck()
    checkpoint()
    return {"status": "verified_existing_monitoring_corpus", "content_hash": actual["content_hash"],
            "verified_monitoring_samples": actual["verified_monitoring_samples"],
            "retry_allowed": False, "model_promotion_allowed": False}


def _monitoring_reconciliation_scope(payload):
    extra = {"prior_workspace", *_MONITORING_WITNESSES}
    base = {key: value for key, value in payload.items() if key not in extra}
    domain, _, _ = _corpus_scope(base)
    if set(payload) != set(base) | extra or domain not in (Domain.AU, Domain.HKJC):
        raise ValueError("invalid monitoring reconciliation scope")
    return base


class RacingMonitoringCorpusReconciliationRunner:
    def __init__(self, runtime, registry):
        self.runtime, self.registry = runtime, registry

    def run(self, *, domain, evidence_root, as_of, prior_workspace, inventory_sha256,
            prediction_coverage_sha256, settlement_inventory_sha256, monitoring_coverage_sha256,
            estimated_bytes, timeout_seconds, relocation_roots=(), max_refs=MAX_ARTIFACTS,
            max_records=MAX_PAGE_RECORDS):
        from .research_supervision import _phase, SourceInspectionResult
        if not isinstance(domain, Domain) or domain not in (Domain.AU, Domain.HKJC) or not isinstance(relocation_roots, tuple):
            raise ValueError("native racing domain and tuple relocation roots required")
        payload = {"domain": domain.value, "evidence_root": str(Path(evidence_root).absolute()),
                   "as_of": _at(as_of).isoformat(), "relocation_roots": [str(Path(p).absolute()) for p in relocation_roots],
                   "max_refs": max_refs, "max_records": max_records, "prior_workspace": str(Path(prior_workspace).absolute()),
                   "inventory_sha256": inventory_sha256, "prediction_coverage_sha256": prediction_coverage_sha256,
                   "settlement_inventory_sha256": settlement_inventory_sha256, "monitoring_coverage_sha256": monitoring_coverage_sha256}
        disposition, status, attempt, receipt = _phase(
            self.runtime, self.registry, None, action="racing-monitoring-corpus-reconcile", payload=payload,
            estimated_bytes=estimated_bytes, timeout_seconds=timeout_seconds)
        valid = receipt if disposition is ResearchDisposition.SUCCEEDED else {}
        return SourceInspectionResult(disposition, status, attempt,
                                      Path(valid["report_path"]) if valid.get("report_path") else None,
                                      valid.get("content_hash"))


def run_racing_monitoring_corpus_reconciliation_request(request, *, runtime, workspace, checkpoint):
    payload = request["payload"]
    base = _monitoring_reconciliation_scope(payload)
    prior = _safe(Path(payload["prior_workspace"]))
    witnesses = {key: payload[key] for key in _MONITORING_WITNESSES}
    reconcile_racing_monitoring_corpus(payload=base, runtime=runtime, workspace=prior, checkpoint=checkpoint, **witnesses)
    values, _, readers = _read_monitoring_outputs(base, prior, witnesses, checkpoint)
    for name, value in values.items():
        _write_report(workspace / name, value, resource_checkpoint=checkpoint, create_parents=False)
    for reader in readers:
        reader.recheck()
    proof = reconcile_racing_monitoring_corpus(payload=base, runtime=runtime, workspace=workspace,
                                              checkpoint=checkpoint, **witnesses)
    for reader in readers:
        reader.recheck()
    checkpoint()
    return {"disposition": "succeeded", "status": "racing_monitoring_corpus_reconciled_sample_projection",
            "report_path": str(workspace / "racing-monitoring-coverage.json"), "content_hash": proof["content_hash"],
            "verified_monitoring_samples": proof["verified_monitoring_samples"], "terminal_labels_emitted": False,
            "model_promotion_allowed": False, "reevaluate_promotion_allowed": False}


def verify_racing_monitoring_corpus_reconciliation_receipt(*, payload, runtime, report_path, receipt):
    base = _monitoring_reconciliation_scope(payload)
    reader = _Reader(lambda: None, max_record_bytes=MAX_INVENTORY_BYTES)
    for key, name in _MONITORING_WITNESSES.items():
        _, digest = reader.read(report_path.parent / name)
        if digest != payload[key]:
            raise ValueError("monitoring reconciliation output differs from pinned prior bytes")
    verify_racing_monitoring_corpus_receipt(payload=base, runtime=runtime, report_path=report_path, receipt=receipt)
    reader.recheck()
