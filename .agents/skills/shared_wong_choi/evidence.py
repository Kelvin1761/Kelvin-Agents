"""Append-only evidence records for the central Wong Choi governance plane."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import quote
from uuid import uuid4

from .contracts import Domain


SCHEMA_VERSION = "wong-choi-evidence/v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class EvidenceConflictError(RuntimeError):
    """Raised when an immutable record ID already has different content."""


class MissingEvidenceParentError(RuntimeError):
    """Raised when a record references evidence that has not been appended."""


class RecordKind(str, Enum):
    MODEL_RELEASE = "model_release"
    PREDICTION = "prediction"
    DECISION = "decision"
    SETTLEMENT = "settlement"


class ReleaseStage(str, Enum):
    RESEARCH = "research"
    SHADOW = "shadow"
    PAPER = "paper"
    LIMITED = "limited"
    PRODUCTION = "production"
    RETIRED = "retired"


class DecisionState(str, Enum):
    RECOMMEND = "recommend"
    NO_BET = "no_bet"
    SHADOW = "shadow"
    BLOCKED = "blocked"


class SettlementState(str, Enum):
    SETTLED = "settled"
    HIT = "hit"
    MISS = "miss"
    VOID = "void"
    UNVERIFIED = "unverified"


def _aware(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be ISO-8601: {value!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")
    return parsed


def _hash_payload(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class ArtifactRef:
    path: str
    sha256: str
    captured_at: str
    source: str

    def validate(self) -> None:
        if not self.path.strip() or not self.source.strip():
            raise ValueError("artifact path and source are required")
        if not _SHA256.fullmatch(self.sha256):
            raise ValueError(f"artifact sha256 is invalid: {self.sha256!r}")
        _aware(self.captured_at, "artifact.captured_at")


@dataclass(frozen=True)
class EvidenceRecord:
    record_id: str
    kind: RecordKind
    domain: Domain
    created_at: str
    body: Mapping[str, Any]
    links: Mapping[str, str] = field(default_factory=dict)
    artifacts: tuple[ArtifactRef, ...] = ()

    def validate(self) -> None:
        if not self.record_id.startswith(f"wc:{self.domain.value}:"):
            raise ValueError("record_id must use the record domain canonical prefix")
        _aware(self.created_at, "created_at")
        for artifact in self.artifacts:
            artifact.validate()
            if _aware(artifact.captured_at, "artifact.captured_at") > _aware(
                self.created_at, "created_at"
            ):
                raise ValueError("artifact captured_at cannot be later than record created_at")
        for name, parent in self.links.items():
            if not name.strip() or not parent.startswith("wc:"):
                raise ValueError("evidence links require canonical parent IDs")
        required_links = {
            RecordKind.MODEL_RELEASE: frozenset(),
            RecordKind.PREDICTION: frozenset({"model_release_id"}),
            RecordKind.DECISION: frozenset({"prediction_id"}),
            RecordKind.SETTLEMENT: frozenset({"decision_id"}),
        }[self.kind]
        if not required_links.issubset(self.links):
            missing = sorted(required_links.difference(self.links))
            raise ValueError(f"{self.kind.value} missing required links: {missing}")

        required_body = {
            RecordKind.MODEL_RELEASE: frozenset(
                {"release_stage", "code_commit", "evaluation_contract_version"}
            ),
            RecordKind.PREDICTION: frozenset(
                {"event_id", "source_cutoff_at", "recommendations"}
            ),
            RecordKind.DECISION: frozenset({"decision_state"}),
            RecordKind.SETTLEMENT: frozenset({"settlement_state", "settled_at"}),
        }[self.kind]
        if not required_body.issubset(self.body):
            missing = sorted(required_body.difference(self.body))
            raise ValueError(f"{self.kind.value} missing required body fields: {missing}")
        if self.kind is RecordKind.MODEL_RELEASE:
            ReleaseStage(str(self.body["release_stage"]))
            if not re.fullmatch(r"[0-9a-f]{7,64}", str(self.body["code_commit"])):
                raise ValueError("model release code_commit must be a git hex SHA")
        elif self.kind is RecordKind.PREDICTION:
            cutoff = _aware(str(self.body["source_cutoff_at"]), "source_cutoff_at")
            if cutoff > _aware(self.created_at, "created_at"):
                raise ValueError("source_cutoff_at cannot be later than prediction created_at")
            if not isinstance(self.body["recommendations"], list):
                raise ValueError("prediction recommendations must be a list")
        elif self.kind is RecordKind.DECISION:
            DecisionState(str(self.body["decision_state"]))
        elif self.kind is RecordKind.SETTLEMENT:
            SettlementState(str(self.body["settlement_state"]))
            _aware(str(self.body["settled_at"]), "settled_at")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        payload: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "record_id": self.record_id,
            "kind": self.kind.value,
            "domain": self.domain.value,
            "created_at": self.created_at,
            "links": dict(sorted(self.links.items())),
            "artifacts": [asdict(item) for item in self.artifacts],
            "body": dict(self.body),
        }
        payload["content_hash"] = _hash_payload(payload)
        return payload


@dataclass(frozen=True)
class AppendResult:
    status: str
    path: Path
    content_hash: str


class EvidenceStore:
    """Create-only JSON store; identical retries are idempotent, conflicts fail."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).expanduser().resolve()

    def path_for(self, kind: RecordKind, record_id: str) -> Path:
        filename = quote(record_id, safe="._-") + ".json"
        return self.root / "records" / kind.value / filename

    def find(self, record_id: str) -> Path | None:
        for kind in RecordKind:
            path = self.path_for(kind, record_id)
            if path.exists():
                return path
        return None

    def load(self, record_id: str) -> dict[str, Any]:
        path = self.find(record_id)
        if path is None:
            raise FileNotFoundError(record_id)
        payload = json.loads(path.read_text(encoding="utf-8"))
        content_hash = payload.pop("content_hash", None)
        if content_hash != _hash_payload(payload):
            raise EvidenceConflictError(f"evidence content hash mismatch: {record_id}")
        payload["content_hash"] = content_hash
        return payload

    def append(self, record: EvidenceRecord) -> AppendResult:
        payload = record.to_dict()
        expected_parent_kinds = {
            "model_release_id": RecordKind.MODEL_RELEASE,
            "previous_release_id": RecordKind.MODEL_RELEASE,
            "prediction_id": RecordKind.PREDICTION,
            "decision_id": RecordKind.DECISION,
            "rollback_release_id": RecordKind.MODEL_RELEASE,
        }
        for link_name, parent in record.links.items():
            if self.find(parent) is None:
                raise MissingEvidenceParentError(
                    f"missing parent {parent!r} for {record.record_id!r}"
                )
            parent_payload = self.load(parent)
            expected_kind = expected_parent_kinds.get(link_name)
            if expected_kind is not None and parent_payload["kind"] != expected_kind.value:
                raise MissingEvidenceParentError(
                    f"{link_name} requires {expected_kind.value}, got {parent_payload['kind']}"
                )
            if parent_payload["domain"] != record.domain.value:
                raise MissingEvidenceParentError(
                    f"cross-domain evidence link blocked: {parent!r}"
                )
        path = self.path_for(record.kind, record.record_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            existing = self.load(record.record_id)
            if existing == payload:
                return AppendResult("duplicate", path, payload["content_hash"])
            raise EvidenceConflictError(f"immutable evidence conflict: {record.record_id}")

        temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        try:
            os.link(temporary, path)
        except FileExistsError:
            existing = self.load(record.record_id)
            if existing != payload:
                raise EvidenceConflictError(
                    f"immutable evidence conflict: {record.record_id}"
                )
            return AppendResult("duplicate", path, payload["content_hash"])
        finally:
            temporary.unlink(missing_ok=True)
        return AppendResult("created", path, payload["content_hash"])

    def audit(self) -> dict[str, Any]:
        counts = {kind.value: 0 for kind in RecordKind}
        errors: list[str] = []
        records: list[dict[str, Any]] = []
        for kind in RecordKind:
            folder = self.root / "records" / kind.value
            if not folder.exists():
                continue
            for path in sorted(folder.glob("*.json")):
                try:
                    payload = self.load(json.loads(path.read_text(encoding="utf-8"))["record_id"])
                except (OSError, ValueError, KeyError, EvidenceConflictError) as exc:
                    errors.append(f"{path}: {type(exc).__name__}: {exc}")
                    continue
                counts[kind.value] += 1
                records.append(payload)
        known = {item["record_id"] for item in records}
        for item in records:
            for parent in item.get("links", {}).values():
                if parent not in known:
                    errors.append(f"{item['record_id']}: missing parent {parent}")
        return {
            "schema_version": "wong-choi-evidence-audit/v1",
            "status": "ok" if not errors else "failed",
            "counts": counts,
            "errors": errors,
        }


def artifacts(values: Iterable[Mapping[str, str]]) -> tuple[ArtifactRef, ...]:
    return tuple(ArtifactRef(**dict(value)) for value in values)
