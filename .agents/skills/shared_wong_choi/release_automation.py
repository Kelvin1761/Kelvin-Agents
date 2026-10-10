"""User-delegated release approval, retaining immutable checks and rollback."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .control import single_run_lock
from .runtime_launchd import DOMAIN_LABELS, _load_plist


CONFIG_PATH = Path(".agents/skills/central_wong_choi/resources/release_automation.json")


def release_automation_config(repo: Path) -> dict:
    from .release_manager import ReleaseError

    path = repo / CONFIG_PATH
    if not path.exists():
        return {"enabled": False}
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ReleaseError(f"invalid release automation configuration: {path}") from exc
    if not isinstance(config, dict) or type(config.get("enabled")) is not bool:
        raise ReleaseError("release automation requires a boolean enabled setting")
    if config["enabled"] and not str(config.get("authorization") or "").strip():
        raise ReleaseError("automatic approval requires recorded user authorization")
    return config


def production_roots() -> dict[str, Path]:
    """Use explicit environment or consistent installed launchd script paths."""
    roots = {}
    agents = Path.home() / "Library" / "LaunchAgents"
    for domain, labels in DOMAIN_LABELS.items():
        configured = os.environ.get(f"WC_{domain.upper()}_PRODUCTION_ROOT")
        if configured:
            roots[domain] = Path(configured).expanduser().resolve()
            continue
        found = set()
        for label, scripts in labels.items():
            plist, _error = _load_plist(agents / f"{label}.plist")
            if plist is None:
                break
            arguments = plist.get("ProgramArguments") or []
            matches = {
                Path(str(argument)[:-len(script)].rstrip("/")).resolve()
                for script in scripts for argument in arguments
                if str(argument).endswith("/" + script) and Path(str(argument)).is_absolute()
            }
            if len(matches) != 1:
                break
            found.update(matches)
        else:
            if len(found) == 1:
                roots[domain] = found.pop()
    return roots


def auto_approve_release(
    repo: Path, state_root: Path, *, selector: str, notify: bool = True,
    expected_results: tuple[str, ...] = (),
) -> dict:
    from .release_activation import activate_release
    from .release_approval import _load_release, approve_release
    from .release_manager import ReleaseError, _notify
    from .release_events import ReleaseEventStore, effective_status

    config = release_automation_config(repo)
    if not config["enabled"]:
        raise ReleaseError("automatic approval is disabled")
    _path, manifest = _load_release(state_root / "releases", selector)
    effective = effective_status(manifest, ReleaseEventStore(state_root / "release-events").list(manifest["release_id"]))
    if effective["status"] in {"rejected", "superseded"}:
        raise ReleaseError(f"automatic approval cannot reopen a {effective['status']} release")
    actor = "user-delegated:auto-release"
    result = {"commit": manifest["commit"], "status": "blocked", "activation": "not_started"}
    expected = expected_results or manifest.get("expected_results") or [
        "Expected impact was not supplied; no measured improvement is claimed."
    ]
    try:
        with single_run_lock(state_root / "auto-release.lock") as acquired:
            if not acquired:
                raise ReleaseError("another automatic release is running; retry after it finishes")
            roots = production_roots()
            plan = manifest.get("activation_plan") or {}
            missing = set(plan.get("production_sync_domains") or []).difference(roots)
            if missing or plan.get("manual_required"):
                raise ReleaseError(
                    f"activation preflight blocked: missing roots={sorted(missing)}; "
                    f"installer requirements={plan.get('manual_reasons') or []}"
                )
            if notify:
                _notify(repo, "▶️ 自動發佈，毋須 Telegram 批准\n"
                        f"{manifest.get('message') or manifest['commit'][:12]}\n"
                        "預期結果（未來效果並非保證）：\n" + "\n".join(expected), dry_run=False)
            merged = approve_release(repo, state_root, selector=selector, actor=actor,
                                     authorization=config["authorization"], notify=False)
            result.update(merged)
            # Docs/tests still have no production activation side effects.
            if manifest["policy"]["risk"] != "docs_tests":
                activation = activate_release(
                    repo, state_root, selector=selector, actor=actor,
                    production_roots=roots, notify=False,
                )
                result["activation_result"] = activation
                result["activation"] = "succeeded"
    except (ReleaseError, OSError) as exc:
        effective = effective_status(manifest, ReleaseEventStore(state_root / "release-events").list(manifest["release_id"]))
        result["status"] = effective["status"]
        result["activation"] = effective["activation"]
        result["error"] = str(exc)
        result["automation_status"] = "blocked"
    else:
        result["automation_status"] = "completed"
    if notify:
        done = result["automation_status"] == "completed"
        result["telegram"] = _notify(
            repo,
            ("✅ 自動發佈完成" if done else "⚠️ 自動發佈未完成")
            + f"\n{manifest.get('message') or ''}\ncommit：{manifest['commit'][:12]}"
            + f"\nmerge：{result['status']} · activation：{result['activation']}"
            + "\n預期結果（非已量度改善）：\n" + "\n".join(expected)
            + (f"\n原因：{result['error']}" if result.get("error") else ""),
            dry_run=False,
        )
    return result
