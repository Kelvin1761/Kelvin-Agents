"""User-delegated release approval, retaining immutable checks and rollback."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
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
            path = agents / f"{label}.plist"
            # Root discovery is separate from runtime health verification.
            # A newly introduced/optional job may not be installed yet.
            if not path.exists():
                continue
            plist, _error = _load_plist(path)
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


# Delegated approval may replay an expired release onto the new main at most this many
# times in one run (docs/plans/2026-10-21-release-expiry-fast-path.md §4 B).
MAX_REPLAYS = 3
_EXPIRY_MARKERS = ("approval expired", "changed while approval gate was running")


def _git_out(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=True).stdout


def _replay_conflicts(repo: Path, manifest: dict) -> list[str]:
    """Scoped paths that main also changed since the release was gated.

    Paths marked `merge=union` on origin/main (docs/experiments/INDEX.md) are left to the
    cherry-pick: both sides' added lines are kept, and the replayed commit is gated again.
    """
    scope = set(manifest.get("scope") or manifest.get("selected_scope") or [])
    moved = set(filter(None, _git_out(repo, "diff", "--name-only", "-z",
                                      manifest["rollback_target"], "origin/main").split("\0")))
    overlap = sorted(scope & moved)
    if not overlap:
        return []
    attrs = _git_out(repo, "check-attr", "--source", "origin/main", "-z", "merge", "--", *overlap).split("\0")
    union = {attrs[i] for i in range(0, len(attrs) - 2, 3) if attrs[i + 2] == "union"}
    return [path for path in overlap if path not in union]


def _replay_release(repo: Path, state_root: Path, selector: str, *, actor: str) -> str:
    """Replay one expired release onto origin/main in a throwaway worktree; return the new SHA.

    Uses the existing `refresh_release` (cherry-pick, full prepare gate, push a never-reused
    branch, supersede the old manifest). It runs in its own worktree so the caller's checkout —
    possibly the main checkout — never changes branch.
    """
    from .release_refresh import refresh_release

    with tempfile.TemporaryDirectory(prefix="wc-release-replay-") as raw:
        checkout = Path(raw) / "checkout"
        _git_out(repo, "worktree", "add", "-q", "--detach", str(checkout), "origin/main")
        branch = None
        try:
            for marker in repo.glob(".wongchoi_*root"):
                shutil.copy2(marker, checkout / marker.name)
            refreshed = refresh_release(checkout, state_root, selector=selector, actor=actor,
                                        notify=False, auto_approve=False)
            branch = refreshed.get("branch")
            return str(refreshed["release"]["commit"])
        finally:
            subprocess.run(["git", "worktree", "remove", "--force", str(checkout)], cwd=repo,
                           capture_output=True, check=False)
            if branch:
                subprocess.run(["git", "branch", "-D", branch], cwd=repo, capture_output=True, check=False)


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
            replayed = []
            while True:
                try:
                    merged = approve_release(repo, state_root, selector=selector, actor=actor,
                                             authorization=config["authorization"], notify=False)
                    break
                except ReleaseError as exc:
                    if not any(marker in str(exc) for marker in _EXPIRY_MARKERS):
                        raise
                    if len(replayed) >= MAX_REPLAYS:
                        raise ReleaseError(f"{exc}; replay limit ({MAX_REPLAYS}) reached") from exc
                    _run_fetch = subprocess.run(["git", "fetch", "-q", "origin"], cwd=repo,
                                                capture_output=True, check=False)
                    if _run_fetch.returncode != 0:
                        raise ReleaseError(f"{exc}; cannot refresh origin to replay") from exc
                    conflicts = _replay_conflicts(repo, manifest)
                    if conflicts:
                        raise ReleaseError(f"{exc}; main also changed {conflicts} — needs a human") from exc
                    replayed.append(selector)
                    selector = _replay_release(repo, state_root, selector, actor=actor)
                    _path, manifest = _load_release(state_root / "releases", selector)
            result.update(merged)
            if replayed:
                result["replayed_from"] = replayed
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
