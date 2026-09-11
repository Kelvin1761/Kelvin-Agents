"""Read-only AU feature/source provenance inventory.

A score description is not point-in-time evidence. A feature is availability-
verified only when its structured provenance binds an allowlisted pre-race input
artifact, artifact digest, source field and timestamp no later than the immutable
prediction cutoff. This inventory never qualifies labels or monitoring samples.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Callable

from .contracts import Domain
from .research_index import _at, _encoded, _hash, _hashed, _safe
from .research_prediction_artifacts import _Blobs, inspect_prediction_artifacts
from .research_review_clock import _digest


SCHEMA = "wong-choi-au-feature-provenance/v1"
MAX_RECORDS = 10000
MAX_FEATURES = 1000000
OUTPUT_NAME = re.compile(
    r"(?:Data_Health\.json|Meeting_Auto_Scoring\.csv|"
    r"Race_\d+_(?:Logic\.json|Auto_Analysis\.md|Auto_Scoring\.csv))"
)
LOGIC_NAME = re.compile(r"Race_\d+_Logic\.json")
BLOCKER_ORDER = (
    "prediction_bundle_unverified",
    "input_artifacts_missing",
    "feature_provenance_missing",
    "legacy_feature_provenance",
    "feature_contract_invalid",
    "feature_source_missing",
    "feature_source_is_prediction_output",
    "feature_source_digest_mismatch",
    "feature_source_after_cutoff",
)
SOURCE_FAILURES = frozenset(BLOCKER_ORDER[5:])


def _add(blockers: set[str], code: str) -> None:
    blockers.add(code)


def _source_valid(source: object, *, files: dict[str, str], cutoff: datetime,
                  blockers: set[str]) -> bool:
    if (not isinstance(source, dict)
            or set(source) != {"artifact", "sha256", "available_at", "field"}
            or not isinstance(source.get("artifact"), str)
            or Path(source["artifact"]).name != source["artifact"]
            or not isinstance(source.get("field"), str) or not source["field"].strip()):
        _add(blockers, "feature_contract_invalid")
        return False
    artifact = source["artifact"]
    try:
        _digest(source["sha256"])
        available = _at(source["available_at"])
    except (ValueError, RuntimeError, TypeError):
        _add(blockers, "feature_contract_invalid")
        return False
    if artifact not in files:
        _add(blockers, "feature_source_missing")
        return False
    if OUTPUT_NAME.fullmatch(artifact):
        _add(blockers, "feature_source_is_prediction_output")
        return False
    if source["sha256"] != files[artifact]:
        _add(blockers, "feature_source_digest_mismatch")
        return False
    if available > cutoff:
        _add(blockers, "feature_source_after_cutoff")
        return False
    return True


def _feature_valid(value: object, *, files: dict[str, str], cutoff: datetime,
                   blockers: set[str]) -> tuple[bool, str]:
    if isinstance(value, str):
        _add(blockers, "legacy_feature_provenance")
        return False, "legacy"
    if (not isinstance(value, dict) or set(value) != {"derivation", "sources"}
            or not isinstance(value.get("derivation"), str) or not value["derivation"].strip()
            or not isinstance(value.get("sources"), list) or not value["sources"]):
        _add(blockers, "feature_contract_invalid")
        return False, "invalid"
    valid = all(_source_valid(item, files=files, cutoff=cutoff, blockers=blockers)
                for item in value["sources"])
    return valid, "structured"


def inspect_au_feature_provenance(*, root: Path, as_of: datetime,
                                  relocation_roots: tuple[Path, ...] = (),
                                  checkpoint: Callable[[], None] = lambda: None) -> dict:
    """Inspect verified prediction bundles without granting sample authority."""
    if not isinstance(relocation_roots, tuple):
        raise ValueError("tuple relocation roots required")
    root, end = _safe(root), _at(as_of)
    roots = tuple(_safe(Path(item)) for item in relocation_roots)
    prediction_report = inspect_prediction_artifacts(
        root=root, domain=Domain.AU, as_of=end, relocation_roots=roots, checkpoint=checkpoint,
    )
    blobs, records = _Blobs(checkpoint), []
    for prediction in prediction_report["records"]:
        blockers: set[str] = set()
        bundle = prediction["snapshot_bundle_verified"]
        totals = {
            "input_artifacts": 0, "logic_files": 0, "horses": 0,
            "feature_entries": 0, "structured_feature_entries": 0,
            "legacy_feature_entries": 0, "invalid_feature_entries": 0,
            "verified_feature_entries": 0,
        }
        snapshot_root = prediction["resolved_snapshot_root"]
        if not bundle or snapshot_root is None:
            _add(blockers, "prediction_bundle_unverified")
        else:
            snapshot = _safe(Path(snapshot_root))
            manifest_raw, _manifest_digest, _manifest_size = blobs.read(snapshot / "manifest.json")
            try:
                manifest = json.loads(manifest_raw)
            except (ValueError, UnicodeError) as exc:
                raise ValueError("invalid AU prediction manifest JSON") from exc
            files = {
                item["name"]: item["sha256"] for item in manifest.get("files", [])
                if isinstance(item, dict) and set(item) == {"name", "bytes", "sha256"}
            }
            if len(files) != len(manifest.get("files", [])):
                raise ValueError("invalid AU prediction manifest file projection")
            totals["input_artifacts"] = sum(not OUTPUT_NAME.fullmatch(name) for name in files)
            if totals["input_artifacts"] == 0:
                _add(blockers, "input_artifacts_missing")
            cutoff = _at(prediction["source_cutoff_at"])
            logic_names = sorted(name for name in files if LOGIC_NAME.fullmatch(name))
            totals["logic_files"] = len(logic_names)
            for name in logic_names:
                raw, digest, _size = blobs.read(snapshot / name)
                if digest != files[name]:
                    raise ValueError("AU Logic digest differs from verified manifest")
                try:
                    logic = json.loads(raw)
                except (ValueError, UnicodeError) as exc:
                    raise ValueError("invalid AU Logic JSON") from exc
                horses = logic.get("horses") if isinstance(logic, dict) else None
                if not isinstance(horses, dict):
                    raise ValueError("AU Logic horses must be a mapping")
                totals["horses"] += len(horses)
                for horse in horses.values():
                    provenance = ((horse.get("python_auto") or {}).get("score_provenance")
                                  if isinstance(horse, dict) else None)
                    if not isinstance(provenance, dict) or not provenance:
                        _add(blockers, "feature_provenance_missing")
                        continue
                    for feature, value in provenance.items():
                        if not isinstance(feature, str) or not feature.endswith("_score"):
                            _add(blockers, "feature_contract_invalid")
                            totals["invalid_feature_entries"] += 1
                            totals["feature_entries"] += 1
                            continue
                        totals["feature_entries"] += 1
                        valid, kind = _feature_valid(value, files=files, cutoff=cutoff,
                                                     blockers=blockers)
                        totals[f"{kind}_feature_entries"] += 1
                        totals["verified_feature_entries"] += int(valid)
            if totals["feature_entries"] == 0:
                _add(blockers, "feature_provenance_missing")
        ordered = [code for code in BLOCKER_ORDER if code in blockers]
        ready = (bundle and totals["input_artifacts"] > 0 and totals["feature_entries"] > 0
                 and totals["verified_feature_entries"] == totals["feature_entries"]
                 and not ordered)
        records.append({
            "record_id": prediction["record_id"], "event_id": prediction["event_id"],
            "source_cutoff_at": prediction["source_cutoff_at"],
            "snapshot_root": snapshot_root, "bundle_verified": bundle,
            **totals, "feature_availability_verified": ready, "blockers": ordered,
        })
    blobs.recheck()
    count_fields = (
        "input_artifacts", "logic_files", "horses", "feature_entries",
        "structured_feature_entries", "legacy_feature_entries", "invalid_feature_entries",
        "verified_feature_entries",
    )
    report = {
        "schema_version": SCHEMA, "domain": Domain.AU.value, "root": str(root),
        "as_of": end.isoformat(), "relocation_roots": [str(item) for item in roots],
        "prediction_report_hash": prediction_report["content_hash"],
        "records_seen": len(records),
        "verified_bundles": sum(item["bundle_verified"] for item in records),
        **{key: sum(item[key] for item in records) for key in count_fields},
        "records": records,
        "feature_availability_verified": bool(records) and all(
            item["feature_availability_verified"] for item in records),
        "source_coverage_complete": False,
        "verified_monitoring_samples": None,
        "model_promotion_allowed": False,
    }
    report["content_hash"] = _hash(report)
    verify_au_feature_provenance_report(report, root=root, as_of=end, relocation_roots=roots)
    return report


def verify_au_feature_provenance_report(report: dict, *, root: Path, as_of: datetime,
                                        relocation_roots: tuple[Path, ...]) -> None:
    """Validate bounded report claims; bundle reads remain in the worker."""
    _hashed(report, SCHEMA)
    count_fields = (
        "input_artifacts", "logic_files", "horses", "feature_entries",
        "structured_feature_entries", "legacy_feature_entries", "invalid_feature_entries",
        "verified_feature_entries",
    )
    expected = {
        "schema_version", "domain", "root", "as_of", "relocation_roots",
        "prediction_report_hash", "records_seen", "verified_bundles", *count_fields,
        "records", "feature_availability_verified", "source_coverage_complete",
        "verified_monitoring_samples", "model_promotion_allowed", "content_hash",
    }
    roots = tuple(_safe(Path(item)) for item in relocation_roots)
    if (set(report) != expected or report["domain"] != Domain.AU.value
            or report["root"] != str(_safe(root)) or report["as_of"] != _at(as_of).isoformat()
            or report["relocation_roots"] != [str(item) for item in roots]
            or len(_encoded(report)) > 262144):
        raise ValueError("AU feature provenance report scope or size mismatch")
    _digest(report["prediction_report_hash"])
    if (report["source_coverage_complete"] is not False
            or report["verified_monitoring_samples"] is not None
            or report["model_promotion_allowed"] is not False
            or type(report["feature_availability_verified"]) is not bool):
        raise ValueError("AU feature inventory cannot grant sample or model authority")
    for key in ("records_seen", "verified_bundles", *count_fields):
        limit = MAX_FEATURES if "feature" in key else MAX_RECORDS
        if type(report[key]) is not int or not 0 <= report[key] <= limit:
            raise ValueError("invalid AU feature provenance aggregate")
    if not isinstance(report["records"], list) or len(report["records"]) > MAX_RECORDS:
        raise ValueError("invalid AU feature provenance records")
    fields = {
        "record_id", "event_id", "source_cutoff_at", "snapshot_root", "bundle_verified",
        *count_fields, "feature_availability_verified", "blockers",
    }
    ids = set()
    for item in report["records"]:
        if (not isinstance(item, dict) or set(item) != fields or item["record_id"] in ids
                or not item["record_id"].startswith("wc:au:prediction:")
                or not isinstance(item["event_id"], str) or not item["event_id"]
                or _at(item["source_cutoff_at"]) > _at(as_of)
                or type(item["bundle_verified"]) is not bool
                or type(item["feature_availability_verified"]) is not bool):
            raise ValueError("invalid AU feature provenance projection")
        for key in count_fields:
            if type(item[key]) is not int or not 0 <= item[key] <= MAX_FEATURES:
                raise ValueError("invalid AU feature provenance count")
        if (item["feature_entries"] != item["structured_feature_entries"]
                + item["legacy_feature_entries"] + item["invalid_feature_entries"]
                or item["verified_feature_entries"] > item["structured_feature_entries"]):
            raise ValueError("AU feature provenance count mismatch")
        if item["snapshot_root"] is not None:
            path = Path(item["snapshot_root"])
            if not path.is_absolute():
                raise ValueError("AU snapshot root must be absolute")
            _safe(path)
        if (not isinstance(item["blockers"], list)
                or item["blockers"] != [code for code in BLOCKER_ORDER if code in item["blockers"]]
                or len(item["blockers"]) != len(set(item["blockers"]))):
            raise ValueError("invalid AU feature provenance blockers")
        blockers = set(item["blockers"])
        if (not item["bundle_verified"]) != ("prediction_bundle_unverified" in blockers):
            raise ValueError("AU bundle blocker mismatch")
        if (item["bundle_verified"] and item["input_artifacts"] == 0) != (
                "input_artifacts_missing" in blockers):
            raise ValueError("AU input artifact blocker mismatch")
        if (item["bundle_verified"] and item["feature_entries"] == 0) != (
                "feature_provenance_missing" in blockers):
            raise ValueError("AU missing provenance blocker mismatch")
        if (item["legacy_feature_entries"] > 0) != ("legacy_feature_provenance" in blockers):
            raise ValueError("AU legacy provenance blocker mismatch")
        if (item["invalid_feature_entries"] > 0) != ("feature_contract_invalid" in blockers):
            raise ValueError("AU feature contract blocker mismatch")
        if (item["structured_feature_entries"] > item["verified_feature_entries"]
                and not blockers.intersection(SOURCE_FAILURES | {"feature_contract_invalid"})):
            raise ValueError("AU unverified structured provenance lacks a blocker")
        ready = (item["bundle_verified"] and item["input_artifacts"] > 0
                 and item["feature_entries"] > 0
                 and item["verified_feature_entries"] == item["feature_entries"]
                 and not item["blockers"])
        if item["feature_availability_verified"] is not ready:
            raise ValueError("AU feature readiness mismatch")
        ids.add(item["record_id"])
    if (report["records_seen"] != len(report["records"])
            or report["verified_bundles"] != sum(item["bundle_verified"] for item in report["records"])
            or any(report[key] != sum(item[key] for item in report["records"])
                   for key in count_fields)
            or report["feature_availability_verified"] is not (
                bool(report["records"])
                and all(item["feature_availability_verified"] for item in report["records"]))):
        raise ValueError("AU feature provenance aggregates mismatch")
