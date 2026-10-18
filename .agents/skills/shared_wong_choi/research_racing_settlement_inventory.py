"""Frozen racing label/parent metadata, not verified labels or sample authority.

Operational source I/O requires the existing supervisor/heavy lock/WARM guard.
AU/HKJC independently validate their canonical evidence and parent contracts.
Prediction inventory cannot substitute for this complete settlement inventory.
"""
from pathlib import Path
import json
import re

from .contracts import Domain
from .evidence import RecordKind
from .research_index import _Reader, _at, _encoded, _hash, _hashed, _safe
from .research_prediction_pages import MAX_INVENTORY_BYTES

SCHEMA = "wong-choi-racing-settlement-inventory/v1"


def freeze_racing_settlement_inventory(*, root, domain, as_of, checkpoint=lambda: None):
    if not isinstance(domain, Domain) or domain not in (Domain.AU, Domain.HKJC):
        raise ValueError("native racing domain required")
    root, end = _safe(Path(root)), _at(as_of)
    if not root.is_dir() or not (root / "records").is_dir():
        raise ValueError("canonical racing evidence root required")
    reader = _Reader(checkpoint)
    if domain is Domain.AU:
        from .research_au_settlement_source import _evidence
        records = {key: value[0] for key, value in _evidence(root, end, reader).items()}
    else:
        from .research_hkjc_settlement_source import _evidence
        records = _evidence(root, end, reader)
    settlements = []
    for value in sorted(records.values(), key=lambda v: v.record_id):
        checkpoint()
        if value.kind is not RecordKind.SETTLEMENT:
            continue
        decision = records[value.links["decision_id"]]
        prediction = records[decision.links["prediction_id"]]
        settlements.append({"settlement_id": value.record_id, "decision_id": decision.record_id,
                            "prediction_id": prediction.record_id, "event_id": value.body["event_id"],
                            "created_at": value.created_at, "settlement_state": value.body["settlement_state"]})
    reader.recheck()
    body = {"schema_version": SCHEMA, "domain": domain.value, "root": str(root), "as_of": end.isoformat(),
            "source_files": [{"path": str(path), "sha256": digest}
                             for path, digest in sorted(reader.files.items(), key=lambda v: str(v[0]))],
            "collections": [{"path": str(path), "names_hash": _hash(list(names))}
                            for path, names in sorted(reader.directories.items(), key=lambda v: str(v[0]))],
            "evidence_records_seen": len(records), "settlements": settlements,
            "label_source_verified": False, "source_coverage_complete": False,
            "verified_monitoring_samples": None, "model_promotion_allowed": False}
    report = {**body, "content_hash": _hash(body)}
    if len(_encoded(report)) > MAX_INVENTORY_BYTES:
        raise ValueError("settlement inventory exceeds compact read bound")
    return report


def verify_racing_settlement_inventory(report, *, root, domain, as_of, checkpoint=lambda: None):
    _hashed(report, SCHEMA)
    if len(_encoded(report)) > MAX_INVENTORY_BYTES:
        raise ValueError("oversized settlement inventory")
    actual = freeze_racing_settlement_inventory(root=root, domain=domain, as_of=as_of, checkpoint=checkpoint)
    if _encoded(report) != _encoded(actual):
        raise ValueError("settlement inventory differs from complete current metadata")
    return report


def _inventory_scope(payload):
    if set(payload) != {"domain", "evidence_root", "as_of"}:
        raise ValueError("invalid settlement inventory request scope")
    domain = Domain(payload["domain"])
    if domain not in (Domain.AU, Domain.HKJC):
        raise ValueError("native racing domain required")
    return domain, _safe(Path(payload["evidence_root"])), _at(payload["as_of"])


class RacingSettlementInventoryRunner:
    def __init__(self, runtime, registry):
        self.runtime, self.registry = runtime, registry

    def run(self, *, domain, evidence_root, as_of, estimated_bytes, timeout_seconds):
        from .research_supervision import _phase, SourceInspectionResult
        from .research_runner import ResearchDisposition
        if not isinstance(domain, Domain) or domain not in (Domain.AU, Domain.HKJC):
            raise ValueError("native racing domain required")
        payload = {"domain": domain.value, "evidence_root": str(Path(evidence_root).absolute()),
                   "as_of": _at(as_of).isoformat()}
        disposition, status, attempt, receipt = _phase(
            self.runtime, self.registry, None, action="racing-settlement-inventory", payload=payload,
            estimated_bytes=estimated_bytes, timeout_seconds=timeout_seconds,
        )
        valid = receipt if disposition is ResearchDisposition.SUCCEEDED else {}
        return SourceInspectionResult(disposition, status, attempt,
                                      Path(valid["report_path"]) if valid.get("report_path") else None,
                                      valid.get("content_hash"))


def run_racing_settlement_inventory_request(request, *, runtime, workspace, checkpoint):
    from .research_evaluation import _write_report
    domain, root, end = _inventory_scope(request["payload"])
    report = freeze_racing_settlement_inventory(root=root, domain=domain, as_of=end, checkpoint=checkpoint)
    if len((json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()) > MAX_INVENTORY_BYTES:
        raise ValueError("persisted settlement inventory exceeds read bound")
    path = workspace / "settlement-inventory.json"
    _write_report(path, report, resource_checkpoint=checkpoint, create_parents=False)
    verify_racing_settlement_inventory(report, root=root, domain=domain, as_of=end, checkpoint=checkpoint)
    checkpoint()
    return {"disposition": "succeeded", "status": "racing_settlement_metadata_inventory_only",
            "report_path": str(path), "content_hash": report["content_hash"],
            "normalized_source_verified": False, "verified_monitoring_samples": None,
            "model_promotion_allowed": False}


def verify_racing_settlement_inventory_receipt(*, payload, runtime, report_path, receipt):
    """Bounded parent metadata checks; source reconstruction stays in child."""
    domain, root, end = _inventory_scope(payload)
    report_path = _safe(Path(report_path))
    if report_path.name != "settlement-inventory.json" or not report_path.is_relative_to(_safe(runtime.warm_root)):
        raise ValueError("invalid settlement inventory output scope")
    reader = _Reader(lambda: None, max_records=1, max_record_bytes=MAX_INVENTORY_BYTES,
                     max_total_bytes=MAX_INVENTORY_BYTES * 2)
    report, _ = reader.read(report_path)
    _hashed(report, SCHEMA)
    expected = {"schema_version", "domain", "root", "as_of", "source_files", "collections",
                "evidence_records_seen", "settlements", "label_source_verified", "source_coverage_complete",
                "verified_monitoring_samples", "model_promotion_allowed", "content_hash"}
    if (set(report) != expected or report["root"] != str(root) or report["domain"] != domain.value
            or report["as_of"] != end.isoformat() or report["content_hash"] != receipt["content_hash"]
            or report["label_source_verified"] is not False or report["source_coverage_complete"] is not False
            or report["verified_monitoring_samples"] is not None or report["model_promotion_allowed"] is not False
            or type(report["evidence_records_seen"]) is not int or not 0 <= report["evidence_records_seen"] <= 10000):
        raise ValueError("settlement inventory identity or authority mismatch")
    files, collections, settlements = report["source_files"], report["collections"], report["settlements"]
    if not isinstance(files, list) or len(files) > 10000 or not isinstance(collections, list) or not isinstance(settlements, list):
        raise ValueError("invalid settlement inventory collections")
    for item in files:
        if (not isinstance(item, dict) or set(item) != {"path", "sha256"}
                or not _safe(Path(item["path"])).is_relative_to(root / "records")
                or not re.fullmatch("[0-9a-f]{64}", item["sha256"])):
            raise ValueError("invalid settlement metadata file witness")
    if [v["path"] for v in files] != sorted({v["path"] for v in files}):
        raise ValueError("duplicate or unordered settlement metadata witnesses")
    for item in collections:
        if (not isinstance(item, dict) or set(item) != {"path", "names_hash"}
                or not re.fullmatch("[0-9a-f]{64}", item["names_hash"])):
            raise ValueError("invalid settlement collection witness")
    if {v["path"] for v in collections} != {str(root / "records" / kind.value) for kind in RecordKind} or len(collections) != len(RecordKind):
        raise ValueError("incomplete settlement metadata collections")
    if len(settlements) > report["evidence_records_seen"]:
        raise ValueError("settlement metadata count mismatch")
    for value in settlements:
        if set(value) != {"settlement_id", "decision_id", "prediction_id", "event_id", "created_at", "settlement_state"}:
            raise ValueError("invalid settlement metadata record")
        for key, kind in (("settlement_id", "settlement"), ("decision_id", "decision"), ("prediction_id", "prediction")):
            if not isinstance(value[key], str) or not value[key].startswith(f"wc:{domain.value}:{kind}:"):
                raise ValueError("cross-domain settlement metadata identity")
        if _at(value["created_at"]) > end:
            raise ValueError("future settlement included in selected inventory")
    ids = [value["settlement_id"] for value in settlements]
    if ids != sorted(set(ids)):
        raise ValueError("duplicate or unordered settlement metadata identities")
    reader.recheck()
