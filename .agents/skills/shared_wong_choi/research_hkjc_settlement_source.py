"""Read-only HKJC settlement/result applicability inventory.

The rendered reflection report is not a label source. Labels require a
settlement-hash-pinned full-day results JSON, a canonical prediction bundle and
complete top-three results for exactly the races represented in that bundle.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable
from urllib.parse import quote, unquote

from .contracts import Domain
from .evidence import ArtifactRef, EvidenceRecord, RecordKind
from .research_index import _Reader, _at, _encoded, _hash, _hashed, _safe
from .research_prediction_artifacts import _Blobs, inspect_prediction_artifacts
from .research_review_clock import _digest


SCHEMA = "wong-choi-hkjc-settlement-candidates/v1"
MAX_RECORDS = 10000
MAX_SETTLEMENTS = 1000
RESULT_NAME = re.compile(r"(?:\d{4}-\d{2}-\d{2}_.+_全日賽果|full_day_results)\.json")
LOGIC_NAME = re.compile(r"Race_(\d+)_Logic\.json")
BLOCKER_ORDER = (
    "prediction_bundle_unverified",
    "result_artifact_missing",
    "result_artifact_not_evidenced",
    "result_artifact_incomplete",
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
        or value.domain is not Domain.HKJC
        or path.name != quote(value.record_id, safe="._-") + ".json"
    ):
        raise ValueError("noncanonical or corrupt HKJC production evidence")
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
            if parts[1] != Domain.HKJC.value:
                continue
            raw, _ = reader.read(path)
            value = _record(raw, kind, path)
            if _at(value.created_at) > end:
                continue
            if value.record_id in records:
                raise ValueError("duplicate HKJC evidence identity across kinds")
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
            raise ValueError("missing, future or wrong-kind HKJC evidence parent")
    return records


def _canonical_results(path: Path) -> dict[int, dict]:
    scripts = Path(__file__).resolve().parents[1] / "shared_racing" / "race_reflector" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from unified_reflector_core import load_structured_results

    return load_structured_results("hkjc", path)


def _expected_races(snapshot_root: str | None, blobs: _Blobs) -> set[int]:
    if snapshot_root is None:
        return set()
    root = _safe(Path(snapshot_root))
    raw, _digest_value, _size = blobs.read(root / "manifest.json")
    try:
        manifest = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise ValueError("invalid HKJC prediction manifest JSON") from exc
    files = manifest.get("files") if isinstance(manifest, dict) else None
    if not isinstance(files, list):
        return set()
    races = set()
    for item in files:
        if not isinstance(item, dict):
            return set()
        match = LOGIC_NAME.fullmatch(str(item.get("name") or ""))
        if match:
            races.add(int(match.group(1)))
    return races


def _result_counts(path: Path, expected_races: set[int]) -> tuple[int, int, bool]:
    parsed = _canonical_results(path)
    rows = 0
    complete = bool(expected_races) and set(parsed) == expected_races
    for race_num, race in parsed.items():
        results = race.get("results") if isinstance(race, dict) else None
        if type(race_num) is not int or not isinstance(results, list):
            complete = False
            continue
        rows += len(results)
        top3 = results[:3]
        if (
            len(top3) != 3
            or [item.get("placing") for item in top3] != [1, 2, 3]
            or any(
                type(item.get("horse_no")) is not int
                or item["horse_no"] <= 0
                or not isinstance(item.get("horse_name"), str)
                or not item["horse_name"].strip()
                for item in top3
            )
            or len({item["horse_no"] for item in top3}) != 3
        ):
            complete = False
    return len(parsed), rows, complete


def _event_folder_matches(event_id: str, folder: Path) -> bool:
    parts = event_id.split("|")
    return len(parts) == 2 and folder.name.startswith(parts[0]) and parts[1] in folder.name


def inspect_hkjc_settlement_candidates(
    *,
    root: Path,
    as_of: datetime,
    relocation_roots: tuple[Path, ...] = (),
    checkpoint: Callable[[], None] = lambda: None,
) -> dict:
    """Inventory HKJC label sources without granting PIT/sample authority."""
    if not isinstance(relocation_roots, tuple):
        raise ValueError("tuple relocation roots required")
    root, end = _safe(root), _at(as_of)
    roots = tuple(_safe(Path(item)) for item in relocation_roots)
    prediction_report = inspect_prediction_artifacts(
        root=root, domain=Domain.HKJC, as_of=end, relocation_roots=roots,
        checkpoint=checkpoint,
    )
    predictions = {item["record_id"]: item for item in prediction_report["records"]}
    reader, blobs = _Reader(checkpoint), _Blobs(checkpoint)
    records = _evidence(root, end, reader)
    settlements = sorted(
        (item for item in records.values()
         if item.kind is RecordKind.SETTLEMENT
         and item.body["settlement_state"] in {"settled", "hit", "miss"}),
        key=lambda item: item.record_id,
    )
    if len(settlements) > MAX_SETTLEMENTS:
        raise ValueError("HKJC settlement candidate limit exceeded")
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
            raise ValueError("HKJC settlement chronology or event mismatch")
        result_paths, parents = [], set()
        for ref in settlement.artifacts:
            path = _safe(Path(ref.path))
            _raw, digest, _ = blobs.read(path)
            if (
                digest != ref.sha256
                or ref.source != "hkjc_settlement"
                or _at(ref.captured_at) != _at(settlement.body["settled_at"])
            ):
                raise ValueError("HKJC settlement artifact provenance mismatch")
            parents.add(path.parent)
            if RESULT_NAME.fullmatch(path.name):
                result_paths.append(path)
        if parents and (
            len(parents) != 1
            or not _event_folder_matches(event_id, next(iter(parents)))
        ):
            raise ValueError("HKJC settlement artifacts do not belong to event meeting")
        if len(result_paths) > 1:
            raise ValueError("multiple canonical HKJC result artifacts")
        result_path = result_paths[0] if result_paths else None
        prediction_item = predictions.get(prediction.record_id)
        bundle = bool(prediction_item and prediction_item["snapshot_bundle_verified"])
        expected_races = _expected_races(
            prediction_item["resolved_snapshot_root"] if bundle else None, blobs,
        )
        race_count = row_count = 0
        labels = False
        if result_path is not None:
            race_count, row_count, labels = _result_counts(result_path, expected_races)
        adjacent = False
        if result_path is None and parents:
            adjacent = any(
                child.is_file() and RESULT_NAME.fullmatch(child.name)
                for child in next(iter(parents)).iterdir()
            )
        blockers = []
        if not bundle:
            blockers.append("prediction_bundle_unverified")
        if result_path is None:
            blockers.append("result_artifact_not_evidenced" if adjacent else "result_artifact_missing")
        elif not labels:
            blockers.append("result_artifact_incomplete")
        blockers.append("feature_availability_unverified")
        candidates.append({
            "settlement_id": settlement.record_id,
            "decision_id": decision.record_id,
            "prediction_id": prediction.record_id,
            "event_id": event_id,
            "created_at": settlement.created_at,
            "prediction_bundle_verified": bundle,
            "settlement_artifacts": len(settlement.artifacts),
            "settlement_artifacts_verified": len(settlement.artifacts),
            "referenced_result_artifact": str(result_path) if result_path else None,
            "adjacent_unreferenced_result": adjacent,
            "label_source_verified": labels,
            "expected_races": len(expected_races),
            "parsed_result_races": race_count,
            "parsed_result_rows": row_count,
            "blockers": [code for code in BLOCKER_ORDER if code in blockers],
            "sample_qualified": False,
        })
    blobs.recheck()
    reader.recheck()
    report = {
        "schema_version": SCHEMA,
        "domain": Domain.HKJC.value,
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
        "parsed_result_races": sum(item["parsed_result_races"] for item in candidates),
        "parsed_result_rows": sum(item["parsed_result_rows"] for item in candidates),
        "candidates": candidates,
        "label_source_verified": bool(candidates) and all(item["label_source_verified"] for item in candidates),
        "feature_availability_verified": False,
        "source_coverage_complete": False,
        "verified_monitoring_samples": None,
        "model_promotion_allowed": False,
    }
    report["content_hash"] = _hash(report)
    verify_hkjc_settlement_candidate_report(
        report, root=root, as_of=end, relocation_roots=roots,
    )
    return report


def verify_hkjc_settlement_candidate_report(
    report: dict,
    *,
    root: Path,
    as_of: datetime,
    relocation_roots: tuple[Path, ...],
) -> None:
    """Validate bounded report claims; source bytes stay in supervised worker."""
    _hashed(report, SCHEMA)
    expected = {
        "schema_version", "domain", "root", "as_of", "relocation_roots",
        "prediction_report_hash", "evidence_records_seen", "settlements_seen",
        "verified_prediction_bundles", "settlement_artifacts",
        "settlement_artifacts_verified", "label_verified_settlements",
        "parsed_result_races", "parsed_result_rows", "candidates",
        "label_source_verified", "feature_availability_verified",
        "source_coverage_complete", "verified_monitoring_samples",
        "model_promotion_allowed", "content_hash",
    }
    roots = tuple(_safe(Path(item)) for item in relocation_roots)
    if (
        set(report) != expected
        or report["domain"] != Domain.HKJC.value
        or report["root"] != str(_safe(root))
        or report["as_of"] != _at(as_of).isoformat()
        or report["relocation_roots"] != [str(item) for item in roots]
        or len(_encoded(report)) > 262144
    ):
        raise ValueError("HKJC settlement report scope or size mismatch")
    _digest(report["prediction_report_hash"])
    if (
        report["feature_availability_verified"] is not False
        or report["source_coverage_complete"] is not False
        or report["verified_monitoring_samples"] is not None
        or report["model_promotion_allowed"] is not False
    ):
        raise ValueError("HKJC label inventory cannot grant source, sample or model authority")
    count_fields = (
        "evidence_records_seen", "settlements_seen", "verified_prediction_bundles",
        "settlement_artifacts", "settlement_artifacts_verified",
        "label_verified_settlements", "parsed_result_races", "parsed_result_rows",
    )
    if any(type(report[key]) is not int or not 0 <= report[key] <= MAX_RECORDS for key in count_fields):
        raise ValueError("invalid HKJC settlement aggregate")
    if not isinstance(report["candidates"], list) or len(report["candidates"]) > MAX_SETTLEMENTS:
        raise ValueError("invalid HKJC settlement candidates")
    fields = {
        "settlement_id", "decision_id", "prediction_id", "event_id", "created_at",
        "prediction_bundle_verified", "settlement_artifacts",
        "settlement_artifacts_verified", "referenced_result_artifact",
        "adjacent_unreferenced_result", "label_source_verified", "expected_races",
        "parsed_result_races", "parsed_result_rows", "blockers", "sample_qualified",
    }
    ids = set()
    for item in report["candidates"]:
        if (
            not isinstance(item, dict)
            or set(item) != fields
            or item["settlement_id"] in ids
            or not item["settlement_id"].startswith("wc:hkjc:settlement:")
            or not item["decision_id"].startswith("wc:hkjc:decision:")
            or not item["prediction_id"].startswith("wc:hkjc:prediction:")
            or _at(item["created_at"]) > _at(as_of)
        ):
            raise ValueError("invalid HKJC settlement candidate projection")
        for key in (
            "prediction_bundle_verified", "adjacent_unreferenced_result",
            "label_source_verified", "sample_qualified",
        ):
            if type(item[key]) is not bool:
                raise ValueError("invalid HKJC settlement candidate status")
        for key in (
            "settlement_artifacts", "settlement_artifacts_verified", "expected_races",
            "parsed_result_races", "parsed_result_rows",
        ):
            if type(item[key]) is not int or not 0 <= item[key] <= MAX_RECORDS:
                raise ValueError("invalid HKJC settlement candidate count")
        blockers = []
        if not item["prediction_bundle_verified"]:
            blockers.append("prediction_bundle_unverified")
        if item["referenced_result_artifact"] is None:
            blockers.append(
                "result_artifact_not_evidenced"
                if item["adjacent_unreferenced_result"] else "result_artifact_missing"
            )
        elif not item["label_source_verified"]:
            blockers.append("result_artifact_incomplete")
        blockers.append("feature_availability_unverified")
        if (
            item["blockers"] != blockers
            or item["sample_qualified"] is not False
            or item["settlement_artifacts_verified"] != item["settlement_artifacts"]
            or item["label_source_verified"] != (
                item["expected_races"] > 0
                and item["parsed_result_races"] == item["expected_races"]
                and item["parsed_result_rows"] >= item["expected_races"] * 3
            )
        ):
            raise ValueError("HKJC settlement blocker or authority mismatch")
        ids.add(item["settlement_id"])
    aggregates = {
        "settlements_seen": len(report["candidates"]),
        "verified_prediction_bundles": sum(item["prediction_bundle_verified"] for item in report["candidates"]),
        "settlement_artifacts": sum(item["settlement_artifacts"] for item in report["candidates"]),
        "settlement_artifacts_verified": sum(item["settlement_artifacts_verified"] for item in report["candidates"]),
        "label_verified_settlements": sum(item["label_source_verified"] for item in report["candidates"]),
        "parsed_result_races": sum(item["parsed_result_races"] for item in report["candidates"]),
        "parsed_result_rows": sum(item["parsed_result_rows"] for item in report["candidates"]),
    }
    if any(report[key] != value for key, value in aggregates.items()):
        raise ValueError("HKJC settlement aggregate mismatch")
    if report["label_source_verified"] != (
        bool(report["candidates"])
        and all(item["label_source_verified"] for item in report["candidates"])
    ):
        raise ValueError("HKJC overall label authority mismatch")
