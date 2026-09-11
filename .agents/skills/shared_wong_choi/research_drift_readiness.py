"""Project what the frozen rulers do and do not authorize for live drift.

This module deliberately stops at contract readiness.  The existing rulers do
not freeze a drift window, sample floor, source artifact schema, or drift
decision threshold, so those values must remain absent until separately
reviewed.  It never reads candidate output or computes a model decision.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from .contracts import Domain
from .evaluation_rulers import DEFAULT_RULER_ROOT, load_evaluation_ruler
from .research_index import _encoded, _hash


SCHEMA = "wong-choi-drift-readiness/v1"
_UNRESOLVED_BASE = [
    "comparison_window",
    "minimum_drift_samples",
    "metric_drift_decision_thresholds",
]
_UNRESOLVED_MARKET = [
    "market_distribution_fields",
    "market_drift_decision_thresholds",
]
_MARKET_FIELDS = [
    "market_identity",
    "selection_identity",
    "captured_at",
    "offered_price",
    "no_vig_methodology",
    "source_artifact_digest",
]


def _aware(value: datetime | str) -> datetime:
    try:
        parsed = (
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            if isinstance(value, str) else value
        )
    except ValueError as exc:
        raise ValueError("as_of must be an aware ISO-8601 timestamp") from exc
    if (not isinstance(parsed, datetime) or parsed.tzinfo is None
            or parsed.utcoffset() is None):
        raise ValueError("as_of must be an aware ISO-8601 timestamp")
    return parsed.astimezone(timezone.utc)


def _ruler_source(domain: Domain, root: Path):
    if not isinstance(domain, Domain):
        raise ValueError("known drift domain required")
    source_root = Path(root).expanduser().absolute()
    matches = sorted(source_root.glob(f"{domain.value}-v*.json"))
    if (len(matches) != 1 or matches[0].is_symlink()
            or not matches[0].is_file()):
        raise ValueError("exactly one regular frozen ruler is required")
    before = matches[0].read_bytes()
    ruler = load_evaluation_ruler(domain, root=source_root)
    after = matches[0].read_bytes()
    if before != after:
        raise ValueError("frozen ruler changed during readiness projection")
    return ruler, hashlib.sha256(before).hexdigest()


def _projection(*, domain: Domain, as_of: datetime | str,
                ruler_root: Path) -> dict:
    observed = _aware(as_of)
    ruler, digest = _ruler_source(domain, ruler_root)
    market_required = ruler.price_snapshot_policy is not None
    report = {
        "schema_version": SCHEMA,
        "domain": domain.value,
        "as_of": observed.isoformat(),
        "ruler_id": ruler.ruler_id,
        "ruler_sha256": digest,
        "model_release_id": ruler.model_release_id,
        "model_stage": ruler.model_stage,
        "metric_inputs": [
            {
                "name": item["name"],
                "role": item["role"],
                "direction": item["direction"],
            }
            for item in ruler.metrics
        ],
        "cohort_inputs": list(ruler.cohorts),
        "review_cadence": dict(ruler.review),
        "sample_policy": dict(ruler.sample_policy),
        "market_input": {
            "status": (
                "source_contract_required"
                if market_required else "not_required_by_ruler"
            ),
            "price_snapshot_policy": ruler.price_snapshot_policy,
            "required_source_fields": list(_MARKET_FIELDS) if market_required else [],
        },
        "unresolved_contract_fields": [
            *_UNRESOLVED_BASE,
            *(_UNRESOLVED_MARKET if market_required else []),
            "producer_artifact_schema",
        ],
        "contract_status": "blocked_missing_frozen_drift_contract",
        "comparison_window": None,
        "minimum_drift_samples": None,
        "decision_thresholds": None,
        "source_reverification_required": True,
        "descriptive_projection_allowed": False,
        "metric_drift_verified": False,
        "market_drift_verified": False,
        "threshold_decision_allowed": False,
        "model_promotion_allowed": False,
    }
    report["content_hash"] = _hash(report)
    if len(_encoded(report)) > 32768:
        raise ValueError("drift readiness projection exceeds size bound")
    return report


def build_drift_readiness(
    *, domain: Domain, as_of: datetime | str,
    ruler_root: Path = DEFAULT_RULER_ROOT,
) -> dict:
    """Build a ruler-bound projection without filling unresolved policy."""
    report = _projection(domain=domain, as_of=as_of, ruler_root=ruler_root)
    verify_drift_readiness(
        report, domain=domain, as_of=as_of, ruler_root=ruler_root,
    )
    return report


def verify_drift_readiness(
    report: dict, *, domain: Domain, as_of: datetime | str,
    ruler_root: Path = DEFAULT_RULER_ROOT,
) -> None:
    """Rebuild from the current ruler and reject forged readiness claims."""
    if (not isinstance(report, dict) or report.get("schema_version") != SCHEMA
            or report.get("content_hash") != _hash({
                key: value for key, value in report.items()
                if key != "content_hash"
            })):
        raise ValueError("invalid drift readiness hash or schema")
    _ruler, current_digest = _ruler_source(domain, ruler_root)
    if report.get("ruler_sha256") != current_digest:
        raise ValueError("frozen ruler changed after readiness projection")
    expected = _projection(domain=domain, as_of=as_of, ruler_root=ruler_root)
    if _encoded(report) != _encoded(expected):
        raise ValueError("drift readiness projection differs from frozen ruler")
