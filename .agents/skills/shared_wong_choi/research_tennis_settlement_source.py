"""Read-only Tennis settlement outcome applicability inventory."""
from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Callable
from urllib.parse import quote, unquote

from .contracts import Domain
from .evidence import ArtifactRef, EvidenceRecord, RecordKind
from .research_index import _Reader, _at, _encoded, _hash, _hashed, _safe
from .research_prediction_artifacts import _Blobs, inspect_prediction_artifacts
from .research_review_clock import _digest


SCHEMA = "wong-choi-tennis-settlement-candidates/v1"
OUTCOME_SCHEMA = "wong-choi-tennis-settlement-evidence/v2"
RAW_RESULT_SCHEMA = "wong-choi-tennis-settlement-raw-result/v1"
MAX_RECORDS = 10000
MAX_SETTLEMENTS = 1000
BLOCKERS = (
    "prediction_bundle_unverified", "outcome_artifact_missing",
    "outcome_artifact_not_evidenced", "outcome_artifact_incomplete",
    "feature_availability_unverified",
)
ROW_FIELDS = {
    "prediction_id", "match_id", "match_date", "prediction_created_at",
    "player_a_id", "player_b_id", "player_a_name", "player_b_name",
    "selection_player_id", "model_probability", "no_vig_market_probability",
    "winner_player_id", "result_source_provider", "result_raw_response_id",
    "result_raw_artifact", "result_raw_response_sha256",
    "result_raw_fetched_at", "result_raw_created_at", "result_created_at",
}
RAW_RESULT_FIELDS = {
    "schema_version", "event_id", "raw_response_id", "source_provider",
    "fetched_at", "created_at", "response_sha256", "response_json",
}


def _record(raw, kind, path):
    value = EvidenceRecord(
        raw["record_id"], RecordKind(raw["kind"]), Domain(raw["domain"]),
        raw["created_at"], raw["body"], raw["links"],
        tuple(ArtifactRef(**item) for item in raw["artifacts"]),
    )
    if (value.to_dict() != raw or value.kind is not kind
            or value.domain is not Domain.TENNIS
            or path.name != quote(value.record_id, safe="._-") + ".json"):
        raise ValueError("noncanonical or corrupt Tennis evidence")
    return value


def _evidence(root, end, reader):
    records, domains = {}, {item.value for item in Domain}
    for kind in RecordKind:
        for path in reader.listing(root / "records" / kind.value):
            identity, parts = unquote(path.stem), unquote(path.stem).split(":")
            if (path.name != quote(identity, safe="._-") + ".json" or len(parts) < 3
                    or parts[0] != "wc" or parts[1] not in domains):
                raise ValueError("noncanonical evidence filename cannot be omitted")
            if parts[1] != Domain.TENNIS.value:
                continue
            raw, _ = reader.read(path)
            value = _record(raw, kind, path)
            if _at(value.created_at) > end:
                continue
            if value.record_id in records:
                raise ValueError("duplicate Tennis evidence identity")
            records[value.record_id] = value
    required = {
        RecordKind.PREDICTION: ("model_release_id", RecordKind.MODEL_RELEASE),
        RecordKind.DECISION: ("prediction_id", RecordKind.PREDICTION),
        RecordKind.SETTLEMENT: ("decision_id", RecordKind.DECISION),
    }
    for value in records.values():
        if value.kind in required:
            link, kind = required[value.kind]
            parent = records.get(value.links[link])
            if parent is None or parent.kind is not kind:
                raise ValueError("missing or wrong-kind Tennis evidence parent")
    return records


def _number(value):
    return type(value) in {int, float} and math.isfinite(float(value))


def _name(value: object) -> str:
    if not isinstance(value, str):
        return ""
    folded = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return " ".join(re.findall(r"[a-z0-9]+", folded.casefold()))


def _raw_result_state(response: object, row: dict) -> str:
    if isinstance(response, dict) and isinstance(response.get("parsed_results"), list):
        candidates = response["parsed_results"]
    else:
        candidates = response if isinstance(response, list) else [response]
    expected_pair = {_name(row["player_a_name"]), _name(row["player_b_name"])}
    winner_name = (
        row["player_a_name"]
        if row["winner_player_id"] == row["player_a_id"]
        else row["player_b_name"]
    )
    expected_winner = _name(winner_name)
    found = confirmed = conflicted = False
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        pairs = []
        if (isinstance(candidate.get("winner_name"), str)
                and isinstance(candidate.get("loser_name"), str)):
            pairs.append((candidate["winner_name"], candidate["loser_name"],
                          candidate["winner_name"]))
        if (isinstance(candidate.get("player_name"), str)
                and isinstance(candidate.get("opponent_name"), str)
                and type(candidate.get("won")) in {bool, int}
                and candidate["won"] in {0, 1}):
            pairs.append((candidate["player_name"], candidate["opponent_name"],
                          candidate["player_name"] if candidate["won"]
                          else candidate["opponent_name"]))
        for left, right, winner in pairs:
            if {_name(left), _name(right)} != expected_pair:
                continue
            found = True
            if _name(winner) == expected_winner:
                confirmed = True
            else:
                conflicted = True
    if not found:
        return "missing_pair"
    return "confirmed" if confirmed and not conflicted else "winner_mismatch"


def _raw_result(raw: bytes, *, row: dict, event_id: str, cutoff: datetime,
                result_at: datetime) -> bool:
    try:
        payload = json.loads(raw)
        fetched = _at(payload["fetched_at"])
        created = _at(payload["created_at"])
        response_json = payload["response_json"]
        response = json.loads(response_json)
    except (KeyError, TypeError, ValueError, UnicodeError):
        return False
    if (not isinstance(payload, dict) or set(payload) != RAW_RESULT_FIELDS
            or payload.get("schema_version") != RAW_RESULT_SCHEMA
            or payload.get("event_id") != event_id
            or payload.get("raw_response_id") != row["result_raw_response_id"]
            or payload.get("source_provider") != row["result_source_provider"]
            or payload.get("fetched_at") != row["result_raw_fetched_at"]
            or payload.get("created_at") != row["result_raw_created_at"]
            or not isinstance(response_json, str)
            or hashlib.sha256(response_json.encode("utf-8")).hexdigest()
            != row["result_raw_response_sha256"]
            or payload.get("response_sha256") != row["result_raw_response_sha256"]
            or fetched < cutoff or fetched > created or created > result_at):
        return False
    expected_name = (
        f"Tennis_Settlement_Raw_{event_id}_{row['result_raw_response_id']}_"
        f"{row['result_raw_response_sha256'][:12]}.json"
    )
    return (row["result_raw_artifact"] == expected_name
            and _raw_result_state(response, row) == "confirmed")


def _outcomes(raw, *, event_id, cutoff, settled_at, recommendation_ids,
              raw_artifacts):
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeError):
        return 0, False
    if (not isinstance(payload, dict) or set(payload) != {
            "schema_version", "event_id", "generated_at", "rows"}
            or payload["schema_version"] != OUTCOME_SCHEMA
            or payload["event_id"] != event_id
            or _at(payload["generated_at"]) != settled_at
            or not isinstance(payload["rows"], list)):
        return 0, False
    seen, used_raw_artifacts = set(), set()
    for row in payload["rows"]:
        if not isinstance(row, dict):
            return 0, False
        try:
            prediction_at = _at(row["prediction_created_at"])
            result_at = _at(row["result_created_at"])
            raw_fetched = _at(row["result_raw_fetched_at"])
            raw_created = _at(row["result_raw_created_at"])
        except (KeyError, TypeError, ValueError, RuntimeError):
            return 0, False
        participants = {row.get("player_a_id"), row.get("player_b_id")}
        if (not isinstance(row, dict) or set(row) != ROW_FIELDS
                or type(row["prediction_id"]) is not int
                or row["prediction_id"] in seen
                or row["match_date"] != event_id
                or prediction_at > cutoff or result_at > settled_at
                or len(participants) != 2
                or any(type(row[key]) is not int or row[key] <= 0 for key in (
                    "match_id", "player_a_id", "player_b_id",
                    "selection_player_id", "winner_player_id",
                    "result_raw_response_id"))
                or row["selection_player_id"] not in participants
                or row["winner_player_id"] not in participants
                or any(not _number(row[key]) or not 0 < row[key] < 1 for key in (
                    "model_probability", "no_vig_market_probability"))
                or not isinstance(row["result_source_provider"], str)
                or not row["result_source_provider"].strip()
                or not isinstance(row["player_a_name"], str)
                or not isinstance(row["player_b_name"], str)
                or not _name(row["player_a_name"])
                or not _name(row["player_b_name"])
                or _name(row["player_a_name"]) == _name(row["player_b_name"])
                or not isinstance(row["result_raw_artifact"], str)
                or not row["result_raw_artifact"]
                or not isinstance(row["result_raw_response_sha256"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", row["result_raw_response_sha256"])
                or raw_fetched < cutoff or raw_fetched > raw_created
                or raw_created > result_at):
            return 0, False
        raw_result = raw_artifacts.get(row["result_raw_artifact"])
        if raw_result is None or not _raw_result(
                raw_result, row=row, event_id=event_id, cutoff=cutoff,
                result_at=result_at):
            return 0, False
        used_raw_artifacts.add(row["result_raw_artifact"])
        seen.add(row["prediction_id"])
    valid = (bool(seen) and seen == recommendation_ids
             and used_raw_artifacts == set(raw_artifacts))
    return len(seen) if valid else 0, valid


def inspect_tennis_settlement_candidates(*, root: Path, as_of: datetime,
                                         relocation_roots: tuple[Path, ...] = (),
                                         checkpoint: Callable[[], None] = lambda: None):
    if not isinstance(relocation_roots, tuple):
        raise ValueError("tuple relocation roots required")
    root, end = _safe(root), _at(as_of)
    roots = tuple(_safe(Path(item)) for item in relocation_roots)
    prediction_report = inspect_prediction_artifacts(
        root=root, domain=Domain.TENNIS, as_of=end, relocation_roots=roots,
        checkpoint=checkpoint)
    predictions = {item["record_id"]: item for item in prediction_report["records"]}
    reader, blobs = _Reader(checkpoint), _Blobs(checkpoint)
    records = _evidence(root, end, reader)
    settlements = sorted((item for item in records.values()
                          if item.kind is RecordKind.SETTLEMENT), key=lambda x: x.record_id)
    if len(settlements) > MAX_SETTLEMENTS:
        raise ValueError("Tennis settlement limit exceeded")
    candidates = []
    for settlement in settlements:
        decision = records[settlement.links["decision_id"]]
        prediction = records[decision.links["prediction_id"]]
        event_id = str(settlement.body["event_id"])
        settled_at, cutoff = _at(settlement.body["settled_at"]), _at(prediction.body["source_cutoff_at"])
        if event_id != prediction.body["event_id"] or settled_at < _at(decision.created_at):
            raise ValueError("Tennis settlement chronology or event mismatch")
        outcome_name = f"Tennis_Settlement_Evidence_{event_id}.json"
        outcome_raw, outcome_path, parents, raw_artifacts = None, None, set(), {}
        for ref in settlement.artifacts:
            path = _safe(Path(ref.path)); raw, digest, _ = blobs.read(path)
            if (digest != ref.sha256 or ref.source != "tennis_settlement"
                    or _at(ref.captured_at) != settled_at):
                raise ValueError("Tennis settlement artifact provenance mismatch")
            parents.add(path.parent)
            if path.name == outcome_name:
                if outcome_raw is not None:
                    raise ValueError("multiple Tennis outcome artifacts")
                outcome_raw, outcome_path = raw, path
            elif path.name.startswith(f"Tennis_Settlement_Raw_{event_id}_"):
                if path.name in raw_artifacts:
                    raise ValueError("duplicate Tennis raw result artifact")
                raw_artifacts[path.name] = raw
        if parents and (len(parents) != 1 or not next(iter(parents)).name.startswith(event_id)):
            raise ValueError("Tennis outcome artifact belongs to wrong event folder")
        adjacent = bool(parents and (next(iter(parents)) / outcome_name).is_file())
        recommendation_ids = {item.get("id") for item in prediction.body["recommendations"]}
        valid_ids = all(type(item) is int and item > 0 for item in recommendation_ids)
        outcomes, labels = (0, False) if outcome_raw is None or not valid_ids else _outcomes(
            outcome_raw, event_id=event_id, cutoff=cutoff, settled_at=settled_at,
            recommendation_ids=recommendation_ids, raw_artifacts=raw_artifacts)
        if not labels:
            outcomes = 0
        pred = predictions.get(prediction.record_id)
        bundle = bool(pred and pred["snapshot_bundle_verified"])
        blockers = []
        if not bundle: blockers.append("prediction_bundle_unverified")
        if outcome_raw is None:
            blockers.append("outcome_artifact_not_evidenced" if adjacent else "outcome_artifact_missing")
        elif not labels: blockers.append("outcome_artifact_incomplete")
        blockers.append("feature_availability_unverified")
        candidates.append({
            "settlement_id": settlement.record_id, "decision_id": decision.record_id,
            "prediction_id": prediction.record_id, "event_id": event_id,
            "created_at": settlement.created_at, "prediction_bundle_verified": bundle,
            "settlement_artifacts": len(settlement.artifacts),
            "settlement_artifacts_verified": len(settlement.artifacts),
            "referenced_outcome_artifact": str(outcome_path) if outcome_path else None,
            "adjacent_unreferenced_outcome": adjacent, "label_source_verified": labels,
            "recommendations": len(recommendation_ids), "verified_outcomes": outcomes,
            "blockers": [code for code in BLOCKERS if code in blockers], "sample_qualified": False})
    blobs.recheck(); reader.recheck()
    report = {
        "schema_version": SCHEMA, "domain": "tennis", "root": str(root),
        "as_of": end.isoformat(), "relocation_roots": [str(item) for item in roots],
        "prediction_report_hash": prediction_report["content_hash"],
        "evidence_records_seen": len(records), "settlements_seen": len(candidates),
        "verified_prediction_bundles": sum(x["prediction_bundle_verified"] for x in candidates),
        "settlement_artifacts": sum(x["settlement_artifacts"] for x in candidates),
        "settlement_artifacts_verified": sum(x["settlement_artifacts_verified"] for x in candidates),
        "label_verified_settlements": sum(x["label_source_verified"] for x in candidates),
        "verified_outcomes": sum(x["verified_outcomes"] for x in candidates),
        "candidates": candidates, "label_source_verified": bool(candidates) and all(x["label_source_verified"] for x in candidates),
        "feature_availability_verified": False, "source_coverage_complete": False,
        "verified_monitoring_samples": None, "model_promotion_allowed": False}
    report["content_hash"] = _hash(report)
    verify_tennis_settlement_candidate_report(report, root=root, as_of=end, relocation_roots=roots)
    return report


def verify_tennis_settlement_candidate_report(report, *, root, as_of, relocation_roots):
    _hashed(report, SCHEMA)
    roots = tuple(_safe(Path(item)) for item in relocation_roots)
    if (report.get("domain") != "tennis" or report.get("root") != str(_safe(root))
            or report.get("as_of") != _at(as_of).isoformat()
            or report.get("relocation_roots") != [str(x) for x in roots]
            or len(_encoded(report)) > 262144):
        raise ValueError("Tennis settlement report scope mismatch")
    _digest(report["prediction_report_hash"])
    if (report["feature_availability_verified"] is not False
            or report["source_coverage_complete"] is not False
            or report["verified_monitoring_samples"] is not None
            or report["model_promotion_allowed"] is not False):
        raise ValueError("Tennis label report cannot grant sample authority")
    if not isinstance(report["candidates"], list):
        raise ValueError("invalid Tennis candidates")
    for item in report["candidates"]:
        expected = []
        if not item["prediction_bundle_verified"]: expected.append("prediction_bundle_unverified")
        if item["referenced_outcome_artifact"] is None:
            expected.append("outcome_artifact_not_evidenced" if item["adjacent_unreferenced_outcome"] else "outcome_artifact_missing")
        elif not item["label_source_verified"]: expected.append("outcome_artifact_incomplete")
        expected.append("feature_availability_unverified")
        if (item["blockers"] != expected or item["sample_qualified"] is not False
                or item["label_source_verified"] != (item["recommendations"] > 0 and item["verified_outcomes"] == item["recommendations"])):
            raise ValueError("Tennis settlement blocker mismatch")
    aggregates = {
        "settlements_seen": len(report["candidates"]),
        "verified_prediction_bundles": sum(x["prediction_bundle_verified"] for x in report["candidates"]),
        "settlement_artifacts": sum(x["settlement_artifacts"] for x in report["candidates"]),
        "settlement_artifacts_verified": sum(x["settlement_artifacts_verified"] for x in report["candidates"]),
        "label_verified_settlements": sum(x["label_source_verified"] for x in report["candidates"]),
        "verified_outcomes": sum(x["verified_outcomes"] for x in report["candidates"])}
    if any(report[k] != v for k, v in aggregates.items()):
        raise ValueError("Tennis settlement aggregate mismatch")
