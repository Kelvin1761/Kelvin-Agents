"""Bounded cyclic notification selection, executed only under the supervisor.

Pagination is mutable HOT metadata, never delivery evidence. Immutable outbox
intents suppress replay, including when a worker dies before saving pagination.
A complete cycle says nothing about unresolved sends on earlier pages. No
receipt, scheduler, route authority or model-promotion authority is created here.
"""
from __future__ import annotations

import hashlib
import os
import re
from uuid import uuid4

from .research_evaluation import _write_report
from .research_index import _Reader, _encoded, _hash, _hashed, _safe, _load_review_receipt
from .research_notifications import _create, _sync_directory
from .research_presentation import SCHEMA as PRESENTATION_SCHEMA


STATE_SCHEMA = "wong-choi-notification-selection/v1"
SUMMARY_SCHEMA = "wong-choi-notification-catchup-summary/v1"
_COUNT_KEYS = ("skipped_sent", "preexisting_reconcile", "sent", "already_sent", "new_reconcile")


def _digest(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _seal(value):
    return {**value, "content_hash": _hash(value)}


def _context(request, helper_hash):
    return {"domain": request["payload"]["domain"], "registry_root": request["registry"],
            "receipt_root": str(_safe(request["warm_root"]) / "research-reviews"),
            "route_hash": request["payload"]["route_hash"], "helper_sha256": helper_hash}


def _validate_state(value, context):
    _hashed(value, STATE_SCHEMA)
    if (set(value) != {"schema_version", "context", "generation", "after_request_id", "content_hash"}
            or value["context"] != context or not _digest(context["helper_sha256"])
            or type(value["generation"]) is not int or not 1 <= value["generation"] <= 2**53 - 1
            or (value["after_request_id"] is not None and not _digest(value["after_request_id"]))):
        raise ValueError("notification pagination identity or context mismatch")


def _next_state(context, before, observed, complete):
    return _seal({"schema_version": STATE_SCHEMA, "context": context,
                  "generation": (before["generation"] if before else 0) + 1,
                  "after_request_id": None if complete else observed[-1]["request_id"]})


def _load_state(path, checkpoint):
    if not _safe(path).exists():
        return None
    return _Reader(checkpoint, max_record_bytes=65536, max_total_bytes=65536).read(path)[0]


def _advance_state(path, before, after, checkpoint):
    """Compare and replace only pagination under the supervisor's heavy lock.

An fsync/ack failure may leave either generation visible: both are safe because
neither is the source of truth for send attempts. No intents are removed/reset.
"""
    checkpoint()
    if _load_state(path, checkpoint) != before:
        raise ValueError("notification pagination changed during scan")
    if before is None:
        if not _create(path, after):
            raise ValueError("notification pagination was concurrently created")
        return
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    descriptor = os.open(_safe(temporary), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(_encoded(after))
            handle.flush()
            os.fsync(handle.fileno())
        checkpoint()
        if _load_state(path, checkpoint) != before:
            raise ValueError("notification pagination changed before replacement")
        os.replace(temporary, _safe(path))
        _sync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _verify_item(item, *, request, runtime, inspection):
    if (not isinstance(item, dict) or set(item) != {"request_id", "receipt_hash", "result"}
            or not _digest(item["request_id"]) or not _digest(item["receipt_hash"])):
        raise ValueError("invalid notification page item")
    result = item["result"]
    domain = request["payload"]["domain"]
    dedup = _hash({"schema": PRESENTATION_SCHEMA, "registry": request["registry"],
                   "domain": domain, "request_id": item["request_id"]})
    expected = runtime.state_root.expanduser().absolute() / "research-notifications" / domain / dedup / "intent.json"
    allowed = {"already_sent", "reconcile_required", "not_attempted" if inspection else "sent"}
    reasons = {"helper_sent", "helper_nonzero", "helper_reply_unconfirmed", "helper_exception",
               "intent_without_outcome", "dispatch_precondition_changed", "no_intent"}
    if (not isinstance(result, dict) or set(result) != {"status", "intent_path", "reason", "transport_reported_sent",
                                                       "delivery_confirmed", "model_promotion_allowed"}
            or result["status"] not in allowed or result["intent_path"] != str(expected)
            or result["reason"] not in reasons or result["delivery_confirmed"] is not False
            or result["model_promotion_allowed"] is not False
            or result["transport_reported_sent"] is not (result["status"] in {"sent", "already_sent"})
            or (result["status"] in {"sent", "already_sent"}) != (result["reason"] == "helper_sent")
            or (result["status"] == "not_attempted") != (result["reason"] == "no_intent")):
        raise ValueError("notification page result identity or authority mismatch")


def _counts(observed, processed):
    return {"skipped_sent": sum(i["result"]["status"] == "already_sent" for i in observed),
            "preexisting_reconcile": sum(i["result"]["status"] == "reconcile_required" for i in observed),
            **{key: sum(i["result"]["status"] == status for i in processed)
               for key, status in (("sent", "sent"), ("already_sent", "already_sent"), ("new_reconcile", "reconcile_required"))}}


def _status(counts):
    return ("notification_page_reconcile_required" if counts["preexisting_reconcile"] + counts["new_reconcile"]
            else "notification_page_recorded")


def run_catchup_request(request, *, registry, runtime, workspace, checkpoint, box):
    from .research_notification_runtime import _completion
    payload = request["payload"]
    root = _safe(box.root)
    if not root.is_dir() or root.is_relative_to(_safe(runtime.warm_root)):
        raise ValueError("existing HOT outbox root outside WARM required")
    helper = _safe(box.helper_path)
    if not helper.is_file() or helper.stat().st_size > 1048576:
        raise ValueError("bounded local notification helper required")
    helper_hash = hashlib.sha256(helper.read_bytes()).hexdigest()
    context = _context(request, helper_hash)
    state_path = _safe(root / payload["domain"] / "selection.json")
    before = _load_state(state_path, checkpoint)
    if before is not None:
        _validate_state(before, context)
    store = _safe(runtime.warm_root / "research-reviews" / payload["domain"])
    if not store.is_dir():
        raise ValueError("existing review collection required; absence is not healthy emptiness")
    reader = _Reader(checkpoint, max_record_bytes=16777216)
    paths = reader.listing(store)
    if any(not re.fullmatch(r"[0-9a-f]{64}\.json", p.name) or not p.is_file() for p in paths):
        raise ValueError("noncanonical review collection entry")
    previous = before["after_request_id"] if before else None
    start = next((i for i, p in enumerate(paths) if previous is None or p.stem > previous), len(paths))
    wrapped = previous is not None and start == len(paths)
    if wrapped:
        start = 0
    selected = paths[start:start + payload["scan_limit"]]
    remaining = len(paths) - start - len(selected)
    observed = []
    # Verify the whole page before *any* new side effect. Subsequent dispatches
    # independently pin receipt hashes; preexisting ambiguities never get retried.
    for path in selected:
        receipt = _load_review_receipt(path, reader)
        if receipt["domain"] != payload["domain"] or _safe(receipt["index"]["registry_root"]) != _safe(registry.root):
            raise ValueError("notification review belongs to another domain or registry")
        item = {"request_id": path.stem, "receipt_hash": receipt["content_hash"],
                "result": box.inspect(path, expected_receipt_hash=receipt["content_hash"])}
        _verify_item(item, request=request, runtime=runtime, inspection=True)
        observed.append(item)
    reader.recheck()
    processed = []
    for path, item in zip(selected, observed):
        checkpoint()
        if hashlib.sha256(_safe(helper).read_bytes()).hexdigest() != helper_hash:
            raise ValueError("notification helper changed during page")
        if item["result"]["status"] == "not_attempted":
            sent = {**item, "result": box.dispatch(path, expected_receipt_hash=item["receipt_hash"])}
            _verify_item(sent, request=request, runtime=runtime, inspection=False)
            processed.append(sent)
    # Directory changes do not erase sends. Leave the old cursor and re-observe
    # the immutable outbox on recovery, including newly inserted older IDs.
    reader.listing(store)
    checkpoint()
    if hashlib.sha256(_safe(helper).read_bytes()).hexdigest() != helper_hash:
        raise ValueError("notification helper changed before pagination commit")
    after = _next_state(context, before, observed, remaining == 0)
    _validate_state(after, context)
    counts = _counts(observed, processed)
    summary = _seal({"schema_version": SUMMARY_SCHEMA, "domain": payload["domain"], "request_hash": _hash(request),
                     "route_hash": payload["route_hash"], "status": _status(counts), "selection_before": before,
                     "selection_after": after, "listing_count": len(paths), "listing_hash": _hash([p.name for p in paths]),
                     "start_index": start, "wrapped": wrapped, "scanned_count": len(observed),
                     "remaining_in_cycle": remaining, "cycle_complete": remaining == 0,
                     "observed": observed, "processed": processed, "counts": counts,
                     "delivery_confirmed": False, "model_promotion_allowed": False})
    if len(_encoded(summary)) > 65536:
        raise ValueError("notification page summary exceeds metadata bound")
    path = workspace / "notification-summary.json"
    _write_report(path, summary, resource_checkpoint=checkpoint, create_parents=False)
    _sync_directory(workspace)
    checkpoint()
    state_path.parent.mkdir(mode=0o700, exist_ok=True)
    _sync_directory(root)
    _advance_state(state_path, before, after, checkpoint)
    return _completion(request, path, summary)


def verify_catchup_summary(*, request, runtime, report_path, receipt):
    """Only bounded metadata in the parent; full receipts stay under supervision."""
    from .research_notification_runtime import _completion
    payload = request["payload"]
    summary, _ = _Reader(lambda: None, max_record_bytes=65536, max_total_bytes=65536).read(report_path)
    _hashed(summary, SUMMARY_SCHEMA)
    fields = {"schema_version", "domain", "request_hash", "route_hash", "status", "selection_before", "selection_after",
              "listing_count", "listing_hash", "start_index", "wrapped", "scanned_count", "remaining_in_cycle",
              "cycle_complete", "observed", "processed", "counts", "delivery_confirmed", "model_promotion_allowed", "content_hash"}
    if (set(summary) != fields or summary["domain"] != payload["domain"] or summary["request_hash"] != _hash(request)
            or summary["route_hash"] != payload["route_hash"] or summary["delivery_confirmed"] is not False
            or summary["model_promotion_allowed"] is not False):
        raise ValueError("notification page identity or authority mismatch")
    before, after = summary["selection_before"], summary["selection_after"]
    context = _context(request, after["context"]["helper_sha256"])
    _validate_state(after, context)
    if before is not None:
        _validate_state(before, context)
    previous = before["after_request_id"] if before else None
    observed, processed = summary["observed"], summary["processed"]
    if not isinstance(observed, list) or not isinstance(processed, list):
        raise ValueError("notification page arrays required")
    for item in observed:
        _verify_item(item, request=request, runtime=runtime, inspection=True)
    for item in processed:
        _verify_item(item, request=request, runtime=runtime, inspection=False)
    ids = [i["request_id"] for i in observed]
    expected = [(i["request_id"], i["receipt_hash"]) for i in observed if i["result"]["status"] == "not_attempted"]
    if (ids != sorted(set(ids)) or [(i["request_id"], i["receipt_hash"]) for i in processed] != expected):
        raise ValueError("notification page selection/dispatch mismatch")
    integers = ("listing_count", "start_index", "scanned_count", "remaining_in_cycle")
    if (any(type(summary[k]) is not int or not 0 <= summary[k] <= 10000 for k in integers)
            or not _digest(summary["listing_hash"]) or type(summary["wrapped"]) is not bool
            or type(summary["cycle_complete"]) is not bool):
        raise ValueError("notification page bounds invalid")
    total, start, scanned, remaining = (summary[k] for k in integers)
    complete, wrapped = summary["cycle_complete"], summary["wrapped"]
    if (scanned != len(ids) or scanned != min(payload["scan_limit"], total - start)
            or remaining != total - start - scanned or complete != (remaining == 0)
            or (previous is None and (wrapped or start != 0)) or (wrapped and start != 0)
            or (previous is not None and not wrapped and (not ids or ids[0] <= previous))
            or (wrapped and ids and ids[-1] > previous)
            or after != _next_state(context, before, observed, complete)):
        raise ValueError("notification pagination transition mismatch")
    counts = summary["counts"]
    if (not isinstance(counts, dict) or set(counts) != set(_COUNT_KEYS)
            or any(type(v) is not int for v in counts.values()) or counts != _counts(observed, processed)
            or summary["status"] != _status(counts) or receipt != _completion(request, report_path, summary)):
        raise ValueError("notification page completion/count mismatch")
