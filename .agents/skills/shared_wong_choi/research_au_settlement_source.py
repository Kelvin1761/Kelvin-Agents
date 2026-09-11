"""Read-only AU settlement/result applicability inventory.

Only a canonical result file that is itself hash-pinned by the settlement record
may provide labels. An adjacent archive file is useful recovery inventory, never
evidence. Even verified labels do not prove feature availability or qualify a
monitoring sample.
"""
from __future__ import annotations

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


SCHEMA = "wong-choi-au-settlement-candidates/v1"
RESULT_NAME = "Race_Results_Reflector.md"
MAX_RECORDS = 10000
MAX_SETTLEMENTS = 1000
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
    if (value.to_dict() != raw or value.kind is not kind or value.domain is not Domain.AU
            or path.name != quote(value.record_id, safe="._-") + ".json"):
        raise ValueError("noncanonical or corrupt AU production evidence")
    return value


def _evidence(root: Path, end: datetime, reader: _Reader) -> dict[str, tuple[EvidenceRecord, dict]]:
    records = {}
    for kind in RecordKind:
        for path in reader.listing(root / "records" / kind.value):
            identity = unquote(path.stem)
            parts = identity.split(":")
            if (path.name != quote(identity, safe="._-") + ".json" or len(parts) < 3
                    or parts[0] != "wc" or parts[1] not in {item.value for item in Domain}):
                raise ValueError("noncanonical evidence filename cannot be omitted")
            if parts[1] != Domain.AU.value:
                continue
            raw, _digest_value = reader.read(path)
            value = _record(raw, kind, path)
            if _at(value.created_at) > end:
                continue
            if value.record_id in records:
                raise ValueError("duplicate AU evidence identity across kinds")
            records[value.record_id] = (value, raw)
    required = {
        RecordKind.PREDICTION: ("model_release_id", RecordKind.MODEL_RELEASE),
        RecordKind.DECISION: ("prediction_id", RecordKind.PREDICTION),
        RecordKind.SETTLEMENT: ("decision_id", RecordKind.DECISION),
    }
    for value, _raw in records.values():
        if value.kind not in required:
            continue
        link, expected = required[value.kind]
        parent = records.get(value.links[link])
        if parent is None or parent[0].kind is not expected:
            raise ValueError("missing, future or wrong-kind AU evidence parent")
    return records


def _canonical_results(path: Path) -> dict[int, dict]:
    scripts = Path(__file__).resolve().parents[1] / "shared_racing" / "race_reflector" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from unified_reflector_core import load_structured_results

    return load_structured_results("au", path)


def _result_counts(event_id: str, path: Path) -> tuple[int, int, bool]:
    parsed = _canonical_results(path)
    match = re.search(r" Race 1-(\d+)$", event_id)
    expected = int(match.group(1)) if match else None
    rows = 0
    complete = bool(parsed) and expected is not None and set(parsed) == set(range(1, expected + 1))
    for race_num, race in parsed.items():
        results = race.get("results") if isinstance(race, dict) else None
        if type(race_num) is not int or race_num <= 0 or not isinstance(results, list):
            complete = False
            continue
        rows += len(results)
        top3 = results[:3]
        if (len(top3) != 3 or [item.get("placing") for item in top3] != [1, 2, 3]
                or any(type(item.get("horse_no")) is not int or item["horse_no"] <= 0
                       or not isinstance(item.get("horse_name"), str) or not item["horse_name"].strip()
                       for item in top3)
                or len({item["horse_no"] for item in top3}) != 3):
            complete = False
    return len(parsed), rows, complete


def inspect_au_settlement_candidates(*, root: Path, as_of: datetime,
                                     relocation_roots: tuple[Path, ...] = (),
                                     checkpoint: Callable[[], None] = lambda: None) -> dict:
    """Inventory hash-linked labels without granting PIT/sample authority."""
    if not isinstance(relocation_roots, tuple):
        raise ValueError("tuple relocation roots required")
    root, end = _safe(root), _at(as_of)
    roots = tuple(_safe(Path(item)) for item in relocation_roots)
    prediction_report = inspect_prediction_artifacts(
        root=root, domain=Domain.AU, as_of=end, relocation_roots=roots, checkpoint=checkpoint,
    )
    verified_predictions = {
        item["record_id"]: item for item in prediction_report["records"]
        if item["snapshot_bundle_verified"]
    }
    reader = _Reader(checkpoint)
    records = _evidence(root, end, reader)
    settlements = [value for value in records.values()
                   if value[0].kind is RecordKind.SETTLEMENT
                   and value[0].body["settlement_state"] in {"settled", "hit", "miss"}]
    if len(settlements) > MAX_SETTLEMENTS:
        raise ValueError("AU settlement candidate limit exceeded")
    blobs, candidates = _Blobs(checkpoint), []
    for settlement, _raw in sorted(settlements, key=lambda item: item[0].record_id):
        decision = records[settlement.links["decision_id"]][0]
        prediction = records[decision.links["prediction_id"]][0]
        if (settlement.body.get("event_id") != prediction.body.get("event_id")
                or _at(settlement.body["settled_at"]) < max(
                    _at(decision.created_at), _at(prediction.created_at))):
            raise ValueError("AU settlement chronology or event mismatch")
        verified_artifacts, result_paths, artifact_parents = 0, [], set()
        for ref in settlement.artifacts:
            path = _safe(Path(ref.path))
            raw, digest, _size = blobs.read(path)
            if (digest != ref.sha256 or ref.source != "au_settlement"
                    or _at(ref.captured_at) != _at(settlement.body["settled_at"])):
                raise ValueError("AU settlement artifact provenance mismatch")
            verified_artifacts += 1
            artifact_parents.add(path.parent)
            if path.name == RESULT_NAME:
                result_paths.append(path)
        if artifact_parents and (
                len(artifact_parents) != 1
                or next(iter(artifact_parents)).name != settlement.body["event_id"]):
            raise ValueError("AU settlement artifacts do not belong to the event folder")
        if len(result_paths) > 1:
            raise ValueError("multiple canonical AU result artifacts")
        result_path = result_paths[0] if result_paths else None
        race_count = row_count = 0
        label_verified = False
        if result_path is not None:
            race_count, row_count, label_verified = _result_counts(
                str(settlement.body["event_id"]), result_path,
            )
        adjacent = False
        if result_path is None and settlement.artifacts:
            parent = _safe(Path(settlement.artifacts[0].path)).parent
            candidate_path = _safe(parent / RESULT_NAME)
            adjacent = candidate_path.is_file()
        blockers = []
        if prediction.record_id not in verified_predictions:
            blockers.append("prediction_bundle_unverified")
        if result_path is None:
            blockers.append("result_artifact_not_evidenced" if adjacent else "result_artifact_missing")
        elif not label_verified:
            blockers.append("result_artifact_incomplete")
        blockers.append("feature_availability_unverified")
        candidates.append({
            "settlement_id": settlement.record_id,
            "decision_id": decision.record_id,
            "prediction_id": prediction.record_id,
            "event_id": settlement.body["event_id"],
            "created_at": settlement.created_at,
            "prediction_bundle_verified": prediction.record_id in verified_predictions,
            "settlement_artifacts": len(settlement.artifacts),
            "settlement_artifacts_verified": verified_artifacts,
            "referenced_result_artifact": str(result_path) if result_path else None,
            "adjacent_unreferenced_result": adjacent,
            "label_source_verified": label_verified,
            "parsed_result_races": race_count,
            "parsed_result_rows": row_count,
            "blockers": blockers,
            "sample_qualified": False,
        })
    blobs.recheck()
    reader.recheck()
    report = {
        "schema_version": SCHEMA,
        "domain": Domain.AU.value,
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
    verify_au_settlement_candidate_report(
        report, root=root, as_of=end, relocation_roots=roots,
    )
    return report


def verify_au_settlement_candidate_report(report: dict, *, root: Path, as_of: datetime,
                                          relocation_roots: tuple[Path, ...]) -> None:
    """Validate bounded parent claims; source bytes remain a worker responsibility."""
    _hashed(report, SCHEMA)
    expected = {
        "schema_version", "domain", "root", "as_of", "relocation_roots",
        "prediction_report_hash", "evidence_records_seen", "settlements_seen",
        "verified_prediction_bundles", "settlement_artifacts", "settlement_artifacts_verified",
        "label_verified_settlements", "parsed_result_races", "parsed_result_rows", "candidates",
        "label_source_verified", "feature_availability_verified", "source_coverage_complete",
        "verified_monitoring_samples", "model_promotion_allowed", "content_hash",
    }
    roots = tuple(_safe(Path(item)) for item in relocation_roots)
    if (set(report) != expected or report["domain"] != Domain.AU.value
            or report["root"] != str(_safe(root)) or report["as_of"] != _at(as_of).isoformat()
            or report["relocation_roots"] != [str(item) for item in roots]
            or len(_encoded(report)) > 262144):
        raise ValueError("AU settlement candidate report scope or size mismatch")
    _digest(report["prediction_report_hash"])
    if (report["feature_availability_verified"] is not False
            or report["source_coverage_complete"] is not False
            or report["verified_monitoring_samples"] is not None
            or report["model_promotion_allowed"] is not False):
        raise ValueError("AU label inventory cannot grant source, sample or model authority")
    counts = (
        "evidence_records_seen", "settlements_seen", "verified_prediction_bundles",
        "settlement_artifacts", "settlement_artifacts_verified", "label_verified_settlements",
        "parsed_result_races", "parsed_result_rows",
    )
    if any(type(report[key]) is not int or not 0 <= report[key] <= MAX_RECORDS for key in counts):
        raise ValueError("invalid AU settlement aggregate count")
    if (not isinstance(report["candidates"], list) or len(report["candidates"]) > MAX_SETTLEMENTS
            or type(report["label_source_verified"]) is not bool):
        raise ValueError("invalid AU settlement candidates")
    fields = {
        "settlement_id", "decision_id", "prediction_id", "event_id", "created_at",
        "prediction_bundle_verified", "settlement_artifacts", "settlement_artifacts_verified",
        "referenced_result_artifact", "adjacent_unreferenced_result", "label_source_verified",
        "parsed_result_races", "parsed_result_rows", "blockers", "sample_qualified",
    }
    ids = set()
    for item in report["candidates"]:
        if (not isinstance(item, dict) or set(item) != fields or item["settlement_id"] in ids
                or not item["settlement_id"].startswith("wc:au:settlement:")
                or not item["decision_id"].startswith("wc:au:decision:")
                or not item["prediction_id"].startswith("wc:au:prediction:")
                or not isinstance(item["event_id"], str) or not item["event_id"]
                or _at(item["created_at"]) > _at(as_of)):
            raise ValueError("invalid AU settlement candidate projection")
        for key in ("prediction_bundle_verified", "adjacent_unreferenced_result",
                    "label_source_verified", "sample_qualified"):
            if type(item[key]) is not bool:
                raise ValueError("invalid AU settlement candidate status")
        if item["sample_qualified"] is not False:
            raise ValueError("AU candidate inventory cannot qualify samples")
        for key in ("settlement_artifacts", "settlement_artifacts_verified",
                    "parsed_result_races", "parsed_result_rows"):
            if type(item[key]) is not int or not 0 <= item[key] <= MAX_RECORDS:
                raise ValueError("invalid AU settlement candidate count")
        if item["settlement_artifacts_verified"] != item["settlement_artifacts"]:
            raise ValueError("AU settlement artifact verification mismatch")
        if item["referenced_result_artifact"] is not None:
            path = Path(item["referenced_result_artifact"])
            if not path.is_absolute() or path.name != RESULT_NAME:
                raise ValueError("invalid AU result artifact path")
            _safe(path)
        if (not isinstance(item["blockers"], list) or not item["blockers"]
                or item["blockers"] != [code for code in BLOCKER_ORDER if code in item["blockers"]]
                or len(item["blockers"]) != len(set(item["blockers"]))):
            raise ValueError("invalid AU settlement blocker set")
        expected_blockers = []
        if not item["prediction_bundle_verified"]:
            expected_blockers.append("prediction_bundle_unverified")
        if item["referenced_result_artifact"] is None:
            expected_blockers.append(
                "result_artifact_not_evidenced"
                if item["adjacent_unreferenced_result"] else "result_artifact_missing"
            )
            if (item["label_source_verified"] or item["parsed_result_races"]
                    or item["parsed_result_rows"]):
                raise ValueError("unevidenced AU result cannot provide labels")
        else:
            if item["adjacent_unreferenced_result"]:
                raise ValueError("referenced AU result cannot also be adjacent-only")
            if item["label_source_verified"]:
                if (item["parsed_result_races"] <= 0
                        or item["parsed_result_rows"] < 3 * item["parsed_result_races"]):
                    raise ValueError("verified AU labels require complete top-three rows")
            else:
                expected_blockers.append("result_artifact_incomplete")
        expected_blockers.append("feature_availability_unverified")
        if item["blockers"] != expected_blockers:
            raise ValueError("AU settlement blocker semantics mismatch")
        ids.add(item["settlement_id"])
    sums = {
        "verified_prediction_bundles": sum(item["prediction_bundle_verified"] for item in report["candidates"]),
        "settlement_artifacts": sum(item["settlement_artifacts"] for item in report["candidates"]),
        "settlement_artifacts_verified": sum(item["settlement_artifacts_verified"] for item in report["candidates"]),
        "label_verified_settlements": sum(item["label_source_verified"] for item in report["candidates"]),
        "parsed_result_races": sum(item["parsed_result_races"] for item in report["candidates"]),
        "parsed_result_rows": sum(item["parsed_result_rows"] for item in report["candidates"]),
    }
    if (report["settlements_seen"] != len(report["candidates"])
            or any(report[key] != value for key, value in sums.items())
            or report["label_source_verified"] is not (
                bool(report["candidates"])
                and report["label_verified_settlements"] == len(report["candidates"]))):
        raise ValueError("AU settlement candidate aggregates mismatch")
