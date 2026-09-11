"""Read-only NBA game-level feature/source provenance inventory."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Callable

from .contracts import Domain
from .evidence import RecordKind
from .research_index import _Reader, _at, _encoded, _hash, _hashed, _safe
from .research_nba_settlement_source import _evidence
from .research_prediction_artifacts import _Blobs, inspect_prediction_artifacts
from .research_review_clock import _digest


SCHEMA = "wong-choi-nba-feature-provenance/v1"
FEATURE_SCHEMA = "wong-choi-nba-feature-evidence/v1"
FEATURE_CONTRACT = "nba-pregame-feature-v1"
FAMILIES = frozenset({
    "market", "player_form", "team_context", "schedule_context", "injury_context",
})
REQUIRED_AVAILABLE = frozenset({
    "market", "player_form", "team_context", "schedule_context",
})
BLOCKER_ORDER = (
    "prediction_bundle_unverified", "feature_artifact_missing",
    "feature_artifact_invalid", "game_rows_missing", "game_tag_set_mismatch",
    "feature_family_contract_incomplete", "feature_family_contract_invalid",
    "feature_source_missing", "feature_source_is_prediction_output",
    "feature_source_digest_mismatch", "feature_source_after_cutoff",
)
MAX_RECORDS = 10000
MAX_GAMES = 10000
TAG = re.compile(r"[A-Z0-9]{2,4}_[A-Z0-9]{2,4}")


def _source_valid(source: object, *, family: str, tag: str,
                  files: dict[str, str], cutoff: datetime,
                  blockers: set[str]) -> bool:
    if (not isinstance(source, dict)
            or set(source) != {"artifact", "sha256", "available_at", "field"}
            or not isinstance(source.get("artifact"), str)
            or Path(source["artifact"]).name != source["artifact"]
            or not isinstance(source.get("field"), str) or not source["field"].strip()):
        blockers.add("feature_family_contract_invalid")
        return False
    artifact = source["artifact"]
    expected = (f"Sportsbet_Odds_{tag}.json" if family == "market"
                else f"nba_game_data_{tag}.json")
    if artifact != expected:
        blockers.add("feature_source_is_prediction_output")
        return False
    try:
        _digest(source["sha256"])
        available = _at(source["available_at"])
    except (ValueError, RuntimeError, TypeError):
        blockers.add("feature_family_contract_invalid")
        return False
    if artifact not in files:
        blockers.add("feature_source_missing")
        return False
    if source["sha256"] != files[artifact]:
        blockers.add("feature_source_digest_mismatch")
        return False
    if available > cutoff:
        blockers.add("feature_source_after_cutoff")
        return False
    return True


def _families(value: object, *, tag: str, files: dict[str, str], cutoff: datetime,
              blockers: set[str]) -> tuple[int, int, bool]:
    if not isinstance(value, dict) or set(value) != FAMILIES:
        blockers.add("feature_family_contract_incomplete")
        return 0, 0, False
    available = unavailable = 0
    valid = True
    for name in sorted(FAMILIES):
        family = value[name]
        if not isinstance(family, dict):
            blockers.add("feature_family_contract_invalid")
            valid = False
            continue
        if family.get("status") == "available":
            available += 1
            if (set(family) != {"status", "derivation", "sources"}
                    or not isinstance(family.get("derivation"), str)
                    or not family["derivation"].strip()
                    or not isinstance(family.get("sources"), list)
                    or not family["sources"]):
                blockers.add("feature_family_contract_invalid")
                valid = False
                continue
            valid = all(_source_valid(item, family=name, tag=tag, files=files,
                                      cutoff=cutoff, blockers=blockers)
                        for item in family["sources"]) and valid
        elif family.get("status") == "unavailable":
            unavailable += 1
            if (set(family) != {"status", "reason", "sources"}
                    or not isinstance(family.get("reason"), str)
                    or not family["reason"].strip() or family.get("sources") != []
                    or name in REQUIRED_AVAILABLE):
                blockers.add("feature_family_contract_invalid")
                valid = False
        else:
            blockers.add("feature_family_contract_invalid")
            valid = False
    return available, unavailable, valid


def _projection(raw: bytes, *, event_id: str, cutoff: datetime,
                game_tags: set[str], files: dict[str, str]) -> tuple[list[dict], set[str]]:
    blockers: set[str] = set()
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeError):
        return [], {"feature_artifact_invalid"}
    if (not isinstance(payload, dict)
            or set(payload) != {"schema_version", "event_id", "generated_at", "rows"}
            or payload.get("schema_version") != FEATURE_SCHEMA
            or payload.get("event_id") != event_id
            or not isinstance(payload.get("rows"), list)):
        return [], {"feature_artifact_invalid"}
    try:
        if _at(payload["generated_at"]) != cutoff:
            blockers.add("feature_artifact_invalid")
    except (ValueError, RuntimeError, TypeError):
        blockers.add("feature_artifact_invalid")
    rows, seen = [], set()
    for row in payload["rows"]:
        row_blockers: set[str] = set()
        if (not isinstance(row, dict)
                or set(row) != {"game_tag", "feature_contract_id", "families"}
                or not isinstance(row.get("game_tag"), str)
                or not TAG.fullmatch(row["game_tag"])
                or row["game_tag"] in seen
                or row.get("feature_contract_id") != FEATURE_CONTRACT):
            blockers.add("feature_artifact_invalid")
            continue
        seen.add(row["game_tag"])
        available, unavailable, valid = _families(
            row["families"], tag=row["game_tag"], files=files,
            cutoff=cutoff, blockers=row_blockers,
        )
        rows.append({
            "game_tag": row["game_tag"], "available_families": available,
            "unavailable_families": unavailable,
            "verified": valid and not row_blockers,
            "blockers": [code for code in BLOCKER_ORDER if code in row_blockers],
        })
        blockers.update(row_blockers)
    if not game_tags:
        blockers.add("game_rows_missing")
    if seen != game_tags:
        blockers.add("game_tag_set_mismatch")
    if blockers.intersection({"game_rows_missing", "game_tag_set_mismatch"}):
        for row in rows:
            row["verified"] = False
    return rows, blockers


def inspect_nba_feature_provenance(*, root: Path, as_of: datetime,
                                   relocation_roots: tuple[Path, ...] = (),
                                   checkpoint: Callable[[], None] = lambda: None) -> dict:
    if not isinstance(relocation_roots, tuple):
        raise ValueError("tuple relocation roots required")
    root, end = _safe(root), _at(as_of)
    roots = tuple(_safe(Path(item)) for item in relocation_roots)
    prediction_report = inspect_prediction_artifacts(
        root=root, domain=Domain.NBA, as_of=end, relocation_roots=roots,
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
        rows: list[dict] = []
        feature_path = None
        if not bundle or item["resolved_snapshot_root"] is None:
            blockers.add("prediction_bundle_unverified")
        else:
            prediction = predictions[item["record_id"]]
            tags = {
                value.get("event_id") for value in prediction.body["recommendations"]
                if isinstance(value, dict) and isinstance(value.get("event_id"), str)
                and TAG.fullmatch(value["event_id"])
            }
            snapshot = _safe(Path(item["resolved_snapshot_root"]))
            manifest_raw, _manifest_digest, _manifest_size = blobs.read(snapshot / "manifest.json")
            try:
                manifest = json.loads(manifest_raw)
            except (ValueError, UnicodeError) as exc:
                raise ValueError("invalid NBA prediction manifest JSON") from exc
            files = {
                value["name"]: value["sha256"] for value in manifest.get("files", [])
                if isinstance(value, dict) and set(value) == {"name", "bytes", "sha256"}
            }
            if len(files) != len(manifest.get("files", [])):
                raise ValueError("invalid NBA prediction manifest file projection")
            feature_name = f"NBA_Feature_Evidence_{item['event_id']}.json"
            if feature_name not in files:
                blockers.add("feature_artifact_missing")
            else:
                feature_path = snapshot / feature_name
                raw, digest, _size = blobs.read(feature_path)
                if digest != files[feature_name]:
                    raise ValueError("NBA feature digest differs from verified manifest")
                rows, found = _projection(
                    raw, event_id=item["event_id"], cutoff=_at(item["source_cutoff_at"]),
                    game_tags=tags, files=files,
                )
                blockers.update(found)
        verified = sum(row["verified"] for row in rows)
        ready = bundle and bool(rows) and verified == len(rows) and not blockers
        records.append({
            "record_id": item["record_id"], "event_id": item["event_id"],
            "source_cutoff_at": item["source_cutoff_at"],
            "snapshot_root": item["resolved_snapshot_root"], "bundle_verified": bundle,
            "feature_artifact": str(feature_path) if feature_path else None,
            "games": len(rows), "verified_games": verified,
            "available_families": sum(row["available_families"] for row in rows),
            "unavailable_families": sum(row["unavailable_families"] for row in rows),
            "feature_availability_verified": ready,
            "blockers": [code for code in BLOCKER_ORDER if code in blockers],
        })
    blobs.recheck(); reader.recheck()
    counts = ("games", "verified_games", "available_families", "unavailable_families")
    report = {
        "schema_version": SCHEMA, "domain": Domain.NBA.value, "root": str(root),
        "as_of": end.isoformat(), "relocation_roots": [str(item) for item in roots],
        "prediction_report_hash": prediction_report["content_hash"],
        "records_seen": len(records),
        "verified_bundles": sum(item["bundle_verified"] for item in records),
        **{key: sum(item[key] for item in records) for key in counts},
        "records": records,
        "feature_availability_verified": bool(records) and all(
            item["feature_availability_verified"] for item in records),
        "source_coverage_complete": False, "verified_monitoring_samples": None,
        "model_promotion_allowed": False,
    }
    report["content_hash"] = _hash(report)
    verify_nba_feature_provenance_report(
        report, root=root, as_of=end, relocation_roots=roots,
    )
    return report


def verify_nba_feature_provenance_report(report: dict, *, root: Path,
                                          as_of: datetime,
                                          relocation_roots: tuple[Path, ...]) -> None:
    _hashed(report, SCHEMA)
    roots = tuple(_safe(Path(item)) for item in relocation_roots)
    counts = ("games", "verified_games", "available_families", "unavailable_families")
    expected = {
        "schema_version", "domain", "root", "as_of", "relocation_roots",
        "prediction_report_hash", "records_seen", "verified_bundles", *counts,
        "records", "feature_availability_verified", "source_coverage_complete",
        "verified_monitoring_samples", "model_promotion_allowed", "content_hash",
    }
    if (set(report) != expected or report["domain"] != Domain.NBA.value
            or report["root"] != str(_safe(root))
            or report["as_of"] != _at(as_of).isoformat()
            or report["relocation_roots"] != [str(item) for item in roots]
            or len(_encoded(report)) > 262144):
        raise ValueError("NBA feature provenance report scope mismatch")
    _digest(report["prediction_report_hash"])
    if (report["source_coverage_complete"] is not False
            or report["verified_monitoring_samples"] is not None
            or report["model_promotion_allowed"] is not False
            or type(report["feature_availability_verified"]) is not bool):
        raise ValueError("NBA feature report cannot grant sample authority")
    if not isinstance(report["records"], list) or len(report["records"]) > MAX_RECORDS:
        raise ValueError("invalid NBA feature records")
    fields = {
        "record_id", "event_id", "source_cutoff_at", "snapshot_root",
        "bundle_verified", "feature_artifact", *counts,
        "feature_availability_verified", "blockers",
    }
    identities = set()
    for item in report["records"]:
        if (not isinstance(item, dict) or set(item) != fields
                or item["record_id"] in identities
                or not item["record_id"].startswith("wc:nba:prediction:")
                or _at(item["source_cutoff_at"]) > _at(as_of)
                or type(item["bundle_verified"]) is not bool
                or type(item["feature_availability_verified"]) is not bool
                or not isinstance(item["blockers"], list)
                or item["blockers"] != [code for code in BLOCKER_ORDER if code in item["blockers"]]
                or len(item["blockers"]) != len(set(item["blockers"]))):
            raise ValueError("invalid NBA feature projection")
        for key in counts:
            if type(item[key]) is not int or not 0 <= item[key] <= MAX_GAMES * len(FAMILIES):
                raise ValueError("invalid NBA feature count")
        if (item["verified_games"] > item["games"]
                or item["available_families"] + item["unavailable_families"]
                > item["games"] * len(FAMILIES)):
            raise ValueError("NBA feature count mismatch")
        if item["snapshot_root"] is not None:
            _safe(Path(item["snapshot_root"]))
        if item["feature_artifact"] is not None:
            _safe(Path(item["feature_artifact"]))
        ready = (item["bundle_verified"] and item["games"] > 0
                 and item["verified_games"] == item["games"] and not item["blockers"])
        if item["feature_availability_verified"] is not ready:
            raise ValueError("NBA feature readiness mismatch")
        identities.add(item["record_id"])
    if (report["records_seen"] != len(report["records"])
            or report["verified_bundles"] != sum(item["bundle_verified"] for item in report["records"])
            or any(report[key] != sum(item[key] for item in report["records"])
                   for key in counts)
            or report["feature_availability_verified"] is not (
                bool(report["records"])
                and all(item["feature_availability_verified"] for item in report["records"]))):
        raise ValueError("NBA feature aggregates mismatch")
