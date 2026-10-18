"""Native bounded label pages pinned to full prediction and settlement metadata.

Operational reads require supervision/heavy-lock/WARM guards. Label coverage is
not feature availability, qualified samples, retry approval or model authority.
"""
from pathlib import Path

from .contracts import Domain
from .research_index import _at, _encoded, _hash, _hashed, _safe
from .research_prediction_artifacts import MAX_ARTIFACTS
from .research_prediction_pages import (
    MAX_PAGE_RECORDS, inspect_prediction_page, plan_prediction_pages, verify_prediction_inventory,
)
from .research_racing_settlement_inventory import verify_racing_settlement_inventory

SCHEMA = "wong-choi-racing-settlement-page/v1"
COVERAGE_SCHEMA = "wong-choi-racing-settlement-page-coverage/v1"
COUNTS = ("settlements_seen", "verified_prediction_bundles", "settlement_artifacts",
          "settlement_artifacts_verified", "label_verified_settlements", "parsed_result_races", "parsed_result_rows")


def _selected_labels(settlement_inventory, prediction_ids):
    return [r for r in settlement_inventory["settlements"]
            if r["settlement_state"] in {"settled", "hit", "miss"} and r["prediction_id"] in prediction_ids]


def inspect_racing_settlement_page(*, inventory, settlement_inventory, page, root, domain, as_of,
                                  relocation_roots=(), max_refs=MAX_ARTIFACTS,
                                  max_records=MAX_PAGE_RECORDS, checkpoint=lambda: None,
                                  evidence_snapshot=None):
    if not isinstance(domain, Domain) or domain not in (Domain.AU, Domain.HKJC) or not isinstance(relocation_roots, tuple):
        raise ValueError("native racing domain and tuple relocation roots required")
    root, end = _safe(Path(root)), _at(as_of)

    def verify_metadata():
        if evidence_snapshot is None:
            verify_prediction_inventory(inventory, root=root, domain=domain, as_of=end, checkpoint=checkpoint)
            verify_racing_settlement_inventory(settlement_inventory, root=root, domain=domain, as_of=end, checkpoint=checkpoint)
        else:
            from .research_native_evidence_snapshot import _NativeEvidenceSnapshot
            if type(evidence_snapshot) is not _NativeEvidenceSnapshot:
                raise ValueError("native evidence snapshot required")
            evidence_snapshot.verify_inventories(inventory, settlement_inventory, root=root,
                                                 domain=domain, as_of=end, checkpoint=checkpoint)

    verify_metadata()
    options = dict(inventory=inventory, page=page, root=root, domain=domain, as_of=end,
                   relocation_roots=relocation_roots, max_refs=max_refs, max_records=max_records, checkpoint=checkpoint)
    prediction = inspect_prediction_page(**options)
    if domain is Domain.AU:
        from .research_au_settlement_source import _inspect_au_settlement_records as native
    else:
        from .research_hkjc_settlement_source import _inspect_hkjc_settlement_records as native
    report = native(prediction_report=prediction, root=root, end=end,
                    roots=tuple(_safe(Path(p)) for p in relocation_roots), checkpoint=checkpoint,
                    selected_prediction_ids=set(page["record_ids"]), evidence_snapshot=evidence_snapshot)
    expected = _selected_labels(settlement_inventory, set(page["record_ids"]))
    if [r["settlement_id"] for r in report["candidates"]] != [r["settlement_id"] for r in expected]:
        raise ValueError("label page differs from frozen complete settlement metadata")
    for candidate, selected in zip(report["candidates"], expected):
        for key in ("settlement_id", "decision_id", "prediction_id", "event_id", "created_at"):
            if candidate[key] != selected[key]:
                raise ValueError("label identity differs from frozen metadata")
    after = inspect_prediction_page(**options)
    if _encoded(after) != _encoded(prediction):
        raise ValueError("prediction source changed during label inspection")
    labels_after = native(prediction_report=after, root=root, end=end,
                          roots=tuple(_safe(Path(p)) for p in relocation_roots), checkpoint=checkpoint,
                          selected_prediction_ids=set(page["record_ids"]), evidence_snapshot=evidence_snapshot)
    if _encoded(labels_after) != _encoded(report):
        raise ValueError("label source changed during page inspection")
    verify_metadata()
    body = {"schema_version": SCHEMA, "domain": domain.value,
            "inventory_hash": inventory["content_hash"], "settlement_inventory_hash": settlement_inventory["content_hash"],
            "page_plan_hash": page["content_hash"], "prediction_page_hash": prediction["content_hash"],
            "settlement_report": report, "source_coverage_complete": False,
            "verified_monitoring_samples": None, "model_promotion_allowed": False}
    result = {**body, "content_hash": _hash(body)}
    if len(_encoded(result)) > 262144:
        raise ValueError("label page exceeds compact proof bound")
    return result


def aggregate_racing_settlement_pages(*, results, inventory, settlement_inventory, root, domain, as_of,
                                     relocation_roots=(), max_refs=MAX_ARTIFACTS,
                                     max_records=MAX_PAGE_RECORDS, checkpoint=lambda: None):
    if not isinstance(domain, Domain) or domain not in (Domain.AU, Domain.HKJC):
        raise ValueError("native racing domain required")
    plans = plan_prediction_pages(inventory, max_refs=max_refs, max_records=max_records)
    if not isinstance(results, list) or len(results) != len(plans):
        raise ValueError("incomplete native label page coverage")
    common = dict(root=root, domain=domain, as_of=as_of, checkpoint=checkpoint)
    verify_prediction_inventory(inventory, **common)
    verify_racing_settlement_inventory(settlement_inventory, **common)
    candidates, hashes = [], []
    for supplied, page in zip(results, plans):
        _hashed(supplied, SCHEMA)
        if len(_encoded(supplied)) > 262144:
            raise ValueError("oversized native label page proof")
        actual = inspect_racing_settlement_page(
            inventory=inventory, settlement_inventory=settlement_inventory, page=page,
            relocation_roots=relocation_roots, max_refs=max_refs, max_records=max_records, **common)
        if _encoded(supplied) != _encoded(actual):
            raise ValueError("label page differs from current source")
        candidates.extend(supplied["settlement_report"]["candidates"])
        hashes.append(supplied["content_hash"])
    expected = [r for r in settlement_inventory["settlements"] if r["settlement_state"] in {"settled", "hit", "miss"}]
    if sorted(c["settlement_id"] for c in candidates) != [r["settlement_id"] for r in expected]:
        raise ValueError("label corpus missing or duplicating frozen settlements")
    verify_prediction_inventory(inventory, **common)
    verify_racing_settlement_inventory(settlement_inventory, **common)
    body = {"schema_version": COVERAGE_SCHEMA, "domain": domain.value,
            "inventory_hash": inventory["content_hash"], "settlement_inventory_hash": settlement_inventory["content_hash"],
            "page_hashes": hashes, "page_coverage_complete": True,
            **{key: sum(r["settlement_report"][key] for r in results) for key in COUNTS},
            "label_source_verified": bool(candidates) and all(c["label_source_verified"] for c in candidates),
            "feature_availability_verified": False, "source_coverage_complete": False,
            "verified_monitoring_samples": None, "model_promotion_allowed": False}
    report = {**body, "content_hash": _hash(body)}
    if len(_encoded(report)) > 131072:
        raise ValueError("label coverage exceeds compact proof bound")
    return report
