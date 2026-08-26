"""Revalidate and merge one immutable Wong Choi release after human approval."""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any

from .release_events import ReleaseEventStore, effective_status
from .release_manager import ReleaseError, _notify, _run


COMMIT_SELECTOR = re.compile(r"^[0-9a-f]{12,64}$")


def _load_release(releases_root: Path, selector: str) -> tuple[Path, dict[str, Any]]:
    if not COMMIT_SELECTOR.fullmatch(selector):
        raise ReleaseError("approval selector must be a 12-64 character lowercase git SHA")
    matches = []
    for path in releases_root.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if str(payload.get("commit") or "").startswith(selector):
            matches.append((path, payload))
    if len(matches) != 1:
        raise ReleaseError(f"approval selector matched {len(matches)} releases")
    return matches[0]


def _remote_sha(repo: Path, ref: str) -> str | None:
    result = _run(repo, "git", "rev-parse", ref, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def _run_gate_in_clean_clone(repo: Path, commit: str, check_name: str) -> None:
    with tempfile.TemporaryDirectory(prefix="wc-release-approval-") as raw:
        clone = Path(raw) / "checkout"
        cloned = _run(
            repo,
            "git",
            "clone",
            "--shared",
            "--no-checkout",
            str(repo),
            str(clone),
            check=False,
            timeout=300,
        )
        if cloned.returncode != 0:
            raise ReleaseError("approval recheck could not create clean checkout")
        checked_out = _run(
            clone, "git", "checkout", "--detach", commit, check=False, timeout=120
        )
        if checked_out.returncode != 0:
            raise ReleaseError("approval commit is not available in clean checkout")
        command = ["./檢查.sh"]
        if check_name == "quick":
            command.append("--quick")
        gate = _run(clone, *command, check=False, timeout=7200)
        if gate.returncode != 0:
            raise ReleaseError("approval recheck gate failed")


def approve_release(
    repo: Path,
    state_root: Path,
    *,
    selector: str,
    actor: str,
    notify: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Approve and fast-forward main; activation remains a separate recorded step."""
    repo = repo.expanduser().resolve()
    state_root = state_root.expanduser().resolve()
    releases_root = state_root / "releases"
    _path, manifest = _load_release(releases_root, selector)
    events = ReleaseEventStore(state_root / "release-events")
    prior = events.list(manifest["release_id"])
    effective = effective_status(manifest, prior)
    if effective["status"] == "merged":
        return {
            "status": "already_merged",
            "release_id": manifest["release_id"],
            "commit": manifest["commit"],
        }
    if manifest.get("status") != "pushed":
        raise ReleaseError(f"release is not approval-ready: {manifest.get('status')}")
    plan = {
        "status": "dry_run",
        "release_id": manifest["release_id"],
        "commit": manifest["commit"],
        "branch": manifest["branch"],
        "risk": manifest["policy"]["risk"],
        "check": manifest["policy"]["check"],
        "rollback_target": manifest["rollback_target"],
    }
    if dry_run:
        return plan

    fetch = _run(repo, "git", "fetch", "origin", check=False, timeout=300)
    if fetch.returncode != 0:
        raise ReleaseError("cannot refresh origin before approval")
    branch_ref = f"origin/{manifest['branch']}"
    if _remote_sha(repo, branch_ref) != manifest["commit"]:
        raise ReleaseError("remote release branch no longer matches immutable commit")
    if _remote_sha(repo, "origin/main") != manifest["rollback_target"]:
        raise ReleaseError("origin/main changed after release; approval expired")

    _run_gate_in_clean_clone(repo, manifest["commit"], manifest["policy"]["check"])
    fetch = _run(repo, "git", "fetch", "origin", check=False, timeout=300)
    if fetch.returncode != 0 or _remote_sha(repo, "origin/main") != manifest["rollback_target"]:
        raise ReleaseError("origin/main changed while approval gate was running")

    approval = events.append(
        release_id=manifest["release_id"],
        commit=manifest["commit"],
        event_type="approval_granted",
        actor=actor,
        detail={"selector": selector, "rollback_target": manifest["rollback_target"]},
    )
    pushed = _run(
        repo,
        "git",
        "push",
        "origin",
        f"{manifest['commit']}:main",
        check=False,
        timeout=300,
    )
    if pushed.returncode != 0:
        raise ReleaseError("approved commit could not fast-forward main")
    merged = events.append(
        release_id=manifest["release_id"],
        commit=manifest["commit"],
        event_type="merged",
        actor="central-wong-choi",
        detail={"approval_event": approval["content_hash"]},
    )
    result = {
        "status": "merged",
        "release_id": manifest["release_id"],
        "commit": manifest["commit"],
        "activation": "not_started",
        "approval_event": approval["path"],
        "merge_event": merged["path"],
    }
    if notify:
        result["telegram"] = _notify(
            repo,
            "✅ 中央旺財已批准並merge\n"
            f"commit：{manifest['commit'][:12]}\n"
            "activation：未開始（會獨立驗證及記錄）",
            dry_run=False,
        )
    return result
