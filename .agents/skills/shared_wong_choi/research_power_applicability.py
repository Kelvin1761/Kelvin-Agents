"""Fail-closed inventory of frozen-ruler power-profile applicability.

The evaluation rulers require preregistered power, but they deliberately do not
contain an effect size, variance floor or power-method approval.  Those values
must arrive in a separate, human-reviewed, frozen profile.  This module checks
that profile's binding and metric-family compatibility; it never invents values
or grants model-promotion authority.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

from .contracts import Domain
from .evaluation_rulers import DEFAULT_RULER_ROOT, EvaluationRuler, load_evaluation_ruler
from .research_index import _encoded, _hash, _hashed, _safe


SCHEMA = "wong-choi-power-applicability/v1"
PROFILE_SCHEMA = "wong-choi-power-profile/v1"
DEFAULT_PROFILE_ROOT = Path(__file__).resolve().parent / "resources" / "power_profiles"
MAX_PROFILE_BYTES = 262144
BLOCKER_ORDER = (
    "ruler_power_not_required",
    "power_profile_missing",
    "multiple_power_profiles",
    "power_profile_invalid",
    "power_profile_ruler_mismatch",
    "power_profile_metric_mismatch",
    "power_profile_method_incompatible",
    "power_profile_assumptions_unverified",
    "power_profile_family_incompatible",
    "power_profile_numerics_invalid",
)
ASSUMPTIONS = {
    "independent_units",
    "paired_observations",
    "dev_only_variance",
    "terminal_size_design",
}


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _number(value: Any) -> bool:
    return type(value) in {int, float} and math.isfinite(float(value))


def _ruler_path(root: Path, ruler: EvaluationRuler) -> Path:
    matches = sorted(root.glob(f"{ruler.domain.value}-v*.json"))
    if len(matches) != 1:
        raise ValueError(f"expected one ruler file for {ruler.domain.value}")
    return matches[0]


def _expected_family(ruler: EvaluationRuler, metric: dict) -> str | None:
    name, role = metric["name"], metric["role"]
    if name in {"gold", "good_positional"}:
        return "binary_rate_difference"
    if name == "mean_top3_model_rank":
        return "ordinal_rank_difference"
    if role == "ranking":
        return "bounded_ranking_difference"
    if name in {"brier_gain_vs_market", "log_loss_gain_vs_market"}:
        return "paired_loss_difference"
    return None


def _profile_blockers(
    payload: object,
    *,
    domain: Domain,
    ruler: EvaluationRuler,
    ruler_sha256: str,
) -> list[str]:
    blockers: set[str] = set()
    required = {
        "schema_version", "profile_id", "domain", "status", "ruler_id",
        "ruler_sha256", "authority", "method", "target", "min_dev_units",
        "unit", "assumptions", "metrics",
    }
    if not isinstance(payload, dict) or set(payload) != required:
        return ["power_profile_invalid"]
    if (
        payload["schema_version"] != PROFILE_SCHEMA
        or not isinstance(payload["profile_id"], str)
        or re.fullmatch(rf"wc:{domain.value}:power-profile:[a-z0-9][a-z0-9._-]*", payload["profile_id"]) is None
        or payload["domain"] != domain.value
        or payload["status"] != "frozen"
        or not isinstance(payload["authority"], str)
        or not payload["authority"].strip()
    ):
        blockers.add("power_profile_invalid")
    if payload["ruler_id"] != ruler.ruler_id or payload["ruler_sha256"] != ruler_sha256:
        blockers.add("power_profile_ruler_mismatch")
    if payload["method"] != "paired_t_design" or payload["unit"] != ruler.bootstrap["unit"]:
        blockers.add("power_profile_method_incompatible")
    assumptions = payload["assumptions"]
    if not isinstance(assumptions, dict) or set(assumptions) != ASSUMPTIONS or not all(
        value is True for value in assumptions.values()
    ):
        blockers.add("power_profile_assumptions_unverified")
    eligible = {
        item["name"]: item
        for item in ruler.metrics
        if item["role"] in {"primary", "ranking"}
    }
    metrics = payload["metrics"]
    if not isinstance(metrics, dict) or set(metrics) != set(eligible):
        blockers.add("power_profile_metric_mismatch")
    else:
        for name, metric_profile in metrics.items():
            if not isinstance(metric_profile, dict) or set(metric_profile) != {
                "analysis_family", "minimum_effect", "sd_floor", "rationale"
            }:
                blockers.add("power_profile_invalid")
                continue
            expected = _expected_family(ruler, eligible[name])
            if expected is None or metric_profile["analysis_family"] != expected:
                blockers.add("power_profile_family_incompatible")
            if (
                not _number(metric_profile["minimum_effect"])
                or metric_profile["minimum_effect"] <= 0
                or not _number(metric_profile["sd_floor"])
                or metric_profile["sd_floor"] <= 0
                or not isinstance(metric_profile["rationale"], str)
                or not metric_profile["rationale"].strip()
            ):
                blockers.add("power_profile_numerics_invalid")
    if (
        not _number(payload["target"])
        or not 0.5 < payload["target"] < 1
        or type(payload["min_dev_units"]) is not int
        or payload["min_dev_units"] < 2
    ):
        blockers.add("power_profile_numerics_invalid")
    return [code for code in BLOCKER_ORDER if code in blockers]


def _build(*, ruler_root: Path, profile_root: Path) -> dict:
    ruler_root, profile_root = _safe(ruler_root), _safe(profile_root)
    records = []
    for domain in Domain:
        ruler = load_evaluation_ruler(domain, root=ruler_root)
        ruler_path = _ruler_path(ruler_root, ruler)
        ruler_sha256 = _digest(ruler_path)
        eligible = sorted(
            item["name"] for item in ruler.metrics if item["role"] in {"primary", "ranking"}
        )
        matches = sorted(profile_root.glob(f"{domain.value}-power-v*.json")) if profile_root.exists() else []
        blockers: list[str] = []
        profile_path = profile_sha256 = None
        if ruler.sample_policy.get("power_required") is not True:
            blockers.append("ruler_power_not_required")
        if not matches:
            blockers.append("power_profile_missing")
        elif len(matches) > 1:
            blockers.append("multiple_power_profiles")
        else:
            selected = matches[0]
            profile_path = str(selected)
            try:
                if selected.is_symlink() or selected.stat().st_size > MAX_PROFILE_BYTES:
                    raise ValueError("power profile too large")
                profile_sha256 = _digest(selected)
                payload = json.loads(selected.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, ValueError):
                blockers.append("power_profile_invalid")
            else:
                blockers.extend(_profile_blockers(
                    payload, domain=domain, ruler=ruler, ruler_sha256=ruler_sha256,
                ))
        blockers = [code for code in BLOCKER_ORDER if code in set(blockers)]
        records.append({
            "domain": domain.value,
            "ruler_id": ruler.ruler_id,
            "ruler_sha256": ruler_sha256,
            "decision_mode": ruler.decision_mode,
            "ruler_promotion_allowed": ruler.promotion_allowed,
            "power_required": ruler.sample_policy.get("power_required") is True,
            "bootstrap_unit": ruler.bootstrap["unit"],
            "eligible_metric_names": eligible,
            "eligible_metrics": len(eligible),
            "profile_path": profile_path,
            "profile_sha256": profile_sha256,
            "power_profile_verified": not blockers,
            "blockers": blockers,
        })
    ready = len(records) == len(Domain) and all(row["power_profile_verified"] for row in records)
    report = {
        "schema_version": SCHEMA,
        "ruler_root": str(ruler_root),
        "profile_root": str(profile_root),
        "domains_seen": len(records),
        "profiles_verified": sum(row["power_profile_verified"] for row in records),
        "records": records,
        "power_applicability_verified": ready,
        "verified_monitoring_samples": None,
        "model_promotion_allowed": False,
    }
    report["content_hash"] = _hash(report)
    return report


def inspect_power_applicability(
    *,
    ruler_root: Path = DEFAULT_RULER_ROOT,
    profile_root: Path = DEFAULT_PROFILE_ROOT,
) -> dict:
    """Inventory four frozen rulers and separately reviewed power profiles."""
    report = _build(ruler_root=Path(ruler_root), profile_root=Path(profile_root))
    verify_power_applicability_report(
        report, ruler_root=Path(ruler_root), profile_root=Path(profile_root),
    )
    return report


def verify_power_applicability_report(
    report: dict,
    *,
    ruler_root: Path = DEFAULT_RULER_ROOT,
    profile_root: Path = DEFAULT_PROFILE_ROOT,
) -> None:
    """Recompute static evidence so a rehashed report cannot grant authority."""
    _hashed(report, SCHEMA)
    expected = _build(ruler_root=Path(ruler_root), profile_root=Path(profile_root))
    if _encoded(report) != _encoded(expected):
        raise ValueError("power applicability report differs from current frozen evidence")
    if report["verified_monitoring_samples"] is not None or report["model_promotion_allowed"] is not False:
        raise ValueError("power applicability inventory cannot grant sample or promotion authority")
