"""Read-only NBA settlement/result applicability inventory.

Labels require an immutable prediction bundle plus a settlement-hash-pinned
reflector summary, results brief and complete props verification.  Files merely
adjacent in an archive are recovery inventory, never evidence.  Verified labels
still do not prove pre-game feature availability or qualify a research sample.
"""
from __future__ import annotations

import json
import math
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable
from urllib.parse import quote, unquote

from .contracts import Domain
from .evidence import ArtifactRef, EvidenceRecord, RecordKind
from .research_index import _Reader, _at, _encoded, _hash, _hashed, _safe
from .research_prediction_artifacts import _Blobs, inspect_prediction_artifacts
from .research_review_clock import _digest


SCHEMA = "wong-choi-nba-settlement-candidates/v1"
MAX_RECORDS = 10000
MAX_SETTLEMENTS = 1000
BLOCKER_ORDER = (
    "prediction_bundle_unverified",
    "reflector_summary_missing",
    "result_artifact_missing",
    "verification_artifact_missing",
    "verification_artifact_not_evidenced",
    "result_chain_incomplete",
    "feature_availability_unverified",
)


def _record(raw: dict, kind: RecordKind, path: Path) -> EvidenceRecord:
    value = EvidenceRecord(
        raw["record_id"], RecordKind(raw["kind"]), Domain(raw["domain"]),
        raw["created_at"], raw["body"], raw["links"],
        tuple(ArtifactRef(**item) for item in raw["artifacts"]),
    )
    if (
        value.to_dict() != raw
        or value.kind is not kind
        or value.domain is not Domain.NBA
        or path.name != quote(value.record_id, safe="._-") + ".json"
    ):
        raise ValueError("noncanonical or corrupt NBA production evidence")
    return value


def _evidence(root: Path, end: datetime, reader: _Reader) -> dict[str, EvidenceRecord]:
    records = {}
    domains = {item.value for item in Domain}
    for kind in RecordKind:
        for path in reader.listing(root / "records" / kind.value):
            identity = unquote(path.stem)
            parts = identity.split(":")
            if (
                path.name != quote(identity, safe="._-") + ".json"
                or len(parts) < 3
                or parts[0] != "wc"
                or parts[1] not in domains
            ):
                raise ValueError("noncanonical evidence filename cannot be omitted")
            if parts[1] != Domain.NBA.value:
                continue
            raw, _ = reader.read(path)
            value = _record(raw, kind, path)
            if _at(value.created_at) > end:
                continue
            if value.record_id in records:
                raise ValueError("duplicate NBA evidence identity across kinds")
            records[value.record_id] = value
    required = {
        RecordKind.PREDICTION: ("model_release_id", RecordKind.MODEL_RELEASE),
        RecordKind.DECISION: ("prediction_id", RecordKind.PREDICTION),
        RecordKind.SETTLEMENT: ("decision_id", RecordKind.DECISION),
    }
    for value in records.values():
        if value.kind not in required:
            continue
        link, expected = required[value.kind]
        parent = records.get(value.links[link])
        if parent is None or parent.kind is not expected:
            raise ValueError("missing, future or wrong-kind NBA evidence parent")
    return records


def _json(raw: bytes, label: str) -> dict:
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise ValueError(f"invalid NBA {label} JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"NBA {label} must be an object")
    return value


def _number(value: object) -> bool:
    return type(value) in {int, float} and math.isfinite(float(value))


def _verification_counts(value: dict) -> tuple[int, bool]:
    summary, legs = value.get("summary"), value.get("legs")
    fields = {"total_legs", "hits", "misses", "voids", "unverified"}
    if (
        value.get("_version") != "PROPS_VERIFICATION_V1"
        or not isinstance(summary, dict)
        or not fields <= set(summary)
        or not isinstance(legs, list)
        or any(type(summary.get(key)) is not int or summary[key] < 0 for key in fields)
    ):
        return 0, False
    total = summary["total_legs"]
    if total <= 0 or summary["unverified"] != 0 or len(legs) != total:
        return 0, False
    hits = misses = voids = 0
    for leg in legs:
        if not isinstance(leg, dict):
            return 0, False
        if leg.get("outcome") == "void":
            if leg.get("cleared") is not None:
                return 0, False
            voids += 1
            continue
        cleared = leg.get("cleared")
        actual, line = leg.get("actual"), leg.get("line")
        if type(cleared) is not bool or not _number(actual) or not _number(line):
            return 0, False
        if cleared != (float(actual) >= float(line)):
            return 0, False
        hits += int(cleared)
        misses += int(not cleared)
    complete = (
        hits == summary["hits"]
        and misses == summary["misses"]
        and voids == summary["voids"]
        and hits + misses + voids == total
    )
    return (total if complete else 0), complete


def _result_chain(event_id: str, artifacts: dict[str, bytes]) -> tuple[int, bool]:
    try:
        analysis_date = date.fromisoformat(event_id)
    except ValueError:
        return 0, False
    us_date = (analysis_date - timedelta(days=1)).isoformat()
    summary_name = f"Reflector_Run_Summary_{event_id}.json"
    results_name = f"Results_Brief_{us_date}.json"
    verification_name = f"Props_Verification_{us_date}.json"
    if not all(name in artifacts for name in (summary_name, results_name, verification_name)):
        return 0, False
    summary = _json(artifacts[summary_name], "reflector summary")
    results = _json(artifacts[results_name], "results brief")
    verification = _json(artifacts[verification_name], "props verification")
    if (
        summary.get("analysis_date") != event_id
        or summary.get("us_game_date") != us_date
        or Path(str(summary.get("results_path") or "")).name != results_name
        or Path(str(summary.get("verification_path") or "")).name != verification_name
        or type(summary.get("rows_recorded")) is not int
        or summary["rows_recorded"] <= 0
        or results.get("_version") != "RESULTS_BRIEF_V1"
        or results.get("date") != us_date
        or type(results.get("total_games")) is not int
        or results["total_games"] <= 0
        or not isinstance(results.get("games"), list)
        or len(results["games"]) != results["total_games"]
    ):
        return 0, False
    return _verification_counts(verification)


def inspect_nba_settlement_candidates(
    *,
    root: Path,
    as_of: datetime,
    relocation_roots: tuple[Path, ...] = (),
    checkpoint: Callable[[], None] = lambda: None,
) -> dict:
    """Inventory NBA hash-linked labels without granting feature/sample authority."""
    if not isinstance(relocation_roots, tuple):
        raise ValueError("tuple relocation roots required")
    root, end = _safe(root), _at(as_of)
    roots = tuple(_safe(Path(item)) for item in relocation_roots)
    prediction_report = inspect_prediction_artifacts(
        root=root, domain=Domain.NBA, as_of=end, relocation_roots=roots,
        checkpoint=checkpoint,
    )
    verified_predictions = {
        item["record_id"] for item in prediction_report["records"]
        if item["snapshot_bundle_verified"]
    }
    reader, blobs = _Reader(checkpoint), _Blobs(checkpoint)
    records = _evidence(root, end, reader)
    settlements = sorted(
        (item for item in records.values()
         if item.kind is RecordKind.SETTLEMENT
         and item.body["settlement_state"] in {"settled", "hit", "miss"}),
        key=lambda item: item.record_id,
    )
    if len(settlements) > MAX_SETTLEMENTS:
        raise ValueError("NBA settlement candidate limit exceeded")
    candidates = []
    for settlement in settlements:
        decision = records[settlement.links["decision_id"]]
        prediction = records[decision.links["prediction_id"]]
        event_id = str(settlement.body["event_id"])
        if (
            event_id != prediction.body.get("event_id")
            or _at(settlement.body["settled_at"]) < max(
                _at(prediction.created_at), _at(decision.created_at)
            )
        ):
            raise ValueError("NBA settlement chronology or event mismatch")
        artifacts, parents = {}, set()
        for ref in settlement.artifacts:
            path = _safe(Path(ref.path))
            raw, digest, _ = blobs.read(path)
            if (
                digest != ref.sha256
                or ref.source != "nba_settlement"
                or _at(ref.captured_at) != _at(settlement.body["settled_at"])
                or path.name in artifacts
            ):
                raise ValueError("NBA settlement artifact provenance mismatch")
            artifacts[path.name] = raw
            parents.add(path.parent)
        if parents and (
            len(parents) != 1
            or not next(iter(parents)).name.startswith(f"{event_id} NBA Analysis")
        ):
            raise ValueError("NBA settlement artifacts do not belong to event archive")
        try:
            us_date = (date.fromisoformat(event_id) - timedelta(days=1)).isoformat()
        except ValueError:
            us_date = "invalid"
        summary_name = f"Reflector_Run_Summary_{event_id}.json"
        result_name = f"Results_Brief_{us_date}.json"
        verification_name = f"Props_Verification_{us_date}.json"
        adjacent = False
        if verification_name not in artifacts and parents:
            adjacent = (next(iter(parents)) / verification_name).is_file()
        blockers = []
        if prediction.record_id not in verified_predictions:
            blockers.append("prediction_bundle_unverified")
        if summary_name not in artifacts:
            blockers.append("reflector_summary_missing")
        if result_name not in artifacts:
            blockers.append("result_artifact_missing")
        if verification_name not in artifacts:
            blockers.append(
                "verification_artifact_not_evidenced" if adjacent
                else "verification_artifact_missing"
            )
        legs, labels = _result_chain(event_id, artifacts)
        if all(name in artifacts for name in (summary_name, result_name, verification_name)) and not labels:
            blockers.append("result_chain_incomplete")
        blockers.append("feature_availability_unverified")
        candidates.append({
            "settlement_id": settlement.record_id,
            "decision_id": decision.record_id,
            "prediction_id": prediction.record_id,
            "event_id": event_id,
            "created_at": settlement.created_at,
            "prediction_bundle_verified": prediction.record_id in verified_predictions,
            "settlement_artifacts": len(settlement.artifacts),
            "settlement_artifacts_verified": len(artifacts),
            "reflector_summary_evidenced": summary_name in artifacts,
            "results_evidenced": result_name in artifacts,
            "verification_evidenced": verification_name in artifacts,
            "adjacent_unreferenced_verification": adjacent,
            "label_source_verified": labels,
            "verified_legs": legs,
            "blockers": [code for code in BLOCKER_ORDER if code in blockers],
            "sample_qualified": False,
        })
    blobs.recheck()
    reader.recheck()
    report = {
        "schema_version": SCHEMA,
        "domain": Domain.NBA.value,
        "root": str(root),
        "as_of": end.isoformat(),
        "relocation_roots": [str(item) for item in roots],
        "prediction_report_hash": prediction_report["content_hash"],
        "evidence_records_seen": len(records),
        "settlements_seen": len(candidates),
        "verified_prediction_bundles": sum(item["prediction_bundle_verified"] for item in candidates),
        "settlement_artifacts": sum(item["settlement_artifacts"] for item in candidates),
        "settlement_artifacts_verified": sum(item["settlement_artifacts_verified"] for item in candidates),
        "label_verified_settlements": sum(item["label_source_verified"] for item in candidates),
        "verified_legs": sum(item["verified_legs"] for item in candidates),
        "candidates": candidates,
        "label_source_verified": bool(candidates) and all(item["label_source_verified"] for item in candidates),
        "feature_availability_verified": False,
        "source_coverage_complete": False,
        "verified_monitoring_samples": None,
        "model_promotion_allowed": False,
    }
    report["content_hash"] = _hash(report)
    verify_nba_settlement_candidate_report(
        report, root=root, as_of=end, relocation_roots=roots,
    )
    return report


def verify_nba_settlement_candidate_report(
    report: dict,
    *,
    root: Path,
    as_of: datetime,
    relocation_roots: tuple[Path, ...],
) -> None:
    """Validate bounded report claims; source bytes stay inside the worker."""
    _hashed(report, SCHEMA)
    expected = {
        "schema_version", "domain", "root", "as_of", "relocation_roots",
        "prediction_report_hash", "evidence_records_seen", "settlements_seen",
        "verified_prediction_bundles", "settlement_artifacts",
        "settlement_artifacts_verified", "label_verified_settlements",
        "verified_legs", "candidates", "label_source_verified",
        "feature_availability_verified", "source_coverage_complete",
        "verified_monitoring_samples", "model_promotion_allowed", "content_hash",
    }
    roots = tuple(_safe(Path(item)) for item in relocation_roots)
    if (
        set(report) != expected
        or report["domain"] != Domain.NBA.value
        or report["root"] != str(_safe(root))
        or report["as_of"] != _at(as_of).isoformat()
        or report["relocation_roots"] != [str(item) for item in roots]
        or len(_encoded(report)) > 262144
    ):
        raise ValueError("NBA settlement report scope or size mismatch")
    _digest(report["prediction_report_hash"])
    if (
        report["feature_availability_verified"] is not False
        or report["source_coverage_complete"] is not False
        or report["verified_monitoring_samples"] is not None
        or report["model_promotion_allowed"] is not False
    ):
        raise ValueError("NBA label inventory cannot grant source, sample or model authority")
    count_fields = (
        "evidence_records_seen", "settlements_seen", "verified_prediction_bundles",
        "settlement_artifacts", "settlement_artifacts_verified",
        "label_verified_settlements", "verified_legs",
    )
    if any(type(report[key]) is not int or not 0 <= report[key] <= MAX_RECORDS for key in count_fields):
        raise ValueError("invalid NBA settlement aggregate")
    if (
        not isinstance(report["candidates"], list)
        or len(report["candidates"]) > MAX_SETTLEMENTS
        or type(report["label_source_verified"]) is not bool
    ):
        raise ValueError("invalid NBA settlement candidates")
    fields = {
        "settlement_id", "decision_id", "prediction_id", "event_id", "created_at",
        "prediction_bundle_verified", "settlement_artifacts",
        "settlement_artifacts_verified", "reflector_summary_evidenced",
        "results_evidenced", "verification_evidenced",
        "adjacent_unreferenced_verification", "label_source_verified",
        "verified_legs", "blockers", "sample_qualified",
    }
    ids = set()
    for item in report["candidates"]:
        if (
            not isinstance(item, dict)
            or set(item) != fields
            or item["settlement_id"] in ids
            or not item["settlement_id"].startswith("wc:nba:settlement:")
            or not item["decision_id"].startswith("wc:nba:decision:")
            or not item["prediction_id"].startswith("wc:nba:prediction:")
            or _at(item["created_at"]) > _at(as_of)
        ):
            raise ValueError("invalid NBA settlement candidate projection")
        for key in (
            "prediction_bundle_verified", "reflector_summary_evidenced",
            "results_evidenced", "verification_evidenced",
            "adjacent_unreferenced_verification", "label_source_verified",
            "sample_qualified",
        ):
            if type(item[key]) is not bool:
                raise ValueError("invalid NBA settlement candidate status")
        for key in ("settlement_artifacts", "settlement_artifacts_verified", "verified_legs"):
            if type(item[key]) is not int or not 0 <= item[key] <= MAX_RECORDS:
                raise ValueError("invalid NBA settlement candidate count")
        expected_blockers = []
        if not item["prediction_bundle_verified"]:
            expected_blockers.append("prediction_bundle_unverified")
        if not item["reflector_summary_evidenced"]:
            expected_blockers.append("reflector_summary_missing")
        if not item["results_evidenced"]:
            expected_blockers.append("result_artifact_missing")
        if not item["verification_evidenced"]:
            expected_blockers.append(
                "verification_artifact_not_evidenced"
                if item["adjacent_unreferenced_verification"]
                else "verification_artifact_missing"
            )
        elif not item["label_source_verified"]:
            expected_blockers.append("result_chain_incomplete")
        expected_blockers.append("feature_availability_unverified")
        if (
            item["blockers"] != expected_blockers
            or item["sample_qualified"] is not False
            or item["settlement_artifacts_verified"] != item["settlement_artifacts"]
            or item["label_source_verified"] != (item["verified_legs"] > 0)
        ):
            raise ValueError("NBA settlement blocker or authority mismatch")
        ids.add(item["settlement_id"])
    aggregates = {
        "settlements_seen": len(report["candidates"]),
        "verified_prediction_bundles": sum(item["prediction_bundle_verified"] for item in report["candidates"]),
        "settlement_artifacts": sum(item["settlement_artifacts"] for item in report["candidates"]),
        "settlement_artifacts_verified": sum(item["settlement_artifacts_verified"] for item in report["candidates"]),
        "label_verified_settlements": sum(item["label_source_verified"] for item in report["candidates"]),
        "verified_legs": sum(item["verified_legs"] for item in report["candidates"]),
    }
    if any(report[key] != value for key, value in aggregates.items()):
        raise ValueError("NBA settlement aggregate mismatch")
    if report["label_source_verified"] != (
        bool(report["candidates"])
        and all(item["label_source_verified"] for item in report["candidates"])
    ):
        raise ValueError("NBA settlement overall label authority mismatch")
