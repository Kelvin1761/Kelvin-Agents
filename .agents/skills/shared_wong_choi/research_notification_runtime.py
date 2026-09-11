"""Supervised dispatch of already recorded reviews; disabled without route config.

Credentials travel only through the worker environment, never the persisted phase
request. Trusted deployment code supplies the route; research records cannot grant
notification or model authority. This module installs no scheduler or credentials.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import re

from .contracts import Domain
from .research_evaluation import _write_report
from .research_index import _Reader, _encoded, _hash, _hashed, _safe, load_review_receipt
from .research_notifications import TelegramRoute, ResearchTelegramOutbox, _HELPER
from .research_presentation import SCHEMA as PRESENTATION_SCHEMA
from .research_runner import ResearchDisposition


SUMMARY_SCHEMA = "wong-choi-supervised-notification-summary/v1"
_ENV = ("WC_RESEARCH_NOTIFY_ENABLED", "WC_RESEARCH_NOTIFY_TOKEN", "WC_RESEARCH_NOTIFY_PRIMARY", "WC_RESEARCH_NOTIFY_AUTHORIZED")


def _route_hash(route):
    return _hash({"bot": route.token.split(":", 1)[0], "chat": route.primary_chat_id})


def validate_notification_payload(payload):
    fields = set(payload)
    manual = {"domain", "request_ids", "helper_path", "route_hash"}
    catchup = {"domain", "scan_limit", "helper_path", "route_hash"}
    if fields not in (manual, catchup, manual | {"review_summary_path"}):
        raise ValueError("invalid notification request fields")
    Domain(payload["domain"])
    if fields == catchup:
        if type(payload["scan_limit"]) is not int or not 1 <= payload["scan_limit"] <= 50:
            raise ValueError("notification scan limit must be an integer from 1 to 50")
    else:
        ids = payload["request_ids"]
        if (not isinstance(ids, list) or not 1 <= len(ids) <= 50
            or any(not isinstance(item, str) or not re.fullmatch(r"[0-9a-f]{64}", item) for item in ids)
            or ids != sorted(set(ids))):
            raise ValueError("1 to 50 unique canonical review request IDs required")
    if not isinstance(payload["route_hash"], str) or not re.fullmatch(r"[0-9a-f]{64}", payload["route_hash"]):
        raise ValueError("notification route fingerprint required")
    _safe(payload["helper_path"])
    if "review_summary_path" in payload:
        if not isinstance(payload["review_summary_path"], str):
            raise ValueError("review summary path must be a string")
        _safe(payload["review_summary_path"])
    if len(_encoded(payload)) > 16384:
        raise ValueError("notification request metadata exceeds size bound")


def notification_environment(route, payload):
    validate_notification_payload(payload)
    if not isinstance(route, TelegramRoute) or route.blocked_reason() or _route_hash(route) != payload["route_hash"]:
        raise ValueError("notification route absent, disabled or unbound")
    return dict(zip(_ENV, ("1", route.token, route.primary_chat_id, route.authorized_chat_id)))


@dataclass(frozen=True)
class ResearchNotificationResult:
    disposition: ResearchDisposition
    status: str
    attempt_path: Path | None = None
    report_path: Path | None = None
    content_hash: str | None = None


class ResearchNotificationRunner:
    def __init__(self, runtime, registry):
        self.runtime, self.registry = runtime, registry

    def run(self, *, domain, request_ids, route=None, helper_path=_HELPER,
            review_summary_path=None, estimated_bytes, timeout_seconds):
        from .research_supervision import _phase
        route = route if route is not None else TelegramRoute()
        if not isinstance(route, TelegramRoute) or not isinstance(domain, Domain):
            raise ValueError("known domain and trusted notification route required")
        if route.blocked_reason():
            return ResearchNotificationResult(ResearchDisposition.DEFERRED, route.blocked_reason())
        ids = list(request_ids)
        # Validate duplicates before sorting (do not silently discard a request).
        payload = {"domain": domain.value, "request_ids": sorted(ids),
                   "helper_path": str(helper_path), "route_hash": _route_hash(route)}
        if review_summary_path is not None:
            payload["review_summary_path"] = str(review_summary_path)
        validate_notification_payload(payload)
        disposition, status, attempt, completed = _phase(
            self.runtime, self.registry, None, action="notify", payload=payload,
            estimated_bytes=estimated_bytes, timeout_seconds=timeout_seconds, notification_route=route,
        )
        valid = completed if disposition is ResearchDisposition.SUCCEEDED else {}
        return ResearchNotificationResult(disposition, status, attempt,
                                           Path(valid["report_path"]) if valid.get("report_path") else None,
                                           valid.get("content_hash"))

    def catch_up(self, *, domain, route=None, helper_path=_HELPER, scan_limit=10, estimated_bytes, timeout_seconds):
        """One supervised, bounded page; no scheduler, receipt creation or retry."""
        from .research_supervision import _phase
        route = route if route is not None else TelegramRoute()
        if not isinstance(route, TelegramRoute) or not isinstance(domain, Domain):
            raise ValueError("known domain and trusted notification route required")
        if route.blocked_reason():
            return ResearchNotificationResult(ResearchDisposition.DEFERRED, route.blocked_reason())
        payload = {"domain": domain.value, "scan_limit": scan_limit,
                   "helper_path": str(helper_path), "route_hash": _route_hash(route)}
        validate_notification_payload(payload)
        disposition, status, attempt, completed = _phase(
            self.runtime, self.registry, None, action="notify", payload=payload,
            estimated_bytes=estimated_bytes, timeout_seconds=timeout_seconds, notification_route=route,
        )
        valid = completed if disposition is ResearchDisposition.SUCCEEDED else {}
        return ResearchNotificationResult(disposition, status, attempt,
                                           Path(valid["report_path"]) if valid.get("report_path") else None,
                                           valid.get("content_hash"))


def run_notification_request(request, *, registry, runtime, workspace, checkpoint):
    payload = request["payload"]
    validate_notification_payload(payload)
    enabled, token, primary, authorized = (os.environ.pop(key, "") for key in _ENV)
    route = TelegramRoute(token=token, primary_chat_id=primary, authorized_chat_id=authorized, enabled=enabled == "1")
    notification_environment(route, payload)  # Validate, without re-exporting secrets.
    root = _safe(runtime.state_root / "research-notifications")
    if root.is_relative_to(_safe(runtime.warm_root)):
        raise ValueError("durable HOT notification state must be outside WARM")
    box = ResearchTelegramOutbox(root, route, helper_path=Path(payload["helper_path"]), checkpoint=checkpoint)
    if "scan_limit" in payload:
        from .research_notification_catchup import run_catchup_request
        return run_catchup_request(request, registry=registry, runtime=runtime, workspace=workspace,
                                   checkpoint=checkpoint, box=box)
    processed = []
    summary_path = payload.get("review_summary_path")
    if summary_path is not None:
        path = _safe(summary_path)
        phase_root = _safe(runtime.warm_root / "research-phases" / payload["domain"])
        if not path.is_relative_to(phase_root):
            raise ValueError("notification review summary belongs to another runtime")
        # Verify the entire requested batch before any new send. A summary
        # cannot lend its storage proof to a receipt from a different review.
        for request_id in payload["request_ids"]:
            receipt_path = _safe(runtime.warm_root / "research-reviews" / payload["domain"] / (request_id + ".json"))
            receipt = load_review_receipt(receipt_path)
            if receipt["domain"] != payload["domain"] or _safe(receipt["index"]["registry_root"]) != _safe(registry.root):
                raise ValueError("notification review belongs to another domain or registry")
            box.inspect(receipt_path, expected_receipt_hash=receipt["content_hash"],
                        review_summary_path=summary_path)
    for request_id in payload["request_ids"]:
        checkpoint()
        path = _safe(runtime.warm_root / "research-reviews" / payload["domain"] / (request_id + ".json"))
        receipt = load_review_receipt(path)
        if receipt["domain"] != payload["domain"] or _safe(receipt["index"]["registry_root"]) != _safe(registry.root):
            raise ValueError("notification review belongs to another domain or registry")
        result = box.dispatch(path, expected_receipt_hash=receipt["content_hash"],
                              review_summary_path=summary_path)
        processed.append({"request_id": request_id, "receipt_hash": receipt["content_hash"], "result": result})
    checkpoint()
    counts = {key: sum(item["result"]["status"] == key for item in processed)
              for key in ("sent", "already_sent", "reconcile_required")}
    status = "notification_reconcile_required" if counts["reconcile_required"] else "notifications_recorded"
    summary = {"schema_version": SUMMARY_SCHEMA, "domain": payload["domain"], "request_hash": _hash(request),
               "route_hash": payload["route_hash"], "status": status, "processed": processed, **counts,
               "delivery_confirmed": False, "model_promotion_allowed": False}
    summary["content_hash"] = _hash(summary)
    if len(_encoded(summary)) > 65536:
        raise ValueError("notification summary exceeds metadata bound")
    path = workspace / "notification-summary.json"
    _write_report(path, summary, resource_checkpoint=checkpoint, create_parents=False)
    return _completion(request, path, summary)


def _completion(request, path, summary):
    return {"disposition": "succeeded", "status": summary["status"], "report_path": str(path),
            "content_hash": summary["content_hash"], "request_hash": _hash(request),
            "delivery_confirmed": False, "model_promotion_allowed": False}


def verify_notification_summary(*, request, runtime, report_path, receipt):
    """Parent reads only bounded metadata; receipt and outbox I/O stay supervised."""
    payload = request["payload"]
    validate_notification_payload(payload)
    if "scan_limit" in payload:
        from .research_notification_catchup import verify_catchup_summary
        return verify_catchup_summary(request=request, runtime=runtime, report_path=report_path, receipt=receipt)
    summary, _ = _Reader(lambda: None, max_record_bytes=65536, max_total_bytes=65536).read(report_path)
    _hashed(summary, SUMMARY_SCHEMA)
    expected = {"schema_version", "domain", "request_hash", "route_hash", "status", "processed", "sent", "already_sent",
                "reconcile_required", "delivery_confirmed", "model_promotion_allowed", "content_hash"}
    if (set(summary) != expected or summary["domain"] != payload["domain"] or summary["request_hash"] != _hash(request)
            or summary["route_hash"] != payload["route_hash"] or summary["delivery_confirmed"] is not False
            or summary["model_promotion_allowed"] is not False):
        raise ValueError("notification summary identity or authority mismatch")
    processed = summary["processed"]
    if not isinstance(processed, list) or [item.get("request_id") for item in processed] != payload["request_ids"]:
        raise ValueError("notification summary review set mismatch")
    for item in processed:
        if set(item) != {"request_id", "receipt_hash", "result"} or not re.fullmatch(r"[0-9a-f]{64}", item["receipt_hash"]):
            raise ValueError("invalid notification review receipt")
        result = item["result"]
        dedup_key = _hash({"schema": PRESENTATION_SCHEMA, "registry": request["registry"],
                          "domain": payload["domain"], "request_id": item["request_id"]})
        expected_path = runtime.state_root.expanduser().absolute() / "research-notifications" / payload["domain"] / dedup_key / "intent.json"
        if (set(result) != {"status", "intent_path", "reason", "transport_reported_sent", "delivery_confirmed", "model_promotion_allowed"}
                or result["status"] not in {"sent", "already_sent", "reconcile_required"}
                or result["intent_path"] != str(expected_path)
                or result["delivery_confirmed"] is not False or result["model_promotion_allowed"] is not False
                or result["transport_reported_sent"] is not (result["status"] in {"sent", "already_sent"})
                or result["reason"] not in {"helper_sent", "helper_nonzero", "helper_reply_unconfirmed", "helper_exception",
                                             "intent_without_outcome", "dispatch_precondition_changed"}
                or (result["status"] in {"sent", "already_sent"}) != (result["reason"] == "helper_sent")):
            raise ValueError("notification result status or path mismatch")
    for key in ("sent", "already_sent", "reconcile_required"):
        if type(summary[key]) is not int or summary[key] != sum(item["result"]["status"] == key for item in processed):
            raise ValueError("notification count mismatch")
    status = "notification_reconcile_required" if summary["reconcile_required"] else "notifications_recorded"
    if summary["status"] != status or receipt != _completion(request, report_path, summary):
        raise ValueError("notification completion mismatch")
