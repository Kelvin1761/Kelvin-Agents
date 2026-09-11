"""Read-only Tennis prediction feature/source provenance inventory.

The mutable Tennis database is not prediction-time evidence. Availability is
verified only from a compact feature projection frozen inside the canonical
prediction snapshot. This module never grants labels, samples or promotion.
"""
from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Callable

from .contracts import Domain
from .evidence import RecordKind
from .research_index import _Reader, _at, _encoded, _hash, _hashed, _safe
from .research_prediction_artifacts import _Blobs, inspect_prediction_artifacts
from .research_tennis_settlement_source import _evidence
from .research_review_clock import _digest


SCHEMA = "wong-choi-tennis-feature-provenance/v1"
FEATURE_SCHEMA = "wong-choi-tennis-feature-evidence/v3"
COMPONENTS = frozenset({
    "surface_elo_edge", "overall_elo_edge", "serve_return_edge",
    "recent_form_edge", "opponent_rank_bucket_edge", "tournament_level_edge",
    "round_performance_edge", "big_match_edge", "pressure_edge",
    "head_to_head_edge", "fatigue_edge",
})
BLOCKER_ORDER = (
    "prediction_bundle_unverified", "feature_artifact_missing",
    "feature_artifact_invalid", "prediction_rows_missing",
    "prediction_id_set_mismatch", "prediction_output_mismatch",
    "feature_snapshot_invalid", "feature_snapshot_digest_mismatch",
    "component_contract_incomplete", "component_input_invalid",
    "decision_input_invalid",
    "feature_value_digest_mismatch", "raw_input_invalid", "raw_input_missing",
    "raw_input_digest_mismatch", "feature_source_mismatch",
    "feature_source_after_cutoff",
)
ROW_FIELDS = {
    "prediction_id", "match_id", "feature_set_version", "prediction_created_at",
    "selection_player_id", "model_probability", "no_vig_market_probability",
    "current_market_odds", "edge", "feature_snapshot",
    "feature_snapshot_sha256", "components", "decision_inputs", "raw_input_ids",
}
RAW_FIELDS = {
    "raw_response_id", "source_provider", "source_endpoint", "fetched_at",
    "created_at", "artifact_name", "response_sha256",
}
DECISION_INPUT_PATHS = {
    "tour": ["match_context", "tour"],
    "tournament_level": ["match_context", "level"],
    "player_a_odds": ["market", "player_a_odds"],
    "player_b_odds": ["market", "player_b_odds"],
}
MAX_RECORDS = 10000
MAX_ROWS = 100000


def _number(value: object) -> bool:
    return type(value) in {int, float} and math.isfinite(float(value))


def _path(root: object, parts: object) -> object | None:
    if (not isinstance(parts, list) or not parts
            or any(not isinstance(part, str) or not part for part in parts)):
        return None
    current = root
    for part in parts:
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _raw_inputs(items: object, *, event_id: str, cutoff: datetime,
                artifacts: dict[str, bytes], blockers: set[str]) -> dict[int, dict]:
    if not isinstance(items, list):
        blockers.add("raw_input_invalid")
        return {}
    output = {}
    for item in items:
        if (not isinstance(item, dict) or set(item) != RAW_FIELDS
                or type(item.get("raw_response_id")) is not int
                or item["raw_response_id"] <= 0 or item["raw_response_id"] in output
                or not isinstance(item.get("source_provider"), str)
                or not item["source_provider"].strip()
                or not isinstance(item.get("source_endpoint"), str)
                or not item["source_endpoint"].strip()):
            blockers.add("raw_input_invalid")
            continue
        try:
            fetched, created = _at(item["fetched_at"]), _at(item["created_at"])
            _digest(item["response_sha256"])
        except (ValueError, RuntimeError, TypeError):
            blockers.add("raw_input_invalid")
            continue
        expected_name = (f"Tennis_Raw_Evidence_{event_id}_"
                         f"{item['raw_response_id']}_{item['response_sha256'][:12]}.json")
        if item.get("artifact_name") != expected_name:
            blockers.add("raw_input_invalid")
            continue
        raw = artifacts.get(expected_name)
        if raw is None:
            blockers.add("raw_input_missing")
            continue
        try:
            response = json.loads(raw)
        except (ValueError, UnicodeError):
            blockers.add("raw_input_invalid")
            continue
        if item["response_sha256"] != _hash(response):
            blockers.add("raw_input_digest_mismatch")
        if fetched > created or created > cutoff:
            blockers.add("feature_source_after_cutoff")
        output[item["raw_response_id"]] = {**item, "response_json": response}
    if set(artifacts) != {
        item["artifact_name"] for item in output.values()
    }:
        blockers.add("raw_input_invalid")
    return output


def _input_valid(item: object, *, snapshot: dict, raws: dict[int, dict],
                 cutoff: datetime, prediction_at: datetime, blockers: set[str],
                 invalid_code: str = "component_input_invalid") -> bool:
    if (not isinstance(item, dict)
            or set(item) != {"path", "value_sha256", "raw_response_ids"}
            or not isinstance(item.get("raw_response_ids"), list)
            or len(item["raw_response_ids"]) != 1
            or type(item["raw_response_ids"][0]) is not int):
        blockers.add(invalid_code)
        return False
    try:
        _digest(item["value_sha256"])
    except (ValueError, RuntimeError, TypeError):
        blockers.add(invalid_code)
        return False
    point = _path(snapshot, item["path"])
    if (not isinstance(point, dict) or "value" not in point
            or not isinstance(point.get("provenance"), dict)):
        blockers.add(invalid_code)
        return False
    if item["value_sha256"] != _hash(point["value"]):
        blockers.add("feature_value_digest_mismatch")
    provenance = point["provenance"]
    expected = {
        "source_provider", "source_endpoint", "source_timestamp", "calculated_at",
        "raw_response_id", "warnings",
    }
    if (set(provenance) != expected or type(provenance.get("raw_response_id")) is not int
            or provenance["raw_response_id"] != item["raw_response_ids"][0]
            or provenance.get("warnings") != []):
        blockers.add(invalid_code)
        return False
    raw = raws.get(provenance["raw_response_id"])
    if raw is None:
        blockers.add("raw_input_missing")
        return False
    if (provenance.get("source_provider") != raw["source_provider"]
            or provenance.get("source_endpoint") != raw["source_endpoint"]):
        blockers.add("feature_source_mismatch")
    try:
        source_at, calculated = _at(provenance["source_timestamp"]), _at(provenance["calculated_at"])
        fetched, created = _at(raw["fetched_at"]), _at(raw["created_at"])
    except (ValueError, RuntimeError, TypeError):
        blockers.add(invalid_code)
        return False
    if (source_at != fetched or max(source_at, created) > calculated
            or calculated > prediction_at or prediction_at > cutoff):
        blockers.add("feature_source_after_cutoff")
    return True


def _components(items: object, *, snapshot: dict, raws: dict[int, dict],
                cutoff: datetime, prediction_at: datetime,
                blockers: set[str]) -> tuple[int, int, set[int]]:
    if not isinstance(items, list):
        blockers.add("component_contract_incomplete")
        return 0, 0, set()
    names, active, inputs, raw_ids = set(), 0, 0, set()
    for component in items:
        if (not isinstance(component, dict)
                or set(component) != {"name", "active", "warnings", "inputs"}
                or component.get("name") in names
                or component.get("name") not in COMPONENTS
                or type(component.get("active")) is not bool
                or not isinstance(component.get("warnings"), list)
                or any(not isinstance(value, str) or not value for value in component["warnings"])
                or len(component["warnings"]) != len(set(component["warnings"]))
                or not isinstance(component.get("inputs"), list)):
            blockers.add("component_contract_incomplete")
            continue
        names.add(component["name"])
        if component["active"]:
            active += 1
            if component["warnings"] or not component["inputs"]:
                blockers.add("component_contract_incomplete")
            for item in component["inputs"]:
                inputs += 1
                if _input_valid(item, snapshot=snapshot, raws=raws, cutoff=cutoff,
                                prediction_at=prediction_at, blockers=blockers):
                    raw_ids.update(item["raw_response_ids"])
        elif not component["warnings"] or component["inputs"]:
            blockers.add("component_contract_incomplete")
    if names != COMPONENTS:
        blockers.add("component_contract_incomplete")
    if active == 0:
        blockers.add("component_contract_incomplete")
    return active, inputs, raw_ids


def _decision_inputs(items: object, *, snapshot: dict, raws: dict[int, dict],
                     cutoff: datetime, prediction_at: datetime,
                     blockers: set[str]) -> set[int]:
    if not isinstance(items, dict) or set(items) != set(DECISION_INPUT_PATHS):
        blockers.add("decision_input_invalid")
        return set()
    raw_ids = set()
    for name, expected_path in DECISION_INPUT_PATHS.items():
        item = items[name]
        if not isinstance(item, dict) or item.get("path") != expected_path:
            blockers.add("decision_input_invalid")
            continue
        if _input_valid(
            item,
            snapshot=snapshot,
            raws=raws,
            cutoff=cutoff,
            prediction_at=prediction_at,
            blockers=blockers,
            invalid_code="decision_input_invalid",
        ):
            raw_ids.update(item["raw_response_ids"])
    return raw_ids


def _participant_ids(snapshot: dict) -> set[int]:
    output = set()
    for name in ("player_a", "player_b"):
        player = snapshot.get(name)
        identity = player.get("id") if isinstance(player, dict) else None
        value = identity.get("value") if isinstance(identity, dict) else None
        if type(value) is int and value > 0:
            output.add(value)
    return output


def _projection(raw: bytes, *, event_id: str, cutoff: datetime,
                recommendations: dict[int, dict],
                raw_artifacts: dict[str, bytes]) -> tuple[dict, set[str]]:
    blockers: set[str] = set()
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeError):
        return {"rows": []}, {"feature_artifact_invalid"}
    if (not isinstance(payload, dict)
            or set(payload) != {"schema_version", "event_id", "generated_at",
                               "raw_inputs", "rows"}
            or payload.get("schema_version") != FEATURE_SCHEMA
            or payload.get("event_id") != event_id
            or not isinstance(payload.get("rows"), list)):
        return {"rows": []}, {"feature_artifact_invalid"}
    try:
        if _at(payload["generated_at"]) != cutoff:
            blockers.add("feature_artifact_invalid")
    except (ValueError, RuntimeError, TypeError):
        blockers.add("feature_artifact_invalid")
    raws = _raw_inputs(
        payload.get("raw_inputs"), event_id=event_id, cutoff=cutoff,
        artifacts=raw_artifacts, blockers=blockers,
    )
    rows, seen = [], set()
    used_raw_ids = set()
    for row in payload["rows"]:
        row_blockers: set[str] = set()
        if (not isinstance(row, dict) or set(row) != ROW_FIELDS
                or type(row.get("prediction_id")) is not int
                or row["prediction_id"] <= 0 or row["prediction_id"] in seen
                or type(row.get("match_id")) is not int or row["match_id"] <= 0
                or type(row.get("selection_player_id")) is not int
                or row["selection_player_id"] <= 0
                or not isinstance(row.get("feature_set_version"), str)
                or not row["feature_set_version"].strip()
                or any(not _number(row.get(key)) for key in (
                    "model_probability", "no_vig_market_probability",
                    "current_market_odds", "edge"))
                or not 0 < row["model_probability"] < 1
                or not 0 < row["no_vig_market_probability"] < 1
                or row["current_market_odds"] <= 1):
            blockers.add("feature_artifact_invalid")
            continue
        raw_ids = row.get("raw_input_ids")
        if (not isinstance(raw_ids, list)
                or any(type(value) is not int or value <= 0 for value in raw_ids)
                or len(raw_ids) != len(set(raw_ids))):
            blockers.add("raw_input_invalid")
            continue
        used_raw_ids.update(raw_ids)
        seen.add(row["prediction_id"])
        try:
            prediction_at = _at(row["prediction_created_at"])
            _digest(row["feature_snapshot_sha256"])
        except (ValueError, RuntimeError, TypeError):
            blockers.add("feature_artifact_invalid")
            continue
        if prediction_at > cutoff:
            row_blockers.add("feature_source_after_cutoff")
        recommendation = recommendations.get(row["prediction_id"])
        if recommendation is not None and recommendation.get("edge") != row["edge"]:
            row_blockers.add("prediction_output_mismatch")
        snapshot = row["feature_snapshot"]
        if (not isinstance(snapshot, dict)
                or snapshot.get("feature_set_version") != row["feature_set_version"]
                or snapshot.get("entity_mapping_complete") is not True
                or not isinstance(snapshot.get("match_id"), dict)
                or snapshot["match_id"].get("value") != row["match_id"]
                or len(_participant_ids(snapshot)) != 2
                or row["selection_player_id"] not in _participant_ids(snapshot)):
            row_blockers.add("feature_snapshot_invalid")
        elif row["feature_snapshot_sha256"] != _hash(snapshot):
            row_blockers.add("feature_snapshot_digest_mismatch")
        row_raws = {raw_id: raws[raw_id] for raw_id in raw_ids if raw_id in raws}
        if len(row_raws) != len(raw_ids):
            row_blockers.add("raw_input_missing")
        active, inputs, component_raw_ids = _components(
            row["components"], snapshot=snapshot if isinstance(snapshot, dict) else {},
            raws=row_raws, cutoff=cutoff, prediction_at=prediction_at,
            blockers=row_blockers,
        )
        decision_raw_ids = _decision_inputs(
            row["decision_inputs"],
            snapshot=snapshot if isinstance(snapshot, dict) else {},
            raws=row_raws,
            cutoff=cutoff,
            prediction_at=prediction_at,
            blockers=row_blockers,
        )
        if set(raw_ids) != component_raw_ids | decision_raw_ids:
            row_blockers.add("raw_input_invalid")
        rows.append({"prediction_id": row["prediction_id"], "active_components": active,
                     "component_inputs": inputs, "raw_inputs": len(row_raws),
                     "verified": not row_blockers,
                     "blockers": [code for code in BLOCKER_ORDER if code in row_blockers]})
        blockers.update(row_blockers)
    if not recommendations:
        blockers.add("prediction_rows_missing")
    if seen != set(recommendations):
        blockers.add("prediction_id_set_mismatch")
    if used_raw_ids != set(raws):
        blockers.add("raw_input_invalid")
    if blockers.intersection({"prediction_rows_missing", "prediction_id_set_mismatch",
                              "raw_input_invalid", "raw_input_missing",
                              "raw_input_digest_mismatch"}):
        for row in rows:
            row["verified"] = False
    return {"rows": rows}, blockers


def inspect_tennis_feature_provenance(*, root: Path, as_of: datetime,
                                      relocation_roots: tuple[Path, ...] = (),
                                      checkpoint: Callable[[], None] = lambda: None) -> dict:
    if not isinstance(relocation_roots, tuple):
        raise ValueError("tuple relocation roots required")
    root, end = _safe(root), _at(as_of)
    roots = tuple(_safe(Path(item)) for item in relocation_roots)
    prediction_report = inspect_prediction_artifacts(
        root=root, domain=Domain.TENNIS, as_of=end, relocation_roots=roots,
        checkpoint=checkpoint,
    )
    reader, blobs = _Reader(checkpoint), _Blobs(checkpoint)
    evidence = _evidence(root, end, reader)
    predictions = {key: value for key, value in evidence.items()
                   if value.kind is RecordKind.PREDICTION}
    records = []
    for item in prediction_report["records"]:
        blockers: set[str] = set()
        bundle = item["snapshot_bundle_verified"]
        projection_rows, active, inputs, raw_count, verified = 0, 0, 0, 0, 0
        feature_path = None
        if not bundle or item["resolved_snapshot_root"] is None:
            blockers.add("prediction_bundle_unverified")
        else:
            prediction = predictions[item["record_id"]]
            recommendations = {
                value.get("id"): value for value in prediction.body["recommendations"]
                if isinstance(value, dict) and type(value.get("id")) is int
            }
            snapshot = _safe(Path(item["resolved_snapshot_root"]))
            manifest_raw, _digest_value, _size = blobs.read(snapshot / "manifest.json")
            manifest = json.loads(manifest_raw)
            files = {value["name"]: value["sha256"] for value in manifest["files"]}
            feature_name = f"Tennis_Feature_Evidence_{item['event_id']}.json"
            if feature_name not in files:
                blockers.add("feature_artifact_missing")
            else:
                feature_path = snapshot / feature_name
                raw, _feature_digest, _feature_size = blobs.read(feature_path)
                prefix = f"Tennis_Raw_Evidence_{item['event_id']}_"
                raw_artifacts = {}
                for name, expected_digest in files.items():
                    if not name.startswith(prefix):
                        continue
                    content, digest, _size = blobs.read(snapshot / name)
                    if digest != expected_digest:
                        raise ValueError("Tennis raw artifact digest differs from manifest")
                    raw_artifacts[name] = content
                projection, found = _projection(
                    raw, event_id=item["event_id"], cutoff=_at(item["source_cutoff_at"]),
                    recommendations=recommendations, raw_artifacts=raw_artifacts,
                )
                blockers.update(found)
                projection_rows = len(projection["rows"])
                active = sum(row["active_components"] for row in projection["rows"])
                inputs = sum(row["component_inputs"] for row in projection["rows"])
                raw_count = sum(row["raw_inputs"] for row in projection["rows"])
                verified = sum(row["verified"] for row in projection["rows"])
        ready = bundle and projection_rows > 0 and verified == projection_rows and not blockers
        records.append({
            "record_id": item["record_id"], "event_id": item["event_id"],
            "source_cutoff_at": item["source_cutoff_at"],
            "snapshot_root": item["resolved_snapshot_root"], "bundle_verified": bundle,
            "feature_artifact": str(feature_path) if feature_path else None,
            "prediction_rows": projection_rows, "verified_predictions": verified,
            "active_components": active, "component_inputs": inputs,
            "raw_inputs": raw_count, "feature_availability_verified": ready,
            "blockers": [code for code in BLOCKER_ORDER if code in blockers],
        })
    blobs.recheck(); reader.recheck()
    count_fields = ("prediction_rows", "verified_predictions", "active_components",
                    "component_inputs", "raw_inputs")
    report = {
        "schema_version": SCHEMA, "domain": Domain.TENNIS.value, "root": str(root),
        "as_of": end.isoformat(), "relocation_roots": [str(item) for item in roots],
        "prediction_report_hash": prediction_report["content_hash"],
        "records_seen": len(records),
        "verified_bundles": sum(item["bundle_verified"] for item in records),
        **{key: sum(item[key] for item in records) for key in count_fields},
        "records": records,
        "feature_availability_verified": bool(records) and all(
            item["feature_availability_verified"] for item in records),
        "source_coverage_complete": False, "verified_monitoring_samples": None,
        "model_promotion_allowed": False,
    }
    report["content_hash"] = _hash(report)
    verify_tennis_feature_provenance_report(
        report, root=root, as_of=end, relocation_roots=roots,
    )
    return report


def verify_tennis_feature_provenance_report(report: dict, *, root: Path,
                                             as_of: datetime,
                                             relocation_roots: tuple[Path, ...]) -> None:
    _hashed(report, SCHEMA)
    roots = tuple(_safe(Path(item)) for item in relocation_roots)
    count_fields = ("prediction_rows", "verified_predictions", "active_components",
                    "component_inputs", "raw_inputs")
    expected = {
        "schema_version", "domain", "root", "as_of", "relocation_roots",
        "prediction_report_hash", "records_seen", "verified_bundles", *count_fields,
        "records", "feature_availability_verified", "source_coverage_complete",
        "verified_monitoring_samples", "model_promotion_allowed", "content_hash",
    }
    if (set(report) != expected or report["domain"] != Domain.TENNIS.value
            or report["root"] != str(_safe(root))
            or report["as_of"] != _at(as_of).isoformat()
            or report["relocation_roots"] != [str(item) for item in roots]
            or len(_encoded(report)) > 262144):
        raise ValueError("Tennis feature provenance report scope mismatch")
    _digest(report["prediction_report_hash"])
    if (report["source_coverage_complete"] is not False
            or report["verified_monitoring_samples"] is not None
            or report["model_promotion_allowed"] is not False
            or type(report["feature_availability_verified"]) is not bool):
        raise ValueError("Tennis feature report cannot grant sample authority")
    if not isinstance(report["records"], list) or len(report["records"]) > MAX_RECORDS:
        raise ValueError("invalid Tennis feature records")
    fields = {
        "record_id", "event_id", "source_cutoff_at", "snapshot_root",
        "bundle_verified", "feature_artifact", *count_fields,
        "feature_availability_verified", "blockers",
    }
    identities = set()
    for item in report["records"]:
        if (not isinstance(item, dict) or set(item) != fields
                or item["record_id"] in identities
                or not item["record_id"].startswith("wc:tennis:prediction:")
                or _at(item["source_cutoff_at"]) > _at(as_of)
                or type(item["bundle_verified"]) is not bool
                or type(item["feature_availability_verified"]) is not bool
                or not isinstance(item["blockers"], list)
                or item["blockers"] != [code for code in BLOCKER_ORDER if code in item["blockers"]]
                or len(item["blockers"]) != len(set(item["blockers"]))):
            raise ValueError("invalid Tennis feature projection")
        for key in count_fields:
            if type(item[key]) is not int or not 0 <= item[key] <= MAX_ROWS:
                raise ValueError("invalid Tennis feature count")
        if item["verified_predictions"] > item["prediction_rows"]:
            raise ValueError("Tennis verified prediction count mismatch")
        if item["snapshot_root"] is not None:
            _safe(Path(item["snapshot_root"]))
        if item["feature_artifact"] is not None:
            _safe(Path(item["feature_artifact"]))
        ready = (item["bundle_verified"] and item["prediction_rows"] > 0
                 and item["verified_predictions"] == item["prediction_rows"]
                 and not item["blockers"])
        if item["feature_availability_verified"] is not ready:
            raise ValueError("Tennis feature readiness mismatch")
        identities.add(item["record_id"])
    if (report["records_seen"] != len(report["records"])
            or report["verified_bundles"] != sum(item["bundle_verified"] for item in report["records"])
            or any(report[key] != sum(item[key] for item in report["records"])
                   for key in count_fields)
            or report["feature_availability_verified"] is not (
                bool(report["records"])
                and all(item["feature_availability_verified"] for item in report["records"]))):
        raise ValueError("Tennis feature aggregates mismatch")
