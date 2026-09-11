"""Create-only research Telegram intents and transport outcomes.

No scheduler is installed here. Route configuration is trusted deployment input,
not authority obtained from a research receipt. Disabled by default. Use the
existing Telegram helper in a subprocess with a pinned primary recipient; never
send to content/extra readers. No automatic retry after an intent is committed.
An acknowledged helper response is not an independent Telegram delivery receipt.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
from uuid import uuid4

from .research_index import _Reader, _at, _encoded, _hash, _hashed, _safe
from .research_presentation import prepare_review_presentation
from .research_safety import ResearchSafetyError, _json


INTENT_SCHEMA = "wong-choi-research-notification-intent/v1"
OUTCOME_SCHEMA = "wong-choi-research-notification-outcome/v1"
_SENT = {"ok": True, "status": "sent", "sent_parts": 1, "sent_targets": 1}
_HELPER = Path(__file__).resolve().parents[1] / "shared_racing/scripts/racing_telegram.py"


class NotificationError(RuntimeError):
    pass


@dataclass(frozen=True)
class TelegramRoute:
    token: str = field(default="", repr=False)
    primary_chat_id: str = field(default="", repr=False)
    authorized_chat_id: str = field(default="", repr=False)
    enabled: bool = False

    def blocked_reason(self):
        if self.enabled is not True or os.environ.get("WC_TELEGRAM_DISABLE", "").lower().strip() in {"1", "true", "yes"}:
            return "disabled"
        if not isinstance(self.token, str) or not re.fullmatch(r"[1-9][0-9]*:[A-Za-z0-9_-]+", self.token):
            return "not_configured"
        if (not isinstance(self.primary_chat_id, str) or not re.fullmatch(r"-?[1-9][0-9]*", self.primary_chat_id)
                or self.primary_chat_id != self.authorized_chat_id):
            return "unauthorized_route"
        return None


def _seal(payload):
    return {**payload, "content_hash": _hash(payload)}


def _sync_directory(folder):
    descriptor = os.open(folder, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _create(path, payload):
    """Return True only for the creator after file and directory durability."""
    path = _safe(path)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(_encoded(payload))
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            return False
        _sync_directory(path.parent)
        return True
    finally:
        temporary.unlink(missing_ok=True)


def _read(path, schema):
    payload, _ = _Reader(lambda: None, max_record_bytes=65536).read(path)
    return _hashed(payload, schema)


def _valid_sent(reply):
    # bool is an int subclass, so equality with the expected dict is insufficient.
    return (isinstance(reply, dict) and set(reply) == set(_SENT) and reply["ok"] is True
            and reply["status"] == "sent" and type(reply["sent_parts"]) is int
            and type(reply["sent_targets"]) is int and reply == _SENT)


def _result(status, *, path=None, reason=None):
    return {"status": status, "intent_path": str(path) if path else None, "reason": reason,
            "transport_reported_sent": status in {"sent", "already_sent"},
            "delivery_confirmed": False, "model_promotion_allowed": False}


class ResearchTelegramOutbox:
    def __init__(self, root, route, *, helper_path=_HELPER, run=subprocess.run,
                 clock=lambda: datetime.now(timezone.utc), checkpoint=lambda: None):
        if not isinstance(route, TelegramRoute):
            raise NotificationError("trusted TelegramRoute configuration required")
        self.root, self.route, self.helper_path = Path(root), route, Path(helper_path)
        self.run, self.clock, self.checkpoint = run, clock, checkpoint

    def _prepare(self, receipt_path, expected_receipt_hash, review_summary_path=None):
        self.checkpoint()
        root = _safe(self.root)
        if not root.is_dir():
            raise NotificationError("existing local outbox root required; storage unavailable")
        helper = _safe(self.helper_path)
        if not helper.is_file() or helper.stat().st_size > 1048576:
            raise NotificationError("bounded local Telegram helper required")
        helper_hash = hashlib.sha256(helper.read_bytes()).hexdigest()
        presentation = prepare_review_presentation(
            receipt_path, review_summary_path=review_summary_path,
        )
        view, preview = presentation["projection"], presentation["telegram"]
        if expected_receipt_hash is not None and view["receipt_hash"] != expected_receipt_hash:
            raise NotificationError("review receipt changed after scope verification")
        # Preserve preview semantics; the wire copy must not claim it was unsent.
        lines = preview["text"].splitlines()
        lines[0] = lines[0].replace("（本機預覽）", "")
        lines[-1] = "只係研究通知；唔代表批准部署、下注或模型升級。"
        text = "\n".join(lines)
        if len(text.encode("utf-16-le")) // 2 > 4096:
            raise NotificationError("research digest must fit one Telegram message")
        route = self.route
        binding = {
            "dedup_key": preview["dedup_key"], "domain": view["domain"], "request_id": view["request_id"],
            "receipt_hash": view["receipt_hash"], "projection_hash": view["content_hash"],
            "preview_hash": preview["content_hash"], "message_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "route_hash": _hash({"bot": route.token.split(":", 1)[0], "chat": route.primary_chat_id}),
            "helper_sha256": helper_hash,
        }
        folder = _safe(root / view["domain"] / preview["dedup_key"])
        return folder, binding, text, helper, helper_hash

    def _existing(self, folder, binding):
        intent_path, outcome_path = _safe(folder / "intent.json"), _safe(folder / "outcome.json")
        if not intent_path.exists():
            if outcome_path.exists():
                raise NotificationError("orphan notification outcome")
            return _result("not_attempted", path=intent_path, reason="no_intent")
        intent = _read(intent_path, INTENT_SCHEMA)
        if (set(intent) != {"schema_version", "binding", "created_at", "model_promotion_allowed", "content_hash"}
                or intent["binding"] != binding or intent["model_promotion_allowed"] is not False):
            raise NotificationError("immutable notification intent conflict")
        _at(intent["created_at"])
        if not outcome_path.exists():
            return _result("reconcile_required", path=intent_path, reason="intent_without_outcome")
        outcome = _read(outcome_path, OUTCOME_SCHEMA)
        expected = {"schema_version", "intent_hash", "created_at", "status", "reason", "helper_reply",
                    "delivery_confirmed", "model_promotion_allowed", "content_hash"}
        if (set(outcome) != expected or outcome["intent_hash"] != intent["content_hash"]
                or _at(outcome["created_at"]) < _at(intent["created_at"])
                or outcome["delivery_confirmed"] is not False or outcome["model_promotion_allowed"] is not False
                or outcome["status"] not in {"sent", "unconfirmed"}
                or outcome["reason"] not in {"helper_sent", "helper_nonzero", "helper_reply_unconfirmed", "helper_exception"}
                or (outcome["status"] == "sent") != _valid_sent(outcome["helper_reply"])
                or (outcome["status"] == "sent") != (outcome["reason"] == "helper_sent")):
            raise NotificationError("notification outcome identity or semantics conflict")
        return _result("already_sent" if outcome["status"] == "sent" else "reconcile_required",
                       path=intent_path, reason=outcome["reason"])

    def inspect(self, receipt_path, *, expected_receipt_hash=None, review_summary_path=None):
        """Verify receipt/route/outbox state without creating an intent or sending."""
        blocked = self.route.blocked_reason()
        if blocked:
            return _result(blocked)
        folder, binding, _, _, _ = self._prepare(
            receipt_path, expected_receipt_hash, review_summary_path,
        )
        result = self._existing(folder, binding)
        self.checkpoint()
        return result

    def dispatch(self, receipt_path, *, expected_receipt_hash=None, review_summary_path=None):
        blocked = self.route.blocked_reason()
        if blocked:
            return _result(blocked)
        folder, binding, text, helper, helper_hash = self._prepare(
            receipt_path, expected_receipt_hash, review_summary_path,
        )
        root, route = self.root, self.route
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        _sync_directory(folder.parent)
        _sync_directory(root)
        intent_path, outcome_path = _safe(folder / "intent.json"), _safe(folder / "outcome.json")
        if outcome_path.exists() and not intent_path.exists():
            raise NotificationError("orphan notification outcome")
        intent = _seal({"schema_version": INTENT_SCHEMA, "binding": binding,
                        "created_at": _at(self.clock()).isoformat(), "model_promotion_allowed": False})
        self.checkpoint()
        created = _create(intent_path, intent)
        if not created:
            return self._existing(folder, binding)

        # An interruption from here onwards deliberately leaves an unresolved
        # intent. Its presence must stop automatic replay after any crash.
        self.checkpoint()
        if route.blocked_reason() or hashlib.sha256(_safe(helper).read_bytes()).hexdigest() != helper_hash:
            return _result("reconcile_required", path=intent_path, reason="dispatch_precondition_changed")
        env = {**os.environ, "TELEGRAM_BOT_TOKEN": route.token, "WC_NOTIFY_TELEGRAM_TOKEN": route.token,
               "TELEGRAM_CHAT_ID": route.primary_chat_id, "WC_NOTIFY_TELEGRAM_CHAT": route.primary_chat_id,
               "WC_NOTIFY_TELEGRAM_EXTRA": "", "PYTHONDONTWRITEBYTECODE": "1"}
        reply, reason = None, "helper_exception"
        try:
            result = self.run([sys.executable, str(helper), "--message", text, "--audience", "primary", "--json"],
                              env=env, capture_output=True, text=True, timeout=30, check=False)
            if result.returncode != 0:
                reason = "helper_nonzero"
            else:
                value = _json(result.stdout.encode()) if len(result.stdout) <= 65536 else None
                reply = dict(_SENT) if _valid_sent(value) else None
                reason = "helper_sent" if reply else "helper_reply_unconfirmed"
        except (OSError, ValueError, subprocess.SubprocessError, ResearchSafetyError):
            # Never persist exception text / stderr: URLs can contain bot tokens.
            pass
        outcome = _seal({"schema_version": OUTCOME_SCHEMA, "intent_hash": intent["content_hash"],
                         "created_at": _at(self.clock()).isoformat(), "status": "sent" if reply else "unconfirmed",
                         "reason": reason, "helper_reply": reply,
                         "delivery_confirmed": False, "model_promotion_allowed": False})
        self.checkpoint()
        if not _create(outcome_path, outcome):
            raise NotificationError("immutable notification outcome conflict")
        return _result("sent" if reply else "reconcile_required", path=intent_path, reason=reason)
