"""Create one dev-only power observation artifact from frozen engine metrics.

This boundary packages output from a reviewed domain command.  It never runs or
imports an AU/HKJC scoring engine and cannot grant a power profile, sample or
promotion decision.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Callable, Sequence

from .contracts import Domain
from .evaluation_rulers import DEFAULT_RULER_ROOT, load_evaluation_ruler
from .research_dataset import load_dataset_snapshot
from .research_evaluation import _observation_series, _strict_json
from .research_index import _Reader, _at, _encoded, _hash, _safe
from .research_power_projection import (
    DEV_SCHEMA,
    MAX_INPUT_BYTES,
    _artifact,
    _digest,
    _write_create_only,
)
from .research_power_variance import _validate_metric_value


VARIANT_SCHEMA = "wong-choi-power-variant-manifest/v1"
PROTOCOL_SCHEMA = "wong-choi-power-neutral-protocol/v1"
VARIANT_KEYS = {
    "schema_version", "domain", "role", "variant_id", "engine_commit",
    "purpose", "registered_at", "selected_by_outcome", "terminal_accessed",
    "model_change", "configuration",
}
PROTOCOL_KEYS = {
    "schema_version", "domain", "protocol_id", "comparison_kind",
    "preregistered_at", "selected_by_outcome", "baseline_variant_id",
    "comparator_variant_id",
}
COMMIT = re.compile(r"[0-9a-f]{40}")


class PowerDevProducerError(ValueError):
    """Raised when engine metrics cannot prove an exact dev-only projection."""


def _variant(
    payload: object,
    *,
    domain: Domain,
    role: str,
    engine_commit: str,
    generated_at: datetime,
) -> dict:
    if not isinstance(payload, dict) or set(payload) != VARIANT_KEYS:
        raise PowerDevProducerError("invalid variant manifest contract")
    expected_purpose = "known_good" if role == "baseline" else "neutral_variance_probe"
    if (
        payload["schema_version"] != VARIANT_SCHEMA
        or payload["domain"] != domain.value
        or payload["role"] != role
        or payload["purpose"] != expected_purpose
        or payload["engine_commit"] != engine_commit
    ):
        raise PowerDevProducerError("variant role/purpose/engine commit mismatch")
    if (
        not isinstance(payload["variant_id"], str)
        or not payload["variant_id"].strip()
        or payload["selected_by_outcome"] is not False
    ):
        raise PowerDevProducerError("outcome-selected variant forbidden")
    if payload["terminal_accessed"] is not False:
        raise PowerDevProducerError("terminal access is forbidden")
    if payload["model_change"] is not False:
        raise PowerDevProducerError("variance probe cannot contain a model change")
    if not isinstance(payload["configuration"], dict) or not payload["configuration"]:
        raise PowerDevProducerError("variant configuration must be explicit")
    if _at(payload["registered_at"]) > generated_at:
        raise PowerDevProducerError("variant must be registered before generation")
    return dict(payload)


def _protocol(payload: object, *, domain: Domain, generated_at: datetime) -> dict:
    if not isinstance(payload, dict) or set(payload) != PROTOCOL_KEYS:
        raise PowerDevProducerError("invalid neutral protocol contract")
    if (
        payload["schema_version"] != PROTOCOL_SCHEMA
        or payload["domain"] != domain.value
        or payload["comparison_kind"] != "neutral_perturbation"
        or payload["selected_by_outcome"] is not False
        or not isinstance(payload["protocol_id"], str)
        or not payload["protocol_id"].strip()
    ):
        raise PowerDevProducerError("outcome-selected or non-neutral protocol forbidden")
    if any(
        not isinstance(payload[name], str) or not payload[name].strip()
        for name in ("baseline_variant_id", "comparator_variant_id")
    ) or payload["baseline_variant_id"] == payload["comparator_variant_id"]:
        raise PowerDevProducerError("neutral protocol requires distinct variant identities")
    if _at(payload["preregistered_at"]) > generated_at:
        raise PowerDevProducerError("protocol must be pre-registered")
    return dict(payload)


def _build_power_dev_observation(
    *,
    metrics_path: Path,
    dataset_snapshot: Path,
    variant_manifest_path: Path,
    protocol_path: Path,
    domain: Domain | str,
    role: str,
    engine_commit: str,
    command_argv: Sequence[str],
    generated_at: datetime,
    ruler_root: Path = DEFAULT_RULER_ROOT,
    checkpoint: Callable[[], None] = lambda: None,
) -> dict:
    """Validate a reviewed command's complete dev output and build one artifact."""
    selected = domain if isinstance(domain, Domain) else Domain(str(domain))
    if selected not in {Domain.AU, Domain.HKJC}:
        raise PowerDevProducerError("power dev producer supports AU or HKJC only")
    if role not in {"baseline", "neutral_comparator"}:
        raise PowerDevProducerError("invalid power dev producer role")
    if not isinstance(engine_commit, str) or COMMIT.fullmatch(engine_commit) is None:
        raise PowerDevProducerError("invalid frozen engine commit")
    argv = tuple(command_argv)
    if not argv or any(not isinstance(item, str) or not item.strip() for item in argv):
        raise PowerDevProducerError("reviewed command argv required")
    metrics_path = _safe(Path(metrics_path))
    dataset_snapshot = _safe(Path(dataset_snapshot))
    variant_manifest_path = _safe(Path(variant_manifest_path))
    protocol_path = _safe(Path(protocol_path))
    ruler_root = _safe(Path(ruler_root))
    generated = _at(generated_at)
    ruler_path = ruler_root / f"{selected.value}-v2.json"
    ruler_before = _digest(ruler_path)
    ruler = load_evaluation_ruler(selected, root=ruler_root)
    ruler_sha256 = _digest(ruler_path)
    if ruler_before != ruler_sha256:
        raise PowerDevProducerError("frozen ruler bytes changed during read")

    snapshot = load_dataset_snapshot(dataset_snapshot)
    if snapshot.manifest.domain is not selected:
        raise PowerDevProducerError("dataset snapshot domain mismatch")
    manifest = snapshot.manifest.to_payload()
    rows_bytes = (snapshot.path / "rows.jsonl").read_bytes()
    frozen_rows = [_strict_json(line) for line in rows_bytes.decode("utf-8").splitlines()]
    dev_rows = {row["row_id"]: row for row in frozen_rows if row["split"] == "dev"}
    if len(dev_rows) < 2:
        raise PowerDevProducerError("at least two frozen dev rows required")

    reader = _Reader(
        checkpoint,
        max_records=3,
        max_record_bytes=MAX_INPUT_BYTES,
        max_total_bytes=MAX_INPUT_BYTES * 6,
    )
    metrics_raw, _ = reader.read(metrics_path)
    variant_raw, variant_sha256 = reader.read(variant_manifest_path)
    protocol_raw, _ = reader.read(protocol_path)
    variant = _variant(
        variant_raw,
        domain=selected,
        role=role,
        engine_commit=engine_commit,
        generated_at=generated,
    )
    protocol = _protocol(protocol_raw, domain=selected, generated_at=generated)
    expected_variant = (
        protocol["baseline_variant_id"]
        if role == "baseline"
        else protocol["comparator_variant_id"]
    )
    if variant["variant_id"] != expected_variant:
        raise PowerDevProducerError("variant identity differs from pre-registered protocol")

    series = _observation_series(metrics_raw)
    if (
        series.domain is not selected
        or series.sample_hash != snapshot.manifest.sample_hash
        or series.dataset_manifest_id != snapshot.manifest.record_id
        or series.dataset_artifact_digest != snapshot.manifest.artifact_digest
    ):
        raise PowerDevProducerError("engine metrics dataset lineage mismatch")
    observed = {row.row_id: row for row in series.observations}
    if len(observed) != len(series.observations) or set(observed) != set(dev_rows):
        raise PowerDevProducerError("engine metrics must contain all and only frozen dev rows")
    eligible = {
        str(item["name"])
        for item in ruler.metrics
        if item["role"] in {"primary", "ranking"}
    }
    observations = []
    for identity in sorted(dev_rows):
        checkpoint()
        source, row = dev_rows[identity], observed[identity]
        if (
            row.split != "dev"
            or row.event_at != source["event_at"]
            or row.fold != source["payload"].get("fold")
            or dict(row.cohorts) != source["payload"].get("cohorts")
        ):
            raise PowerDevProducerError("engine metric row provenance mismatch")
        if set(row.metrics) != eligible:
            raise PowerDevProducerError("engine metric contract mismatch")
        observations.append(
            {
                "row_id": identity,
                "event_at": row.event_at,
                "fold": row.fold,
                "cohorts": dict(row.cohorts),
                "metrics": {
                    name: _validate_metric_value(name, row.metrics[name])
                    for name in sorted(eligible)
                },
            }
        )

    payload = {
        "schema_version": DEV_SCHEMA,
        "domain": selected.value,
        "role": role,
        "engine_commit": engine_commit,
        "variant_id": variant["variant_id"],
        "variant_manifest_sha256": variant_sha256,
        "command_sha256": _hash(list(argv)),
        "ruler_id": ruler.ruler_id,
        "ruler_sha256": ruler_sha256,
        "dataset_manifest_id": snapshot.manifest.record_id,
        "dataset_manifest_sha256": manifest["content_hash"],
        "dataset_artifact_digest": snapshot.manifest.artifact_digest,
        "sample_hash": snapshot.manifest.sample_hash,
        "generated_at": generated.isoformat(),
        "source_split": "dev",
        "terminal_metrics_emitted": False,
        "protocol": {
            "protocol_id": protocol["protocol_id"],
            "comparison_kind": protocol["comparison_kind"],
            "preregistered_at": _at(protocol["preregistered_at"]).isoformat(),
            "selected_by_outcome": False,
        },
        "observations": observations,
    }
    _artifact(
        payload,
        role=role,
        domain=selected,
        ruler_id=ruler.ruler_id,
        ruler_sha256=ruler_sha256,
        metric_names=eligible,
        cohort_names=set(ruler.cohorts),
        as_of=generated,
        checkpoint=checkpoint,
    )
    reader.recheck()
    if load_dataset_snapshot(dataset_snapshot).manifest.to_payload() != manifest:
        raise PowerDevProducerError("dataset snapshot changed during production")
    return payload


def produce_power_dev_observation(
    *,
    metrics_path: Path,
    dataset_snapshot: Path,
    variant_manifest_path: Path,
    protocol_path: Path,
    output_path: Path,
    domain: Domain | str,
    role: str,
    engine_commit: str,
    command_argv: Sequence[str],
    generated_at: datetime,
    ruler_root: Path = DEFAULT_RULER_ROOT,
    checkpoint: Callable[[], None] = lambda: None,
) -> dict:
    """Build and create one canonical dev observation artifact without overwrite."""
    output_path = _safe(Path(output_path))
    if output_path.exists():
        raise FileExistsError(f"power dev output already exists: {output_path}")
    payload = _build_power_dev_observation(
        metrics_path=metrics_path,
        dataset_snapshot=dataset_snapshot,
        variant_manifest_path=variant_manifest_path,
        protocol_path=protocol_path,
        domain=domain,
        role=role,
        engine_commit=engine_commit,
        command_argv=command_argv,
        generated_at=generated_at,
        ruler_root=ruler_root,
        checkpoint=checkpoint,
    )
    _write_create_only(output_path, payload, checkpoint)
    verify_power_dev_observation(
        output_path=output_path,
        metrics_path=metrics_path,
        dataset_snapshot=dataset_snapshot,
        variant_manifest_path=variant_manifest_path,
        protocol_path=protocol_path,
        domain=domain,
        role=role,
        engine_commit=engine_commit,
        command_argv=command_argv,
        generated_at=generated_at,
        ruler_root=ruler_root,
        checkpoint=checkpoint,
    )
    return payload


def verify_power_dev_observation(
    *,
    output_path: Path,
    metrics_path: Path,
    dataset_snapshot: Path,
    variant_manifest_path: Path,
    protocol_path: Path,
    domain: Domain | str,
    role: str,
    engine_commit: str,
    command_argv: Sequence[str],
    generated_at: datetime,
    ruler_root: Path = DEFAULT_RULER_ROOT,
    checkpoint: Callable[[], None] = lambda: None,
) -> None:
    """Rebuild expected bytes from frozen sources and reject any output drift."""
    output_path = _safe(Path(output_path))
    expected = _build_power_dev_observation(
        metrics_path=metrics_path,
        dataset_snapshot=dataset_snapshot,
        variant_manifest_path=variant_manifest_path,
        protocol_path=protocol_path,
        domain=domain,
        role=role,
        engine_commit=engine_commit,
        command_argv=command_argv,
        generated_at=generated_at,
        ruler_root=ruler_root,
        checkpoint=checkpoint,
    )
    reader = _Reader(
        checkpoint,
        max_records=1,
        max_record_bytes=MAX_INPUT_BYTES,
        max_total_bytes=MAX_INPUT_BYTES * 2,
    )
    stored, _ = reader.read(output_path)
    if _encoded(stored) != _encoded(expected):
        raise PowerDevProducerError("power dev artifact differs from frozen source evidence")
    reader.recheck()
