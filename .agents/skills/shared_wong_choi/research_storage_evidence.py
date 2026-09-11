"""Bounded read-only storage evidence for Stage 5 research reviews.

This projection distinguishes live service availability from backup durability.
It cannot move/delete data, prove historical uptime, or grant model authority.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable

from .contracts import Domain
from .research_index import _at, _encoded, _hash, _hashed, _safe
from .storage_status import collect_storage_status


SCHEMA = "wong-choi-research-storage-evidence/v1"


def storage_report_reference(path: Path, report: dict) -> dict:
    """Return the bounded identity persisted by review summaries/cursors."""
    _hashed(report, SCHEMA)
    if report.get("storage_health") not in {"ok", "attention"}:
        raise ValueError("invalid storage evidence health")
    return {
        "path": str(path),
        "content_hash": report["content_hash"],
        "observed_at": _at(report["as_of"]).isoformat(),
        "storage_health": report["storage_health"],
    }


def _tier(raw: dict, name: str) -> dict:
    tiers = raw.get("tiers")
    item = tiers.get(name) if isinstance(tiers, dict) else None
    if not isinstance(item, dict) or not isinstance(item.get("status"), str):
        raise ValueError("storage tier evidence missing")
    if name == "hot":
        pressure = item.get("pressure")
        if pressure not in {"ok", "warning", "critical", "unknown"}:
            raise ValueError("invalid HOT pressure")
        return {"status": item["status"], "pressure": pressure}
    if not isinstance(item.get("configured"), bool):
        raise ValueError("invalid storage tier configuration")
    return {"configured": item["configured"], "status": item["status"]}


def _projection(raw: dict, as_of: datetime) -> dict:
    if (not isinstance(raw, dict)
            or raw.get("schema_version") != "wong-choi-storage-status/v1"):
        raise ValueError("unsupported storage source")
    end = _at(as_of)
    hot, warm, cold = (_tier(raw, name) for name in ("hot", "warm", "cold"))
    backups = raw.get("backups")
    if not isinstance(backups, dict):
        raise ValueError("storage backup evidence missing")
    d1 = backups.get("dashboard_d1")
    artifacts = backups.get("catalog_artifacts")
    if not isinstance(d1, dict) or not isinstance(artifacts, dict):
        raise ValueError("storage backup evidence missing")

    snapshot_at = d1.get("snapshot_at")
    age_hours = None
    if snapshot_at is not None:
        snapshot = _at(snapshot_at)
        if snapshot > end:
            raise ValueError("future D1 backup snapshot")
        snapshot_at = snapshot.isoformat()
        age_hours = round((end - snapshot).total_seconds() / 3600, 2)
    stale_after = d1.get("stale_after_hours")
    if stale_after is not None and (type(stale_after) not in (int, float)
                                    or stale_after <= 0):
        raise ValueError("invalid D1 backup stale threshold")
    d1_attention = (
        snapshot_at is None
        or (stale_after is not None and age_hours > stale_after)
        or d1.get("warm_verified") is not True
    )
    d1_view = {
        # Central service availability belongs to a separate health source.
        # A backup record must never imply that D1 itself is reachable.
        "service_available": None,
        "status": (
            d1.get("status", "unknown") if snapshot_at is None
            else "attention" if d1_attention else "ok"
        ),
        "snapshot_at": snapshot_at,
        "age_hours": age_hours,
        "stale_after_hours": stale_after,
        "restore_verified": d1.get("restore_verified") is True,
        "warm_verified": d1.get("warm_verified") is True,
        "cold_verified": d1.get("cold_verified") is True,
        "artifact_id": d1.get("artifact_id"),
    }

    counts = {
        key: artifacts.get(key)
        for key in ("known_artifacts", "verified_artifacts", "unverified_artifacts")
    }
    if any(type(value) is not int or value < 0 for value in counts.values()):
        raise ValueError("invalid artifact COLD counts")
    if counts["known_artifacts"] != (counts["verified_artifacts"]
                                     + counts["unverified_artifacts"]):
        raise ValueError("artifact COLD counts disagree")
    providers = artifacts.get("providers")
    domains = artifacts.get("domains")
    if (not isinstance(providers, list) or providers != sorted(set(providers))
            or any(not isinstance(item, str) or not item for item in providers)
            or not isinstance(domains, dict) or len(domains) > len(Domain) + 1):
        raise ValueError("invalid artifact COLD coverage")
    for item in domains.values():
        if (not isinstance(item, dict) or set(item) != {"known", "verified"}
                or any(type(value) is not int or value < 0 for value in item.values())
                or item["verified"] > item["known"]):
            raise ValueError("invalid artifact COLD domain coverage")
    artifact_view = {
        "status": artifacts.get("status", "unknown"),
        **counts,
        "providers": providers,
        "domains": {key: domains[key] for key in sorted(domains)},
    }

    attention = []
    if hot["pressure"] != "ok":
        attention.append("hot_storage_" + hot["pressure"])
    if warm["status"] != "available":
        attention.append("warm_archive_unavailable")
    if cold["configured"] and cold["status"] != "available":
        attention.append("cold_mirror_unavailable")
    if snapshot_at is None:
        attention.append("dashboard_d1_backup_no_data")
    else:
        if stale_after is not None and age_hours > stale_after:
            attention.append("dashboard_d1_backup_stale")
        if not d1_view["warm_verified"]:
            attention.append("dashboard_d1_backup_warm_pending")
        if cold["configured"] and not d1_view["cold_verified"]:
            attention.append("dashboard_d1_backup_cold_pending")
    if artifact_view["status"] in {"attention", "invalid"}:
        attention.append("artifact_cold_backlog")

    return {
        "storage_health": "attention" if attention else "ok",
        "attention": sorted(set(attention)),
        "tiers": {"hot": hot, "warm": warm, "cold": cold},
        "dashboard_d1": d1_view,
        "artifact_cold": artifact_view,
    }


def collect_research_storage_evidence(
        *, repo_root: Path, state_root: Path, domain: Domain, as_of: datetime,
        checkpoint: Callable[[], None] = lambda: None) -> dict:
    """Capture one current storage projection without scanning large inventory."""
    if not isinstance(domain, Domain):
        raise ValueError("known domain required")
    repo, state, end = _safe(repo_root), _safe(state_root), _at(as_of)
    if not repo.is_dir() or not state.is_dir():
        raise ValueError("existing storage evidence roots required")
    checkpoint()
    view = _projection(collect_storage_status(repo, state, scan=False), end)
    checkpoint()
    report = {
        "schema_version": SCHEMA,
        "domain": domain.value,
        "repo_root": str(repo),
        "state_root": str(state),
        "as_of": end.isoformat(),
        **view,
        "source_reverified": True,
        "historical_availability_verified": False,
        "process_liveness_verified": False,
        "live_drift_verified": False,
        "model_promotion_allowed": False,
    }
    report["content_hash"] = _hash(report)
    verify_research_storage_evidence(
        report, repo_root=repo, state_root=state, domain=domain,
        as_of=end, reverify_source=False,
    )
    return report


def verify_research_storage_evidence(
        report: dict, *, repo_root: Path, state_root: Path, domain: Domain,
        as_of: datetime, reverify_source: bool = False,
        checkpoint: Callable[[], None] = lambda: None) -> None:
    """Validate the bounded projection and optionally rebuild the live source."""
    _hashed(report, SCHEMA)
    expected = {
        "schema_version", "domain", "repo_root", "state_root", "as_of",
        "storage_health", "attention", "tiers", "dashboard_d1",
        "artifact_cold", "source_reverified", "historical_availability_verified",
        "process_liveness_verified", "live_drift_verified",
        "model_promotion_allowed", "content_hash",
    }
    repo, state, end = _safe(repo_root), _safe(state_root), _at(as_of)
    if (set(report) != expected or report["domain"] != domain.value
            or report["repo_root"] != str(repo) or report["state_root"] != str(state)
            or report["as_of"] != end.isoformat() or len(_encoded(report)) > 32768):
        raise ValueError("storage evidence scope or size mismatch")
    if (report["source_reverified"] is not True
            or any(report[key] is not False for key in (
                "historical_availability_verified", "process_liveness_verified",
                "live_drift_verified", "model_promotion_allowed",
            ))):
        raise ValueError("storage evidence cannot grant unrelated authority")
    view = {key: report[key] for key in (
        "storage_health", "attention", "tiers", "dashboard_d1", "artifact_cold",
    )}
    if reverify_source:
        checkpoint()
        rebuilt = _projection(collect_storage_status(repo, state, scan=False), end)
        checkpoint()
        if view != rebuilt:
            raise ValueError("storage source changed during verification")
