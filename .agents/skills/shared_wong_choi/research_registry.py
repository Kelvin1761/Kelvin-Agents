"""Append-only contracts and registry for reproducible Wong Choi research."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Protocol, Union
from urllib.parse import quote
from uuid import uuid4

from .contracts import Domain


SCHEMA_VERSION = "wong-choi-research-record/v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


class ResearchConflictError(RuntimeError):
    """Raised when immutable content or frozen provenance conflicts."""


class MissingResearchParentError(RuntimeError):
    """Raised when a parent is missing, has the wrong kind, or crosses domains."""


class ResearchKind(str, Enum):
    EXPERIMENT_SPEC = "experiment_spec"
    DATASET_MANIFEST = "dataset_manifest"
    EXPERIMENT_RUN = "experiment_run"
    EXPERIMENT_DECISION = "experiment_decision"


class ExperimentRunState(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"


class ExperimentDecisionState(str, Enum):
    REJECT = "reject"
    INCONCLUSIVE = "inconclusive"
    SHADOW_REVIEW_PROPOSAL = "shadow_review_proposal"
    BLOCKED = "blocked"


def _aware(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be ISO-8601: {value!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")
    return parsed


def _digest(value: str, field_name: str) -> None:
    if not _SHA256.fullmatch(value):
        raise ValueError(f"{field_name} must be a full sha256 digest")


def _commit(value: str, field_name: str) -> None:
    if not _GIT_SHA.fullmatch(value):
        raise ValueError(f"{field_name} must be a full git SHA")


def _canonical_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_identity(
    record_id: str, domain: Domain, kind: ResearchKind, created_at: str
) -> None:
    prefix = f"wc:{domain.value}:{kind.value.replace('_', '-')}:"
    if not record_id.startswith(prefix) or not record_id[len(prefix) :].strip():
        raise ValueError(f"record_id must use canonical prefix {prefix!r}")
    _aware(created_at, "created_at")


def _base_payload(record: "ResearchRecord") -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "record_id": record.record_id,
        "kind": record.kind.value,
        "domain": record.domain.value,
        "created_at": record.created_at,
        "links": dict(sorted(record.links.items())),
    }


def _finish(payload: dict[str, Any]) -> dict[str, Any]:
    payload["content_hash"] = _canonical_hash(payload)
    return payload


@dataclass(frozen=True)
class SourceWatermark:
    source_id: str
    available_at: str
    content_digest: str

    def validate(self) -> None:
        if not self.source_id.strip():
            raise ValueError("source watermark source_id is required")
        _aware(self.available_at, "source_watermark.available_at")
        _digest(self.content_digest, "source_watermark.content_digest")


@dataclass(frozen=True)
class DatasetSplit:
    name: str
    row_count: int
    sample_hash: str

    def validate(self) -> None:
        if self.name not in {"train", "dev", "terminal"}:
            raise ValueError(f"unsupported dataset split: {self.name!r}")
        if self.row_count < 1:
            raise ValueError("dataset split row_count must be positive")
        _digest(self.sample_hash, "dataset_split.sample_hash")


class ResearchRecord(Protocol):
    record_id: str
    domain: Domain
    created_at: str

    @property
    def kind(self) -> ResearchKind: ...

    @property
    def links(self) -> Mapping[str, str]: ...

    def validate(self) -> None: ...

    def to_payload(self) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ExperimentSpec:
    record_id: str
    domain: Domain
    created_at: str
    hypothesis: str
    evaluation_ruler_id: str
    evaluation_ruler_digest: str
    baseline_commit: str
    candidate_commit: str
    preregistered_metrics: tuple[str, ...]
    seed: int
    commands: tuple[str, ...]
    protocol_artifact_digest: str
    parent_spec_id: str | None = None

    @property
    def kind(self) -> ResearchKind:
        return ResearchKind.EXPERIMENT_SPEC

    @property
    def links(self) -> Mapping[str, str]:
        return {"parent_spec_id": self.parent_spec_id} if self.parent_spec_id else {}

    def validate(self) -> None:
        _validate_identity(self.record_id, self.domain, self.kind, self.created_at)
        if not self.hypothesis.strip():
            raise ValueError("hypothesis is required")
        if not self.evaluation_ruler_id.startswith(f"{self.domain.value}-"):
            raise ValueError("evaluation_ruler_id must match the experiment domain")
        _digest(self.evaluation_ruler_digest, "evaluation_ruler_digest")
        _commit(self.baseline_commit, "baseline_commit")
        _commit(self.candidate_commit, "candidate_commit")
        metrics = tuple(item.strip() for item in self.preregistered_metrics)
        if not metrics or any(not item for item in metrics):
            raise ValueError("preregistered_metrics cannot be empty")
        if len(set(metrics)) != len(metrics):
            raise ValueError("preregistered_metrics must be unique")
        if self.seed < 0:
            raise ValueError("seed cannot be negative")
        if not self.commands or any(not item.strip() for item in self.commands):
            raise ValueError("commands cannot be empty")
        _digest(self.protocol_artifact_digest, "protocol_artifact_digest")

    def to_payload(self) -> dict[str, Any]:
        self.validate()
        payload = _base_payload(self)
        payload.update(
            {
                "hypothesis": self.hypothesis,
                "evaluation_ruler_id": self.evaluation_ruler_id,
                "evaluation_ruler_digest": self.evaluation_ruler_digest,
                "baseline_commit": self.baseline_commit,
                "candidate_commit": self.candidate_commit,
                "preregistered_metrics": list(self.preregistered_metrics),
                "seed": self.seed,
                "commands": list(self.commands),
                "protocol_artifact_digest": self.protocol_artifact_digest,
            }
        )
        return _finish(payload)


@dataclass(frozen=True)
class DatasetManifest:
    record_id: str
    domain: Domain
    created_at: str
    spec_id: str
    point_in_time_cutoff: str
    sample_hash: str
    row_count: int
    source_watermarks: tuple[SourceWatermark, ...]
    splits: tuple[DatasetSplit, ...]
    artifact_digest: str

    @property
    def kind(self) -> ResearchKind:
        return ResearchKind.DATASET_MANIFEST

    @property
    def links(self) -> Mapping[str, str]:
        return {"spec_id": self.spec_id}

    def validate(self) -> None:
        _validate_identity(self.record_id, self.domain, self.kind, self.created_at)
        cutoff = _aware(self.point_in_time_cutoff, "point_in_time_cutoff")
        if cutoff > _aware(self.created_at, "created_at"):
            raise ValueError("point_in_time_cutoff cannot follow created_at")
        _digest(self.sample_hash, "sample_hash")
        if self.row_count < 1:
            raise ValueError("dataset row_count must be positive")
        if not self.source_watermarks:
            raise ValueError("source_watermarks cannot be empty")
        source_ids = []
        for watermark in self.source_watermarks:
            watermark.validate()
            source_ids.append(watermark.source_id)
            if _aware(watermark.available_at, "source_watermark.available_at") > cutoff:
                raise ValueError("source availability after point-in-time cutoff")
        if len(set(source_ids)) != len(source_ids):
            raise ValueError("source_watermarks must use unique source_id values")
        if {item.name for item in self.splits} != {"train", "dev", "terminal"}:
            raise ValueError("dataset requires exactly train, dev and terminal splits")
        if len(self.splits) != 3:
            raise ValueError("dataset split names must be unique")
        for item in self.splits:
            item.validate()
        if sum(item.row_count for item in self.splits) != self.row_count:
            raise ValueError("split row counts must equal dataset row_count")
        _digest(self.artifact_digest, "artifact_digest")

    def to_payload(self) -> dict[str, Any]:
        self.validate()
        payload = _base_payload(self)
        payload.update(
            {
                "point_in_time_cutoff": self.point_in_time_cutoff,
                "sample_hash": self.sample_hash,
                "row_count": self.row_count,
                "source_watermarks": [asdict(item) for item in self.source_watermarks],
                "splits": [asdict(item) for item in self.splits],
                "artifact_digest": self.artifact_digest,
            }
        )
        return _finish(payload)


@dataclass(frozen=True)
class ExperimentRun:
    record_id: str
    domain: Domain
    created_at: str
    spec_id: str
    dataset_manifest_id: str
    started_at: str
    completed_at: str
    state: ExperimentRunState
    evaluation_ruler_id: str
    evaluation_ruler_digest: str
    baseline_commit: str
    candidate_commit: str
    seed: int
    commands: tuple[str, ...]
    metrics_digest: str
    artifact_digest: str
    stdout_digest: str

    @property
    def kind(self) -> ResearchKind:
        return ResearchKind.EXPERIMENT_RUN

    @property
    def links(self) -> Mapping[str, str]:
        return {"dataset_manifest_id": self.dataset_manifest_id, "spec_id": self.spec_id}

    def validate(self) -> None:
        _validate_identity(self.record_id, self.domain, self.kind, self.created_at)
        started = _aware(self.started_at, "started_at")
        completed = _aware(self.completed_at, "completed_at")
        created = _aware(self.created_at, "created_at")
        if completed < started:
            raise ValueError("completed_at cannot precede started_at")
        if created < completed:
            raise ValueError("created_at cannot precede completed_at")
        ExperimentRunState(self.state)
        if not self.evaluation_ruler_id.startswith(f"{self.domain.value}-"):
            raise ValueError("evaluation_ruler_id must match the run domain")
        _digest(self.evaluation_ruler_digest, "evaluation_ruler_digest")
        _commit(self.baseline_commit, "baseline_commit")
        _commit(self.candidate_commit, "candidate_commit")
        if self.seed < 0:
            raise ValueError("seed cannot be negative")
        if not self.commands or any(not item.strip() for item in self.commands):
            raise ValueError("commands cannot be empty")
        _digest(self.metrics_digest, "metrics_digest")
        _digest(self.artifact_digest, "artifact_digest")
        _digest(self.stdout_digest, "stdout_digest")

    def to_payload(self) -> dict[str, Any]:
        self.validate()
        payload = _base_payload(self)
        payload.update(
            {
                "started_at": self.started_at,
                "completed_at": self.completed_at,
                "state": self.state.value,
                "evaluation_ruler_id": self.evaluation_ruler_id,
                "evaluation_ruler_digest": self.evaluation_ruler_digest,
                "baseline_commit": self.baseline_commit,
                "candidate_commit": self.candidate_commit,
                "seed": self.seed,
                "commands": list(self.commands),
                "metrics_digest": self.metrics_digest,
                "artifact_digest": self.artifact_digest,
                "stdout_digest": self.stdout_digest,
            }
        )
        return _finish(payload)


@dataclass(frozen=True)
class ExperimentDecision:
    record_id: str
    domain: Domain
    created_at: str
    run_id: str
    decided_at: str
    state: ExperimentDecisionState
    rationale: str
    metrics_digest: str
    artifact_digest: str

    @property
    def kind(self) -> ResearchKind:
        return ResearchKind.EXPERIMENT_DECISION

    @property
    def links(self) -> Mapping[str, str]:
        return {"run_id": self.run_id}

    def validate(self) -> None:
        _validate_identity(self.record_id, self.domain, self.kind, self.created_at)
        if _aware(self.created_at, "created_at") < _aware(
            self.decided_at, "decided_at"
        ):
            raise ValueError("created_at cannot precede decided_at")
        ExperimentDecisionState(self.state)
        if not self.rationale.strip():
            raise ValueError("decision rationale is required")
        _digest(self.metrics_digest, "metrics_digest")
        _digest(self.artifact_digest, "artifact_digest")

    def to_payload(self) -> dict[str, Any]:
        self.validate()
        payload = _base_payload(self)
        payload.update(
            {
                "decided_at": self.decided_at,
                "state": self.state.value,
                "rationale": self.rationale,
                "metrics_digest": self.metrics_digest,
                "artifact_digest": self.artifact_digest,
            }
        )
        return _finish(payload)


ResearchRecordType = Union[
    ExperimentSpec, DatasetManifest, ExperimentRun, ExperimentDecision
]


@dataclass(frozen=True)
class ResearchAppendResult:
    status: str
    path: Path
    content_hash: str


def _record_from_payload(payload: Mapping[str, Any]) -> ResearchRecordType:
    kind = ResearchKind(str(payload["kind"]))
    common_fields = {
        "schema_version",
        "record_id",
        "kind",
        "domain",
        "created_at",
        "links",
    }
    kind_fields = {
        ResearchKind.EXPERIMENT_SPEC: {
            "hypothesis",
            "evaluation_ruler_id",
            "evaluation_ruler_digest",
            "baseline_commit",
            "candidate_commit",
            "preregistered_metrics",
            "seed",
            "commands",
            "protocol_artifact_digest",
        },
        ResearchKind.DATASET_MANIFEST: {
            "point_in_time_cutoff",
            "sample_hash",
            "row_count",
            "source_watermarks",
            "splits",
            "artifact_digest",
        },
        ResearchKind.EXPERIMENT_RUN: {
            "started_at",
            "completed_at",
            "state",
            "evaluation_ruler_id",
            "evaluation_ruler_digest",
            "baseline_commit",
            "candidate_commit",
            "seed",
            "commands",
            "metrics_digest",
            "artifact_digest",
            "stdout_digest",
        },
        ResearchKind.EXPERIMENT_DECISION: {
            "decided_at",
            "state",
            "rationale",
            "metrics_digest",
            "artifact_digest",
        },
    }[kind]
    actual_fields = set(payload).difference({"content_hash"})
    expected_fields = common_fields | kind_fields
    unexpected = sorted(actual_fields.difference(expected_fields))
    if unexpected:
        raise ValueError(f"unexpected fields for {kind.value}: {unexpected}")
    missing = sorted(expected_fields.difference(actual_fields))
    if missing:
        raise ValueError(f"missing fields for {kind.value}: {missing}")
    common = {
        "record_id": str(payload["record_id"]),
        "domain": Domain(str(payload["domain"])),
        "created_at": str(payload["created_at"]),
    }
    links = dict(payload.get("links") or {})
    required_links = {
        ResearchKind.EXPERIMENT_SPEC: set(),
        ResearchKind.DATASET_MANIFEST: {"spec_id"},
        ResearchKind.EXPERIMENT_RUN: {"dataset_manifest_id", "spec_id"},
        ResearchKind.EXPERIMENT_DECISION: {"run_id"},
    }[kind]
    allowed_links = (
        {"parent_spec_id"}
        if kind is ResearchKind.EXPERIMENT_SPEC
        else required_links
    )
    unexpected_links = sorted(set(links).difference(allowed_links))
    if unexpected_links:
        raise ValueError(f"unexpected links for {kind.value}: {unexpected_links}")
    missing_links = sorted(required_links.difference(links))
    if missing_links:
        raise ValueError(f"missing links for {kind.value}: {missing_links}")
    if kind is ResearchKind.EXPERIMENT_SPEC:
        record: ResearchRecordType = ExperimentSpec(
            **common,
            hypothesis=str(payload["hypothesis"]),
            evaluation_ruler_id=str(payload["evaluation_ruler_id"]),
            evaluation_ruler_digest=str(payload["evaluation_ruler_digest"]),
            baseline_commit=str(payload["baseline_commit"]),
            candidate_commit=str(payload["candidate_commit"]),
            preregistered_metrics=tuple(payload["preregistered_metrics"]),
            seed=int(payload["seed"]),
            commands=tuple(payload["commands"]),
            protocol_artifact_digest=str(payload["protocol_artifact_digest"]),
            parent_spec_id=links.get("parent_spec_id"),
        )
    elif kind is ResearchKind.DATASET_MANIFEST:
        record = DatasetManifest(
            **common,
            spec_id=str(links["spec_id"]),
            point_in_time_cutoff=str(payload["point_in_time_cutoff"]),
            sample_hash=str(payload["sample_hash"]),
            row_count=int(payload["row_count"]),
            source_watermarks=tuple(
                SourceWatermark(**dict(item)) for item in payload["source_watermarks"]
            ),
            splits=tuple(DatasetSplit(**dict(item)) for item in payload["splits"]),
            artifact_digest=str(payload["artifact_digest"]),
        )
    elif kind is ResearchKind.EXPERIMENT_RUN:
        record = ExperimentRun(
            **common,
            spec_id=str(links["spec_id"]),
            dataset_manifest_id=str(links["dataset_manifest_id"]),
            started_at=str(payload["started_at"]),
            completed_at=str(payload["completed_at"]),
            state=ExperimentRunState(str(payload["state"])),
            evaluation_ruler_id=str(payload["evaluation_ruler_id"]),
            evaluation_ruler_digest=str(payload["evaluation_ruler_digest"]),
            baseline_commit=str(payload["baseline_commit"]),
            candidate_commit=str(payload["candidate_commit"]),
            seed=int(payload["seed"]),
            commands=tuple(payload["commands"]),
            metrics_digest=str(payload["metrics_digest"]),
            artifact_digest=str(payload["artifact_digest"]),
            stdout_digest=str(payload["stdout_digest"]),
        )
    else:
        record = ExperimentDecision(
            **common,
            run_id=str(links["run_id"]),
            decided_at=str(payload["decided_at"]),
            state=ExperimentDecisionState(str(payload["state"])),
            rationale=str(payload["rationale"]),
            metrics_digest=str(payload["metrics_digest"]),
            artifact_digest=str(payload["artifact_digest"]),
        )
    record.validate()
    return record


class ExperimentRegistry:
    """Create-only JSON registry with strict parent and provenance validation."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).expanduser().resolve()

    def path_for(
        self,
        record_or_kind: ResearchRecordType | ResearchKind,
        record_id: str | None = None,
    ) -> Path:
        if isinstance(record_or_kind, ResearchKind):
            kind = record_or_kind
            if record_id is None:
                raise ValueError("record_id is required with a ResearchKind")
            identifier = record_id
        else:
            kind = record_or_kind.kind
            identifier = record_or_kind.record_id
        filename = quote(identifier, safe="._-") + ".json"
        return self.root / "records" / kind.value / filename

    def find(self, record_id: str) -> Path | None:
        for kind in ResearchKind:
            path = self.path_for(kind, record_id)
            if path.exists():
                return path
        return None

    def load(self, record_id: str) -> dict[str, Any]:
        path = self.find(record_id)
        if path is None:
            raise FileNotFoundError(record_id)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("schema_version") != SCHEMA_VERSION:
                raise ValueError(
                    f"unsupported research schema: {payload.get('schema_version')!r}"
                )
            content_hash = payload.pop("content_hash", None)
            if content_hash != _canonical_hash(payload):
                raise ResearchConflictError(
                    f"research content hash mismatch: {record_id}"
                )
            _record_from_payload(payload)
        except ResearchConflictError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise ResearchConflictError(
                f"invalid immutable research record {record_id}: {exc}"
            ) from exc
        payload["content_hash"] = content_hash
        return payload

    def _parent(
        self,
        child: ResearchRecordType,
        link_name: str,
        parent_id: str,
        expected_kind: ResearchKind,
    ) -> dict[str, Any]:
        if self.find(parent_id) is None:
            raise MissingResearchParentError(
                f"missing parent {parent_id!r} for {child.record_id!r}"
            )
        parent = self.load(parent_id)
        if parent["kind"] != expected_kind.value:
            raise MissingResearchParentError(
                f"{link_name} requires {expected_kind.value}, got {parent['kind']}"
            )
        if parent["domain"] != child.domain.value:
            raise MissingResearchParentError(
                f"cross-domain research link blocked: {parent_id!r}"
            )
        return parent

    def _validate_links(self, record: ResearchRecordType) -> None:
        if isinstance(record, ExperimentSpec):
            if record.parent_spec_id:
                self._parent(
                    record,
                    "parent_spec_id",
                    record.parent_spec_id,
                    ResearchKind.EXPERIMENT_SPEC,
                )
            return
        if isinstance(record, DatasetManifest):
            self._parent(
                record, "spec_id", record.spec_id, ResearchKind.EXPERIMENT_SPEC
            )
            return
        if isinstance(record, ExperimentRun):
            spec = self._parent(
                record, "spec_id", record.spec_id, ResearchKind.EXPERIMENT_SPEC
            )
            dataset = self._parent(
                record,
                "dataset_manifest_id",
                record.dataset_manifest_id,
                ResearchKind.DATASET_MANIFEST,
            )
            if dataset["links"]["spec_id"] != record.spec_id:
                raise ResearchConflictError(
                    "dataset_manifest_id does not belong to the frozen spec_id"
                )
            comparisons = {
                "evaluation_ruler_id": record.evaluation_ruler_id,
                "evaluation_ruler_digest": record.evaluation_ruler_digest,
                "baseline_commit": record.baseline_commit,
                "candidate_commit": record.candidate_commit,
                "seed": record.seed,
                "commands": list(record.commands),
            }
            for field_name, value in comparisons.items():
                if spec[field_name] != value:
                    raise ResearchConflictError(
                        f"run {field_name} conflicts with frozen experiment spec"
                    )
            return
        run = self._parent(
            record, "run_id", record.run_id, ResearchKind.EXPERIMENT_RUN
        )
        if run["metrics_digest"] != record.metrics_digest:
            raise ResearchConflictError(
                "decision metrics_digest conflicts with experiment run"
            )
        if _aware(record.decided_at, "decided_at") < _aware(
            str(run["completed_at"]), "completed_at"
        ):
            raise ValueError("decided_at cannot precede run completed_at")

    def append(self, record: ResearchRecordType) -> ResearchAppendResult:
        record.validate()
        self._validate_links(record)
        payload = record.to_payload()
        path = self.path_for(record)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            existing = self.load(record.record_id)
            if existing == payload:
                return ResearchAppendResult(
                    "duplicate", path, str(payload["content_hash"])
                )
            raise ResearchConflictError(
                f"immutable research conflict: {record.record_id}"
            )

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
                raise ResearchConflictError(
                    f"immutable research conflict: {record.record_id}"
                )
            return ResearchAppendResult(
                "duplicate", path, str(payload["content_hash"])
            )
        finally:
            temporary.unlink(missing_ok=True)
        return ResearchAppendResult("created", path, str(payload["content_hash"]))

    def audit(self) -> dict[str, Any]:
        counts = {kind.value: 0 for kind in ResearchKind}
        errors: list[str] = []
        records: list[ResearchRecordType] = []
        for kind in ResearchKind:
            folder = self.root / "records" / kind.value
            if not folder.exists():
                continue
            for path in sorted(folder.glob("*.json")):
                try:
                    raw = json.loads(path.read_text(encoding="utf-8"))
                    payload = self.load(str(raw["record_id"]))
                    records.append(_record_from_payload(payload))
                    counts[kind.value] += 1
                except (OSError, KeyError, ValueError, ResearchConflictError) as exc:
                    errors.append(f"{path}: {type(exc).__name__}: {exc}")
        for record in records:
            try:
                self._validate_links(record)
            except (
                ValueError,
                ResearchConflictError,
                MissingResearchParentError,
            ) as exc:
                errors.append(f"{record.record_id}: {type(exc).__name__}: {exc}")
        return {
            "schema_version": "wong-choi-research-audit/v1",
            "status": "ok" if not errors else "failed",
            "counts": counts,
            "errors": errors,
        }
