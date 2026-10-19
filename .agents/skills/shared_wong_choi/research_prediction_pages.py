"""Freeze the complete prediction metadata inventory and plan bounded pages.

No blob inspection, database/scoring inputs, coverage or promotion grant here.
Consumers must reverify inventory against its source before accepting page work.
Each page contains whole bundles; limits are not enlarged to fit the corpus.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Callable
from urllib.parse import quote

from .contracts import Domain
from .evidence import RecordKind
from .research_evaluation import _write_report
from .research_index import _MetadataPages, _Reader, _at, _encoded, _hash, _hashed, _safe
from .research_prediction_artifacts import MAX_ARTIFACTS, _Blobs, _project_prediction, _record, _records
from .research_review_clock import _digest

SCHEMA = "wong-choi-prediction-inventory/v1"
PAGE_SCHEMA = "wong-choi-prediction-page-plan/v1"
RESULT_SCHEMA = "wong-choi-prediction-page-result/v1"
COVERAGE_SCHEMA = "wong-choi-prediction-page-coverage/v1"
MAX_PAGE_RECORDS = 100
MAX_INVENTORY_BYTES = 4 * 1024 * 1024


def freeze_prediction_inventory(
    *, root: Path, domain: Domain, as_of: datetime,
    checkpoint: Callable[[], None] = lambda: None,
) -> dict:
    """Canonical all-history metadata read with native budgets and recheck."""
    if not isinstance(domain, Domain):
        raise ValueError("known domain required")
    root, end = _safe(root), _at(as_of)
    if not root.is_dir() or not (root / "records").is_dir():
        raise ValueError("production evidence store unavailable")
    reader = _MetadataPages(checkpoint)
    predictions = _records(root, domain, end, reader)
    records = []
    for value, raw in sorted(predictions, key=lambda item: item[0].record_id):
        checkpoint()
        path = root / "records" / "prediction" / (quote(value.record_id, safe="._-") + ".json")
        records.append({
            "record_id": value.record_id,
            "content_hash": raw["content_hash"],
            "source_sha256": reader.files[path],
            "artifact_refs": len(value.artifacts),
        })
    body = {
        "schema_version": SCHEMA, "root": str(root), "domain": domain.value,
        "as_of": end.isoformat(), "records": records,
        "records_seen": len(records),
        "artifact_refs": sum(item["artifact_refs"] for item in records),
        # Include release parents and excluded future metadata in source binding.
        "source_files": {str(path.relative_to(root)): digest for path, digest in sorted(reader.files.items())},
        "artifact_contents_verified": False, "source_coverage_complete": False,
        "model_promotion_allowed": False,
    }
    body["content_hash"] = _hash(body)
    _validate(body)
    reader.recheck()
    return body


def _validate(inventory: dict) -> None:
    _hashed(inventory, SCHEMA)
    expected = {
        "schema_version", "root", "domain", "as_of", "records", "records_seen",
        "artifact_refs", "source_files", "artifact_contents_verified",
        "source_coverage_complete", "model_promotion_allowed", "content_hash",
    }
    if set(inventory) != expected or len(_encoded(inventory)) > MAX_INVENTORY_BYTES:
        raise ValueError("invalid or oversized prediction inventory")
    domain = Domain(inventory["domain"])
    _safe(Path(inventory["root"]))
    _at(inventory["as_of"])
    if any(inventory[key] is not False for key in (
        "artifact_contents_verified", "source_coverage_complete", "model_promotion_allowed",
    )):
        raise ValueError("metadata inventory cannot grant authority")
    records = inventory["records"]
    if not isinstance(records, list) or len(records) > 10000:
        raise ValueError("invalid inventory records")
    identities = []
    for record in records:
        if not isinstance(record, dict) or set(record) != {
            "record_id", "content_hash", "source_sha256", "artifact_refs",
        }:
            raise ValueError("invalid inventory record")
        identity = record["record_id"]
        if not isinstance(identity, str) or not identity.startswith(f"wc:{domain.value}:prediction:"):
            raise ValueError("invalid inventory identity")
        for name in ("content_hash", "source_sha256"):
            _digest(record[name])
        if type(record["artifact_refs"]) is not int or record["artifact_refs"] <= 0:
            raise ValueError("prediction bundle must have artifact references")
        identities.append(identity)
    if identities != sorted(set(identities)):
        raise ValueError("inventory identities must be sorted and unique")
    if (type(inventory["records_seen"]) is not int or inventory["records_seen"] != len(records)
            or type(inventory["artifact_refs"]) is not int
            or inventory["artifact_refs"] != sum(r["artifact_refs"] for r in records)):
        raise ValueError("inventory totals mismatch")
    files = inventory["source_files"]
    if not isinstance(files, dict):
        raise ValueError("source file binding required")
    for name, digest in files.items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or relative.parts[:1] != ("records",):
            raise ValueError("source file outside canonical records")
        _digest(digest)
    for record in records:
        name = "records/prediction/" + quote(record["record_id"], safe="._-") + ".json"
        if files.get(name) != record["source_sha256"]:
            raise ValueError("source file binding mismatch")


def verify_prediction_inventory(
    inventory: dict, *, root: Path, domain: Domain, as_of: datetime,
    checkpoint: Callable[[], None] = lambda: None,
) -> None:
    """Rebuild all source bindings; a rehashed narrowed inventory is invalid."""
    _validate(inventory)
    actual = freeze_prediction_inventory(root=root, domain=domain, as_of=as_of, checkpoint=checkpoint)
    if _encoded(inventory) != _encoded(actual):
        raise ValueError("prediction inventory differs from complete source")


def plan_prediction_pages(
    inventory: dict, *, max_refs: int = MAX_ARTIFACTS,
    max_records: int = MAX_PAGE_RECORDS,
) -> tuple[dict, ...]:
    """Deterministic metadata plans only; no completed-page/coverage assertion."""
    _validate(inventory)
    if (type(max_refs) is not int or not 1 <= max_refs <= MAX_ARTIFACTS
            or type(max_records) is not int or not 1 <= max_records <= MAX_PAGE_RECORDS):
        raise ValueError("page limits must preserve existing resource bounds")
    groups, group, refs = [], [], 0
    for record in inventory["records"]:
        count = record["artifact_refs"]
        if count > max_refs:
            raise ValueError("oversized prediction bundle cannot be split")
        if group and (refs + count > max_refs or len(group) >= max_records):
            groups.append(group)
            group, refs = [], 0
        group.append(record)
        refs += count
    if group:
        groups.append(group)
    pages = []
    for index, group in enumerate(groups):
        body = {
            "schema_version": PAGE_SCHEMA, "inventory_hash": inventory["content_hash"],
            "page_index": index, "total_pages": len(groups),
            "record_ids": [r["record_id"] for r in group],
            "artifact_refs": sum(r["artifact_refs"] for r in group),
            "max_refs": max_refs, "max_records": max_records,
            "next_page_index": index + 1 if index + 1 < len(groups) else None,
        }
        pages.append({**body, "content_hash": _hash(body)})
    return tuple(pages)


def verify_prediction_page_plan(
    page: dict, inventory: dict, *, max_refs: int = MAX_ARTIFACTS,
    max_records: int = MAX_PAGE_RECORDS,
) -> None:
    """Check an exact planned page, not caller-chosen record subsets or bounds."""
    _hashed(page, PAGE_SCHEMA)
    index = page.get("page_index")
    expected = plan_prediction_pages(inventory, max_refs=max_refs, max_records=max_records)
    if (type(index) is not int or not 0 <= index < len(expected)
            or _encoded(page) != _encoded(expected[index])):
        raise ValueError("prediction page differs from complete inventory plan")


def inspect_prediction_page(
    *, inventory: dict, page: dict, root: Path, domain: Domain, as_of: datetime,
    relocation_roots: tuple[Path, ...] = (), max_refs: int = MAX_ARTIFACTS,
    max_records: int = MAX_PAGE_RECORDS,
    checkpoint: Callable[[], None] = lambda: None,
) -> dict:
    """Inspect an exact page through byte-bounded whole-bundle subpages.

    Operational callers must use the process supervisor and production/WARM
    guard. This primitive does not publish or initialize any persistent state.
    """
    verify_prediction_page_plan(page, inventory, max_refs=max_refs, max_records=max_records)
    root, end = _safe(root), _at(as_of)
    if (inventory["root"] != str(root) or inventory["domain"] != domain.value
            or inventory["as_of"] != end.isoformat()):
        raise ValueError("prediction page inventory scope mismatch")
    if not isinstance(relocation_roots, tuple):
        raise ValueError("tuple relocation roots required")
    roots = tuple(_safe(Path(item)) for item in relocation_roots)
    if len(set(roots)) != len(roots) or any(not item.is_dir() for item in roots):
        raise ValueError("unique existing relocation directories required")
    reader = _MetadataPages(checkpoint)
    records, source_blobs = [], {}
    for identity in page["record_ids"]:
        checkpoint()
        path = root / "records" / "prediction" / (quote(identity, safe="._-") + ".json")
        raw, digest = reader.read(path)
        if inventory["source_files"].get(str(path.relative_to(root))) != digest:
            raise ValueError("prediction source changed before page blob read")
        value = _record(raw, RecordKind.PREDICTION, domain, path)
        parent_id = value.links["model_release_id"]
        parent_path = root / "records" / "model_release" / (quote(parent_id, safe="._-") + ".json")
        parent_raw, parent_digest = reader.read(parent_path)
        if inventory["source_files"].get(str(parent_path.relative_to(root))) != parent_digest:
            raise ValueError("prediction release parent changed before page read")
        parent = _record(parent_raw, RecordKind.MODEL_RELEASE, domain, parent_path)
        if _at(value.created_at) > end or _at(parent.created_at) > end:
            raise ValueError("prediction page has future evidence")
        blobs = _Blobs(checkpoint)
        records.append(_project_prediction(value, raw, domain, roots, blobs))
        # A complete bundle and all resolution attempts share the native cap.
        # Never split an oversized bundle or reset a physical reader counter.
        blobs.recheck()
        for path, expected in blobs.files.items():
            if path in source_blobs and source_blobs[path] != expected:
                raise ValueError("prediction artifact changed across bundle pages")
            source_blobs[path] = expected
    # Protect returned proof against a change during the page read itself.
    for path, expected in source_blobs.items():
        checkpoint()
        bounded = _Blobs(checkpoint)
        _raw, digest, size = bounded.read(path)
        if (digest, size) != expected:
            raise ValueError("prediction artifact changed across bundle pages")
        bounded.recheck()
    reader.recheck()
    body = {
        "schema_version": RESULT_SCHEMA, "inventory_hash": inventory["content_hash"],
        "page_plan_hash": page["content_hash"], "page_index": page["page_index"],
        "relocation_roots": [str(item) for item in roots], "records": records,
        "source_coverage_complete": False, "model_promotion_allowed": False,
    }
    if len(_encoded(body)) > 131072:
        raise ValueError("prediction page result exceeds compact report bound")
    return {**body, "content_hash": _hash(body)}


def aggregate_prediction_pages(
    *, results: list[dict], inventory: dict, root: Path, domain: Domain, as_of: datetime,
    relocation_roots: tuple[Path, ...] = (), max_refs: int = MAX_ARTIFACTS,
    max_records: int = MAX_PAGE_RECORDS,
    checkpoint: Callable[[], None] = lambda: None,
) -> dict:
    """Accept only all planned pages, rebuilt from current canonical bytes.

    This is a bundle-coverage proof only, never a PIT/sample authority. Parent
    callers must supervise this I/O and persist create-only outputs themselves.
    """
    plans = plan_prediction_pages(inventory, max_refs=max_refs, max_records=max_records)
    if not isinstance(results, list) or len(results) != len(plans):
        raise ValueError("incomplete prediction page coverage")
    verify_prediction_inventory(inventory, root=root, domain=domain, as_of=as_of, checkpoint=checkpoint)
    hashes, records = [], []
    for supplied, plan in zip(results, plans):
        checkpoint()
        _hashed(supplied, RESULT_SCHEMA)
        if len(_encoded(supplied)) > 131072:
            raise ValueError("oversized prediction page result")
        actual = inspect_prediction_page(
            inventory=inventory, page=plan, root=root, domain=domain, as_of=as_of,
            relocation_roots=relocation_roots, max_refs=max_refs, max_records=max_records,
            checkpoint=checkpoint,
        )
        if _encoded(supplied) != _encoded(actual):
            raise ValueError("prediction page proof differs from current source")
        hashes.append(supplied["content_hash"])
        records.extend(supplied["records"])
    verify_prediction_inventory(inventory, root=root, domain=domain, as_of=as_of, checkpoint=checkpoint)
    if [r["record_id"] for r in records] != [r["record_id"] for r in inventory["records"]]:
        raise ValueError("prediction record coverage mismatch")
    # Compact aggregate: per-record details remain in the bounded page proofs.
    body = {
        "schema_version": COVERAGE_SCHEMA, "inventory_hash": inventory["content_hash"],
        "page_hashes": hashes, "page_coverage_complete": True,
        "records_seen": len(records), "artifact_refs": sum(r["artifact_refs"] for r in records),
        "verified_bundles": sum(r["snapshot_bundle_verified"] for r in records),
        "unavailable_refs": sum(r["unavailable_refs"] for r in records),
        "artifact_contents_verified": bool(records) and all(r["snapshot_bundle_verified"] for r in records),
        "source_coverage_complete": False, "verified_monitoring_samples": None,
        "model_promotion_allowed": False,
    }
    if len(_encoded(body)) > 131072:
        raise ValueError("prediction coverage report exceeds compact report bound")
    return {**body, "content_hash": _hash(body)}


def _receipt_path(output_root: Path, page: dict) -> Path:
    output_root = _safe(Path(output_root))
    if not output_root.is_dir():
        raise ValueError("existing non-symlink receipt directory required")
    path = _safe(output_root / f"prediction-page-{page['content_hash']}.json")
    if path.exists() and not path.is_file():
        raise ValueError("receipt must be a regular file")
    return path


def persist_prediction_page(
    *, inventory: dict, page: dict, root: Path, domain: Domain, as_of: datetime,
    output_root: Path, relocation_roots: tuple[Path, ...] = (),
    max_refs: int = MAX_ARTIFACTS, max_records: int = MAX_PAGE_RECORDS,
    checkpoint: Callable[[], None] = lambda: None,
) -> dict:
    """Create-only page receipt in an existing supervised workspace.

    Never call operationally outside the shared supervisor/WARM guard. A raised
    exception after link publication is uncertain, not success; explicitly
    reconcile the pinned receipt before resuming. No directory/state creation.
    """
    verify_prediction_page_plan(page, inventory, max_refs=max_refs, max_records=max_records)
    path = _receipt_path(output_root, page)
    verify_prediction_inventory(inventory, root=root, domain=domain, as_of=as_of, checkpoint=checkpoint)
    report = inspect_prediction_page(
        inventory=inventory, page=page, root=root, domain=domain, as_of=as_of,
        relocation_roots=relocation_roots, max_refs=max_refs, max_records=max_records,
        checkpoint=checkpoint,
    )
    encoded_size = len((json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode())
    if encoded_size > 131072:
        raise ValueError("persisted page receipt exceeds read bound")
    publication = _write_report(path, report, resource_checkpoint=checkpoint, create_parents=False)
    checkpoint()
    return {"publication": publication, "path": path, "content_hash": report["content_hash"],
            "model_promotion_allowed": False, "source_coverage_complete": False}


def reconcile_prediction_page(
    *, inventory: dict, page: dict, root: Path, domain: Domain, as_of: datetime,
    output_root: Path, relocation_roots: tuple[Path, ...] = (),
    max_refs: int = MAX_ARTIFACTS, max_records: int = MAX_PAGE_RECORDS,
    checkpoint: Callable[[], None] = lambda: None,
) -> dict:
    """Read-only reconstruction of an explicitly inventory-bound saved receipt."""
    verify_prediction_page_plan(page, inventory, max_refs=max_refs, max_records=max_records)
    path = _receipt_path(output_root, page)
    reader = _Reader(checkpoint, max_records=1, max_record_bytes=131072, max_total_bytes=262144)
    saved, _ = reader.read(path)
    _hashed(saved, RESULT_SCHEMA)
    verify_prediction_inventory(inventory, root=root, domain=domain, as_of=as_of, checkpoint=checkpoint)
    expected = inspect_prediction_page(
        inventory=inventory, page=page, root=root, domain=domain, as_of=as_of,
        relocation_roots=relocation_roots, max_refs=max_refs, max_records=max_records,
        checkpoint=checkpoint,
    )
    if _encoded(saved) != _encoded(expected):
        raise ValueError("saved page receipt differs from current source")
    reader.recheck()
    return {"publication": "verified_existing", "path": path,
            "content_hash": expected["content_hash"], "model_promotion_allowed": False,
            "source_coverage_complete": False}
