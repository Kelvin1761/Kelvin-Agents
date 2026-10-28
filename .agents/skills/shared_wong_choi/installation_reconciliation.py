"""Read-only eligibility for the approved forward-only installer proposal.

This preview cannot issue an intent, approve a release or run an installer.
An eligible preview still requires the fresh full gate and independent approval.
"""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Mapping
from urllib.parse import quote

from .release_activation import EXPECTED_MUTABLE_PATHS, _is_ancestor
from .release_approval import _load_release
from .release_events import EVENT_SCHEMA, EVENT_TYPES, _hash, effective_status
from .release_manager import ReleaseError, _run

INSTALLER = ".agents/skills/central_wong_choi/install_production_runtime.sh"
DOMAINS = ("au", "hkjc", "nba", "tennis")
# Explicit human scope in this chat. Never infer ownership from --actor, branch
# name, main membership, or a caller-supplied list of supposedly owned releases.
OWN_FAILED_RELEASES = frozenset({"e7e1d28e0076f9981b8bf135cfc1f42eb90c353f"})
_SHA = re.compile(r"[0-9a-f]{40}")
_DEPENDENCY_ROOTS = (
    ".agents/scripts/",
    ".agents/skills/",
    "tennis-wong-choi/scripts/",
    "tennis-wong-choi/src/",
    "tennis-wong-choi/launchd/",
)


def _dependency(path: str) -> bool:
    # Deliberate superset: native review imports domain adapters and engines.
    # Include new/removed files and mode changes, not only the entry scripts.
    # The preview and CLI dispatcher are not executed by any installer.
    return ((path.startswith(_DEPENDENCY_ROOTS) or "/" not in path)
            and "/tests/" not in path and not path.endswith(".md")
            and path not in {
                ".agents/skills/shared_wong_choi/installation_reconciliation.py",
                ".agents/skills/central_wong_choi/scripts/central_wong_choi.py",
            })


def changed_installation_dependencies(repo: Path, source: str, target: str) -> list[str]:
    changes = _run(repo, "git", "diff", "--name-only", "--no-renames", "-z",
                   source, target, "--").stdout.split("\0")
    return sorted(path for path in changes if path and _dependency(path))


def _remote(repo: Path, ref: str) -> str:
    # ls-remote is read-only and checks the server, not a possibly stale local
    # tracking ref. Use full refs so branch names cannot be interpreted as flags.
    result = _run(repo, "git", "ls-remote", "--exit-code", "origin", ref)
    lines = result.stdout.splitlines()
    if len(lines) != 1 or len(lines[0].split()) != 2:
        raise ReleaseError(f"remote ref is missing or ambiguous: {ref}")
    sha, actual = lines[0].split()
    if actual != ref or not _SHA.fullmatch(sha):
        raise ReleaseError(f"invalid remote ref: {ref}")
    return sha


def _provenance(state: Path, commit: str, *, failed: bool) -> dict:
    _, manifest = _load_release(state / "releases", commit)
    events = []
    folder = state / "release-events" / quote(manifest["release_id"], safe="._-")
    # Status projections deliberately tolerate damaged records. Eligibility
    # cannot: silently dropping a rejection/failure can resurrect an approval.
    for path in sorted(folder.glob("*.json")):
        try:
            if path.is_symlink():
                raise ValueError("event is a symlink")
            value = json.loads(path.read_text(encoding="utf-8"))
            digest = value.pop("content_hash")
            stamp = datetime.fromisoformat(value["created_at"])
            if (digest != _hash(value) or value.get("schema_version") != EVENT_SCHEMA
                    or value.get("release_id") != manifest["release_id"]
                    or value.get("commit") != commit
                    or value.get("event_type") not in EVENT_TYPES
                    or not isinstance(value.get("detail"), dict)
                    or not isinstance(value.get("actor"), str) or not value["actor"].strip()
                    or stamp.tzinfo is None or stamp.utcoffset() is None):
                raise ValueError("event identity/schema/hash mismatch")
            expected_name = f"{stamp.strftime('%Y%m%dT%H%M%S.%fZ')}-{digest[:16]}.json"
            if path.name != expected_name:
                raise ValueError("event filename differs from hashed timestamp/content")
            value["content_hash"] = digest
            events.append(value)
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            raise ReleaseError(f"invalid release event: {path.name}") from exc
    events.sort(key=lambda event: (datetime.fromisoformat(event["created_at"]), event["content_hash"]))
    effective = effective_status(manifest, events)
    if effective["status"] != "merged" or not effective["approved"]:
        raise ReleaseError("release lacks existing merged approval provenance")
    if manifest.get("check_exit_code") != 0 or manifest.get("push_exit_code") != 0:
        raise ReleaseError("release lacks successful source gate/push provenance")
    gate = manifest.get("gate") or {}
    if gate.get("commit") != commit or gate.get("check") != "full":
        raise ReleaseError("release lacks exact-SHA full source gate provenance")
    if manifest.get("policy", {}).get("risk") in {"model", "evaluation"}:
        raise ReleaseError("model/evaluation release cannot be reconciled")
    approvals = {e["content_hash"] for e in events if e["event_type"] == "approval_granted"}
    merges = [e for e in events if e["event_type"] == "merged"]
    if not merges or merges[-1]["detail"].get("approval_event") not in approvals:
        raise ReleaseError("merge lacks linked immutable approval")
    if failed:
        plan = manifest.get("activation_plan") or {}
        if (effective["activation"] not in {"failed", "rolled_back"}
                or plan.get("installers") != [INSTALLER]
                or set(plan.get("production_sync_domains") or []) != set(DOMAINS)
                or plan.get("manual_required") or plan.get("dashboard_deploy")):
            raise ReleaseError("source is not a failed four-domain installer intent")
    else:
        successes = [e for e in events if e["event_type"] == "activation_succeeded"]
        if effective["activation"] != "succeeded" or not successes:
            raise ReleaseError("target lacks existing successful deployment provenance")
        verified = successes[-1]["detail"].get("verification") or []
        if {item.get("domain") for item in verified
                if item.get("status") == "aligned" and item.get("target_commit") == commit} != set(DOMAINS):
            raise ReleaseError("target lacks four-domain exact-SHA deployment provenance")
    return manifest


def preview_installation_reconciliation(
    repo: Path, state_root: Path, *, source_commit: str, target_commit: str,
    production_roots: Mapping[str, Path],
) -> dict:
    """Check eligibility without writing state, fetching, gating or installing."""
    result = {"schema_version": "wong-choi-installation-preview/v1",
              "source_commit": source_commit, "target_commit": target_commit,
              "status": "blocked", "activation": "not_started",
              "installation_authorized": False, "fresh_full_gate_required": True,
              "independent_approval_required": True}
    try:
        if not all(_SHA.fullmatch(value) for value in (source_commit, target_commit)):
            raise ReleaseError("full immutable source and target SHAs are required")
        if source_commit not in OWN_FAILED_RELEASES:
            raise ReleaseError("source release is outside this chat's explicit authority")
        repo = repo.expanduser().resolve()
        if _remote(repo, "refs/heads/main") != target_commit:
            raise ReleaseError("current remote main differs from explicit target")
        if not _is_ancestor(repo, source_commit, target_commit):
            raise ReleaseError("source release is not an ancestor of the target")
        source = _provenance(state_root, source_commit, failed=True)
        changes = changed_installation_dependencies(repo, source_commit, target_commit)
        result["changed_dependencies"] = changes
        if changes:
            raise ReleaseError("installer/dependency bytes changed; independent review required")
        target = _provenance(state_root, target_commit, failed=False)
        for manifest in (source, target):
            branch = manifest.get("branch")
            if not isinstance(branch, str) or not branch or "\n" in branch:
                raise ReleaseError("manifest release branch is invalid")
            if _remote(repo, "refs/heads/" + branch) != manifest["commit"]:
                raise ReleaseError("remote release branch moved from immutable commit")
        if set(production_roots) != set(DOMAINS):
            raise ReleaseError("all four production roots must be explicit")
        roots = {Path(root).expanduser().resolve() for root in production_roots.values()}
        if len(roots) != 1:
            raise ReleaseError("unified installer requires one shared production checkout")
        for root in roots:
            if _run(root, "git", "rev-parse", "HEAD").stdout.strip() != target_commit:
                raise ReleaseError("production moved from explicit target; never retarget")
            status = _run(root, "git", "status", "--porcelain", "-z",
                          "--untracked-files=all", "--no-renames", check=False)
            if status.returncode != 0:
                raise ReleaseError("production status probe failed; cleanliness unverified")
            dirty = {entry[3:] for entry in status.stdout.split("\0") if entry}
            unexpected = dirty - EXPECTED_MUTABLE_PATHS
            if unexpected:
                raise ReleaseError("production has unrelated concurrent writes: " + ", ".join(sorted(unexpected)))
        # Recheck remote state at the end of this read-only observation window.
        if _remote(repo, "refs/heads/main") != target_commit:
            raise ReleaseError("main moved during preview")
        result.update(status="eligible_for_fresh_gate", installers=[INSTALLER],
                      source_release_id=source["release_id"], target_release_id=target["release_id"])
    except ReleaseError as exc:
        result["error"] = str(exc)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, subprocess.SubprocessError) as exc:
        result["error"] = f"preview probe failed closed: {type(exc).__name__}"
    return result
