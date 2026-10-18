"""Bounded racing feature proofs; native domain PIT rules remain separate.

Operational I/O must run under the shared supervisor/heavy lock/WARM guard.
Page completion does not establish complete corpus or monitoring sample authority.
"""
from __future__ import annotations

from pathlib import Path

from .contracts import Domain
from .research_index import _at, _encoded, _hash, _hashed, _safe
from .research_prediction_artifacts import MAX_ARTIFACTS
from .research_prediction_pages import (
    MAX_PAGE_RECORDS, inspect_prediction_page, plan_prediction_pages, verify_prediction_inventory,
)

SCHEMA = "wong-choi-racing-feature-page/v1"
COVERAGE_SCHEMA = "wong-choi-racing-feature-page-coverage/v1"
COUNTS = ("input_artifacts", "logic_files", "horses", "feature_entries",
          "structured_feature_entries", "legacy_feature_entries", "invalid_feature_entries",
          "verified_feature_entries")


def inspect_racing_feature_page(*, inventory, page, root, domain, as_of,
                               relocation_roots=(), max_refs=MAX_ARTIFACTS,
                               max_records=MAX_PAGE_RECORDS, checkpoint=lambda: None):
    if domain not in (Domain.AU, Domain.HKJC) or not isinstance(domain, Domain):
        raise ValueError("native racing domain required")
    root, end = _safe(Path(root)), _at(as_of)
    prediction = inspect_prediction_page(
        inventory=inventory, page=page, root=root, domain=domain, as_of=end,
        relocation_roots=relocation_roots, max_refs=max_refs, max_records=max_records, checkpoint=checkpoint,
    )
    if domain is Domain.AU:
        from .research_au_feature_provenance import _inspect_au_feature_records as native
    else:
        from .research_hkjc_feature_provenance import _inspect_hkjc_feature_records as native
    report = native(prediction_report=prediction, root=root, end=end,
                    roots=tuple(_safe(Path(p)) for p in relocation_roots), checkpoint=checkpoint)
    after = inspect_prediction_page(
        inventory=inventory, page=page, root=root, domain=domain, as_of=end,
        relocation_roots=relocation_roots, max_refs=max_refs, max_records=max_records, checkpoint=checkpoint,
    )
    if _encoded(after) != _encoded(prediction):
        raise ValueError("prediction bundle changed during feature inspection")
    if [r["record_id"] for r in report["records"]] != page["record_ids"]:
        raise ValueError("feature page differs from prediction coverage")
    body = {"schema_version": SCHEMA, "domain": domain.value,
            "inventory_hash": inventory["content_hash"], "page_plan_hash": page["content_hash"],
            "prediction_page_hash": prediction["content_hash"], "feature_report": report,
            "source_coverage_complete": False, "verified_monitoring_samples": None,
            "model_promotion_allowed": False}
    result = {**body, "content_hash": _hash(body)}
    if len(_encoded(result)) > 262144:
        raise ValueError("feature page exceeds compact proof bound")
    return result


def aggregate_racing_feature_pages(*, results, inventory, root, domain, as_of,
                                  relocation_roots=(), max_refs=MAX_ARTIFACTS,
                                  max_records=MAX_PAGE_RECORDS, checkpoint=lambda: None):
    """Rebuild all pages before accepting compact whole-corpus feature coverage."""
    if domain not in (Domain.AU, Domain.HKJC) or not isinstance(domain, Domain):
        raise ValueError("native racing domain required")
    plans = plan_prediction_pages(inventory, max_refs=max_refs, max_records=max_records)
    if not isinstance(results, list) or len(results) != len(plans):
        raise ValueError("incomplete racing feature page coverage")
    verify_prediction_inventory(inventory, root=root, domain=domain, as_of=as_of, checkpoint=checkpoint)
    records, hashes = [], []
    for supplied, page in zip(results, plans):
        checkpoint()
        _hashed(supplied, SCHEMA)
        if len(_encoded(supplied)) > 262144:
            raise ValueError("oversized racing feature page proof")
        actual = inspect_racing_feature_page(
            inventory=inventory, page=page, root=root, domain=domain, as_of=as_of,
            relocation_roots=relocation_roots, max_refs=max_refs, max_records=max_records, checkpoint=checkpoint,
        )
        if _encoded(supplied) != _encoded(actual):
            raise ValueError("feature page differs from current source")
        records.extend(supplied["feature_report"]["records"])
        hashes.append(supplied["content_hash"])
    verify_prediction_inventory(inventory, root=root, domain=domain, as_of=as_of, checkpoint=checkpoint)
    if [r["record_id"] for r in records] != [r["record_id"] for r in inventory["records"]]:
        raise ValueError("feature corpus record coverage mismatch")
    body = {"schema_version": COVERAGE_SCHEMA, "domain": domain.value,
            "inventory_hash": inventory["content_hash"], "page_hashes": hashes,
            "records_seen": len(records), "verified_bundles": sum(r["bundle_verified"] for r in records),
            **{key: sum(r[key] for r in records) for key in COUNTS},
            "page_coverage_complete": True,
            "feature_availability_verified": bool(records) and all(r["feature_availability_verified"] for r in records),
            "source_coverage_complete": False, "verified_monitoring_samples": None,
            "model_promotion_allowed": False}
    result = {**body, "content_hash": _hash(body)}
    if len(_encoded(result)) > 131072:
        raise ValueError("feature coverage exceeds compact proof bound")
    return result
