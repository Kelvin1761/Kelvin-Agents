"""Create-only AU/HKJC variance input from dev-only engine observations.

The generator never reads a terminal metrics artifact and does not calculate a
power threshold.  Its output is consumed by ``research_power_variance`` and has
no profile, sample, experiment, or promotion authority.
"""
from __future__ import annotations

import hashlib
import os
import re
import stat
from datetime import datetime
from pathlib import Path
from typing import Callable

from .contracts import Domain
from .evaluation_rulers import DEFAULT_RULER_ROOT, load_evaluation_ruler
from .research_index import _Reader, _at, _encoded, _hash, _safe
from .research_power_variance import INPUT_SCHEMA, _parse, _validate_metric_value


DEV_SCHEMA = "wong-choi-power-dev-observations/v1"
MAX_INPUT_BYTES = 16 * 1024 * 1024
ROOT_KEYS = {
    "schema_version", "domain", "role", "engine_commit", "variant_id",
    "variant_manifest_sha256", "command_sha256", "ruler_id", "ruler_sha256",
    "dataset_manifest_id", "dataset_manifest_sha256", "dataset_artifact_digest",
    "sample_hash", "generated_at", "source_split", "terminal_metrics_emitted",
    "protocol", "observations",
}
PROTOCOL_KEYS = {
    "protocol_id", "comparison_kind", "preregistered_at", "selected_by_outcome",
}
ROW_KEYS = {"row_id", "event_at", "fold", "cohorts", "metrics"}
HEX64 = re.compile(r"[0-9a-f]{64}")
COMMIT = re.compile(r"[0-9a-f]{40}")


class PowerProjectionError(ValueError):
    """Raised when dev-only engine evidence cannot form a safe pair."""


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact(
    payload: object,
    *,
    role: str,
    domain: Domain,
    ruler_id: str,
    ruler_sha256: str,
    metric_names: set[str],
    cohort_names: set[str],
    as_of: datetime,
    checkpoint: Callable[[], None],
) -> dict:
    if not isinstance(payload, dict) or set(payload) != ROOT_KEYS:
        raise PowerProjectionError("invalid dev observation artifact")
    if payload["schema_version"] != DEV_SCHEMA or payload["domain"] != domain.value:
        raise PowerProjectionError("dev observation domain/schema mismatch")
    if payload["role"] != role:
        raise PowerProjectionError("dev observation role mismatch")
    if (
        not isinstance(payload["engine_commit"], str)
        or COMMIT.fullmatch(payload["engine_commit"]) is None
        or not isinstance(payload["variant_id"], str)
        or not payload["variant_id"].strip()
        or not isinstance(payload["variant_manifest_sha256"], str)
        or HEX64.fullmatch(payload["variant_manifest_sha256"]) is None
        or not isinstance(payload["command_sha256"], str)
        or HEX64.fullmatch(payload["command_sha256"]) is None
    ):
        raise PowerProjectionError("invalid engine/variant command binding")
    if payload["ruler_id"] != ruler_id or payload["ruler_sha256"] != ruler_sha256:
        raise PowerProjectionError("dev observation ruler mismatch")
    for name in ("dataset_manifest_sha256", "dataset_artifact_digest", "sample_hash"):
        if not isinstance(payload[name], str) or HEX64.fullmatch(payload[name]) is None:
            raise PowerProjectionError("invalid dataset lineage digest")
    if (
        not isinstance(payload["dataset_manifest_id"], str)
        or not payload["dataset_manifest_id"].startswith(
            f"wc:{domain.value}:dataset-manifest:"
        )
    ):
        raise PowerProjectionError("invalid dataset lineage identity")
    generated = _at(payload["generated_at"])
    if generated > as_of:
        raise PowerProjectionError("future dev observation artifact")
    if payload["source_split"] != "dev" or payload["terminal_metrics_emitted"] is not False:
        raise PowerProjectionError("terminal metrics are forbidden in dev observation artifact")
    protocol = payload["protocol"]
    if not isinstance(protocol, dict) or set(protocol) != PROTOCOL_KEYS:
        raise PowerProjectionError("invalid neutral protocol")
    if (
        not isinstance(protocol["protocol_id"], str)
        or not protocol["protocol_id"].strip()
        or protocol["comparison_kind"] != "neutral_perturbation"
        or protocol["selected_by_outcome"] is not False
    ):
        raise PowerProjectionError("outcome-selected or non-neutral protocol forbidden")
    if _at(protocol["preregistered_at"]) > generated:
        raise PowerProjectionError("neutral protocol was not pre-registered")
    observations = payload["observations"]
    if not isinstance(observations, list) or len(observations) < 2:
        raise PowerProjectionError("at least two dev observation rows required")
    seen: set[str] = set()
    rows = []
    for row in observations:
        checkpoint()
        if not isinstance(row, dict) or set(row) != ROW_KEYS:
            raise PowerProjectionError("invalid dev observation row")
        identity = row["row_id"]
        if not isinstance(identity, str) or not identity.strip() or identity in seen:
            raise PowerProjectionError("duplicate or invalid dev row identity")
        seen.add(identity)
        event = _at(row["event_at"])
        if event > generated or event > as_of:
            raise PowerProjectionError("future dev observation row")
        if type(row["fold"]) is not int or row["fold"] < 1:
            raise PowerProjectionError("dev row requires a positive fold")
        cohorts, metrics = row["cohorts"], row["metrics"]
        if (
            not isinstance(cohorts, dict)
            or set(cohorts) != cohort_names
            or any(not isinstance(value, str) or not value.strip() for value in cohorts.values())
        ):
            raise PowerProjectionError("dev observation cohort mismatch")
        if not isinstance(metrics, dict) or set(metrics) != metric_names:
            raise PowerProjectionError("dev observation metric mismatch")
        rows.append(
            {
                "row_id": identity,
                "event_at": event.isoformat(),
                "fold": row["fold"],
                "cohorts": dict(cohorts),
                "metrics": {
                    name: _validate_metric_value(name, metrics[name]) for name in sorted(metric_names)
                },
            }
        )
    return {**payload, "generated_at": generated, "protocol": dict(protocol), "observations": rows}


def _write_create_only(path: Path, payload: dict, checkpoint: Callable[[], None]) -> None:
    path = _safe(path)
    parent = path.parent
    if not parent.is_dir() or any(item.is_symlink() for item in (parent, *parent.parents)):
        raise PowerProjectionError("unsafe or missing projection output parent")
    raw = _encoded(payload) + b"\n"
    checkpoint()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        offset = 0
        while offset < len(raw):
            checkpoint()
            offset += os.write(descriptor, raw[offset:])
        os.fsync(descriptor)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise PowerProjectionError("projection output is not a regular file")
    finally:
        os.close(descriptor)
    checkpoint()


def build_power_variance_projection(
    *,
    baseline_path: Path,
    comparator_path: Path,
    output_path: Path,
    domain: Domain | str,
    as_of: datetime,
    ruler_root: Path = DEFAULT_RULER_ROOT,
    checkpoint: Callable[[], None] = lambda: None,
) -> dict:
    """Pair two dev-only engine artifacts and create one variance input."""
    selected = domain if isinstance(domain, Domain) else Domain(str(domain))
    if selected not in {Domain.AU, Domain.HKJC}:
        raise PowerProjectionError("power projection supports AU or HKJC only")
    baseline_path, comparator_path = _safe(Path(baseline_path)), _safe(Path(comparator_path))
    output_path, ruler_root = _safe(Path(output_path)), _safe(Path(ruler_root))
    if output_path.exists():
        raise FileExistsError(f"projection output already exists: {output_path}")
    end = _at(as_of)
    ruler_path = ruler_root / f"{selected.value}-v2.json"
    ruler_before = _digest(ruler_path)
    ruler = load_evaluation_ruler(selected, root=ruler_root)
    ruler_sha256 = _digest(ruler_path)
    if ruler_before != ruler_sha256:
        raise PowerProjectionError("frozen ruler bytes changed during read")
    metrics = {
        str(item["name"])
        for item in ruler.metrics
        if item["role"] in {"primary", "ranking"}
    }
    cohorts = set(ruler.cohorts)
    reader = _Reader(
        checkpoint,
        max_records=2,
        max_record_bytes=MAX_INPUT_BYTES,
        max_total_bytes=MAX_INPUT_BYTES * 4,
    )
    baseline_raw, baseline_sha = reader.read(baseline_path)
    comparator_raw, comparator_sha = reader.read(comparator_path)
    baseline = _artifact(
        baseline_raw,
        role="baseline",
        domain=selected,
        ruler_id=ruler.ruler_id,
        ruler_sha256=ruler_sha256,
        metric_names=metrics,
        cohort_names=cohorts,
        as_of=end,
        checkpoint=checkpoint,
    )
    comparator = _artifact(
        comparator_raw,
        role="neutral_comparator",
        domain=selected,
        ruler_id=ruler.ruler_id,
        ruler_sha256=ruler_sha256,
        metric_names=metrics,
        cohort_names=cohorts,
        as_of=end,
        checkpoint=checkpoint,
    )
    lineage = (
        "engine_commit", "ruler_id", "ruler_sha256", "dataset_manifest_id",
        "dataset_manifest_sha256", "dataset_artifact_digest", "sample_hash",
    )
    if any(baseline[name] != comparator[name] for name in lineage):
        if baseline["engine_commit"] != comparator["engine_commit"]:
            raise PowerProjectionError("neutral pair must use the same frozen engine commit")
        raise PowerProjectionError("neutral pair dataset/ruler lineage mismatch")
    if baseline["protocol"] != comparator["protocol"]:
        raise PowerProjectionError("neutral pair protocol mismatch")
    if baseline["variant_id"] == comparator["variant_id"]:
        raise PowerProjectionError("baseline and neutral variant identities must differ")
    baseline_rows = {row["row_id"]: row for row in baseline["observations"]}
    comparator_rows = {row["row_id"]: row for row in comparator["observations"]}
    if set(baseline_rows) != set(comparator_rows):
        raise PowerProjectionError("neutral pair row identities mismatch")
    rows = []
    for identity in sorted(baseline_rows):
        checkpoint()
        left, right = baseline_rows[identity], comparator_rows[identity]
        if any(left[name] != right[name] for name in ("event_at", "fold", "cohorts")):
            raise PowerProjectionError("neutral pair row provenance mismatch")
        rows.append(
            {
                "unit_id": identity,
                "observed_at": left["event_at"],
                "fold": left["fold"],
                "cohorts": left["cohorts"],
                "baseline": left["metrics"],
                "comparator": right["metrics"],
            }
        )
    protocol = baseline["protocol"]
    generated = max(baseline["generated_at"], comparator["generated_at"])
    identity_hash = _hash(
        {
            "baseline_sha256": baseline_sha,
            "comparator_sha256": comparator_sha,
            "dataset_manifest_sha256": baseline["dataset_manifest_sha256"],
            "protocol": protocol,
        }
    )
    payload = {
        "schema_version": INPUT_SCHEMA,
        "evidence_id": f"wc:{selected.value}:power-variance-input:{identity_hash[:24]}",
        "domain": selected.value,
        "ruler_id": ruler.ruler_id,
        "ruler_sha256": ruler_sha256,
        "generated_at": generated.isoformat(),
        "source_role": "development_only",
        "engine_evidence": {
            "baseline_artifact_sha256": baseline_sha,
            "comparator_artifact_sha256": comparator_sha,
            "baseline_variant_id": baseline["variant_id"],
            "comparator_variant_id": comparator["variant_id"],
            "baseline_variant_manifest_sha256": baseline["variant_manifest_sha256"],
            "comparator_variant_manifest_sha256": comparator["variant_manifest_sha256"],
            "baseline_command_sha256": baseline["command_sha256"],
            "comparator_command_sha256": comparator["command_sha256"],
        },
        "protocol": {
            "protocol_id": protocol["protocol_id"],
            "comparison_kind": protocol["comparison_kind"],
            "preregistered_at": _at(protocol["preregistered_at"]).isoformat(),
            "terminal_accessed": False,
            "selected_by_outcome": False,
        },
        "corpus": {
            "manifest_sha256": baseline["dataset_manifest_sha256"],
            "code_commit": baseline["engine_commit"],
            "unit": ruler.bootstrap["unit"],
            "split": "dev",
        },
        "rows": rows,
    }
    _parse(
        payload,
        domain=selected,
        ruler=ruler,
        ruler_sha256=ruler_sha256,
        as_of=end,
        checkpoint=checkpoint,
    )
    reader.recheck()
    _write_create_only(output_path, payload, checkpoint)
    output_reader = _Reader(
        checkpoint,
        max_records=1,
        max_record_bytes=MAX_INPUT_BYTES,
        max_total_bytes=MAX_INPUT_BYTES * 2,
    )
    stored, _ = output_reader.read(output_path)
    if _encoded(stored) != _encoded(payload):
        raise PowerProjectionError("created projection bytes differ from canonical payload")
    output_reader.recheck()
    return payload


def verify_power_variance_projection(
    *,
    output_path: Path,
    baseline_path: Path,
    comparator_path: Path,
    domain: Domain | str,
    as_of: datetime,
    ruler_root: Path = DEFAULT_RULER_ROOT,
    checkpoint: Callable[[], None] = lambda: None,
) -> None:
    """Re-read projection and both sources, then prove their exact pairing."""
    selected = domain if isinstance(domain, Domain) else Domain(str(domain))
    if selected not in {Domain.AU, Domain.HKJC}:
        raise PowerProjectionError("power projection supports AU or HKJC only")
    output_path = _safe(Path(output_path))
    baseline_path = _safe(Path(baseline_path))
    comparator_path = _safe(Path(comparator_path))
    ruler_root = _safe(Path(ruler_root))
    end = _at(as_of)
    ruler_path = ruler_root / f"{selected.value}-v2.json"
    ruler_before = _digest(ruler_path)
    ruler = load_evaluation_ruler(selected, root=ruler_root)
    ruler_sha256 = _digest(ruler_path)
    if ruler_before != ruler_sha256:
        raise PowerProjectionError("frozen ruler bytes changed during read")
    metrics = {
        str(item["name"])
        for item in ruler.metrics
        if item["role"] in {"primary", "ranking"}
    }
    cohorts = set(ruler.cohorts)
    reader = _Reader(
        checkpoint,
        max_records=3,
        max_record_bytes=MAX_INPUT_BYTES,
        max_total_bytes=MAX_INPUT_BYTES * 6,
    )
    projected, _ = reader.read(output_path)
    baseline_raw, baseline_sha = reader.read(baseline_path)
    comparator_raw, comparator_sha = reader.read(comparator_path)
    baseline = _artifact(
        baseline_raw,
        role="baseline",
        domain=selected,
        ruler_id=ruler.ruler_id,
        ruler_sha256=ruler_sha256,
        metric_names=metrics,
        cohort_names=cohorts,
        as_of=end,
        checkpoint=checkpoint,
    )
    comparator = _artifact(
        comparator_raw,
        role="neutral_comparator",
        domain=selected,
        ruler_id=ruler.ruler_id,
        ruler_sha256=ruler_sha256,
        metric_names=metrics,
        cohort_names=cohorts,
        as_of=end,
        checkpoint=checkpoint,
    )
    _parse(
        projected,
        domain=selected,
        ruler=ruler,
        ruler_sha256=ruler_sha256,
        as_of=end,
        checkpoint=checkpoint,
    )
    evidence = projected["engine_evidence"]
    expected_evidence = {
        "baseline_artifact_sha256": baseline_sha,
        "comparator_artifact_sha256": comparator_sha,
        "baseline_variant_id": baseline["variant_id"],
        "comparator_variant_id": comparator["variant_id"],
        "baseline_variant_manifest_sha256": baseline["variant_manifest_sha256"],
        "comparator_variant_manifest_sha256": comparator["variant_manifest_sha256"],
        "baseline_command_sha256": baseline["command_sha256"],
        "comparator_command_sha256": comparator["command_sha256"],
    }
    if evidence != expected_evidence:
        raise PowerProjectionError("projection engine evidence differs from source artifacts")
    lineage = (
        "engine_commit", "ruler_id", "ruler_sha256", "dataset_manifest_id",
        "dataset_manifest_sha256", "dataset_artifact_digest", "sample_hash",
    )
    if any(baseline[name] != comparator[name] for name in lineage):
        raise PowerProjectionError("projection sources no longer share frozen lineage")
    if baseline["protocol"] != comparator["protocol"]:
        raise PowerProjectionError("projection sources no longer share one protocol")
    baseline_rows = {row["row_id"]: row for row in baseline["observations"]}
    comparator_rows = {row["row_id"]: row for row in comparator["observations"]}
    if set(baseline_rows) != set(comparator_rows):
        raise PowerProjectionError("projection source row identities changed")
    expected_rows = []
    for identity in sorted(baseline_rows):
        checkpoint()
        left, right = baseline_rows[identity], comparator_rows[identity]
        if any(left[name] != right[name] for name in ("event_at", "fold", "cohorts")):
            raise PowerProjectionError("projection source row provenance changed")
        expected_rows.append(
            {
                "unit_id": identity,
                "observed_at": left["event_at"],
                "fold": left["fold"],
                "cohorts": left["cohorts"],
                "baseline": left["metrics"],
                "comparator": right["metrics"],
            }
        )
    if projected["rows"] != expected_rows:
        raise PowerProjectionError("projection rows differ from paired engine observations")
    identity_hash = _hash(
        {
            "baseline_sha256": baseline_sha,
            "comparator_sha256": comparator_sha,
            "dataset_manifest_sha256": baseline["dataset_manifest_sha256"],
            "protocol": baseline["protocol"],
        }
    )
    if projected["evidence_id"] != (
        f"wc:{selected.value}:power-variance-input:{identity_hash[:24]}"
    ):
        raise PowerProjectionError("projection identity differs from paired source evidence")
    reader.recheck()
