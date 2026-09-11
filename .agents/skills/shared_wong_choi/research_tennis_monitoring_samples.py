"""Join Tennis labels, PIT features and immutable family cohorts into samples."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Callable

from .contracts import Domain
from .research_index import _Reader, _at, _encoded, _hash, _hashed, _safe
from .research_prediction_artifacts import _Blobs, inspect_prediction_artifacts
from .research_review_clock import SampleSnapshot, _digest
from .research_tennis_feature_provenance import inspect_tennis_feature_provenance
from .research_tennis_settlement_source import (
    _evidence,
    inspect_tennis_settlement_candidates,
)


SCHEMA = "wong-choi-tennis-monitoring-samples/v1"
COHORT_SCHEMA = "wong-choi-tennis-cohort-evidence/v1"
MAX_SETTLEMENTS = 1000
MAX_PREDICTIONS = 100000
TEXT = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")
SURFACES = frozenset({"hard", "clay", "grass", "carpet"})
TOURS = frozenset({"ATP", "WTA"})
BLOCKER_ORDER = (
    "prediction_bundle_unverified",
    "label_source_unverified",
    "feature_record_missing",
    "feature_availability_unverified",
    "cohort_artifact_missing",
    "cohort_artifact_invalid",
    "cohort_prediction_mismatch",
    "cohort_family_invalid",
)


def _digest_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _cohorts(raw: bytes, *, event_id: str, cutoff: datetime,
             prediction_ids: set[int]) -> tuple[list[dict], list[str]]:
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError):
        return [], ["cohort_artifact_invalid"]
    if (not isinstance(value, dict)
            or set(value) != {"schema_version", "event_id", "generated_at", "rows"}
            or value.get("schema_version") != COHORT_SCHEMA
            or value.get("event_id") != event_id
            or not isinstance(value.get("rows"), list)):
        return [], ["cohort_artifact_invalid"]
    try:
        if _at(value["generated_at"]) != cutoff:
            return [], ["cohort_artifact_invalid"]
    except (ValueError, RuntimeError, TypeError):
        return [], ["cohort_artifact_invalid"]
    rows, seen, problems = [], set(), set()
    fields = {
        "prediction_id", "family", "tour", "surface", "tournament_level",
        "odds_bucket",
    }
    for row in value["rows"]:
        if (not isinstance(row, dict) or set(row) != fields
                or type(row.get("prediction_id")) is not int
                or row["prediction_id"] <= 0 or row["prediction_id"] in seen
                or row.get("tour") not in TOURS
                or row.get("surface") not in SURFACES
                or not isinstance(row.get("tournament_level"), str)
                or TEXT.fullmatch(row["tournament_level"]) is None
                or not isinstance(row.get("odds_bucket"), str)
                or TEXT.fullmatch(row["odds_bucket"]) is None):
            problems.add("cohort_artifact_invalid")
            continue
        expected_family = f"match_winner_{row['tour'].lower()}"
        if row.get("family") != expected_family:
            problems.add("cohort_family_invalid")
        seen.add(row["prediction_id"])
        rows.append(dict(row))
    if seen != prediction_ids:
        problems.add("cohort_prediction_mismatch")
    return rows, [code for code in BLOCKER_ORDER if code in problems]


def _build_report(*, root: Path, as_of: datetime,
                  relocation_roots: tuple[Path, ...],
                  checkpoint: Callable[[], None]) -> dict:
    if not isinstance(relocation_roots, tuple):
        raise ValueError("tuple relocation roots required")
    evidence_root, end = _safe(root), _at(as_of)
    roots = tuple(_safe(Path(item)) for item in relocation_roots)
    common = dict(root=evidence_root, as_of=end, relocation_roots=roots,
                  checkpoint=checkpoint)
    settlements = inspect_tennis_settlement_candidates(**common)
    features = inspect_tennis_feature_provenance(**common)
    predictions = inspect_prediction_artifacts(
        root=evidence_root, domain=Domain.TENNIS, as_of=end,
        relocation_roots=roots, checkpoint=checkpoint,
    )
    if len({settlements["prediction_report_hash"],
            features["prediction_report_hash"], predictions["content_hash"]}) != 1:
        raise ValueError("Tennis source inventories do not share prediction evidence")
    feature_records = {item["record_id"]: item for item in features["records"]}
    prediction_records = {item["record_id"]: item for item in predictions["records"]}
    if (len(feature_records) != len(features["records"])
            or len(prediction_records) != len(predictions["records"])):
        raise ValueError("duplicate Tennis prediction identity")
    reader, blobs = _Reader(checkpoint), _Blobs(checkpoint)
    evidence = _evidence(evidence_root, end, reader)
    units, candidates = [], []
    for candidate in settlements["candidates"]:
        checkpoint()
        prediction = evidence[candidate["prediction_id"]]
        feature = feature_records.get(candidate["prediction_id"])
        bundle = prediction_records.get(candidate["prediction_id"])
        blockers = []
        if not candidate["prediction_bundle_verified"]:
            blockers.append("prediction_bundle_unverified")
        if not candidate["label_source_verified"]:
            blockers.append("label_source_unverified")
        if feature is None:
            blockers.append("feature_record_missing")
        elif not feature["feature_availability_verified"]:
            blockers.append("feature_availability_unverified")
        cohort_rows, cohort_digest = [], None
        cohort_name = f"Tennis_Cohort_Evidence_{candidate['event_id']}.json"
        if (bundle is None or not bundle["snapshot_bundle_verified"]
                or bundle["resolved_snapshot_root"] is None):
            blockers.append("cohort_artifact_missing")
        else:
            snapshot = _safe(Path(bundle["resolved_snapshot_root"]))
            manifest_raw, _manifest_digest, _size = blobs.read(snapshot / "manifest.json")
            manifest = json.loads(manifest_raw)
            files = {
                item["name"]: item["sha256"] for item in manifest.get("files", [])
                if isinstance(item, dict) and set(item) == {"name", "bytes", "sha256"}
            }
            if cohort_name not in files:
                blockers.append("cohort_artifact_missing")
            else:
                cohort_raw, cohort_digest, _size = blobs.read(snapshot / cohort_name)
                if cohort_digest != files[cohort_name]:
                    raise ValueError("Tennis cohort digest differs from manifest")
                recommendation_ids = {
                    item.get("id") for item in prediction.body["recommendations"]
                    if isinstance(item, dict) and type(item.get("id")) is int
                    and item["id"] > 0
                }
                cohort_rows, problems = _cohorts(
                    cohort_raw, event_id=candidate["event_id"],
                    cutoff=_at(prediction.body["source_cutoff_at"]),
                    prediction_ids=recommendation_ids,
                )
                blockers.extend(problems)
        outcome_digest = None
        if candidate["label_source_verified"]:
            if candidate["referenced_outcome_artifact"] is None:
                raise ValueError("verified Tennis label has no outcome artifact")
            outcome_digest = _digest_file(_safe(Path(
                candidate["referenced_outcome_artifact"]
            )))
        blockers = [code for code in BLOCKER_ORDER if code in blockers]
        prediction_ids = []
        if not blockers:
            prediction_ids = sorted(item["prediction_id"] for item in cohort_rows)
            for item in cohort_rows:
                units.append({
                    "unit_id": (f"{candidate['prediction_id']}:prediction:"
                                f"{item['prediction_id']}"),
                    "prediction_row_id": item["prediction_id"],
                    "prediction_id": candidate["prediction_id"],
                    "settlement_id": candidate["settlement_id"],
                    "event_id": candidate["event_id"],
                    "family": item["family"],
                    "settled_at": _at(candidate["created_at"]).isoformat(),
                    "cohort_artifact_sha256": cohort_digest,
                    "outcome_artifact_sha256": outcome_digest,
                })
        candidates.append({
            "settlement_id": candidate["settlement_id"],
            "prediction_id": candidate["prediction_id"],
            "event_id": candidate["event_id"],
            "prediction_row_ids": prediction_ids,
            "cohort_artifact_sha256": cohort_digest if not blockers else None,
            "outcome_artifact_sha256": outcome_digest if not blockers else None,
            "blockers": blockers,
        })
    blobs.recheck(); reader.recheck()
    units.sort(key=lambda item: item["unit_id"])
    candidates.sort(key=lambda item: item["settlement_id"])
    if len(candidates) > MAX_SETTLEMENTS or len(units) > MAX_PREDICTIONS:
        raise ValueError("Tennis monitoring sample bound exceeded")
    families = sorted({item["family"] for item in units})
    report = {
        "schema_version": SCHEMA,
        "domain": Domain.TENNIS.value,
        "root": str(evidence_root),
        "as_of": end.isoformat(),
        "relocation_roots": [str(item) for item in roots],
        "prediction_report_hash": predictions["content_hash"],
        "settlement_report_hash": settlements["content_hash"],
        "feature_report_hash": features["content_hash"],
        "candidate_settlements": len(candidates),
        "qualified_settlements": sum(not item["blockers"] for item in candidates),
        "blocked_settlements": sum(bool(item["blockers"]) for item in candidates),
        "qualified_predictions": len(units),
        "families": families,
        "candidates": candidates,
        "units": units,
        "basis": "verified_pit_outcomes",
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


def inspect_tennis_monitoring_samples(
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
        "qualified_predictions", "families", "candidates", "units", "basis",
        "source_coverage_complete", "verified_monitoring_samples",
        "terminal_labels_emitted", "sample_trigger_only", "model_promotion_allowed",
        "reevaluate_promotion_allowed", "content_hash",
    }
    roots = tuple(_safe(Path(item)) for item in relocation_roots)
    if (set(report) != expected or report["domain"] != Domain.TENNIS.value
            or report["root"] != str(_safe(root))
            or report["as_of"] != _at(as_of).isoformat()
            or report["relocation_roots"] != [str(item) for item in roots]
            or report["basis"] != "verified_pit_outcomes"
            or len(_encoded(report)) > 1048576):
        raise ValueError("Tennis monitoring sample report scope mismatch")
    for key in ("prediction_report_hash", "settlement_report_hash", "feature_report_hash"):
        _digest(report[key])
    if (report["terminal_labels_emitted"] is not False
            or report["sample_trigger_only"] is not True
            or report["model_promotion_allowed"] is not False
            or report["reevaluate_promotion_allowed"] is not False):
        raise ValueError("Tennis samples cannot grant terminal or model authority")
    counts = (
        "candidate_settlements", "qualified_settlements", "blocked_settlements",
        "qualified_predictions", "verified_monitoring_samples",
    )
    if any(type(report[key]) is not int or not 0 <= report[key] <= MAX_PREDICTIONS
           for key in counts):
        raise ValueError("invalid Tennis monitoring sample count")
    if (not isinstance(report["families"], list)
            or report["families"] != sorted(set(report["families"]))
            or not isinstance(report["candidates"], list)
            or not isinstance(report["units"], list)
            or report["candidate_settlements"] != len(report["candidates"])
            or report["qualified_predictions"] != len(report["units"])
            or report["verified_monitoring_samples"] != len(report["units"])
            or report["qualified_settlements"] + report["blocked_settlements"]
            != len(report["candidates"])):
        raise ValueError("Tennis monitoring sample aggregate mismatch")
    candidate_fields = {
        "settlement_id", "prediction_id", "event_id", "prediction_row_ids",
        "cohort_artifact_sha256", "outcome_artifact_sha256", "blockers",
    }
    settlement_ids = set()
    for item in report["candidates"]:
        if (not isinstance(item, dict) or set(item) != candidate_fields
                or item["settlement_id"] in settlement_ids
                or not item["settlement_id"].startswith("wc:tennis:settlement:")
                or not item["prediction_id"].startswith("wc:tennis:prediction:")
                or not isinstance(item["prediction_row_ids"], list)
                or item["prediction_row_ids"] != sorted(set(item["prediction_row_ids"]))
                or item["blockers"] != [code for code in BLOCKER_ORDER
                                         if code in item["blockers"]]
                or len(item["blockers"]) != len(set(item["blockers"]))):
            raise ValueError("invalid Tennis monitoring settlement projection")
        if item["blockers"]:
            if (item["prediction_row_ids"]
                    or item["cohort_artifact_sha256"] is not None
                    or item["outcome_artifact_sha256"] is not None):
                raise ValueError("blocked Tennis settlement exposed sample evidence")
        else:
            if not item["prediction_row_ids"]:
                raise ValueError("qualified Tennis settlement has no predictions")
            _digest(item["cohort_artifact_sha256"])
            _digest(item["outcome_artifact_sha256"])
        settlement_ids.add(item["settlement_id"])
    unit_fields = {
        "unit_id", "prediction_row_id", "prediction_id", "settlement_id",
        "event_id", "family", "settled_at", "cohort_artifact_sha256",
        "outcome_artifact_sha256",
    }
    unit_ids = set()
    for item in report["units"]:
        expected_id = (f"{item.get('prediction_id')}:prediction:"
                       f"{item.get('prediction_row_id')}")
        if (not isinstance(item, dict) or set(item) != unit_fields
                or item["unit_id"] != expected_id or item["unit_id"] in unit_ids
                or item["settlement_id"] not in settlement_ids
                or item["family"] not in {"match_winner_atp", "match_winner_wta"}
                or _at(item["settled_at"]) > _at(as_of)):
            raise ValueError("invalid Tennis family monitoring unit")
        _digest(item["cohort_artifact_sha256"])
        _digest(item["outcome_artifact_sha256"])
        unit_ids.add(item["unit_id"])
    if report["families"] != sorted({item["family"] for item in report["units"]}):
        raise ValueError("Tennis monitoring family aggregate mismatch")
    complete = bool(report["candidates"]) and report["blocked_settlements"] == 0
    if report["source_coverage_complete"] is not complete:
        raise ValueError("Tennis monitoring source coverage mismatch")


def verify_tennis_monitoring_sample_report(
    report: dict, *, root: Path, as_of: datetime,
    relocation_roots: tuple[Path, ...] = (),
) -> None:
    _verify_shape(report, root=root, as_of=as_of,
                  relocation_roots=relocation_roots)
    rebuilt = _build_report(root=root, as_of=as_of,
                            relocation_roots=relocation_roots,
                            checkpoint=lambda: None)
    if _encoded(report) != _encoded(rebuilt):
        raise ValueError("Tennis monitoring sample report differs from source evidence")


def monitoring_sample_snapshots(report: dict) -> tuple[SampleSnapshot, ...]:
    roots = tuple(Path(item) for item in report.get("relocation_roots", ()))
    verify_tennis_monitoring_sample_report(
        report, root=Path(report.get("root", "")), as_of=_at(report.get("as_of")),
        relocation_roots=roots,
    )
    return tuple(
        SampleSnapshot(
            domain=Domain.TENNIS, scope=family, basis="verified_pit_outcomes",
            observed_at=_at(report["as_of"]), evidence_digest=report["content_hash"],
            unit_ids=frozenset(item["unit_id"] for item in report["units"]
                               if item["family"] == family),
        )
        for family in report["families"]
    )
