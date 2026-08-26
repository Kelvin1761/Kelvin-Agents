"""Read-only status view across git, releases, evidence and four domain runs."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .contracts import CapabilityReadiness, Domain
from .evidence import EvidenceStore, RecordKind
from .registry import ADAPTER_SPECS
from .release_activation import EXPECTED_MUTABLE_PATHS
from .release_events import ReleaseEventStore, effective_status
from .release_manager import GitStatus, ReleaseError, git_status
from .reliability import collect_reliability


STATUS_SCHEMA = "wong-choi-central-status/v1"


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _latest_json(folder: Path) -> tuple[Path, dict[str, Any]] | None:
    candidates: list[tuple[float, Path, dict[str, Any]]] = []
    if not folder.exists():
        return None
    for path in folder.rglob("*.json"):
        value = _read_json(path)
        if value is None:
            continue
        try:
            modified = path.stat().st_mtime
        except OSError:
            continue
        candidates.append((modified, path, value))
    if not candidates:
        return None
    _, path, value = max(candidates, key=lambda item: (item[0], str(item[1])))
    return path, value


def _git_payload(root: Path) -> dict[str, Any]:
    if not (root / ".git").exists():
        return {"repo": str(root), "status": "missing"}
    try:
        status: GitStatus = git_status(root)
    except (OSError, ReleaseError, ValueError) as exc:
        return {
            "repo": str(root),
            "status": "unavailable",
            "error": f"{type(exc).__name__}: {exc}",
        }
    payload = asdict(status)
    unexpected = sorted(set(status.dirty_paths).difference(EXPECTED_MUTABLE_PATHS))
    expected = sorted(set(status.dirty_paths).intersection(EXPECTED_MUTABLE_PATHS))
    payload["unexpected_dirty_paths"] = unexpected
    payload["expected_runtime_paths"] = expected
    payload["status"] = (
        "dirty"
        if unexpected
        else "clean_runtime_state"
        if expected
        else "clean"
    )
    return payload


def _release_status(releases_root: Path, events_root: Path) -> dict[str, Any]:
    releases: list[dict[str, Any]] = []
    event_store = ReleaseEventStore(events_root)
    if releases_root.exists():
        for path in sorted(releases_root.glob("*.json")):
            item = _read_json(path)
            if item is None or item.get("schema_version") != "wong-choi-release/v1":
                continue
            effective = effective_status(
                item,
                event_store.list(str(item.get("release_id") or "")),
            )
            releases.append(
                {
                    "release_id": item.get("release_id"),
                    "created_at": item.get("created_at"),
                    "status": effective["status"],
                    "risk": (item.get("policy") or {}).get("risk"),
                    "commit": item.get("commit"),
                    "branch": item.get("branch"),
                    "activation": effective["activation"],
                    "approved": effective["approved"],
                }
            )
    releases.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    pending = [item for item in releases if item["status"] == "pushed"]
    failed = [item for item in releases if item["status"] == "push_failed"]
    return {
        "latest": releases[:10],
        "pending_approval": pending,
        "failed": failed,
    }


def _latest_model_release(evidence_root: Path, domain: Domain) -> dict[str, Any] | None:
    folder = evidence_root / "records" / RecordKind.MODEL_RELEASE.value
    values: list[dict[str, Any]] = []
    if folder.exists():
        for path in folder.glob("*.json"):
            item = _read_json(path)
            if item is not None and item.get("domain") == domain.value:
                values.append(item)
    if not values:
        return None
    latest = max(values, key=lambda item: str(item.get("created_at") or ""))
    body = latest.get("body") or {}
    return {
        "record_id": latest.get("record_id"),
        "created_at": latest.get("created_at"),
        "release_stage": body.get("release_stage"),
        "code_commit": body.get("code_commit"),
        "evaluation_contract_version": body.get("evaluation_contract_version"),
    }


def _domain_status(state_root: Path, evidence_root: Path, domain: Domain) -> dict[str, Any]:
    spec = ADAPTER_SPECS[domain]
    latest = _latest_json(state_root / "runs" / domain.value)
    capabilities = {
        readiness.value: sum(
            binding.readiness is readiness for binding in spec.bindings
        )
        for readiness in CapabilityReadiness
    }
    result: dict[str, Any] = {
        "display_name": spec.display_name,
        "capabilities": capabilities,
        "latest_run": None,
        "model_release": _latest_model_release(evidence_root, domain),
    }
    if latest is not None:
        path, payload = latest
        result["latest_run"] = {
            "path": str(path),
            "run_id": payload.get("run_id"),
            "state": payload.get("state"),
            "mode": payload.get("mode"),
            "target_date": payload.get("target_date"),
            "completed_at": payload.get("completed_at"),
            "warnings": len(payload.get("warnings") or []),
            "errors": len(payload.get("errors") or []),
        }
    return result


def collect_status(
    repo_root: Path,
    state_root: Path,
    *,
    production_roots: Mapping[str, Path] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Collect status without changing git, model, scheduler or deployment state."""
    repo_root = repo_root.expanduser().resolve()
    state_root = state_root.expanduser().resolve()
    evidence_root = state_root / "evidence"
    evidence = EvidenceStore(evidence_root).audit()
    domains = {
        domain.value: _domain_status(state_root, evidence_root, domain)
        for domain in Domain
    }
    production = {
        name: _git_payload(Path(path).expanduser().resolve())
        for name, path in sorted((production_roots or {}).items())
    }
    releases = _release_status(
        state_root / "releases",
        state_root / "release-events",
    )
    primary = _git_payload(repo_root)
    reliability = collect_reliability(state_root, now=now)

    attention: list[str] = []
    if primary.get("status") not in {"clean", "clean_runtime_state"}:
        attention.append("primary_git_not_clean")
    if releases["pending_approval"]:
        attention.append("release_pending_approval")
    if releases["failed"]:
        attention.append("release_failed")
    if evidence["status"] != "ok":
        attention.append("evidence_audit_failed")
    if reliability["status"] != "pass":
        attention.extend(reliability["failures"])
    for name, checkout in production.items():
        if checkout.get("status") not in {"clean", "clean_runtime_state"}:
            attention.append(f"production_checkout_not_clean:{name}")

    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None or clock.utcoffset() is None:
        raise ValueError("central status clock must be timezone-aware")
    return {
        "schema_version": STATUS_SCHEMA,
        "generated_at": clock.isoformat(),
        "status": "attention" if attention else "ok",
        "attention": attention,
        "git": {"primary": primary, "production": production},
        "releases": releases,
        "evidence": evidence,
        "reliability": reliability,
        "domains": domains,
    }


def render_telegram(status: Mapping[str, Any]) -> str:
    """Render a compact Cantonese control-tower message."""
    overall = "✅ 正常" if status.get("status") == "ok" else "🟡 要留意"
    primary = (status.get("git") or {}).get("primary") or {}
    head = str(primary.get("head") or "?")[:12]
    dirty = len(primary.get("dirty_paths") or [])
    releases = status.get("releases") or {}
    pending = len(releases.get("pending_approval") or [])
    evidence = status.get("evidence") or {}
    counts = evidence.get("counts") or {}
    lines = [
        f"🐶 中央旺財：{overall}",
        f"Git：{primary.get('branch') or '?'} {head} · dirty {dirty} · "
        f"pushed {'係' if primary.get('pushed') else '否'} · main {'係' if primary.get('merged_to_main') else '否'}",
        f"Release：{pending} 個待批准",
        "Evidence："
        f"prediction {counts.get('prediction', 0)} · decision {counts.get('decision', 0)} · "
        f"settlement {counts.get('settlement', 0)}",
    ]
    reliability = status.get("reliability") or {}
    lines.append(
        f"30日SLO：{'✅' if reliability.get('status') == 'pass' else '❌'} "
        f"{reliability.get('status') or 'unknown'}"
    )
    icons = {
        "succeeded": "✅",
        "dormant": "💤",
        "partial": "⚠️",
        "failed": "❌",
        "blocked": "⛔",
        "running": "⏳",
    }
    for name in ("au", "hkjc", "tennis", "nba"):
        domain = (status.get("domains") or {}).get(name) or {}
        run = domain.get("latest_run") or {}
        state = run.get("state") or "未有中央記錄"
        model = domain.get("model_release") or {}
        model_state = model.get("release_stage") or "未登記"
        lines.append(f"{icons.get(state, '•')} {name.upper()}：{state} · model {model_state}")
    if status.get("attention"):
        lines.append("留意：" + "、".join(status["attention"][:4]))
    return "\n".join(lines)
