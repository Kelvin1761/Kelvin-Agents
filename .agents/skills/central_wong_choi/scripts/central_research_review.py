#!/usr/bin/env python3
"""Fail-closed Stage 5 Central research review entry.

Cursor creation is an explicit one-time operation.  An ordinary review pass
never creates or repairs cursor state and has no notification, deployment, or
model-promotion authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import stat
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping
from urllib.parse import quote
from uuid import uuid4


HERE = Path(__file__).resolve().parent
PACKAGE_ROOT = HERE.parent
REPO_ROOT = HERE.parents[3]
SKILLS_ROOT = REPO_ROOT / ".agents" / "skills"
sys.path.insert(0, str(SKILLS_ROOT))

from shared_wong_choi.contracts import Domain  # noqa: E402
from shared_wong_choi.evaluation_rulers import (  # noqa: E402
    DEFAULT_RULER_ROOT,
    load_evaluation_ruler,
)
from shared_wong_choi.research_evaluation import _strict_json  # noqa: E402
from shared_wong_choi.research_index import _hash, _hashed, _safe  # noqa: E402
from shared_wong_choi.research_registry import ExperimentRegistry  # noqa: E402
from shared_wong_choi.research_review_cursor import (  # noqa: E402
    LIVENESS_SCHEMA,
    MAX_DB_BYTES,
    SAMPLE_SCHEMA,
    SCHEMA,
    STORAGE_SCHEMA,
    ResearchReviewCursorRunner,
)
from shared_wong_choi.research_runner import (  # noqa: E402
    ResearchDisposition,
    ResearchRuntime,
)
from shared_wong_choi.storage_status import DEFAULT_WARM_ROOT  # noqa: E402


CONTRACT_PATH = PACKAGE_ROOT / "resources" / "stage5_research_runtime.json"
RUNTIME_SCHEMA = "wong-choi-central-research-review-runtime/v1"
RUN_SCHEMA = "wong-choi-central-research-review-run/v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_TABLE_SCHEMAS = {
    "cursor_state": SCHEMA,
    "racing_sample_state": SAMPLE_SCHEMA,
    "storage_evidence_state": STORAGE_SCHEMA,
    "liveness_evidence_state": LIVENESS_SCHEMA,
}
RunnerFactory = Callable[[ResearchRuntime, ExperimentRegistry], Any]


@dataclass(frozen=True)
class DomainBinding:
    domain: Domain
    ruler_id: str
    ruler_digest: str
    model_release_id: str
    model_stage: str


@dataclass(frozen=True)
class ReviewRuntimeContract:
    evaluation_release_id: str
    evaluation_release_commit: str
    ruler_released_at: datetime
    initial_window_start: datetime
    estimated_bytes: int
    timeout_seconds_per_domain: float
    max_reviews_per_domain: int
    reserve_bytes: int
    model_promotion_allowed: bool
    telegram_delivery_confirmed: bool
    domains: Mapping[str, DomainBinding]


def _aware(value: Any, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _positive_int(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{key} must be a positive integer")
    return value


def load_runtime_contract(
    path: Path = CONTRACT_PATH,
    *,
    ruler_root: Path = DEFAULT_RULER_ROOT,
) -> ReviewRuntimeContract:
    """Load the machine-pinned ruler release and verify current ruler bytes."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read Central review runtime contract: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != RUNTIME_SCHEMA:
        raise ValueError("unsupported Central review runtime contract")
    release_id = str(payload.get("evaluation_release_id") or "")
    release_commit = str(payload.get("evaluation_release_commit") or "")
    if not release_id.startswith("wc-release:") or not _GIT_SHA.fullmatch(release_commit):
        raise ValueError("invalid evaluation release binding")
    if payload.get("model_promotion_allowed") is not False:
        raise ValueError("Central review runtime cannot grant model promotion")
    if payload.get("telegram_delivery_confirmed") is not False:
        raise ValueError("Central review runtime cannot confirm message delivery")
    raw_domains = payload.get("domains")
    if not isinstance(raw_domains, dict) or tuple(raw_domains) != tuple(
        domain.value for domain in Domain
    ):
        raise ValueError("Central review runtime must bind all domains in canonical order")
    bindings: dict[str, DomainBinding] = {}
    ruler_root = Path(ruler_root)
    for domain in Domain:
        raw = raw_domains.get(domain.value)
        if not isinstance(raw, dict):
            raise ValueError(f"missing ruler binding for {domain.value}")
        digest = str(raw.get("ruler_digest") or "")
        if not _SHA256.fullmatch(digest):
            raise ValueError(f"invalid ruler digest for {domain.value}")
        ruler = load_evaluation_ruler(domain, root=ruler_root)
        source = ruler_root / f"{ruler.ruler_id}.json"
        observed = hashlib.sha256(source.read_bytes()).hexdigest()
        if observed != digest:
            raise ValueError(f"ruler byte digest changed for {domain.value}")
        expected = {
            "ruler_id": ruler.ruler_id,
            "model_release_id": ruler.model_release_id,
            "model_stage": ruler.model_stage,
        }
        if any(str(raw.get(key) or "") != value for key, value in expected.items()):
            raise ValueError(f"ruler metadata changed for {domain.value}")
        bindings[domain.value] = DomainBinding(
            domain=domain,
            ruler_id=ruler.ruler_id,
            ruler_digest=digest,
            model_release_id=ruler.model_release_id,
            model_stage=ruler.model_stage,
        )
    return ReviewRuntimeContract(
        evaluation_release_id=release_id,
        evaluation_release_commit=release_commit,
        ruler_released_at=_aware(payload.get("ruler_released_at"), "ruler_released_at"),
        initial_window_start=_aware(
            payload.get("initial_window_start"), "initial_window_start"
        ),
        estimated_bytes=_positive_int(payload, "estimated_bytes"),
        timeout_seconds_per_domain=float(
            _positive_int(payload, "timeout_seconds_per_domain")
        ),
        max_reviews_per_domain=_positive_int(payload, "max_reviews_per_domain"),
        reserve_bytes=_positive_int(payload, "reserve_bytes"),
        model_promotion_allowed=False,
        telegram_delivery_confirmed=False,
        domains=MappingProxyType(bindings),
    )


@dataclass(frozen=True)
class _Context:
    repo_root: Path
    state_root: Path
    warm_root: Path
    production_lock_paths: tuple[Path, ...]
    registry: ExperimentRegistry
    runtime: ResearchRuntime
    queue_root: Path
    lease_root: Path
    evidence_root: Path
    storage_state_root: Path
    production_evidence_root: Path


def _absolute_safe(path: Path) -> Path:
    return _safe(Path(path).expanduser().absolute())


def _context(
    *,
    repo_root: Path,
    state_root: Path,
    warm_root: Path,
    production_lock_paths: tuple[Path, ...],
    contract: ReviewRuntimeContract,
) -> _Context:
    if not isinstance(production_lock_paths, tuple) or not production_lock_paths:
        raise ValueError("at least one explicit production lock is required")
    repo = _absolute_safe(repo_root)
    state = _absolute_safe(state_root)
    warm = _absolute_safe(warm_root)
    locks = tuple(_absolute_safe(item) for item in production_lock_paths)
    if len(set(locks)) != len(locks):
        raise ValueError("production lock paths must be unique")
    if not repo.is_dir():
        raise ValueError("existing repository root required")
    if not warm.is_dir():
        raise ValueError("existing WARM root required")
    if state == warm or state.is_relative_to(warm) or warm.is_relative_to(state):
        raise ValueError("HOT state and WARM archive roots must be separate")
    registry = ExperimentRegistry(state / "research-registry")
    runtime = ResearchRuntime(
        state_root=state,
        warm_root=warm,
        production_lock_paths=locks,
        reserve_bytes=contract.reserve_bytes,
    )
    return _Context(
        repo_root=repo,
        state_root=state,
        warm_root=warm,
        production_lock_paths=locks,
        registry=registry,
        runtime=runtime,
        queue_root=state / "research-queue",
        lease_root=state / "research-leases",
        evidence_root=state / "evidence",
        storage_state_root=state / "storage",
        production_evidence_root=state / "evidence",
    )


def _expected_configs(
    context: _Context,
    contract: ReviewRuntimeContract,
    binding: DomainBinding,
) -> dict[str, dict[str, Any]]:
    return {
        "cursor_state": {
            "domain": binding.domain.value,
            "registry": str(context.registry.root),
            "warm_root": str(context.warm_root),
            "initial_window_start": contract.initial_window_start.isoformat(),
            "ruler_digest": binding.ruler_digest,
            "ruler_released_at": contract.ruler_released_at.isoformat(),
            "queue_root": str(context.queue_root),
            "production_evidence_root": str(context.production_evidence_root),
        },
        "racing_sample_state": {
            "domain": binding.domain.value,
            "evidence_root": str(context.evidence_root),
            "relocation_roots": [],
        },
        "storage_evidence_state": {
            "domain": binding.domain.value,
            "repo_root": str(context.repo_root),
            "storage_state_root": str(context.storage_state_root),
        },
        "liveness_evidence_state": {
            "domain": binding.domain.value,
            "queue_root": str(context.queue_root),
            "lease_root": str(context.lease_root),
        },
    }


def _inspect_cursor(
    path: Path,
    expected: Mapping[str, Mapping[str, Any]],
) -> set[str]:
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_DB_BYTES:
        raise ValueError(f"invalid or oversized review cursor: {path.name}")
    try:
        with sqlite3.connect(
            f"file:{quote(str(path))}?mode=ro", uri=True, timeout=0
        ) as database:
            tables = {
                row[0]
                for row in database.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            if "cursor_state" not in tables:
                raise ValueError(f"incomplete review cursor: {path.name}")
            missing: set[str] = set()
            for table, schema in _TABLE_SCHEMAS.items():
                if table not in tables:
                    missing.add(table)
                    continue
                rows = database.execute(f"SELECT id, payload FROM {table}").fetchall()
                if len(rows) != 1 or rows[0][0] != 1:
                    raise ValueError(f"invalid {table} row in {path.name}")
                payload = _strict_json(rows[0][1])
                _hashed(payload, schema)
                if payload.get("config") != expected[table]:
                    raise ValueError(
                        f"{table} configuration changed; independent review required"
                    )
                if payload.get("model_promotion_allowed") is not False:
                    raise ValueError(f"invalid promotion authority in {path.name}")
                if table == "cursor_state" and payload.get(
                    "telegram_delivery_confirmed"
                ) is not False:
                    raise ValueError(f"invalid delivery authority in {path.name}")
                if table == "liveness_evidence_state" and payload.get(
                    "queue_mutation_allowed"
                ) is not False:
                    raise ValueError(f"invalid queue authority in {path.name}")
            return missing
    except sqlite3.DatabaseError as exc:
        raise ValueError(f"cannot verify review cursor {path.name}") from exc


def initialize_review_state(
    *,
    repo_root: Path,
    state_root: Path,
    warm_root: Path,
    production_lock_paths: tuple[Path, ...],
    contract_path: Path = CONTRACT_PATH,
    ruler_root: Path = DEFAULT_RULER_ROOT,
) -> dict[str, Any]:
    """Explicitly create or verify all four HOT cursor bundles."""
    contract = load_runtime_contract(contract_path, ruler_root=ruler_root)
    context = _context(
        repo_root=repo_root,
        state_root=state_root,
        warm_root=warm_root,
        production_lock_paths=production_lock_paths,
        contract=contract,
    )
    cursor_root = context.state_root / "research-review-cursors"
    runner = ResearchReviewCursorRunner(context.runtime, context.registry)
    inspections: dict[Domain, set[str] | None] = {}

    # Validate every existing domain before creating any new state. A changed
    # binding can therefore never leave another domain partially updated.
    if cursor_root.exists() and not cursor_root.is_dir():
        raise ValueError("review cursor root must be a directory")
    for binding in contract.domains.values():
        path = cursor_root / f"{binding.domain.value}.sqlite3"
        inspections[binding.domain] = (
            _inspect_cursor(path, _expected_configs(context, contract, binding))
            if path.exists()
            else None
        )

    for root in (
        context.state_root,
        cursor_root,
        context.registry.root,
        context.queue_root,
        context.lease_root,
        context.evidence_root,
        context.storage_state_root,
        context.production_evidence_root,
    ):
        root.mkdir(parents=True, exist_ok=True)

    created = False
    results: dict[str, dict[str, Any]] = {}
    for binding in contract.domains.values():
        domain = binding.domain
        missing = inspections[domain]
        if missing is None:
            runner.initialize(
                domain=domain,
                initial_window_start=contract.initial_window_start,
                ruler_digest=binding.ruler_digest,
                ruler_released_at=contract.ruler_released_at,
                queue_root=context.queue_root,
                production_evidence_root=context.production_evidence_root,
            )
            missing = set(_TABLE_SCHEMAS) - {"cursor_state"}
            created = True
        if "racing_sample_state" in missing:
            runner.initialize_monitoring_samples(
                domain=domain,
                evidence_root=context.evidence_root,
            )
            created = True
        if "storage_evidence_state" in missing:
            runner.initialize_storage_evidence(
                domain=domain,
                repo_root=context.repo_root,
                storage_state_root=context.storage_state_root,
            )
            created = True
        if "liveness_evidence_state" in missing:
            runner.initialize_liveness_evidence(
                domain=domain,
                queue_root=context.queue_root,
                lease_root=context.lease_root,
            )
            created = True
        path = cursor_root / f"{domain.value}.sqlite3"
        remaining = _inspect_cursor(
            path, _expected_configs(context, contract, binding)
        )
        if remaining:
            raise ValueError(f"incomplete review cursor for {domain.value}")
        results[domain.value] = {
            "status": "verified",
            "cursor_path": str(path),
            "ruler_id": binding.ruler_id,
            "ruler_digest": binding.ruler_digest,
            "model_release_id": binding.model_release_id,
            "model_stage": binding.model_stage,
        }
    return {
        "schema_version": "wong-choi-central-research-review-initialization/v1",
        "status": "initialized" if created else "verified",
        "evaluation_release_id": contract.evaluation_release_id,
        "evaluation_release_commit": contract.evaluation_release_commit,
        "domains": results,
        "model_promotion_allowed": False,
        "telegram_delivery_confirmed": False,
    }


def _write_run(path: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    body = dict(payload)
    body["content_hash"] = _hash(body)
    encoded = (
        json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    published = False
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())

        # A hard link publishes the already durable inode without replacing an
        # existing receipt. The official path can therefore never expose a
        # partially written JSON document.
        os.link(temporary, path)
        published = True
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        if published:
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    return body


def _overall_status(results: Mapping[str, Mapping[str, Any]]) -> str:
    dispositions = [item["disposition"] for item in results.values()]
    if dispositions and all(item == ResearchDisposition.SUCCEEDED.value for item in dispositions):
        return "succeeded"
    if any(item == ResearchDisposition.SUCCEEDED.value for item in dispositions):
        return "partial"
    if dispositions and all(
        item
        in {
            ResearchDisposition.DEFERRED.value,
            ResearchDisposition.PREEMPTED.value,
            ResearchDisposition.TIMED_OUT.value,
        }
        for item in dispositions
    ):
        return "deferred"
    return "failed"


def run_review_pass(
    *,
    repo_root: Path,
    state_root: Path,
    warm_root: Path,
    production_lock_paths: tuple[Path, ...],
    now: datetime | None = None,
    contract_path: Path = CONTRACT_PATH,
    ruler_root: Path = DEFAULT_RULER_ROOT,
    runner_factory: RunnerFactory = ResearchReviewCursorRunner,
) -> dict[str, Any]:
    """Run one bounded four-domain pass without creating cursor state."""
    contract = load_runtime_contract(contract_path, ruler_root=ruler_root)
    context = _context(
        repo_root=repo_root,
        state_root=state_root,
        warm_root=warm_root,
        production_lock_paths=production_lock_paths,
        contract=contract,
    )
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None or clock.utcoffset() is None:
        raise ValueError("review pass clock must be timezone-aware")
    runner = runner_factory(context.runtime, context.registry)
    domain_results: dict[str, dict[str, Any]] = {}
    for binding in contract.domains.values():
        try:
            result = runner.run(
                domain=binding.domain,
                now=clock,
                ruler_digest=binding.ruler_digest,
                ruler_released_at=contract.ruler_released_at,
                estimated_bytes=contract.estimated_bytes,
                timeout_seconds=contract.timeout_seconds_per_domain,
                queue_root=context.queue_root,
                max_reviews=contract.max_reviews_per_domain,
                production_evidence_root=context.production_evidence_root,
            )
            disposition = result.disposition.value
            status = result.status
            cursor_path = str(result.cursor_path) if result.cursor_path else None
            generation = result.generation
            advanced = result.advanced
        except Exception as exc:  # one domain cannot erase the other outcomes
            disposition = ResearchDisposition.BLOCKED.value
            status = f"scheduler_exception:{type(exc).__name__}"
            cursor_path = None
            generation = None
            advanced = False
        domain_results[binding.domain.value] = {
            "disposition": disposition,
            "status": status,
            "cursor_path": cursor_path,
            "generation": generation,
            "advanced": bool(advanced),
            "model_promotion_allowed": False,
            "telegram_delivery_confirmed": False,
        }
    stamp = clock.astimezone(timezone.utc).strftime("%H%M%S.%fZ")
    target_date = clock.astimezone(timezone.utc).date().isoformat()
    run_path = (
        context.state_root
        / "runs"
        / "central"
        / target_date
        / "research-review"
        / f"{stamp}-{uuid4().hex[:12]}.json"
    )
    payload = {
        "schema_version": RUN_SCHEMA,
        "status": _overall_status(domain_results),
        "started_at": clock.isoformat(),
        "evaluation_release_id": contract.evaluation_release_id,
        "evaluation_release_commit": contract.evaluation_release_commit,
        "domains": domain_results,
        "model_promotion_allowed": False,
        "telegram_delivery_confirmed": False,
        "run_log": str(run_path),
    }
    return _write_run(run_path, payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initialize", action="store_true")
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path(os.environ.get("WC_PRIMARY_REPO_ROOT", REPO_ROOT)),
    )
    parser.add_argument(
        "--state-root",
        type=Path,
        default=Path(
            os.environ.get(
                "WONGCHOI_CONTROL_STATE_ROOT",
                Path.home() / "WongChoiData" / "WongChoiControl",
            )
        ),
    )
    parser.add_argument(
        "--warm-root",
        type=Path,
        default=Path(os.environ.get("WC_WARM_ARCHIVE_ROOT", str(DEFAULT_WARM_ROOT))),
    )
    parser.add_argument(
        "--production-lock",
        action="append",
        type=Path,
        required=True,
        help="repeat once for each configured production runtime lock",
    )
    parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    args = parser.parse_args()
    options = {
        "repo_root": args.repo,
        "state_root": args.state_root,
        "warm_root": args.warm_root,
        "production_lock_paths": tuple(args.production_lock),
        "contract_path": args.contract,
    }
    result = (
        initialize_review_state(**options)
        if args.initialize
        else run_review_pass(**options)
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] in {"initialized", "verified", "succeeded", "partial", "deferred"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
