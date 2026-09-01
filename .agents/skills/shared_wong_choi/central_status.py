"""Read-only status view across git, releases, evidence and four domain runs."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from .contracts import CapabilityReadiness, Domain
from .dashboard_status import collect_dashboard_status
from .evidence import EvidenceStore, RecordKind
from .registry import ADAPTER_SPECS
from .release_activation import EXPECTED_MUTABLE_PATHS
from .release_events import ReleaseEventStore, effective_status
from .release_manager import GitStatus, ReleaseError, git_status
from .reliability import collect_reliability
from .runtime_launchd import collect_runtime_alignment
from .storage_status import collect_storage_status


STATUS_SCHEMA = "wong-choi-central-status/v1"


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _aware_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _duration_label(seconds: Any) -> str:
    try:
        value = max(0, int(float(seconds)))
    except (TypeError, ValueError):
        return "?"
    hours, remainder = divmod(value, 3600)
    minutes = remainder // 60
    if hours:
        return f"{hours}h{minutes:02d}m"
    return f"{minutes}m"


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
    merged_by_commit: dict[str, dict[str, Any]] = {}
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
            summary = {
                "release_id": item.get("release_id"),
                "created_at": item.get("created_at"),
                "status": effective["status"],
                "risk": (item.get("policy") or {}).get("risk"),
                "commit": item.get("commit"),
                "branch": item.get("branch"),
                "activation": effective["activation"],
                "approved": effective["approved"],
            }
            releases.append(summary)
            commit = str(summary.get("commit") or "")
            if commit and summary["status"] == "merged":
                previous = merged_by_commit.get(commit)
                if previous is None or str(summary.get("created_at") or "") > str(
                    previous.get("created_at") or ""
                ):
                    merged_by_commit[commit] = summary
    releases.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    pending = [item for item in releases if item["status"] == "pushed"]
    failed = [item for item in releases if item["status"] == "push_failed"]
    return {
        "latest": releases[:10],
        "pending_approval": pending,
        "failed": failed,
        "_merged_by_commit": merged_by_commit,
    }


def _release_tracking(
    commit: Any,
    merged_by_commit: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    value = str(commit or "")
    release = merged_by_commit.get(value)
    return {
        "commit": value or None,
        "tracked": release is not None,
        "release_id": release.get("release_id") if release else None,
        "activation": release.get("activation") if release else None,
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


def _domain_status(
    state_root: Path,
    evidence_root: Path,
    domain: Domain,
    *,
    now: datetime,
) -> dict[str, Any]:
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
        state = payload.get("state")
        mode = str(payload.get("mode") or "")
        started_at = _aware_datetime(payload.get("started_at"))
        timeout_seconds = spec.run_timeout_seconds(mode)
        lifecycle = "completed"
        elapsed_seconds = None
        remaining_seconds = None
        deadline_at = None
        if state == "running":
            if started_at is None:
                lifecycle = "unknown_start"
            else:
                elapsed_seconds = max(0, int((now - started_at).total_seconds()))
                deadline = started_at + timedelta(seconds=timeout_seconds)
                deadline_at = deadline.isoformat()
                remaining_seconds = max(0, int((deadline - now).total_seconds()))
                lifecycle = "within_timeout" if now <= deadline else "overdue"
        result["latest_run"] = {
            "path": str(path),
            "run_id": payload.get("run_id"),
            "state": state,
            "mode": mode,
            "target_date": payload.get("target_date"),
            "started_at": payload.get("started_at"),
            "completed_at": payload.get("completed_at"),
            "lifecycle": lifecycle,
            "elapsed_seconds": elapsed_seconds,
            "timeout_seconds": timeout_seconds if state == "running" else None,
            "remaining_seconds": remaining_seconds,
            "deadline_at": deadline_at,
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
    launch_agents_root: Path | None = None,
    probe_launchd: bool = True,
) -> dict[str, Any]:
    """Collect status without changing git, model, scheduler or deployment state."""
    repo_root = repo_root.expanduser().resolve()
    state_root = state_root.expanduser().resolve()
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None or clock.utcoffset() is None:
        raise ValueError("central status clock must be timezone-aware")
    evidence_root = state_root / "evidence"
    evidence = EvidenceStore(evidence_root).audit()
    domains = {
        domain.value: _domain_status(
            state_root,
            evidence_root,
            domain,
            now=clock,
        )
        for domain in Domain
    }
    production = {
        name: _git_payload(Path(path).expanduser().resolve())
        for name, path in sorted((production_roots or {}).items())
    }
    primary = _git_payload(repo_root)
    releases = _release_status(
        state_root / "releases",
        state_root / "release-events",
    )
    merged_by_commit = releases.pop("_merged_by_commit")
    releases["origin_main"] = _release_tracking(
        primary.get("origin_main"), merged_by_commit
    )
    for checkout in production.values():
        tracking = _release_tracking(checkout.get("head"), merged_by_commit)
        checkout["release_tracked"] = tracking["tracked"]
        checkout["release_id"] = tracking["release_id"]
        checkout["release_activation"] = tracking["activation"]
    reliability = collect_reliability(state_root, now=now)
    dashboard = collect_dashboard_status(repo_root, state_root)
    storage = collect_storage_status(repo_root, state_root)
    runtime_control_root = (
        Path((production_roots or {}).get("au", repo_root)).expanduser().resolve()
    )
    runtime = (
        collect_runtime_alignment(
            production_roots or {},
            control_root=runtime_control_root,
            launch_agents_root=launch_agents_root,
            probe_loaded=probe_launchd,
        )
        if production_roots
        else {
            "schema_version": "wong-choi-runtime-launchd/v1",
            "status": "not_configured",
            "domains": {},
            "central": {"status": "not_configured", "labels": []},
            "attention": [],
        }
    )

    attention: list[str] = []
    if primary.get("status") not in {"clean", "clean_runtime_state"}:
        attention.append("primary_git_not_clean")
    if releases["pending_approval"]:
        attention.append("release_pending_approval")
    if releases["failed"]:
        attention.append("release_failed")
    origin_main = releases["origin_main"]
    if origin_main["commit"] and not origin_main["tracked"]:
        attention.append("origin_main_without_release_manifest")
    if evidence["status"] != "ok":
        attention.append("evidence_audit_failed")
    if reliability["status"] != "pass":
        attention.extend(reliability["failures"])
    if dashboard["status"] != "configured":
        attention.extend(dashboard["attention"])
    if storage["status"] != "ok":
        attention.extend(storage["attention"])
    attention.extend(runtime.get("attention") or [])
    for name, domain in domains.items():
        run = domain.get("latest_run") or {}
        if run.get("state") == "running" and run.get("lifecycle") == "overdue":
            attention.append(f"run_overdue:{name}")
        if run.get("state") == "running" and run.get("lifecycle") == "unknown_start":
            attention.append(f"run_started_at_invalid:{name}")
    for name, checkout in production.items():
        if checkout.get("status") not in {"clean", "clean_runtime_state"}:
            attention.append(f"production_checkout_not_clean:{name}")
        if checkout.get("head") and not checkout.get("release_tracked"):
            attention.append(f"production_commit_without_release_manifest:{name}")

    return {
        "schema_version": STATUS_SCHEMA,
        "generated_at": clock.isoformat(),
        "status": "attention" if attention else "ok",
        "attention": attention,
        "git": {"primary": primary, "production": production},
        "releases": releases,
        "evidence": evidence,
        "reliability": reliability,
        "dashboard": dashboard,
        "storage": storage,
        "runtime": runtime,
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
    latest_releases = releases.get("latest") or []
    latest_release = latest_releases[0] if latest_releases else {}
    evidence = status.get("evidence") or {}
    counts = evidence.get("counts") or {}
    lines = [
        f"🐶 中央旺財：{overall}",
        f"Git：{primary.get('branch') or '?'} {head} · dirty {dirty} · "
        f"pushed {'係' if primary.get('pushed') else '否'} · main {'係' if primary.get('merged_to_main') else '否'}",
        (
            "Release：未有記錄"
            if not latest_release
            else f"Release：{str(latest_release.get('commit') or '?')[:12]} · "
            f"{latest_release.get('status') or 'unknown'} · "
            f"activate {latest_release.get('activation') or 'unknown'}"
        ),
        "Evidence："
        f"prediction {counts.get('prediction', 0)} · decision {counts.get('decision', 0)} · "
        f"settlement {counts.get('settlement', 0)}",
    ]
    if pending:
        pending_commit = str(
            (releases.get("pending_approval") or [{}])[0].get("commit") or "?"
        )[:12]
        lines.append(f"待批准：{pending} 個 · Telegram /approve {pending_commit}")
    origin_main = releases.get("origin_main") or {}
    if origin_main.get("commit"):
        lines.append(
            "Main trail："
            + (
                f"✅ {str(origin_main.get('release_id') or '?').split(':')[1]}"
                if origin_main.get("tracked")
                else f"⛔ {str(origin_main.get('commit'))[:12]} 冇Central release manifest"
            )
        )
    production = (status.get("git") or {}).get("production") or {}
    if production:
        by_commit: dict[str, list[str]] = {}
        for name, item in sorted(production.items()):
            commit = str(item.get("head") or "?")[:12]
            by_commit.setdefault(commit, []).append(name.upper())
        lines.append(
            "Production："
            + " · ".join(
                f"{'/'.join(names)} {commit}"
                for commit, names in by_commit.items()
            )
        )
    runtime = status.get("runtime") or {}
    runtime_domains = runtime.get("domains") or {}
    if runtime_domains:
        markers = []
        for name in ("au", "hkjc", "tennis", "nba"):
            aligned = (runtime_domains.get(name) or {}).get("status") == "aligned"
            markers.append(f"{name.upper()} {'✅' if aligned else '❌'}")
        central_aligned = (runtime.get("central") or {}).get("status") == "aligned"
        markers.append(f"CENTRAL {'✅' if central_aligned else '❌'}")
        lines.append("Automation：" + " · ".join(markers))
    reliability = status.get("reliability") or {}
    lines.append(
        f"30日SLO：{'✅' if reliability.get('status') == 'pass' else '❌'} "
        f"{reliability.get('status') or 'unknown'}"
    )
    dashboard = status.get("dashboard") or {}
    storage = status.get("storage") or {}
    hot = ((storage.get("tiers") or {}).get("hot") or {})
    free_gib = ((hot.get("disk") or {}).get("free_gib"))
    lines.append(
        f"Dashboard：{dashboard.get('status') or 'unknown'} · "
        f"D1 {'係' if dashboard.get('betting_ledger_source') == 'cloudflare_d1_wc_ledger' else '否'}"
    )
    lines.append(f"Storage：HOT {hot.get('pressure') or 'unknown'} · free {free_gib if free_gib is not None else 'N/A'} GiB")
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
        if state == "running":
            lifecycle = run.get("lifecycle")
            elapsed = _duration_label(run.get("elapsed_seconds"))
            timeout = _duration_label(run.get("timeout_seconds"))
            if lifecycle == "within_timeout":
                remaining = _duration_label(run.get("remaining_seconds"))
                run_label = f"running {elapsed} / {timeout} · 仲有 {remaining}"
                icon = "⏳"
            elif lifecycle == "overdue":
                run_label = f"running OVERDUE · {elapsed} / {timeout}"
                icon = "🧯"
            else:
                run_label = "running · started_at 無效"
                icon = "❓"
        else:
            run_label = str(state)
            icon = icons.get(state, "•")
        lines.append(f"{icon} {name.upper()}：{run_label} · model {model_state}")
    if status.get("attention"):
        lines.append("留意：" + "、".join(status["attention"][:4]))
    return "\n".join(lines)
