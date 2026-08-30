"""Versioned, fail-closed evaluation rulers for Stage 5 research.

The JSON files are the human-reviewable authority.  This module only validates
and loads them; it never computes a domain score or changes a promotion stage.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .contracts import Domain


SCHEMA_VERSION = "wong-choi-evaluation-ruler/v1"
DEFAULT_RULER_ROOT = Path(__file__).resolve().parent / "resources" / "evaluation_rulers"
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_METRIC_ROLES = frozenset({"primary", "ranking", "guardrail", "descriptive"})
_DIRECTIONS = frozenset({"maximize", "minimize"})
_DECISION_MODES = frozenset({"promotion_gate", "descriptive_only"})
_MODEL_STAGES = frozenset({"research", "shadow", "paper", "limited", "production", "retired"})


class RulerValidationError(ValueError):
    """Raised when a ruler or release boundary is unsafe or incomplete."""


@dataclass(frozen=True)
class EvaluationRuler:
    schema_version: str
    ruler_id: str
    domain: Domain
    status: str
    platform_baseline_commit: str
    model_baseline_commit: str
    model_release_id: str
    model_stage: str
    authority: str
    decision_mode: str
    promotion_allowed: bool
    point_in_time_required: bool
    family_specific: bool
    price_snapshot_policy: str | None
    metrics: tuple[Mapping[str, Any], ...]
    cohorts: tuple[str, ...]
    holdout: Mapping[str, Any]
    bootstrap: Mapping[str, Any]
    sample_policy: Mapping[str, Any]
    review: Mapping[str, Any]
    fixture_cases: tuple[Mapping[str, Any], ...]

    def metric_names(self, role: str) -> set[str]:
        return {
            str(metric["name"])
            for metric in self.metrics
            if metric.get("role") == role
        }


def _require_mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise RulerValidationError(f"{key} must be an object")
    return value


def _validate_payload(payload: Mapping[str, Any], *, source: Path) -> EvaluationRuler:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise RulerValidationError(f"unsupported ruler schema in {source}")
    try:
        domain = Domain(str(payload["domain"]))
    except (KeyError, ValueError) as exc:
        raise RulerValidationError(f"invalid ruler domain in {source}") from exc

    ruler_id = str(payload.get("ruler_id") or "")
    if not re.fullmatch(rf"{re.escape(domain.value)}-v[1-9][0-9]*", ruler_id):
        raise RulerValidationError(f"ruler_id does not match domain/version: {ruler_id!r}")
    if payload.get("status") != "frozen":
        raise RulerValidationError("Stage 5 only accepts frozen rulers")
    platform_baseline_commit = str(payload.get("platform_baseline_commit") or "")
    model_baseline_commit = str(payload.get("model_baseline_commit") or "")
    if not _COMMIT.fullmatch(platform_baseline_commit):
        raise RulerValidationError("platform_baseline_commit must be a full git SHA")
    if not _COMMIT.fullmatch(model_baseline_commit):
        raise RulerValidationError("model_baseline_commit must be a full git SHA")
    model_release_id = str(payload.get("model_release_id") or "")
    if not model_release_id.startswith(f"wc:{domain.value}:model-release:"):
        raise RulerValidationError("model_release_id must match the ruler domain")
    model_stage = str(payload.get("model_stage") or "")
    if model_stage not in _MODEL_STAGES:
        raise RulerValidationError("model_stage is invalid")
    authority = str(payload.get("authority") or "").strip()
    if not authority:
        raise RulerValidationError("ruler authority is required")

    decision_mode = str(payload.get("decision_mode") or "")
    if decision_mode not in _DECISION_MODES:
        raise RulerValidationError(f"unsupported decision_mode: {decision_mode!r}")
    promotion_allowed = payload.get("promotion_allowed")
    if not isinstance(promotion_allowed, bool):
        raise RulerValidationError("promotion_allowed must be boolean")
    if decision_mode == "descriptive_only" and promotion_allowed:
        raise RulerValidationError("descriptive-only ruler cannot allow promotion")

    raw_metrics = payload.get("metrics")
    if not isinstance(raw_metrics, list) or not raw_metrics:
        raise RulerValidationError("metrics must be a non-empty list")
    metrics: list[Mapping[str, Any]] = []
    names: set[str] = set()
    for raw in raw_metrics:
        if not isinstance(raw, Mapping):
            raise RulerValidationError("each metric must be an object")
        name = str(raw.get("name") or "").strip()
        role = str(raw.get("role") or "")
        direction = str(raw.get("direction") or "")
        if not name or name in names:
            raise RulerValidationError(f"metric name is missing or duplicated: {name!r}")
        if role not in _METRIC_ROLES or direction not in _DIRECTIONS:
            raise RulerValidationError(f"invalid metric contract: {name}")
        names.add(name)
        metrics.append(dict(raw))
    if not any(metric["role"] == "primary" for metric in metrics):
        raise RulerValidationError("at least one primary metric is required")

    cohorts = payload.get("cohorts")
    if not isinstance(cohorts, list) or not cohorts or any(not str(v).strip() for v in cohorts):
        raise RulerValidationError("cohorts must be a non-empty list")

    holdout = _require_mapping(payload, "holdout")
    if not holdout.get("strategy") or holdout.get("tuning_forbidden") is not True:
        raise RulerValidationError("holdout must declare strategy and forbid tuning")
    bootstrap = _require_mapping(payload, "bootstrap")
    if int(bootstrap.get("trials") or 0) < 1000:
        raise RulerValidationError("bootstrap requires at least 1000 trials")
    confidence = float(bootstrap.get("confidence") or 0)
    if not 0.5 < confidence < 1:
        raise RulerValidationError("bootstrap confidence is invalid")
    if not bootstrap.get("unit") or not isinstance(bootstrap.get("seed"), int):
        raise RulerValidationError("bootstrap unit and integer seed are required")

    sample_policy = _require_mapping(payload, "sample_policy")
    review = _require_mapping(payload, "review")
    required_review = {"weekly", "monthly", "ruler_review_days", "incident_freezes_queue"}
    if not required_review.issubset(review):
        raise RulerValidationError("review cadence is incomplete")
    if int(review["ruler_review_days"]) < 1 or review["incident_freezes_queue"] is not True:
        raise RulerValidationError("review cadence must fail closed")

    raw_cases = payload.get("fixture_cases")
    if not isinstance(raw_cases, list):
        raise RulerValidationError("fixture_cases must be a list")
    fixture_cases = tuple(dict(case) for case in raw_cases if isinstance(case, Mapping))
    if {case.get("expected") for case in fixture_cases} != {"win", "regression", "noise"}:
        raise RulerValidationError("fixtures must cover win, regression and noise")

    return EvaluationRuler(
        schema_version=SCHEMA_VERSION,
        ruler_id=ruler_id,
        domain=domain,
        status="frozen",
        platform_baseline_commit=platform_baseline_commit,
        model_baseline_commit=model_baseline_commit,
        model_release_id=model_release_id,
        model_stage=model_stage,
        authority=authority,
        decision_mode=decision_mode,
        promotion_allowed=promotion_allowed,
        point_in_time_required=payload.get("point_in_time_required") is True,
        family_specific=payload.get("family_specific") is True,
        price_snapshot_policy=(
            str(payload["price_snapshot_policy"])
            if payload.get("price_snapshot_policy") is not None
            else None
        ),
        metrics=tuple(metrics),
        cohorts=tuple(str(value) for value in cohorts),
        holdout=dict(holdout),
        bootstrap=dict(bootstrap),
        sample_policy=dict(sample_policy),
        review=dict(review),
        fixture_cases=fixture_cases,
    )


def load_evaluation_ruler(
    domain: Domain | str,
    *,
    root: Path | None = None,
) -> EvaluationRuler:
    selected = domain if isinstance(domain, Domain) else Domain(str(domain))
    ruler_root = Path(root) if root is not None else DEFAULT_RULER_ROOT
    matches = sorted(ruler_root.glob(f"{selected.value}-v*.json"))
    if len(matches) != 1:
        raise RulerValidationError(
            f"expected exactly one frozen ruler for {selected.value}, found {len(matches)}"
        )
    try:
        payload = json.loads(matches[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RulerValidationError(f"cannot read ruler {matches[0]}") from exc
    if not isinstance(payload, Mapping):
        raise RulerValidationError("ruler root must be an object")
    return _validate_payload(payload, source=matches[0])


def validate_release_separation(
    *,
    ruler_changed: bool,
    candidate_model_changed: bool,
) -> None:
    if ruler_changed and candidate_model_changed:
        raise RulerValidationError(
            "evaluation ruler and candidate model must use a separate release"
        )
