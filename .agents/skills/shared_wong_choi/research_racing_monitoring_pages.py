"""Native feature/label joins for bounded pages, not complete sample clocks.

Operational reads require the research supervisor's WARM/heavy-lock guards.
Only a separately verified complete corpus may become a review-clock snapshot.
"""
from copy import deepcopy
from pathlib import Path

from .contracts import Domain
from .research_index import _at, _encoded, _hash, _hashed, _safe
from .research_prediction_artifacts import MAX_ARTIFACTS
from .research_prediction_pages import MAX_PAGE_RECORDS, plan_prediction_pages, verify_prediction_inventory
from .research_racing_feature_pages import SCHEMA as FEATURE_SCHEMA, inspect_racing_feature_page
from .research_racing_monitoring_samples import SCHEMA as MONITORING_SCHEMA, MAX_RACES, MAX_SETTLEMENTS, _join_reports
from .research_racing_settlement_inventory import verify_racing_settlement_inventory
from .research_racing_settlement_pages import SCHEMA as SETTLEMENT_SCHEMA, inspect_racing_settlement_page
from .research_review_clock import SampleSnapshot

SCHEMA = "wong-choi-racing-monitoring-page/v1"
COVERAGE_SCHEMA = "wong-choi-racing-monitoring-page-coverage/v1"


def inspect_racing_monitoring_page(*, inventory, settlement_inventory, page,
                                  root, domain, as_of, relocation_roots=(),
                                  max_refs=MAX_ARTIFACTS, max_records=MAX_PAGE_RECORDS,
                                  checkpoint=lambda: None, evidence_snapshot=None):
    options = dict(inventory=inventory, settlement_inventory=settlement_inventory,
                   page=page, root=root, domain=domain, as_of=as_of,
                   relocation_roots=relocation_roots, max_refs=max_refs,
                   max_records=max_records, checkpoint=checkpoint, evidence_snapshot=evidence_snapshot)
    result = _inspect_racing_monitoring_page_once(**options)
    after = _inspect_racing_monitoring_page_once(**options)
    if _encoded(after) != _encoded(result):
        raise ValueError("native source changed during monitoring page join")
    return result


def _inspect_racing_monitoring_page_once(*, inventory, settlement_inventory, page,
                                        root, domain, as_of, relocation_roots=(),
                                        max_refs=MAX_ARTIFACTS, max_records=MAX_PAGE_RECORDS,
                                        checkpoint=lambda: None, evidence_snapshot=None):
    """One native rebuild; corpus callers must retain both full replay passes."""
    common = dict(inventory=inventory, page=page, root=root, domain=domain,
                  as_of=as_of, relocation_roots=relocation_roots,
                  max_refs=max_refs, max_records=max_records, checkpoint=checkpoint)

    features = inspect_racing_feature_page(**common)
    labels = inspect_racing_settlement_page(settlement_inventory=settlement_inventory,
                                           evidence_snapshot=evidence_snapshot, **common)
    if features["prediction_page_hash"] != labels["prediction_page_hash"]:
        raise ValueError("feature and label pages do not share a prediction snapshot")
    _hashed(features, FEATURE_SCHEMA)
    _hashed(labels, SETTLEMENT_SCHEMA)
    joined = _join_reports(
        features=features["feature_report"], settlements=labels["settlement_report"],
        root=root, domain=domain, as_of=as_of, relocation_roots=relocation_roots,
        checkpoint=checkpoint)
    _hashed(joined, MONITORING_SCHEMA)
    body = {"schema_version": SCHEMA, "domain": domain.value,
            "inventory_hash": inventory["content_hash"],
            "settlement_inventory_hash": settlement_inventory["content_hash"],
            "page_plan_hash": page["content_hash"],
            "prediction_page_hash": features["prediction_page_hash"],
            "feature_page_hash": features["content_hash"],
            "settlement_page_hash": labels["content_hash"],
            "monitoring_report": joined, "source_coverage_complete": False,
            "verified_monitoring_samples": None, "model_promotion_allowed": False}
    result = {**body, "content_hash": _hash(body)}
    if len(_encoded(result)) > 262144:
        raise ValueError("monitoring page exceeds compact proof bound")
    return result


def aggregate_racing_monitoring_pages(*, results, inventory, settlement_inventory,
                                     root, domain, as_of, relocation_roots=(),
                                     max_refs=MAX_ARTIFACTS, max_records=MAX_PAGE_RECORDS,
                                     checkpoint=lambda: None, evidence_snapshot=None):
    """Reconstruct every ordered page before granting sample-trigger-only counts."""
    if not isinstance(domain, Domain) or domain not in (Domain.AU, Domain.HKJC):
        raise ValueError("native racing domain required")
    if not isinstance(relocation_roots, tuple):
        raise ValueError("tuple relocation roots required")
    root, end = _safe(Path(root)), _at(as_of)
    roots = tuple(_safe(Path(item)) for item in relocation_roots)
    plans = plan_prediction_pages(inventory, max_refs=max_refs, max_records=max_records)
    if not isinstance(results, list) or len(results) != len(plans):
        raise ValueError("incomplete monitoring page coverage")
    common = dict(root=root, domain=domain, as_of=end, checkpoint=checkpoint)

    def verify_metadata():
        verify_prediction_inventory(inventory, **common)
        verify_racing_settlement_inventory(settlement_inventory, **common)

    verify_metadata()
    # A second complete pass rejects earlier-page sources changed while a later
    # page was inspected. Metadata inventories are reverified around both passes.
    for _ in range(2):
        for supplied, page in zip(results, plans):
            checkpoint()
            _hashed(supplied, SCHEMA)
            if len(_encoded(supplied)) > 262144:
                raise ValueError("oversized monitoring page proof")
            actual = _inspect_racing_monitoring_page_once(
                inventory=inventory, settlement_inventory=settlement_inventory,
                page=page, relocation_roots=roots, max_refs=max_refs,
                max_records=max_records, evidence_snapshot=evidence_snapshot, **common)
            if _encoded(supplied) != _encoded(actual):
                raise ValueError("monitoring page differs from current source")
        verify_metadata()
    return _coverage_projection(results=results, inventory=inventory, settlement_inventory=settlement_inventory,
                                root=root, domain=domain, as_of=end, relocation_roots=roots,
                                max_refs=max_refs, max_records=max_records)


def _coverage_projection(*, results, inventory, settlement_inventory, root, domain,
                         as_of, relocation_roots, max_refs, max_records):
    """Private aggregation; callers must already verify every companion/page."""
    root, end = _safe(Path(root)), _at(as_of)
    roots = tuple(_safe(Path(item)) for item in relocation_roots)
    candidates = sorted([deepcopy(item) for page in results for item in page["monitoring_report"]["candidates"]],
                        key=lambda item: item["settlement_id"])
    units = sorted([deepcopy(item) for page in results for item in page["monitoring_report"]["units"]],
                   key=lambda item: item["unit_id"])
    expected = [item["settlement_id"] for item in settlement_inventory["settlements"]
                if item["settlement_state"] in {"settled", "hit", "miss"}]
    if [item["settlement_id"] for item in candidates] != expected:
        raise ValueError("monitoring corpus missing or duplicating frozen settlements")
    if len({item["unit_id"] for item in units}) != len(units):
        raise ValueError("duplicate settled-race monitoring identity")
    if len(candidates) > MAX_SETTLEMENTS or len(units) > MAX_RACES:
        raise ValueError("racing monitoring sample bound exceeded")
    blocked = sum(bool(item["blockers"]) for item in candidates)
    body = {"schema_version": COVERAGE_SCHEMA, "domain": domain.value,
            "root": str(root), "as_of": end.isoformat(),
            "relocation_roots": [str(item) for item in roots],
            "inventory_hash": inventory["content_hash"],
            "settlement_inventory_hash": settlement_inventory["content_hash"],
            "max_refs": max_refs, "max_records": max_records,
            "page_hashes": [page["content_hash"] for page in results],
            "page_coverage_complete": True, "candidate_settlements": len(candidates),
            "qualified_settlements": len(candidates) - blocked, "blocked_settlements": blocked,
            "qualified_races": len(units), "candidates": candidates, "units": units,
            "basis": "settled_races", "scope": "all",
            "source_coverage_complete": bool(candidates) and blocked == 0,
            "verified_monitoring_samples": len(units), "terminal_labels_emitted": False,
            "sample_trigger_only": True, "model_promotion_allowed": False,
            "reevaluate_promotion_allowed": False}
    report = {**body, "content_hash": _hash(body)}
    if len(_encoded(report)) > 1048576:
        raise ValueError("monitoring coverage exceeds existing sample report bound")
    return report


def paged_monitoring_sample_snapshot(*, report, results, inventory, settlement_inventory,
                                    root, domain, as_of, relocation_roots=(),
                                    max_refs=MAX_ARTIFACTS, max_records=MAX_PAGE_RECORDS,
                                    checkpoint=lambda: None):
    """Convert only after rebuilding complete current native source coverage."""
    _hashed(report, COVERAGE_SCHEMA)
    if len(_encoded(report)) > 1048576:
        raise ValueError("oversized monitoring coverage")
    rebuilt = aggregate_racing_monitoring_pages(
        results=results, inventory=inventory, settlement_inventory=settlement_inventory,
        root=root, domain=domain, as_of=as_of, relocation_roots=relocation_roots,
        max_refs=max_refs, max_records=max_records, checkpoint=checkpoint)
    if _encoded(report) != _encoded(rebuilt):
        raise ValueError("monitoring coverage differs from source evidence")
    return SampleSnapshot(domain=domain, scope="all", basis="settled_races",
                          observed_at=_at(as_of), evidence_digest=report["content_hash"],
                          unit_ids=frozenset(item["unit_id"] for item in report["units"]))
