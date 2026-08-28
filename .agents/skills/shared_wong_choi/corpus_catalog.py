"""Fail-closed resolver for artifacts that have moved beyond one HOT root.

The archive catalog is the durable statement that an artifact belongs to the
research corpus.  A full-history reader must therefore resolve every matching
record to at least one content-verified local copy.  It may use the original
HOT source or the WARM destination, but it must never silently ignore a known
artifact because an external disk is offline.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable

from .artifact_archive import artifact_digest


DEFAULT_CONTROL_ROOT = Path.home() / "WongChoiData" / "WongChoiControl"
MEETING_ARTIFACT_CLASSES = frozenset(
    {"settled-meeting", "settled-day", "analysis-day"}
)


class CorpusCatalogError(RuntimeError):
    """The known full-history corpus cannot be resolved without data loss."""


def default_catalog_root() -> Path:
    control = Path(
        os.environ.get("WONGCHOI_CONTROL_STATE_ROOT", DEFAULT_CONTROL_ROOT)
    ).expanduser()
    return control / "storage" / "catalog"


def _load_records(catalog_root: Path) -> list[tuple[Path, dict[str, Any]]]:
    records = catalog_root.expanduser() / "records"
    if not records.is_dir():
        return []
    loaded: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(records.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise CorpusCatalogError(f"invalid artifact catalog record: {path}: {exc}") from exc
        if payload.get("schema_version") != "wong-choi-artifact/v1":
            continue
        loaded.append((path, payload))
    return loaded


def _verified_copy(path: Path, expected: dict[str, Any]) -> tuple[bool, str | None]:
    try:
        if not path.exists():
            return False, "missing"
        if artifact_digest(path) != expected:
            return False, "digest_mismatch"
    except OSError as exc:
        return False, f"unreadable:{type(exc).__name__}"
    return True, None


def resolve_catalog_artifacts(
    *,
    catalog_root: Path | None = None,
    domain: str,
    artifact_classes: Iterable[str] | None = None,
    strict: bool = True,
) -> dict[str, Any]:
    """Resolve every matching catalog record to a verified HOT or WARM copy.

    The source is preferred while it remains intact; WARM is the fallback once
    a separately approved retention cutover removes HOT.  Both locations are
    checked so a corrupt duplicate is visible even when another copy works.
    """
    catalog_root = (catalog_root or default_catalog_root()).expanduser().resolve()
    domain = domain.strip().lower()
    selected_classes = {
        value.strip().lower() for value in (artifact_classes or ()) if value.strip()
    }
    artifacts: list[dict[str, Any]] = []
    unavailable: list[dict[str, Any]] = []
    degraded: list[dict[str, Any]] = []
    matched_records = 0

    for record_path, record in _load_records(catalog_root):
        artifact_class = str(record.get("artifact_class") or "").lower()
        if str(record.get("domain") or "").lower() != domain:
            continue
        if selected_classes and artifact_class not in selected_classes:
            continue
        matched_records += 1
        expected = record.get("source_digest")
        if not isinstance(expected, dict) or expected != record.get("destination_digest"):
            item = {
                "artifact_id": record.get("artifact_id"),
                "artifact_class": artifact_class,
                "record": str(record_path),
                "reason": "manifest_digest_invariant_failed",
            }
            unavailable.append(item)
            continue

        source_raw = str(record.get("source") or "").strip()
        destination_raw = str(record.get("destination") or "").strip()
        if not source_raw or not destination_raw:
            unavailable.append(
                {
                    "artifact_id": record.get("artifact_id"),
                    "artifact_class": artifact_class,
                    "record": str(record_path),
                    "reason": "manifest_location_missing",
                }
            )
            continue
        source = Path(source_raw)
        destination = Path(destination_raw)
        if not source.is_absolute() or not destination.is_absolute():
            unavailable.append(
                {
                    "artifact_id": record.get("artifact_id"),
                    "artifact_class": artifact_class,
                    "record": str(record_path),
                    "reason": "manifest_location_not_absolute",
                }
            )
            continue
        source_ok, source_error = _verified_copy(source, expected)
        warm_ok, warm_error = _verified_copy(destination, expected)
        resolved = source if source_ok else destination if warm_ok else None
        item = {
            "artifact_id": record.get("artifact_id"),
            "artifact_class": artifact_class,
            "logical_name": source.name,
            "record": str(record_path),
            "source": str(source),
            "source_status": "verified" if source_ok else source_error,
            "warm": str(destination),
            "warm_status": "verified" if warm_ok else warm_error,
            "resolved": str(resolved) if resolved else None,
            "digest": expected,
        }
        artifacts.append(item)
        if resolved is None:
            unavailable.append(item)
        elif not source_ok or not warm_ok:
            degraded.append(item)

    status = (
        "blocked"
        if unavailable
        else "hot_only_unregistered"
        if matched_records == 0
        else "ok"
    )
    report = {
        "schema_version": "wong-choi-corpus-resolution/v1",
        "status": status,
        "domain": domain,
        "artifact_classes": sorted(selected_classes),
        "catalog_root": str(catalog_root),
        "known_artifacts": matched_records,
        "resolved_artifacts": sum(1 for item in artifacts if item.get("resolved")),
        "degraded_artifacts": len(degraded),
        "unavailable_artifacts": len(unavailable),
        "artifacts": artifacts,
        "unavailable": unavailable,
        "coverage_note": (
            "catalog verifies known archived artifacts only; no matching records exist"
            if matched_records == 0
            else "all matching catalog artifacts resolved"
            if not unavailable
            else "one or more known catalog artifacts could not be resolved"
        ),
    }
    if unavailable and strict:
        identities = ", ".join(
            str(item.get("artifact_id") or item.get("record")) for item in unavailable
        )
        raise CorpusCatalogError(
            f"{domain} full-history corpus unavailable: {identities}"
        )
    return report


def catalog_meeting_locations(
    *,
    catalog_root: Path | None = None,
    domain: str,
    artifact_classes: Iterable[str] = MEETING_ARTIFACT_CLASSES,
    strict: bool = True,
) -> list[tuple[str, Path]]:
    """Return logical meeting names and resolved directories from the catalog."""
    report = resolve_catalog_artifacts(
        catalog_root=catalog_root,
        domain=domain,
        artifact_classes=artifact_classes,
        strict=strict,
    )
    meetings: list[tuple[str, Path]] = []
    for item in report["artifacts"]:
        raw = item.get("resolved")
        if not raw:
            continue
        path = Path(str(raw))
        if path.is_dir():
            meetings.append((str(item.get("logical_name") or path.name), path))
    return meetings
