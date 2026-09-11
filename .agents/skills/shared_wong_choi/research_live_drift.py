"""Source-reverified, descriptive live feature-availability drift evidence.

This adapter compares the immutable feature-provenance inventory known at a
baseline cutoff with records first observed after that cutoff.  It deliberately
does not invent a statistical threshold, evaluate model metrics, inspect market
movement, or grant promotion authority.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Callable

from .contracts import Domain
from .research_index import _at, _encoded, _hash, _hashed, _safe
from .research_review_clock import _digest


SCHEMA = "wong-choi-live-feature-drift-evidence/v1"
_STATUSES = {"verified_descriptive", "insufficient_data", "source_incomplete"}
_HEALTH = {"ok", "attention", "unknown"}
_DIRECTIONS = {"improved", "degraded", "unchanged", "unknown"}
_PERIOD_FIELDS = {
    "records", "bundle_verified_records", "verified_records",
    "unavailable_records", "availability_rate", "blocker_counts",
}


def _inspect_feature_source(
        *, root: Path, domain: Domain, as_of: datetime,
        relocation_roots: tuple[Path, ...], checkpoint: Callable[[], None]) -> dict:
    """Route to a domain inspector without sharing any domain scoring code."""
    kwargs = dict(root=root, as_of=as_of, relocation_roots=relocation_roots,
                  checkpoint=checkpoint)
    if domain is Domain.AU:
        from .research_au_feature_provenance import inspect_au_feature_provenance
        return inspect_au_feature_provenance(**kwargs)
    if domain is Domain.HKJC:
        from .research_hkjc_feature_provenance import inspect_hkjc_feature_provenance
        return inspect_hkjc_feature_provenance(**kwargs)
    if domain is Domain.TENNIS:
        from .research_tennis_feature_provenance import inspect_tennis_feature_provenance
        return inspect_tennis_feature_provenance(**kwargs)
    if domain is Domain.NBA:
        from .research_nba_feature_provenance import inspect_nba_feature_provenance
        return inspect_nba_feature_provenance(**kwargs)
    raise ValueError("unsupported live drift domain")


def _valid_source(report: dict, *, domain: Domain, as_of: datetime) -> list[dict]:
    if (not isinstance(report, dict) or report.get("domain") != domain.value
            or report.get("as_of") != _at(as_of).isoformat()
            or not isinstance(report.get("records"), list)):
        raise ValueError("feature provenance source scope mismatch")
    content_hash = report.get("content_hash")
    _digest(content_hash)
    if content_hash != _hash({key: value for key, value in report.items()
                              if key != "content_hash"}):
        raise ValueError("feature provenance source hash mismatch")
    seen = set()
    for item in report["records"]:
        if (not isinstance(item, dict)
                or not isinstance(item.get("record_id"), str)
                or not item["record_id"] or item["record_id"] in seen
                or type(item.get("bundle_verified")) is not bool
                or type(item.get("feature_availability_verified")) is not bool
                or not isinstance(item.get("blockers"), list)
                or any(not isinstance(code, str) or not code for code in item["blockers"])
                or len(item["blockers"]) != len(set(item["blockers"]))
                or _at(item.get("source_cutoff_at")) > _at(as_of)):
            raise ValueError("invalid feature provenance source record")
        seen.add(item["record_id"])
    return report["records"]


def _period(records: list[dict]) -> dict:
    blockers = Counter(code for item in records for code in item["blockers"])
    verified = sum(item["feature_availability_verified"] for item in records)
    total = len(records)
    return {
        "records": total,
        "bundle_verified_records": sum(item["bundle_verified"] for item in records),
        "verified_records": verified,
        "unavailable_records": total - verified,
        "availability_rate": round(verified / total, 6) if total else None,
        "blocker_counts": {key: blockers[key] for key in sorted(blockers)},
    }


def _derived(*, baseline: dict, current: dict,
             late_historical_records: int) -> tuple[str, str, float | None, str, bool]:
    complete = bool(baseline["records"] and current["records"]
                    and late_historical_records == 0)
    if not baseline["records"] or not current["records"]:
        status = "insufficient_data"
    elif late_historical_records:
        status = "source_incomplete"
    else:
        status = "verified_descriptive"
    if not complete:
        return status, "unknown", None, "unknown", False
    delta = round(current["availability_rate"] - baseline["availability_rate"], 6)
    direction = "improved" if delta > 0 else "degraded" if delta < 0 else "unchanged"
    health = "ok" if current["unavailable_records"] == 0 else "attention"
    return status, health, delta, direction, True


def _projection(baseline_source: dict, current_source: dict, *,
                domain: Domain, baseline_as_of: datetime, as_of: datetime) -> dict:
    old = _valid_source(baseline_source, domain=domain, as_of=baseline_as_of)
    now = _valid_source(current_source, domain=domain, as_of=as_of)
    old_by_id = {item["record_id"]: item for item in old}
    now_by_id = {item["record_id"]: item for item in now}
    if not set(old_by_id).issubset(now_by_id):
        raise ValueError("historical feature source shrank")
    if any(_encoded(item) != _encoded(now_by_id[identity])
           for identity, item in old_by_id.items()):
        raise ValueError("historical feature source changed")
    added = [item for identity, item in now_by_id.items() if identity not in old_by_id]
    late = [item for item in added if _at(item["source_cutoff_at"]) <= baseline_as_of]
    current_records = [item for item in added
                       if baseline_as_of < _at(item["source_cutoff_at"]) <= as_of]
    baseline, current = _period(old), _period(current_records)
    status, health, delta, direction, verified = _derived(
        baseline=baseline, current=current, late_historical_records=len(late),
    )
    return {
        "baseline_source_hash": baseline_source["content_hash"],
        "current_source_hash": current_source["content_hash"],
        "baseline": baseline,
        "current": current,
        "late_historical_records": len(late),
        "status": status,
        "feature_health": health,
        "availability_delta": delta,
        "direction": direction,
        "source_reverified": True,
        "live_drift_verified": verified,
        "feature_availability_drift_verified": verified,
        "metric_drift_verified": False,
        "market_drift_verified": False,
        "threshold_decision_allowed": False,
        "model_promotion_allowed": False,
    }


def _build_report(*, root: Path, domain: Domain, baseline_as_of: datetime,
                  as_of: datetime, relocation_roots: tuple[Path, ...],
                  checkpoint: Callable[[], None]) -> dict:
    if not isinstance(domain, Domain) or not isinstance(relocation_roots, tuple):
        raise ValueError("known domain and tuple relocation roots required")
    evidence_root = _safe(Path(root).expanduser().absolute())
    roots = tuple(_safe(Path(item).expanduser().absolute()) for item in relocation_roots)
    baseline_at, end = _at(baseline_as_of), _at(as_of)
    if not evidence_root.is_dir() or not baseline_at < end:
        raise ValueError("existing root and ordered drift window required")
    common = dict(root=evidence_root, domain=domain, relocation_roots=roots,
                  checkpoint=checkpoint)
    baseline_source = _inspect_feature_source(as_of=baseline_at, **common)
    current_source = _inspect_feature_source(as_of=end, **common)
    report = {
        "schema_version": SCHEMA,
        "domain": domain.value,
        "root": str(evidence_root),
        "relocation_roots": [str(item) for item in roots],
        "baseline_as_of": baseline_at.isoformat(),
        "as_of": end.isoformat(),
        **_projection(
            baseline_source, current_source, domain=domain,
            baseline_as_of=baseline_at, as_of=end,
        ),
    }
    report["content_hash"] = _hash(report)
    return report


def inspect_live_feature_drift(
        *, root: Path, domain: Domain, baseline_as_of: datetime,
        as_of: datetime, relocation_roots: tuple[Path, ...] = (),
        checkpoint: Callable[[], None] = lambda: None) -> dict:
    """Build one bounded current-vs-baseline feature-availability projection."""
    report = _build_report(
        root=root, domain=domain, baseline_as_of=baseline_as_of, as_of=as_of,
        relocation_roots=relocation_roots, checkpoint=checkpoint,
    )
    verify_live_feature_drift_report(
        report, root=root, domain=domain, baseline_as_of=baseline_as_of,
        as_of=as_of, relocation_roots=relocation_roots, reverify_source=False,
    )
    return report


def _period_shape(value: object) -> None:
    if not isinstance(value, dict) or set(value) != _PERIOD_FIELDS:
        raise ValueError("invalid live drift period")
    for key in ("records", "bundle_verified_records", "verified_records",
                "unavailable_records"):
        if type(value[key]) is not int or not 0 <= value[key] <= 10000:
            raise ValueError("invalid live drift count")
    total = value["records"]
    if (value["verified_records"] + value["unavailable_records"] != total
            or value["bundle_verified_records"] > total):
        raise ValueError("live drift period count mismatch")
    expected_rate = round(value["verified_records"] / total, 6) if total else None
    if value["availability_rate"] != expected_rate:
        raise ValueError("live drift availability rate mismatch")
    blockers = value["blocker_counts"]
    if (not isinstance(blockers, dict) or list(blockers) != sorted(blockers)
            or any(not isinstance(key, str) or not key for key in blockers)
            or any(type(count) is not int or not 0 < count <= total
                   for count in blockers.values())):
        raise ValueError("invalid live drift blockers")


def verify_live_feature_drift_report(
        report: dict, *, root: Path, domain: Domain,
        baseline_as_of: datetime, as_of: datetime,
        relocation_roots: tuple[Path, ...] = (), reverify_source: bool = False,
        checkpoint: Callable[[], None] = lambda: None) -> None:
    """Validate all derived claims and optionally rebuild both source views."""
    _hashed(report, SCHEMA)
    expected = {
        "schema_version", "domain", "root", "relocation_roots",
        "baseline_as_of", "as_of", "baseline_source_hash",
        "current_source_hash", "baseline", "current",
        "late_historical_records", "status", "feature_health",
        "availability_delta", "direction", "source_reverified",
        "live_drift_verified", "feature_availability_drift_verified",
        "metric_drift_verified", "market_drift_verified",
        "threshold_decision_allowed", "model_promotion_allowed", "content_hash",
    }
    evidence_root = _safe(Path(root).expanduser().absolute())
    roots = tuple(_safe(Path(item).expanduser().absolute()) for item in relocation_roots)
    baseline_at, end = _at(baseline_as_of), _at(as_of)
    if (set(report) != expected or report["domain"] != domain.value
            or report["root"] != str(evidence_root)
            or report["relocation_roots"] != [str(item) for item in roots]
            or report["baseline_as_of"] != baseline_at.isoformat()
            or report["as_of"] != end.isoformat()
            or not baseline_at < end or len(_encoded(report)) > 32768):
        raise ValueError("live drift report scope or size mismatch")
    _digest(report["baseline_source_hash"])
    _digest(report["current_source_hash"])
    _period_shape(report["baseline"])
    _period_shape(report["current"])
    if (type(report["late_historical_records"]) is not int
            or not 0 <= report["late_historical_records"] <= 10000
            or report["status"] not in _STATUSES
            or report["feature_health"] not in _HEALTH
            or report["direction"] not in _DIRECTIONS):
        raise ValueError("invalid live drift derived state")
    derived = _derived(
        baseline=report["baseline"], current=report["current"],
        late_historical_records=report["late_historical_records"],
    )
    actual = (
        report["status"], report["feature_health"], report["availability_delta"],
        report["direction"], report["live_drift_verified"],
    )
    if actual != derived:
        raise ValueError("derived live drift projection mismatch")
    if (report["source_reverified"] is not True
            or report["feature_availability_drift_verified"]
            is not report["live_drift_verified"]
            or any(report[key] is not False for key in (
                "metric_drift_verified", "market_drift_verified",
                "threshold_decision_allowed", "model_promotion_allowed",
            ))):
        raise ValueError("live drift evidence grants unsupported authority")
    if reverify_source:
        rebuilt = _build_report(
            root=evidence_root, domain=domain, baseline_as_of=baseline_at,
            as_of=end, relocation_roots=roots, checkpoint=checkpoint,
        )
        if _encoded(report) != _encoded(rebuilt):
            raise ValueError("live drift source changed during verification")


def live_drift_report_reference(path: Path, report: dict) -> dict:
    """Return a bounded, hash-linked reference suitable for a private review."""
    verify_live_feature_drift_report(
        report, root=Path(report["root"]), domain=Domain(report["domain"]),
        baseline_as_of=_at(report["baseline_as_of"]), as_of=_at(report["as_of"]),
        relocation_roots=tuple(Path(item) for item in report["relocation_roots"]),
        reverify_source=False,
    )
    return {
        "path": str(path),
        "content_hash": report["content_hash"],
        "observed_at": report["as_of"],
        "baseline_as_of": report["baseline_as_of"],
        "status": report["status"],
        "feature_health": report["feature_health"],
        "direction": report["direction"],
        "baseline_records": report["baseline"]["records"],
        "current_records": report["current"]["records"],
        "availability_delta": report["availability_delta"],
        "live_drift_verified": report["live_drift_verified"],
        "metric_drift_verified": False,
        "market_drift_verified": False,
    }
