"""Thirty-day SLO reporting and non-destructive control-state restore drill."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .contracts import Domain
from .evidence import EvidenceStore, RecordKind


RUN_SLO_TARGET = 0.95
RUN_SLO_MIN_SLOTS = 20
PROVENANCE_SLO_TARGET = 1.0
HEALTHY_STATES = frozenset({"succeeded", "dormant"})
TERMINAL_STATES = frozenset({"succeeded", "dormant", "partial", "failed", "blocked"})


def _read(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _aware(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None and parsed.utcoffset() is not None else None


def _domain_reliability(root: Path, domain: Domain, cutoff: datetime) -> dict[str, Any]:
    attempts: dict[str, list[dict[str, Any]]] = {}
    folder = root / "runs" / domain.value
    if folder.exists():
        for path in folder.rglob("attempt-*.json"):
            payload = _read(path)
            if payload is None:
                continue
            completed = _aware(str(payload.get("completed_at") or ""))
            if completed is None or completed < cutoff:
                continue
            key = str(payload.get("idempotency_key") or payload.get("run_id") or path)
            attempts.setdefault(key, []).append(payload)
    final_attempts = [
        max(values, key=lambda item: int(item.get("attempt") or 1))
        for values in attempts.values()
    ]
    terminal = [item for item in final_attempts if item.get("state") in TERMINAL_STATES]
    healthy = [item for item in terminal if item.get("state") in HEALTHY_STATES]
    # 系統升級第二輪第 4 項（2026-11-25）：高頻 poller（NBA postgame 每 15 分鐘）撞到上一轉仲揸住鎖就
    # skipped_locked —— 下一轉會做返，冇嘢冇咗。之後同 mode、同 target_date 有成功 run 嘅 = 被取代，唔計入分母
    # （30 日內 118 個，令 NBA SLO 94.5% < 95%）。冇之後成功嘅照計失敗：真係卡死嘅鎖照報。
    def _skipped_locked(item):
        if item.get("state") != "blocked":
            return False
        for op in item.get("operations") or []:
            payload = (op.get("detail") or {}).get("source_payload") or {}
            if isinstance(payload, dict) and payload.get("status") == "skipped_locked":
                return True
        return False

    later_success = {}
    for item in healthy:
        k = (item.get("mode"), item.get("target_date"))
        t = _aware(str(item.get("completed_at") or ""))
        if t and (k not in later_success or t > later_success[k]):
            later_success[k] = t
    superseded = [
        item for item in terminal
        if _skipped_locked(item)
        and (later_success.get((item.get("mode"), item.get("target_date")))
             or datetime.min.replace(tzinfo=timezone.utc))
        > (_aware(str(item.get("completed_at") or "")) or datetime.max.replace(tzinfo=timezone.utc))
    ]
    if superseded:
        ids = {id(item) for item in superseded}
        terminal = [item for item in terminal if id(item) not in ids]
    recovered = sum(
        1
        for values in attempts.values()
        if len(values) > 1
        and max(values, key=lambda item: int(item.get("attempt") or 1)).get("state")
        in HEALTHY_STATES
        and any(
            item.get("state") not in HEALTHY_STATES
            for item in sorted(values, key=lambda row: int(row.get("attempt") or 1))[:-1]
        )
    )
    availability = len(healthy) / len(terminal) if terminal else None
    return {
        "slots": len(terminal),
        "healthy": len(healthy),
        "failed_or_partial": len(terminal) - len(healthy),
        "recovered_by_retry": recovered,
        "superseded_locked": len(superseded),
        "availability": availability,
        "target": RUN_SLO_TARGET,
        "minimum_slots": RUN_SLO_MIN_SLOTS,
        "status": (
            "no_data"
            if availability is None
            else "provisional"
            if len(terminal) < RUN_SLO_MIN_SLOTS
            else "pass"
            if availability >= RUN_SLO_TARGET
            else "fail"
        ),
    }


def _production_provenance(evidence_root: Path) -> dict[str, Any]:
    store = EvidenceStore(evidence_root)
    decisions = evidence_root / "records" / RecordKind.DECISION.value
    production = 0
    traced = 0
    if decisions.exists():
        for path in decisions.glob("*.json"):
            decision = _read(path)
            if decision is None:
                continue
            try:
                prediction = store.load(str((decision.get("links") or {})["prediction_id"]))
                model = store.load(str((prediction.get("links") or {})["model_release_id"]))
            except (KeyError, FileNotFoundError, ValueError):
                continue
            if str((model.get("body") or {}).get("release_stage")) not in {
                "limited", "production"
            }:
                continue
            production += 1
            if prediction.get("artifacts") and model.get("body", {}).get("code_commit"):
                traced += 1
    ratio = traced / production if production else None
    return {
        "production_decisions": production,
        "fully_traced": traced,
        "ratio": ratio,
        "target": PROVENANCE_SLO_TARGET,
        "status": "no_data" if ratio is None else "pass" if ratio >= 1.0 else "fail",
    }


def collect_reliability(
    state_root: Path,
    *,
    days: int = 30,
    now: datetime | None = None,
) -> dict[str, Any]:
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None or clock.utcoffset() is None:
        raise ValueError("reliability clock must be timezone-aware")
    cutoff = clock - timedelta(days=days)
    domains = {
        domain.value: _domain_reliability(state_root, domain, cutoff)
        for domain in Domain
    }
    evidence_audit = EvidenceStore(state_root / "evidence").audit()
    provenance = _production_provenance(state_root / "evidence")
    failures = [
        f"run_slo:{name}" for name, value in domains.items() if value["status"] == "fail"
    ]
    if evidence_audit["status"] != "ok":
        failures.append("evidence_integrity")
    if provenance["status"] == "fail":
        failures.append("production_provenance")
    return {
        "schema_version": "wong-choi-reliability/v1",
        "generated_at": clock.isoformat(),
        "window_days": days,
        "status": "pass" if not failures else "fail",
        "failures": failures,
        "domains": domains,
        "evidence": {"audit": evidence_audit, "production_provenance": provenance},
    }


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    if root.exists():
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            digest.update(str(path.relative_to(root)).encode("utf-8"))
            digest.update(path.read_bytes())
    return digest.hexdigest()


def run_restore_drill(state_root: Path, destination: Path) -> dict[str, Any]:
    """Copy durable control state to a new destination and verify exact hashes."""
    state_root = state_root.expanduser().resolve()
    destination = destination.expanduser().resolve()
    if destination.exists():
        raise FileExistsError(f"restore destination already exists: {destination}")
    durable = ("runs", "evidence", "releases", "release-events")
    before = {name: _tree_hash(state_root / name) for name in durable}
    destination.mkdir(parents=True)
    for name in durable:
        source = state_root / name
        if source.exists():
            shutil.copytree(source, destination / name)
    source_after = {name: _tree_hash(state_root / name) for name in durable}
    restored = {name: _tree_hash(destination / name) for name in durable}
    evidence_audit = EvidenceStore(destination / "evidence").audit()
    stable = before == source_after
    exact = before == restored
    status = "pass" if stable and exact and evidence_audit["status"] == "ok" else "fail"
    return {
        "schema_version": "wong-choi-restore-drill/v1",
        "status": status,
        "source": str(state_root),
        "destination": str(destination),
        "source_stable": stable,
        "hashes_match": exact,
        "hashes": restored,
        "evidence_audit": evidence_audit,
    }
