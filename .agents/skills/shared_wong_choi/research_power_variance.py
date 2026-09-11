"""Read-only AU/HKJC development variance evidence.

This contract describes paired metric variation from a pre-registered neutral
comparison or a frozen independent candidate archive.  It does not select a
minimum material effect, write a power profile, qualify samples, or authorize a
model change.
"""
from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import fmean, stdev
from typing import Callable

from .contracts import Domain
from .evaluation_rulers import DEFAULT_RULER_ROOT, EvaluationRuler, load_evaluation_ruler
from .research_index import _Reader, _at, _encoded, _hash, _hashed, _safe


SCHEMA = "wong-choi-power-variance/v1"
INPUT_SCHEMA = "wong-choi-power-variance-input/v1"
MAX_INPUT_BYTES = 16 * 1024 * 1024
COMPARISON_KINDS = {"neutral_perturbation", "independent_candidate_archive"}
ROOT_KEYS = {
    "schema_version", "evidence_id", "domain", "ruler_id", "ruler_sha256",
    "generated_at", "source_role", "engine_evidence", "protocol", "corpus", "rows",
}
ENGINE_EVIDENCE_KEYS = {
    "baseline_artifact_sha256", "comparator_artifact_sha256",
    "baseline_variant_id", "comparator_variant_id",
    "baseline_variant_manifest_sha256", "comparator_variant_manifest_sha256",
    "baseline_command_sha256", "comparator_command_sha256",
}
ROW_KEYS = {"unit_id", "observed_at", "fold", "cohorts", "baseline", "comparator"}
PROTOCOL_KEYS = {
    "protocol_id", "comparison_kind", "preregistered_at", "terminal_accessed",
    "selected_by_outcome",
}
CORPUS_KEYS = {"manifest_sha256", "code_commit", "unit", "split"}
HEX64 = re.compile(r"[0-9a-f]{64}")
COMMIT = re.compile(r"[0-9a-f]{40}")


class PowerVarianceError(ValueError):
    """Raised when descriptive variance evidence is unsafe or noncanonical."""


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _number(value: object) -> bool:
    return type(value) in {int, float} and math.isfinite(float(value))


def _ruler_path(root: Path, domain: Domain) -> Path:
    matches = sorted(root.glob(f"{domain.value}-v*.json"))
    if len(matches) != 1:
        raise PowerVarianceError(f"expected one frozen ruler for {domain.value}")
    return matches[0]


def _eligible(ruler: EvaluationRuler) -> dict[str, dict]:
    return {
        str(item["name"]): dict(item)
        for item in ruler.metrics
        if item["role"] in {"primary", "ranking"}
    }


def _validate_metric_value(name: str, value: object) -> float:
    if not _number(value):
        raise PowerVarianceError(f"non-finite metric value: {name}")
    number = float(value)
    if name == "mean_top3_model_rank":
        if number < 1:
            raise PowerVarianceError("ordinal rank metric must be at least one")
    elif not 0 <= number <= 1:
        raise PowerVarianceError(f"bounded metric value outside zero to one: {name}")
    return number


def _percentile(values: list[float], fraction: float) -> float:
    """Nearest-rank percentile with a deterministic lower bound of one item."""
    ordered = sorted(values)
    index = max(0, math.ceil(fraction * len(ordered)) - 1)
    return ordered[index]


def _parse(
    payload: object,
    *,
    domain: Domain,
    ruler: EvaluationRuler,
    ruler_sha256: str,
    as_of: datetime,
    checkpoint: Callable[[], None],
) -> dict:
    if not isinstance(payload, dict) or set(payload) != ROOT_KEYS:
        raise PowerVarianceError("invalid power variance input contract")
    if payload["schema_version"] != INPUT_SCHEMA:
        raise PowerVarianceError("unsupported power variance input schema")
    if (
        payload["domain"] != domain.value
        or not isinstance(payload["evidence_id"], str)
        or re.fullmatch(
            rf"wc:{domain.value}:power-variance-input:[a-z0-9][a-z0-9._-]*",
            payload["evidence_id"],
        ) is None
    ):
        raise PowerVarianceError("power variance identity/domain mismatch")
    if payload["ruler_id"] != ruler.ruler_id or payload["ruler_sha256"] != ruler_sha256:
        raise PowerVarianceError("power variance ruler binding mismatch")
    generated = _at(payload["generated_at"])
    if generated > as_of:
        raise PowerVarianceError("future power variance input")
    if payload["source_role"] != "development_only":
        raise PowerVarianceError("development-only source role required")

    engine_evidence = payload["engine_evidence"]
    if not isinstance(engine_evidence, dict) or set(engine_evidence) != ENGINE_EVIDENCE_KEYS:
        raise PowerVarianceError("invalid engine evidence contract")
    digest_fields = ENGINE_EVIDENCE_KEYS - {
        "baseline_variant_id", "comparator_variant_id",
    }
    if any(
        not isinstance(engine_evidence[name], str)
        or HEX64.fullmatch(engine_evidence[name]) is None
        for name in digest_fields
    ):
        raise PowerVarianceError("invalid engine evidence digest")
    baseline_variant = engine_evidence["baseline_variant_id"]
    comparator_variant = engine_evidence["comparator_variant_id"]
    if (
        not isinstance(baseline_variant, str)
        or not baseline_variant.strip()
        or not isinstance(comparator_variant, str)
        or not comparator_variant.strip()
        or baseline_variant == comparator_variant
    ):
        raise PowerVarianceError("distinct engine variant identities required")

    protocol = payload["protocol"]
    if not isinstance(protocol, dict) or set(protocol) != PROTOCOL_KEYS:
        raise PowerVarianceError("invalid pre-registered protocol")
    if (
        not isinstance(protocol["protocol_id"], str)
        or not protocol["protocol_id"].strip()
        or protocol["comparison_kind"] not in COMPARISON_KINDS
        or protocol["terminal_accessed"] is not False
    ):
        raise PowerVarianceError("development-only protocol forbids terminal access")
    if protocol["selected_by_outcome"] is not False:
        raise PowerVarianceError("pre-registered comparison cannot be selected by outcome")
    preregistered = _at(protocol["preregistered_at"])
    if preregistered > generated:
        raise PowerVarianceError("pre-registered protocol must precede generation")

    corpus = payload["corpus"]
    if not isinstance(corpus, dict) or set(corpus) != CORPUS_KEYS:
        raise PowerVarianceError("invalid development corpus binding")
    if (
        not isinstance(corpus["manifest_sha256"], str)
        or HEX64.fullmatch(corpus["manifest_sha256"]) is None
        or not isinstance(corpus["code_commit"], str)
        or COMMIT.fullmatch(corpus["code_commit"]) is None
        or corpus["unit"] != ruler.bootstrap["unit"]
        or corpus["split"] != "dev"
    ):
        raise PowerVarianceError("development-only corpus/race unit binding mismatch")

    rows = payload["rows"]
    if not isinstance(rows, list) or len(rows) < 2:
        raise PowerVarianceError("at least two development units required")
    eligible = _eligible(ruler)
    expected_metrics = set(eligible)
    expected_cohorts = set(ruler.cohorts)
    seen: set[str] = set()
    parsed_rows = []
    for row in rows:
        checkpoint()
        if not isinstance(row, dict) or set(row) != ROW_KEYS:
            raise PowerVarianceError("invalid variance unit row")
        identity = row["unit_id"]
        if not isinstance(identity, str) or not identity.strip() or identity in seen:
            raise PowerVarianceError("duplicate or invalid variance unit identity")
        seen.add(identity)
        observed = _at(row["observed_at"])
        if observed > as_of or observed > generated:
            raise PowerVarianceError("future variance unit")
        if type(row["fold"]) is not int or row["fold"] < 0:
            raise PowerVarianceError("invalid development fold")
        cohorts = row["cohorts"]
        if (
            not isinstance(cohorts, dict)
            or set(cohorts) != expected_cohorts
            or any(not isinstance(value, str) or not value.strip() for value in cohorts.values())
        ):
            raise PowerVarianceError("cohort contract mismatch")
        baseline, comparator = row["baseline"], row["comparator"]
        if (
            not isinstance(baseline, dict)
            or not isinstance(comparator, dict)
            or set(baseline) != expected_metrics
            or set(comparator) != expected_metrics
        ):
            raise PowerVarianceError("metric contract mismatch")
        parsed_rows.append(
            {
                "unit_id": identity,
                "fold": row["fold"],
                "cohorts": dict(cohorts),
                "baseline": {
                    name: _validate_metric_value(name, baseline[name]) for name in sorted(eligible)
                },
                "comparator": {
                    name: _validate_metric_value(name, comparator[name]) for name in sorted(eligible)
                },
            }
        )
    return {
        "evidence_id": payload["evidence_id"],
        "generated_at": generated,
        "engine_evidence": dict(engine_evidence),
        "protocol": dict(protocol),
        "corpus": dict(corpus),
        "rows": parsed_rows,
        "eligible": eligible,
    }


def _build(
    *,
    input_path: Path,
    domain: Domain,
    as_of: datetime,
    ruler_root: Path,
    checkpoint: Callable[[], None],
) -> dict:
    input_path, ruler_root = _safe(input_path), _safe(ruler_root)
    end = _at(as_of)
    ruler_path = _ruler_path(ruler_root, domain)
    ruler_digest_before = _digest(ruler_path)
    ruler = load_evaluation_ruler(domain, root=ruler_root)
    ruler_sha256 = _digest(ruler_path)
    if ruler_sha256 != ruler_digest_before:
        raise PowerVarianceError("frozen ruler bytes changed during read")
    reader = _Reader(
        checkpoint,
        max_records=1,
        max_record_bytes=MAX_INPUT_BYTES,
        max_total_bytes=MAX_INPUT_BYTES * 2,
    )
    payload, input_sha256 = reader.read(input_path)
    parsed = _parse(
        payload,
        domain=domain,
        ruler=ruler,
        ruler_sha256=ruler_sha256,
        as_of=end,
        checkpoint=checkpoint,
    )
    metrics = []
    for name, contract in sorted(parsed["eligible"].items()):
        checkpoint()
        sign = 1 if contract["direction"] == "maximize" else -1
        deltas = [
            sign * (row["comparator"][name] - row["baseline"][name])
            for row in parsed["rows"]
        ]
        absolute = [abs(value) for value in deltas]
        metrics.append(
            {
                "name": name,
                "role": contract["role"],
                "direction": contract["direction"],
                "units": len(deltas),
                "delta_mean": fmean(deltas),
                "delta_sd": stdev(deltas),
                "delta_min": min(deltas),
                "delta_max": max(deltas),
                "absolute_delta_p50": _percentile(absolute, 0.5),
                "absolute_delta_p90": _percentile(absolute, 0.9),
            }
        )
    cohort_counts = {
        name: dict(sorted(Counter(row["cohorts"][name] for row in parsed["rows"]).items()))
        for name in sorted(ruler.cohorts)
    }
    checkpoint()
    reader.recheck()
    report = {
        "schema_version": SCHEMA,
        "input_path": str(input_path),
        "input_sha256": input_sha256,
        "as_of": end.isoformat(),
        "evidence_id": parsed["evidence_id"],
        "domain": domain.value,
        "ruler_id": ruler.ruler_id,
        "ruler_sha256": ruler_sha256,
        "generated_at": parsed["generated_at"].isoformat(),
        "engine_evidence": parsed["engine_evidence"],
        "protocol_id": parsed["protocol"]["protocol_id"],
        "comparison_kind": parsed["protocol"]["comparison_kind"],
        "corpus_manifest_sha256": parsed["corpus"]["manifest_sha256"],
        "code_commit": parsed["corpus"]["code_commit"],
        "unit": parsed["corpus"]["unit"],
        "units": len(parsed["rows"]),
        "folds": sorted({row["fold"] for row in parsed["rows"]}),
        "cohort_counts": cohort_counts,
        "metrics": metrics,
        "variance_input_contract_verified": True,
        "power_profile_write_allowed": False,
        "verified_monitoring_samples": None,
        "model_promotion_allowed": False,
    }
    report["content_hash"] = _hash(report)
    return report


def inspect_power_variance(
    *,
    input_path: Path,
    domain: Domain | str,
    as_of: datetime,
    ruler_root: Path = DEFAULT_RULER_ROOT,
    checkpoint: Callable[[], None] = lambda: None,
) -> dict:
    selected = domain if isinstance(domain, Domain) else Domain(str(domain))
    if selected not in {Domain.AU, Domain.HKJC}:
        raise PowerVarianceError("power variance input contract supports AU or HKJC only")
    report = _build(
        input_path=Path(input_path),
        domain=selected,
        as_of=as_of,
        ruler_root=Path(ruler_root),
        checkpoint=checkpoint,
    )
    verify_power_variance_report(
        report,
        input_path=Path(input_path),
        domain=selected,
        as_of=as_of,
        ruler_root=Path(ruler_root),
        checkpoint=checkpoint,
    )
    return report


def verify_power_variance_report(
    report: dict,
    *,
    input_path: Path,
    domain: Domain | str,
    as_of: datetime,
    ruler_root: Path = DEFAULT_RULER_ROOT,
    checkpoint: Callable[[], None] = lambda: None,
) -> None:
    selected = domain if isinstance(domain, Domain) else Domain(str(domain))
    if selected not in {Domain.AU, Domain.HKJC}:
        raise PowerVarianceError("power variance input contract supports AU or HKJC only")
    _hashed(report, SCHEMA)
    expected = _build(
        input_path=Path(input_path),
        domain=selected,
        as_of=as_of,
        ruler_root=Path(ruler_root),
        checkpoint=checkpoint,
    )
    if _encoded(report) != _encoded(expected):
        raise PowerVarianceError("power variance report differs from current source evidence")
    if (
        report["variance_input_contract_verified"] is not True
        or report["power_profile_write_allowed"] is not False
        or report["verified_monitoring_samples"] is not None
        or report["model_promotion_allowed"] is not False
    ):
        raise PowerVarianceError("variance evidence cannot grant profile, sample or promotion authority")
