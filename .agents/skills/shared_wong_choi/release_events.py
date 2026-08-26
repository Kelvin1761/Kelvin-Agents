"""Append-only events layered on immutable Wong Choi release manifests."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote
from uuid import uuid4


EVENT_SCHEMA = "wong-choi-release-event/v1"
EVENT_TYPES = frozenset(
    {
        "approval_granted",
        "approval_rejected",
        "merged",
        "activation_started",
        "activation_succeeded",
        "activation_failed",
        "rollback_succeeded",
    }
)


def _hash(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class ReleaseEventStore:
    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()

    def append(
        self,
        *,
        release_id: str,
        commit: str,
        event_type: str,
        actor: str,
        detail: Mapping[str, Any] | None = None,
        created_at: datetime | None = None,
    ) -> dict[str, Any]:
        if event_type not in EVENT_TYPES:
            raise ValueError(f"unknown release event type: {event_type}")
        if not actor.strip():
            raise ValueError("release event actor is required")
        stamp = created_at or datetime.now(timezone.utc)
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError("release event timestamp must be timezone-aware")
        payload: dict[str, Any] = {
            "schema_version": EVENT_SCHEMA,
            "release_id": release_id,
            "commit": commit,
            "event_type": event_type,
            "actor": actor,
            "created_at": stamp.isoformat(),
            "detail": dict(detail or {}),
        }
        payload["content_hash"] = _hash(payload)
        folder = self.root / quote(release_id, safe="._-")
        folder.mkdir(parents=True, exist_ok=True)
        name = f"{stamp.strftime('%Y%m%dT%H%M%S.%fZ')}-{payload['content_hash'][:16]}.json"
        path = folder / name
        temporary = path.with_name(f".{name}.{os.getpid()}.{uuid4().hex}.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        try:
            os.link(temporary, path)
        except FileExistsError:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if existing != payload:
                raise RuntimeError(f"release event conflict: {path}")
        finally:
            temporary.unlink(missing_ok=True)
        return {**payload, "path": str(path)}

    def list(self, release_id: str) -> list[dict[str, Any]]:
        folder = self.root / quote(release_id, safe="._-")
        values: list[dict[str, Any]] = []
        if not folder.exists():
            return values
        for path in sorted(folder.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            content_hash = payload.pop("content_hash", None)
            if content_hash != _hash(payload):
                continue
            payload["content_hash"] = content_hash
            payload["path"] = str(path)
            values.append(payload)
        return values


def effective_status(manifest: Mapping[str, Any], events: list[Mapping[str, Any]]) -> dict:
    status = str(manifest.get("status") or "unknown")
    activation = str(manifest.get("activation") or "not_started")
    approved = False
    for event in events:
        kind = event.get("event_type")
        if kind == "approval_granted":
            approved = True
        elif kind == "approval_rejected":
            approved = False
            status = "rejected"
        elif kind == "merged":
            status = "merged"
        elif kind == "activation_started":
            activation = "running"
        elif kind == "activation_succeeded":
            activation = "succeeded"
        elif kind == "activation_failed":
            activation = "failed"
        elif kind == "rollback_succeeded":
            activation = "rolled_back"
    return {"status": status, "activation": activation, "approved": approved}
