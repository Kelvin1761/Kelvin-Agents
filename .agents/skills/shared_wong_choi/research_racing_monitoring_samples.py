"""Join verified racing labels and point-in-time features into sample clocks.

The AU and HKJC source inspectors remain independent.  This shared joiner only
emits stable settled-race identities after both inspectors agree on the same
canonical prediction bundle.  It never emits result labels, scoring inputs, or
model/promotion authority.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Callable

from .contracts import Domain
from .research_index import _at, _encoded, _hash, _hashed, _safe
from .research_review_clock import SampleSnapshot, _digest


SCHEMA = "wong-choi-racing-monitoring-samples/v1"
MAX_SETTLEMENTS = 1000
MAX_RACES = 10000
BLOCKER_ORDER = (
    "prediction_bundle_unverified",
    "label_source_unverified",
    "feature_record_missing",
    "feature_availability_unverified",
)


def _sources(domain: Domain):
    if domain is Domain.AU:
        from .research_au_feature_provenance import inspect_au_feature_provenance
        from .research_au_settlement_source import (
            _canonical_results,
            inspect_au_settlement_candidates,
        )
        return inspect_au_settlement_candidates, inspect_au_feature_provenance, _canonical_results
    if domain is Domain.HKJC:
        from .research_hkjc_feature_provenance import inspect_hkjc_feature_provenance
        from .research_hkjc_settlement_source import (
            _canonical_results,
            inspect_hkjc_settlement_candidates,
        )
        return inspect_hkjc_settlement_candidates, inspect_hkjc_feature_provenance, _canonical_results
    raise ValueError("racing monitoring samples support AU and HKJC only")


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _build_report(*, root: Path, domain: Domain, as_of: datetime,
                  relocation_roots: tuple[Path, ...],
                  checkpoint: Callable[[], None]) -> dict:
    if not isinstance(domain, Domain):
        raise ValueError("known domain required")
    if not isinstance(relocation_roots, tuple):
        raise ValueError("tuple relocation roots required")
    settlement_inspector, feature_inspector, parse_results = _sources(domain)
    evidence_root, end = _safe(root), _at(as_of)
    roots = tuple(_safe(Path(item)) for item in relocation_roots)
    common = dict(root=evidence_root, as_of=end, relocation_roots=roots,
                  checkpoint=checkpoint)
    settlements = settlement_inspector(**common)
    features = feature_inspector(**common)
    if settlements["prediction_report_hash"] != features["prediction_report_hash"]:
        raise ValueError("label and feature inventories do not share a prediction snapshot")
    feature_records = {item["record_id"]: item for item in features["records"]}
    if len(feature_records) != len(features["records"]):
        raise ValueError("duplicate feature prediction identity")

    units, candidates = [], []
    for candidate in settlements["candidates"]:
        checkpoint()
        feature = feature_records.get(candidate["prediction_id"])
        blockers = []
        if not candidate["prediction_bundle_verified"]:
            blockers.append("prediction_bundle_unverified")
        if not candidate["label_source_verified"]:
            blockers.append("label_source_unverified")
        if feature is None:
            blockers.append("feature_record_missing")
        elif not feature["feature_availability_verified"]:
            blockers.append("feature_availability_unverified")
        result_value = candidate["referenced_result_artifact"]
        race_numbers, result_digest = [], None
        if not blockers:
            if result_value is None:
                raise ValueError("qualified settlement has no canonical result artifact")
            result_path = _safe(Path(result_value))
            parsed = parse_results(result_path)
            race_numbers = sorted(parsed)
            if (not race_numbers or any(type(value) is not int or value <= 0 for value in race_numbers)
                    or len(race_numbers) != candidate["parsed_result_races"]):
                raise ValueError("qualified race identities do not match label inventory")
            result_digest = _file_digest(result_path)
            for race_number in race_numbers:
                units.append({
                    "unit_id": f"{candidate['prediction_id']}:race:{race_number}",
                    "prediction_id": candidate["prediction_id"],
                    "settlement_id": candidate["settlement_id"],
                    "event_id": candidate["event_id"],
                    "race_number": race_number,
                    "settled_at": _at(candidate["created_at"]).isoformat(),
                    "result_artifact_sha256": result_digest,
                })
        candidates.append({
            "settlement_id": candidate["settlement_id"],
            "prediction_id": candidate["prediction_id"],
            "event_id": candidate["event_id"],
            "race_numbers": race_numbers,
            "result_artifact_sha256": result_digest,
            "blockers": [code for code in BLOCKER_ORDER if code in blockers],
        })
    units.sort(key=lambda item: item["unit_id"])
    candidates.sort(key=lambda item: item["settlement_id"])
    if len(candidates) > MAX_SETTLEMENTS or len(units) > MAX_RACES:
        raise ValueError("racing monitoring sample bound exceeded")
    report = {
        "schema_version": SCHEMA,
        "domain": domain.value,
        "root": str(evidence_root),
        "as_of": end.isoformat(),
        "relocation_roots": [str(item) for item in roots],
        "prediction_report_hash": settlements["prediction_report_hash"],
        "settlement_report_hash": settlements["content_hash"],
        "feature_report_hash": features["content_hash"],
        "candidate_settlements": len(candidates),
        "qualified_settlements": sum(not item["blockers"] for item in candidates),
        "blocked_settlements": sum(bool(item["blockers"]) for item in candidates),
        "qualified_races": len(units),
        "candidates": candidates,
        "units": units,
        "basis": "settled_races",
        "scope": "all",
        "source_coverage_complete": bool(candidates) and not any(
            item["blockers"] for item in candidates),
        "verified_monitoring_samples": len(units),
        "terminal_labels_emitted": False,
        "sample_trigger_only": True,
        "model_promotion_allowed": False,
        "reevaluate_promotion_allowed": False,
    }
    report["content_hash"] = _hash(report)
    _verify_shape(report, root=evidence_root, domain=domain, as_of=end,
                  relocation_roots=roots)
    return report


def inspect_racing_monitoring_samples(
    *, root: Path, domain: Domain, as_of: datetime,
    relocation_roots: tuple[Path, ...] = (),
    checkpoint: Callable[[], None] = lambda: None,
) -> dict:
    """Rebuild a sample-only projection from immutable source evidence."""
    return _build_report(root=root, domain=domain, as_of=as_of,
                         relocation_roots=relocation_roots,
                         checkpoint=checkpoint)


def _verify_shape(report: dict, *, root: Path, domain: Domain, as_of: datetime,
                  relocation_roots: tuple[Path, ...]) -> None:
    _hashed(report, SCHEMA)
    expected = {
        "schema_version", "domain", "root", "as_of", "relocation_roots",
        "prediction_report_hash", "settlement_report_hash", "feature_report_hash",
        "candidate_settlements", "qualified_settlements", "blocked_settlements",
        "qualified_races", "candidates", "units", "basis", "scope",
        "source_coverage_complete", "verified_monitoring_samples",
        "terminal_labels_emitted", "sample_trigger_only", "model_promotion_allowed",
        "reevaluate_promotion_allowed", "content_hash",
    }
    roots = tuple(_safe(Path(item)) for item in relocation_roots)
    if (set(report) != expected or report["domain"] != domain.value
            or report["root"] != str(_safe(root))
            or report["as_of"] != _at(as_of).isoformat()
            or report["relocation_roots"] != [str(item) for item in roots]
            or report["basis"] != "settled_races" or report["scope"] != "all"
            or len(_encoded(report)) > 1048576):
        raise ValueError("racing monitoring sample report scope mismatch")
    for key in ("prediction_report_hash", "settlement_report_hash", "feature_report_hash"):
        _digest(report[key])
    if (report["terminal_labels_emitted"] is not False
            or report["sample_trigger_only"] is not True
            or report["model_promotion_allowed"] is not False
            or report["reevaluate_promotion_allowed"] is not False):
        raise ValueError("monitoring samples cannot grant model or terminal authority")
    counts = ("candidate_settlements", "qualified_settlements", "blocked_settlements",
              "qualified_races", "verified_monitoring_samples")
    if any(type(report[key]) is not int or not 0 <= report[key] <= MAX_RACES for key in counts):
        raise ValueError("invalid monitoring sample count")
    if (not isinstance(report["candidates"], list)
            or not isinstance(report["units"], list)
            or report["candidate_settlements"] != len(report["candidates"])
            or report["qualified_races"] != len(report["units"])
            or report["verified_monitoring_samples"] != len(report["units"])
            or report["qualified_settlements"] + report["blocked_settlements"]
            != len(report["candidates"])):
        raise ValueError("monitoring sample aggregate mismatch")
    candidate_fields = {
        "settlement_id", "prediction_id", "event_id", "race_numbers",
        "result_artifact_sha256", "blockers",
    }
    settlement_ids = set()
    for item in report["candidates"]:
        if (not isinstance(item, dict) or set(item) != candidate_fields
                or item["settlement_id"] in settlement_ids
                or not item["settlement_id"].startswith(f"wc:{domain.value}:settlement:")
                or not item["prediction_id"].startswith(f"wc:{domain.value}:prediction:")
                or not isinstance(item["event_id"], str) or not item["event_id"]
                or not isinstance(item["race_numbers"], list)
                or item["race_numbers"] != sorted(set(item["race_numbers"]))
                or any(type(value) is not int or value <= 0 for value in item["race_numbers"])
                or item["blockers"] != [code for code in BLOCKER_ORDER if code in item["blockers"]]
                or len(item["blockers"]) != len(set(item["blockers"]))):
            raise ValueError("invalid monitoring settlement projection")
        if item["blockers"]:
            if item["race_numbers"] or item["result_artifact_sha256"] is not None:
                raise ValueError("blocked settlement cannot expose qualified race units")
        else:
            if not item["race_numbers"]:
                raise ValueError("qualified settlement requires races")
            _digest(item["result_artifact_sha256"])
        settlement_ids.add(item["settlement_id"])
    unit_fields = {
        "unit_id", "prediction_id", "settlement_id", "event_id", "race_number",
        "settled_at", "result_artifact_sha256",
    }
    unit_ids = set()
    for item in report["units"]:
        expected_id = f"{item.get('prediction_id')}:race:{item.get('race_number')}"
        if (not isinstance(item, dict) or set(item) != unit_fields
                or item["unit_id"] != expected_id or item["unit_id"] in unit_ids
                or item["settlement_id"] not in settlement_ids
                or _at(item["settled_at"]) > _at(as_of)):
            raise ValueError("invalid settled-race monitoring unit")
        _digest(item["result_artifact_sha256"])
        unit_ids.add(item["unit_id"])
    complete = bool(report["candidates"]) and report["blocked_settlements"] == 0
    if report["source_coverage_complete"] is not complete:
        raise ValueError("monitoring source coverage mismatch")


def verify_racing_monitoring_sample_report(
    report: dict, *, root: Path, domain: Domain, as_of: datetime,
    relocation_roots: tuple[Path, ...] = (),
) -> None:
    """Parent verifier re-derives the complete report from source bytes."""
    _verify_shape(report, root=root, domain=domain, as_of=as_of,
                  relocation_roots=relocation_roots)
    rebuilt = _build_report(root=root, domain=domain, as_of=as_of,
                            relocation_roots=relocation_roots,
                            checkpoint=lambda: None)
    if _encoded(report) != _encoded(rebuilt):
        raise ValueError("racing monitoring sample report differs from source evidence")


def monitoring_sample_snapshot(report: dict) -> SampleSnapshot:
    """Reverify source evidence, then convert it to the review-clock value type."""
    domain = Domain(report.get("domain"))
    roots = tuple(Path(item) for item in report.get("relocation_roots", ()))
    verify_racing_monitoring_sample_report(
        report, root=Path(report.get("root", "")), domain=domain,
        as_of=_at(report.get("as_of")), relocation_roots=roots,
    )
    return SampleSnapshot(
        domain=domain,
        scope="all",
        basis="settled_races",
        observed_at=_at(report["as_of"]),
        evidence_digest=report["content_hash"],
        unit_ids=frozenset(item["unit_id"] for item in report["units"]),
    )
