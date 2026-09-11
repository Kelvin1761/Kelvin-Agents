"""Derive NBA forward-settled recommendation identities from verified evidence.

The projection joins an immutable pre-game recommendation contract, verified
pregame feature provenance and hash-pinned post-game prop verification.  It
emits identities only: no hit/miss labels, inputs, scores or promotion authority.
"""
from __future__ import annotations

import json
import math
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

from .contracts import Domain
from .evidence import RecordKind
from .research_index import _Reader, _at, _encoded, _hash, _hashed, _safe
from .research_nba_feature_provenance import inspect_nba_feature_provenance
from .research_nba_settlement_source import (
    _evidence,
    inspect_nba_settlement_candidates,
)
from .research_prediction_artifacts import _Blobs, inspect_prediction_artifacts
from .research_review_clock import SampleSnapshot, _digest


SCHEMA = "wong-choi-nba-monitoring-samples/v1"
RECOMMENDATION_SCHEMA = "wong-choi-nba-recommendation-evidence/v1"
MAX_SETTLEMENTS = 1000
MAX_RECOMMENDATIONS = 10000
IDENTITY = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}")
TAG = re.compile(r"[A-Z0-9]{2,4}_[A-Z0-9]{2,4}")
BLOCKER_ORDER = (
    "prediction_bundle_unverified",
    "label_source_unverified",
    "feature_record_missing",
    "feature_availability_unverified",
    "recommendation_projection_missing",
    "recommendation_projection_invalid",
    "recommendation_result_mismatch",
)


def _number(value: object) -> bool:
    return type(value) in {int, float} and math.isfinite(float(value))


def _recommendations(raw: bytes, *, event_id: str, cutoff: datetime,
                     game_tags: set[str]) -> tuple[list[dict], str | None]:
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError):
        return [], "recommendation_projection_invalid"
    if (not isinstance(value, dict)
            or set(value) != {
                "schema_version", "event_id", "generated_at", "recommendations"
            }
            or value.get("schema_version") != RECOMMENDATION_SCHEMA
            or value.get("event_id") != event_id
            or not isinstance(value.get("recommendations"), list)):
        return [], "recommendation_projection_invalid"
    try:
        if _at(value["generated_at"]) != cutoff:
            return [], "recommendation_projection_invalid"
    except (ValueError, RuntimeError, TypeError):
        return [], "recommendation_projection_invalid"
    rows, ids, keys, tags = [], set(), set(), set()
    fields = {
        "recommendation_id", "game_tag", "player", "stat", "line", "side"
    }
    for row in value["recommendations"]:
        if (not isinstance(row, dict) or set(row) != fields
                or not isinstance(row.get("recommendation_id"), str)
                or IDENTITY.fullmatch(row["recommendation_id"]) is None
                or row["recommendation_id"] in ids
                or not isinstance(row.get("game_tag"), str)
                or TAG.fullmatch(row["game_tag"]) is None
                or row["game_tag"] not in game_tags
                or not isinstance(row.get("player"), str) or not row["player"].strip()
                or not isinstance(row.get("stat"), str) or not row["stat"].strip()
                or not _number(row.get("line")) or row.get("side") != "over"):
            return [], "recommendation_projection_invalid"
        key = (row["player"].strip(), row["stat"].strip(), float(row["line"]))
        if key in keys:
            return [], "recommendation_projection_invalid"
        ids.add(row["recommendation_id"]); keys.add(key); tags.add(row["game_tag"])
        rows.append({**row, "player": key[0], "stat": key[1], "line": key[2]})
    if not rows or tags != game_tags:
        return [], "recommendation_projection_invalid"
    return rows, None


def _settled_keys(raw: bytes) -> tuple[set[tuple[str, str, float]], bool]:
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError):
        return set(), False
    summary, legs = value.get("summary"), value.get("legs")
    if (value.get("_version") != "PROPS_VERIFICATION_V1"
            or not isinstance(summary, dict) or not isinstance(legs, list)
            or type(summary.get("total_legs")) is not int
            or summary["total_legs"] <= 0 or summary.get("unverified") != 0
            or len(legs) != summary["total_legs"]):
        return set(), False
    keys = set()
    for leg in legs:
        if (not isinstance(leg, dict)
                or not isinstance(leg.get("player"), str) or not leg["player"].strip()
                or not isinstance(leg.get("stat"), str) or not leg["stat"].strip()
                or not _number(leg.get("line")) or not _number(leg.get("actual"))
                or type(leg.get("cleared")) is not bool
                or leg.get("outcome") == "void"
                or leg["cleared"] != (float(leg["actual"]) >= float(leg["line"]))):
            return set(), False
        key = (leg["player"].strip(), leg["stat"].strip(), float(leg["line"]))
        if key in keys:
            return set(), False
        keys.add(key)
    return keys, True


def _build_report(*, root: Path, as_of: datetime,
                  relocation_roots: tuple[Path, ...],
                  checkpoint: Callable[[], None]) -> dict:
    if not isinstance(relocation_roots, tuple):
        raise ValueError("tuple relocation roots required")
    evidence_root, end = _safe(root), _at(as_of)
    roots = tuple(_safe(Path(item)) for item in relocation_roots)
    common = dict(root=evidence_root, as_of=end, relocation_roots=roots,
                  checkpoint=checkpoint)
    settlements = inspect_nba_settlement_candidates(**common)
    features = inspect_nba_feature_provenance(**common)
    predictions = inspect_prediction_artifacts(
        root=evidence_root, domain=Domain.NBA, as_of=end,
        relocation_roots=roots, checkpoint=checkpoint,
    )
    hashes = {
        settlements["prediction_report_hash"],
        features["prediction_report_hash"], predictions["content_hash"],
    }
    if len(hashes) != 1:
        raise ValueError("NBA label and feature inventories do not share predictions")
    feature_records = {item["record_id"]: item for item in features["records"]}
    prediction_records = {item["record_id"]: item for item in predictions["records"]}
    if (len(feature_records) != len(features["records"])
            or len(prediction_records) != len(predictions["records"])):
        raise ValueError("duplicate NBA prediction identity")
    reader, blobs = _Reader(checkpoint), _Blobs(checkpoint)
    evidence = _evidence(evidence_root, end, reader)

    units, candidates = [], []
    for candidate in settlements["candidates"]:
        checkpoint()
        blockers = []
        prediction = evidence[candidate["prediction_id"]]
        feature = feature_records.get(candidate["prediction_id"])
        bundle = prediction_records.get(candidate["prediction_id"])
        if not candidate["prediction_bundle_verified"]:
            blockers.append("prediction_bundle_unverified")
        if not candidate["label_source_verified"]:
            blockers.append("label_source_unverified")
        if feature is None:
            blockers.append("feature_record_missing")
        elif not feature["feature_availability_verified"]:
            blockers.append("feature_availability_unverified")

        recommendation_rows, recommendation_digest = [], None
        projection_name = f"NBA_Recommendation_Evidence_{candidate['event_id']}.json"
        if (bundle is None or not bundle["snapshot_bundle_verified"]
                or bundle["resolved_snapshot_root"] is None):
            blockers.append("recommendation_projection_missing")
        else:
            snapshot = _safe(Path(bundle["resolved_snapshot_root"]))
            manifest_raw, _digest_value, _size = blobs.read(snapshot / "manifest.json")
            manifest = json.loads(manifest_raw)
            files = {
                item["name"]: item["sha256"] for item in manifest.get("files", [])
                if isinstance(item, dict) and set(item) == {"name", "bytes", "sha256"}
            }
            if projection_name not in files:
                blockers.append("recommendation_projection_missing")
            else:
                projection_raw, recommendation_digest, _size = blobs.read(
                    snapshot / projection_name
                )
                if recommendation_digest != files[projection_name]:
                    raise ValueError("NBA recommendation digest differs from manifest")
                game_tags = {
                    item.get("event_id") for item in prediction.body["recommendations"]
                    if isinstance(item, dict) and isinstance(item.get("event_id"), str)
                    and TAG.fullmatch(item["event_id"])
                }
                recommendation_rows, problem = _recommendations(
                    projection_raw, event_id=candidate["event_id"],
                    cutoff=_at(prediction.body["source_cutoff_at"]),
                    game_tags=game_tags,
                )
                if problem is not None:
                    blockers.append(problem)

        result_digest = None
        if candidate["label_source_verified"]:
            settlement = evidence[candidate["settlement_id"]]
            try:
                us_date = (date.fromisoformat(candidate["event_id"])
                           - timedelta(days=1)).isoformat()
            except ValueError:
                us_date = "invalid"
            verification_name = f"Props_Verification_{us_date}.json"
            matching = [item for item in settlement.artifacts
                        if Path(item.path).name == verification_name]
            if len(matching) != 1:
                raise ValueError("verified NBA label has no unique verification artifact")
            verification_raw, result_digest, _size = blobs.read(Path(matching[0].path))
            result_keys, complete = _settled_keys(verification_raw)
            recommendation_keys = {
                (item["player"], item["stat"], item["line"])
                for item in recommendation_rows
            }
            if not complete or recommendation_keys != result_keys:
                blockers.append("recommendation_result_mismatch")

        blockers = [code for code in BLOCKER_ORDER if code in blockers]
        recommendation_ids = []
        if not blockers:
            recommendation_ids = sorted(
                item["recommendation_id"] for item in recommendation_rows
            )
            for identity in recommendation_ids:
                units.append({
                    "unit_id": f"{candidate['prediction_id']}:recommendation:{identity}",
                    "recommendation_id": identity,
                    "prediction_id": candidate["prediction_id"],
                    "settlement_id": candidate["settlement_id"],
                    "event_id": candidate["event_id"],
                    "settled_at": _at(candidate["created_at"]).isoformat(),
                    "recommendation_artifact_sha256": recommendation_digest,
                    "result_artifact_sha256": result_digest,
                })
        candidates.append({
            "settlement_id": candidate["settlement_id"],
            "prediction_id": candidate["prediction_id"],
            "event_id": candidate["event_id"],
            "recommendation_ids": recommendation_ids,
            "recommendation_artifact_sha256": (
                recommendation_digest if not blockers else None
            ),
            "result_artifact_sha256": result_digest if not blockers else None,
            "blockers": blockers,
        })
    blobs.recheck(); reader.recheck()
    units.sort(key=lambda item: item["unit_id"])
    candidates.sort(key=lambda item: item["settlement_id"])
    if len(candidates) > MAX_SETTLEMENTS or len(units) > MAX_RECOMMENDATIONS:
        raise ValueError("NBA monitoring sample bound exceeded")
    report = {
        "schema_version": SCHEMA,
        "domain": Domain.NBA.value,
        "root": str(evidence_root),
        "as_of": end.isoformat(),
        "relocation_roots": [str(item) for item in roots],
        "prediction_report_hash": predictions["content_hash"],
        "settlement_report_hash": settlements["content_hash"],
        "feature_report_hash": features["content_hash"],
        "candidate_settlements": len(candidates),
        "qualified_settlements": sum(not item["blockers"] for item in candidates),
        "blocked_settlements": sum(bool(item["blockers"]) for item in candidates),
        "qualified_recommendations": len(units),
        "candidates": candidates,
        "units": units,
        "basis": "forward_settled_recommendations",
        "scope": "all",
        "source_coverage_complete": bool(candidates) and not any(
            item["blockers"] for item in candidates
        ),
        "verified_monitoring_samples": len(units),
        "terminal_labels_emitted": False,
        "sample_trigger_only": True,
        "model_promotion_allowed": False,
        "reevaluate_promotion_allowed": False,
    }
    report["content_hash"] = _hash(report)
    _verify_shape(report, root=evidence_root, as_of=end, relocation_roots=roots)
    return report


def inspect_nba_monitoring_samples(
    *, root: Path, as_of: datetime,
    relocation_roots: tuple[Path, ...] = (),
    checkpoint: Callable[[], None] = lambda: None,
) -> dict:
    return _build_report(root=root, as_of=as_of,
                         relocation_roots=relocation_roots,
                         checkpoint=checkpoint)


def _verify_shape(report: dict, *, root: Path, as_of: datetime,
                  relocation_roots: tuple[Path, ...]) -> None:
    _hashed(report, SCHEMA)
    expected = {
        "schema_version", "domain", "root", "as_of", "relocation_roots",
        "prediction_report_hash", "settlement_report_hash", "feature_report_hash",
        "candidate_settlements", "qualified_settlements", "blocked_settlements",
        "qualified_recommendations", "candidates", "units", "basis", "scope",
        "source_coverage_complete", "verified_monitoring_samples",
        "terminal_labels_emitted", "sample_trigger_only", "model_promotion_allowed",
        "reevaluate_promotion_allowed", "content_hash",
    }
    roots = tuple(_safe(Path(item)) for item in relocation_roots)
    if (set(report) != expected or report["domain"] != Domain.NBA.value
            or report["root"] != str(_safe(root))
            or report["as_of"] != _at(as_of).isoformat()
            or report["relocation_roots"] != [str(item) for item in roots]
            or report["basis"] != "forward_settled_recommendations"
            or report["scope"] != "all" or len(_encoded(report)) > 1048576):
        raise ValueError("NBA monitoring sample report scope mismatch")
    for key in ("prediction_report_hash", "settlement_report_hash", "feature_report_hash"):
        _digest(report[key])
    if (report["terminal_labels_emitted"] is not False
            or report["sample_trigger_only"] is not True
            or report["model_promotion_allowed"] is not False
            or report["reevaluate_promotion_allowed"] is not False):
        raise ValueError("NBA samples cannot grant terminal or model authority")
    counts = (
        "candidate_settlements", "qualified_settlements", "blocked_settlements",
        "qualified_recommendations", "verified_monitoring_samples",
    )
    if any(type(report[key]) is not int or not 0 <= report[key] <= MAX_RECOMMENDATIONS
           for key in counts):
        raise ValueError("invalid NBA monitoring sample count")
    if (not isinstance(report["candidates"], list)
            or not isinstance(report["units"], list)
            or report["candidate_settlements"] != len(report["candidates"])
            or report["qualified_recommendations"] != len(report["units"])
            or report["verified_monitoring_samples"] != len(report["units"])
            or report["qualified_settlements"] + report["blocked_settlements"]
            != len(report["candidates"])):
        raise ValueError("NBA monitoring sample aggregate mismatch")
    candidate_fields = {
        "settlement_id", "prediction_id", "event_id", "recommendation_ids",
        "recommendation_artifact_sha256", "result_artifact_sha256", "blockers",
    }
    settlement_ids = set()
    for item in report["candidates"]:
        if (not isinstance(item, dict) or set(item) != candidate_fields
                or item["settlement_id"] in settlement_ids
                or not item["settlement_id"].startswith("wc:nba:settlement:")
                or not item["prediction_id"].startswith("wc:nba:prediction:")
                or not isinstance(item["recommendation_ids"], list)
                or item["recommendation_ids"] != sorted(set(item["recommendation_ids"]))
                or item["blockers"] != [code for code in BLOCKER_ORDER
                                         if code in item["blockers"]]
                or len(item["blockers"]) != len(set(item["blockers"]))):
            raise ValueError("invalid NBA monitoring settlement projection")
        if item["blockers"]:
            if (item["recommendation_ids"]
                    or item["recommendation_artifact_sha256"] is not None
                    or item["result_artifact_sha256"] is not None):
                raise ValueError("blocked NBA settlement exposed sample evidence")
        else:
            if not item["recommendation_ids"]:
                raise ValueError("qualified NBA settlement has no recommendations")
            _digest(item["recommendation_artifact_sha256"])
            _digest(item["result_artifact_sha256"])
        settlement_ids.add(item["settlement_id"])
    unit_fields = {
        "unit_id", "recommendation_id", "prediction_id", "settlement_id",
        "event_id", "settled_at", "recommendation_artifact_sha256",
        "result_artifact_sha256",
    }
    unit_ids = set()
    for item in report["units"]:
        expected_id = (f"{item.get('prediction_id')}:recommendation:"
                       f"{item.get('recommendation_id')}")
        if (not isinstance(item, dict) or set(item) != unit_fields
                or item["unit_id"] != expected_id or item["unit_id"] in unit_ids
                or item["settlement_id"] not in settlement_ids
                or _at(item["settled_at"]) > _at(as_of)):
            raise ValueError("invalid NBA forward recommendation unit")
        _digest(item["recommendation_artifact_sha256"])
        _digest(item["result_artifact_sha256"])
        unit_ids.add(item["unit_id"])
    complete = bool(report["candidates"]) and report["blocked_settlements"] == 0
    if report["source_coverage_complete"] is not complete:
        raise ValueError("NBA monitoring source coverage mismatch")


def verify_nba_monitoring_sample_report(
    report: dict, *, root: Path, as_of: datetime,
    relocation_roots: tuple[Path, ...] = (),
) -> None:
    _verify_shape(report, root=root, as_of=as_of,
                  relocation_roots=relocation_roots)
    rebuilt = _build_report(root=root, as_of=as_of,
                            relocation_roots=relocation_roots,
                            checkpoint=lambda: None)
    if _encoded(report) != _encoded(rebuilt):
        raise ValueError("NBA monitoring sample report differs from source evidence")


def monitoring_sample_snapshot(report: dict) -> SampleSnapshot:
    roots = tuple(Path(item) for item in report.get("relocation_roots", ()))
    verify_nba_monitoring_sample_report(
        report, root=Path(report.get("root", "")), as_of=_at(report.get("as_of")),
        relocation_roots=roots,
    )
    return SampleSnapshot(
        domain=Domain.NBA, scope="all", basis="forward_settled_recommendations",
        observed_at=_at(report["as_of"]), evidence_digest=report["content_hash"],
        unit_ids=frozenset(item["unit_id"] for item in report["units"]),
    )
