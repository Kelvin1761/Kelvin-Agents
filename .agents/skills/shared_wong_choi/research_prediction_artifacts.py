"""Read-only resolution of immutable prediction bundles after meeting relocation.

An explicit relocation root may recover an artifact only at
``ROOT / event_id / <original path below the event folder>``. There is no
basename/hash search and no source repair. Bundle integrity is a prerequisite,
not point-in-time feature provenance, a settled sample, or model authority.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from datetime import datetime
from pathlib import Path
from typing import Callable
from urllib.parse import quote, unquote

from .contracts import Domain
from .evidence import ArtifactRef, EvidenceRecord, RecordKind
from .research_index import _Reader, _at, _encoded, _hash, _hashed, _safe


SCHEMA = "wong-choi-prediction-artifact-resolution/v1"
MAX_ARTIFACTS = 5000
MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_TOTAL_BYTES = 512 * 1024 * 1024


class _Blobs:
    def __init__(self, checkpoint: Callable[[], None]):
        self.checkpoint = checkpoint
        self.files: dict[Path, tuple[str, int]] = {}
        self.bytes_read = 0

    def read(self, path: Path) -> tuple[bytes, str, int]:
        self.checkpoint()
        path = _safe(path)
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or not 0 <= info.st_size <= MAX_FILE_BYTES:
                raise ValueError("prediction artifact type or size limit")
            chunks, length = [], 0
            while True:
                self.checkpoint()
                chunk = os.read(descriptor, min(1024 * 1024, MAX_FILE_BYTES - length + 1))
                if not chunk:
                    break
                length += len(chunk)
                self.bytes_read += len(chunk)
                if length > MAX_FILE_BYTES or self.bytes_read > MAX_TOTAL_BYTES:
                    raise ValueError("prediction artifact read budget exceeded")
                chunks.append(chunk)
        finally:
            os.close(descriptor)
        raw = b"".join(chunks)
        digest = hashlib.sha256(raw).hexdigest()
        prior = self.files.get(path)
        if prior is not None and prior != (digest, len(raw)):
            raise ValueError("prediction artifact changed during inspection")
        self.files[path] = (digest, len(raw))
        return raw, digest, len(raw)

    def recheck(self) -> None:
        for path, expected in tuple(self.files.items()):
            _raw, digest, size = self.read(path)
            if (digest, size) != expected:
                raise ValueError("prediction artifact changed during inspection")
        self.checkpoint()


def _record(raw: dict, kind: RecordKind, domain: Domain, path: Path) -> EvidenceRecord:
    value = EvidenceRecord(
        raw["record_id"], RecordKind(raw["kind"]), Domain(raw["domain"]),
        raw["created_at"], raw["body"], raw["links"],
        tuple(ArtifactRef(**item) for item in raw["artifacts"]),
    )
    if (value.to_dict() != raw or value.kind is not kind or value.domain is not domain
            or path.name != quote(value.record_id, safe="._-") + ".json"):
        raise ValueError("noncanonical or corrupt production evidence")
    return value


def _records(root: Path, domain: Domain, end: datetime, reader: _Reader) -> list[tuple[EvidenceRecord, dict]]:
    releases, predictions, identities = {}, [], set()
    for kind in (RecordKind.MODEL_RELEASE, RecordKind.PREDICTION):
        folder = root / "records" / kind.value
        for path in reader.listing(folder):
            identity = unquote(path.stem)
            parts = identity.split(":")
            if (path.name != quote(identity, safe="._-") + ".json" or len(parts) < 3
                    or parts[0] != "wc" or parts[1] not in {item.value for item in Domain}):
                raise ValueError("noncanonical evidence filename cannot be omitted")
            if parts[1] != domain.value:
                continue
            raw, _ = reader.read(path)
            value = _record(raw, kind, domain, path)
            if _at(value.created_at) > end:
                continue
            if value.record_id in identities:
                raise ValueError("duplicate production evidence identity across kinds")
            identities.add(value.record_id)
            if kind is RecordKind.MODEL_RELEASE:
                releases[value.record_id] = raw
            else:
                predictions.append((value, raw))
    for value, _raw in predictions:
        if value.links["model_release_id"] not in releases:
            raise ValueError("prediction has missing or future model release")
    return predictions


def _relative_candidate(original: Path, event_id: str, relocation_root: Path) -> Path | None:
    positions = [index for index, part in enumerate(original.parts) if part == event_id]
    if len(positions) != 1:
        return None
    suffix = original.parts[positions[0] + 1:]
    if len(suffix) < 3 or suffix[0] != "_prediction_snapshots":
        return None
    return _safe(relocation_root / event_id / Path(*suffix))


def _attempt(refs: tuple[ArtifactRef, ...], paths: tuple[Path | None, ...],
             status: str, blobs: _Blobs) -> tuple[list[tuple], int, int]:
    resolved, valid, invalid = [], 0, 0
    for ref, path in zip(refs, paths):
        raw = size = None
        if path is not None:
            path = _safe(path)
            if path.is_file():
                raw, digest, size = blobs.read(path)
                if digest == ref.sha256:
                    valid += 1
                else:
                    invalid += 1
                    path = raw = size = None
            elif path.exists():
                invalid += 1
                path = None
            else:
                path = None
        resolved.append((ref, status if path is not None else "unavailable", path, raw, size))
    return resolved, valid, invalid


def _resolve_bundle(refs: tuple[ArtifactRef, ...], event_id: str,
                    roots: tuple[Path, ...], blobs: _Blobs) -> tuple[list[tuple], int]:
    originals = tuple(_safe(Path(ref.path)) for ref in refs)
    best, best_valid, direct_invalid = _attempt(refs, originals, "direct", blobs)
    if best_valid == len(refs):
        return best, direct_invalid
    for root in roots:
        paths = tuple(_relative_candidate(path, event_id, root) for path in originals)
        candidate, valid, _invalid = _attempt(refs, paths, "relocated", blobs)
        if valid == len(refs):
            return candidate, direct_invalid
        if valid > best_valid:
            best, best_valid = candidate, valid
    return best, direct_invalid


def _manifest_consistent(record: EvidenceRecord, resolved: list[tuple]) -> tuple[bool, str | None]:
    manifests = [item for item in resolved if Path(item[0].path).name == "manifest.json"]
    if len(manifests) != 1 or manifests[0][3] is None:
        return False, None
    ref, _status, path, raw, _size = manifests[0]
    try:
        manifest = json.loads(raw)
    except (ValueError, UnicodeError):
        return False, str(path) if path else None
    required = {"append_only", "created_at", "domain", "event_id", "files"}
    if (not isinstance(manifest, dict) or not required <= set(manifest)
            or manifest["append_only"] is not True or manifest["domain"] != record.domain.value
            or manifest["event_id"] != record.body["event_id"]
            or _at(manifest["created_at"]) != _at(record.body["source_cutoff_at"])
            or record.body.get("snapshot_manifest_sha256") != ref.sha256
            or not isinstance(manifest["files"], list)):
        return False, str(path) if path else None
    expected, seen = {}, set()
    for artifact, _state, resolved_path, _bytes, size in resolved:
        name = Path(artifact.path).name
        if name == "manifest.json" or resolved_path is None:
            continue
        if name in expected:
            return False, str(path) if path else None
        expected[name] = {"name": name, "bytes": size, "sha256": artifact.sha256}
    for item in manifest["files"]:
        if (not isinstance(item, dict) or set(item) != {"name", "bytes", "sha256"}
                or not isinstance(item["name"], str) or Path(item["name"]).name != item["name"]
                or item["name"] in seen):
            return False, str(path) if path else None
        seen.add(item["name"])
    return ({item["name"]: item for item in manifest["files"]} == expected,
            str(path) if path else None)


def inspect_prediction_artifacts(*, root: Path, domain: Domain, as_of: datetime,
                                 relocation_roots: tuple[Path, ...] = (),
                                 checkpoint: Callable[[], None] = lambda: None) -> dict:
    """Verify direct or exactly relocated prediction bytes without source writes."""
    if not isinstance(domain, Domain) or not isinstance(relocation_roots, tuple):
        raise ValueError("known domain and tuple relocation roots required")
    root, end = _safe(root), _at(as_of)
    roots = tuple(_safe(Path(item)) for item in relocation_roots)
    if len(set(roots)) != len(roots) or any(not item.is_dir() for item in roots):
        raise ValueError("unique existing relocation directories required")
    if not root.is_dir() or not (root / "records").is_dir():
        raise ValueError("production evidence store unavailable")
    reader, blobs = _Reader(checkpoint), _Blobs(checkpoint)
    predictions = _records(root, domain, end, reader)
    if sum(len(value.artifacts) for value, _raw in predictions) > MAX_ARTIFACTS:
        raise ValueError("prediction artifact reference limit exceeded")
    records = []
    for value, raw in sorted(predictions, key=lambda item: item[0].record_id):
        cutoff = _at(value.body["source_cutoff_at"])
        if any(_at(ref.captured_at) != cutoff or ref.source != f"{domain.value}_prediction_snapshot"
               for ref in value.artifacts):
            raise ValueError("prediction artifact provenance conflicts with record")
        resolved, invalid = _resolve_bundle(value.artifacts, value.body["event_id"], roots, blobs)
        direct = sum(item[1] == "direct" for item in resolved)
        relocated = sum(item[1] == "relocated" for item in resolved)
        unavailable = sum(item[1] == "unavailable" for item in resolved)
        manifest_ok, manifest_path = _manifest_consistent(value, resolved)
        resolved_roots = {str(path.parent) for _ref, status, path, _raw, _size in resolved
                          if status != "unavailable" and path is not None}
        bundle = bool(value.artifacts) and unavailable == 0 and manifest_ok and len(resolved_roots) == 1
        records.append({"record_id": value.record_id, "event_id": value.body["event_id"],
                        "created_at": value.created_at, "source_cutoff_at": value.body["source_cutoff_at"],
                        "content_hash": raw["content_hash"], "artifact_refs": len(value.artifacts),
                        "direct_verified": direct, "relocated_verified": relocated,
                        "unavailable_refs": unavailable, "direct_invalid_refs": invalid,
                        "manifest_consistent": manifest_ok, "snapshot_bundle_verified": bundle,
                        "resolved_snapshot_root": next(iter(resolved_roots)) if len(resolved_roots) == 1 else None,
                        "resolved_manifest": manifest_path})
    blobs.recheck()
    reader.recheck()
    report = {"schema_version": SCHEMA, "domain": domain.value, "root": str(root),
              "as_of": end.isoformat(), "relocation_roots": [str(item) for item in roots],
              "records_seen": len(records), "artifact_refs": sum(item["artifact_refs"] for item in records),
              "direct_verified": sum(item["direct_verified"] for item in records),
              "relocated_verified": sum(item["relocated_verified"] for item in records),
              "unavailable_refs": sum(item["unavailable_refs"] for item in records),
              "direct_invalid_refs": sum(item["direct_invalid_refs"] for item in records),
              "verified_bundles": sum(item["snapshot_bundle_verified"] for item in records),
              "records": records,
              "artifact_contents_verified": bool(records) and all(item["snapshot_bundle_verified"] for item in records),
              "normalized_source_verified": False, "source_coverage_complete": False,
              "verified_monitoring_samples": None, "model_promotion_allowed": False}
    report["content_hash"] = _hash(report)
    verify_prediction_artifact_report(report, root=root, domain=domain, as_of=end, relocation_roots=roots)
    return report


def verify_prediction_artifact_report(report: dict, *, root: Path, domain: Domain, as_of: datetime,
                                      relocation_roots: tuple[Path, ...]) -> None:
    """Validate bounded parent claims; bulk artifact reads remain in the worker."""
    _hashed(report, SCHEMA)
    expected = {"schema_version", "domain", "root", "as_of", "relocation_roots", "records_seen",
                "artifact_refs", "direct_verified", "relocated_verified", "unavailable_refs",
                "direct_invalid_refs", "verified_bundles", "records", "artifact_contents_verified",
                "normalized_source_verified", "source_coverage_complete", "verified_monitoring_samples",
                "model_promotion_allowed", "content_hash"}
    roots = tuple(_safe(Path(item)) for item in relocation_roots)
    if (set(report) != expected or report["domain"] != domain.value or report["root"] != str(_safe(root))
            or report["as_of"] != _at(as_of).isoformat()
            or report["relocation_roots"] != [str(item) for item in roots]
            or len(_encoded(report)) > 131072):
        raise ValueError("prediction artifact report scope or size mismatch")
    if (report["normalized_source_verified"] is not False or report["source_coverage_complete"] is not False
            or report["verified_monitoring_samples"] is not None or report["model_promotion_allowed"] is not False):
        raise ValueError("prediction bundle cannot grant source, sample or model authority")
    if not isinstance(report["records"], list) or len(report["records"]) > 10000:
        raise ValueError("invalid prediction artifact records")
    for key in ("records_seen", "artifact_refs", "direct_verified", "relocated_verified",
                "unavailable_refs", "direct_invalid_refs", "verified_bundles"):
        if type(report[key]) is not int or not 0 <= report[key] <= MAX_ARTIFACTS:
            raise ValueError("invalid prediction artifact aggregate count")
    if (type(report["artifact_contents_verified"]) is not bool
            or not re.fullmatch(r"[0-9a-f]{64}", report["content_hash"])):
        raise ValueError("invalid prediction artifact aggregate status")
    fields = {"record_id", "event_id", "created_at", "source_cutoff_at", "content_hash", "artifact_refs",
              "direct_verified", "relocated_verified", "unavailable_refs", "direct_invalid_refs",
              "manifest_consistent", "snapshot_bundle_verified", "resolved_snapshot_root", "resolved_manifest"}
    ids = set()
    for item in report["records"]:
        if (not isinstance(item, dict) or set(item) != fields or item["record_id"] in ids
                or not item["record_id"].startswith(f"wc:{domain.value}:prediction:")
                or not isinstance(item["event_id"], str) or not item["event_id"]
                or not re.fullmatch(r"[0-9a-f]{64}", item["content_hash"])
                or _at(item["created_at"]) > _at(as_of) or _at(item["source_cutoff_at"]) > _at(item["created_at"])):
            raise ValueError("invalid prediction artifact record projection")
        for key in ("artifact_refs", "direct_verified", "relocated_verified", "unavailable_refs", "direct_invalid_refs"):
            if type(item[key]) is not int or not 0 <= item[key] <= MAX_ARTIFACTS:
                raise ValueError("invalid prediction artifact count")
        if item["artifact_refs"] != item["direct_verified"] + item["relocated_verified"] + item["unavailable_refs"]:
            raise ValueError("prediction artifact totals mismatch")
        if type(item["manifest_consistent"]) is not bool or type(item["snapshot_bundle_verified"]) is not bool:
            raise ValueError("invalid prediction bundle status")
        if item["snapshot_bundle_verified"] and (not item["manifest_consistent"] or item["unavailable_refs"]):
            raise ValueError("unverified bundle reported as verified")
        for key in ("resolved_snapshot_root", "resolved_manifest"):
            if item[key] is not None:
                if not isinstance(item[key], str) or not Path(item[key]).is_absolute():
                    raise ValueError("resolved prediction artifact path must be absolute")
                _safe(Path(item[key]))
        if item["snapshot_bundle_verified"] and (
                item["resolved_snapshot_root"] is None or item["resolved_manifest"] is None):
            raise ValueError("verified bundle requires resolved absolute paths")
        ids.add(item["record_id"])
    sums = {key: sum(item[key] for item in report["records"])
            for key in ("artifact_refs", "direct_verified", "relocated_verified", "unavailable_refs", "direct_invalid_refs")}
    if (report["records_seen"] != len(report["records"]) or report["verified_bundles"] != sum(
            item["snapshot_bundle_verified"] for item in report["records"])
            or any(report[key] != value for key, value in sums.items())
            or report["artifact_contents_verified"] is not (
                bool(report["records"]) and report["verified_bundles"] == len(report["records"]))):
        raise ValueError("prediction artifact report aggregate mismatch")
