"""Verified production-checkout activation for an approved Wong Choi release."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any, Mapping

from .deployment_verify import verify_deployment
from .release_approval import _load_release
from .release_events import ReleaseEventStore, effective_status
from .release_manager import ReleaseError, _notify, _run


EXPECTED_MUTABLE_PATHS = frozenset(
    {".agents/skills/au_racing/data/sb_archive_meeting_ids.json"}
)


def _dirty_paths(root: Path) -> list[str]:
    result = _run(root, "git", "status", "--porcelain", "-z", check=False)
    values = []
    for entry in result.stdout.split("\0"):
        if not entry:
            continue
        value = entry[3:].strip()
        if " -> " in value:
            value = value.rsplit(" -> ", 1)[-1]
        values.append(value)
    return sorted(set(values))


def _is_ancestor(root: Path, older: str, newer: str) -> bool:
    return (
        _run(
            root,
            "git",
            "merge-base",
            "--is-ancestor",
            older,
            newer,
            check=False,
        ).returncode
        == 0
    )


def _sync_checkout(root: Path, commit: str) -> dict[str, Any]:
    root = root.expanduser().resolve()
    if not (root / ".git").exists():
        raise ReleaseError(f"production checkout missing: {root}")
    fetched = _run(root, "git", "fetch", "origin", check=False, timeout=300)
    if fetched.returncode != 0:
        raise ReleaseError(f"production fetch failed: {root}")
    current = _run(root, "git", "rev-parse", "HEAD").stdout.strip()
    if current == commit:
        return {"root": str(root), "before": current, "after": current, "status": "already"}
    if not _is_ancestor(root, current, commit):
        raise ReleaseError(f"production checkout cannot fast-forward: {root}")
    dirty = _dirty_paths(root)
    unexpected = sorted(set(dirty).difference(EXPECTED_MUTABLE_PATHS))
    if unexpected:
        raise ReleaseError(f"production checkout has unrelated dirty paths: {unexpected}")

    backups: dict[str, Path] = {}
    with tempfile.TemporaryDirectory(prefix="wc-production-sync-") as raw:
        backup_root = Path(raw)
        for relative in dirty:
            source = root / relative
            if source.is_file():
                backup = backup_root / Path(relative).name
                shutil.copy2(source, backup)
                backups[relative] = backup
                restored = _run(
                    root, "git", "restore", "--worktree", "--", relative, check=False
                )
                if restored.returncode != 0:
                    raise ReleaseError(f"cannot preserve runtime state before sync: {relative}")
        merged = _run(
            root, "git", "merge", "--ff-only", commit, check=False, timeout=300
        )
        if merged.returncode != 0:
            for relative, backup in backups.items():
                shutil.copy2(backup, root / relative)
            raise ReleaseError(f"production fast-forward failed: {root}")
        for relative, backup in backups.items():
            target = root / relative
            merge_script = (
                root / ".agents/skills/au_racing/au_daily_auto/merge_mapping.py"
            )
            if relative.endswith("sb_archive_meeting_ids.json") and merge_script.is_file():
                combined = _run(
                    root,
                    "/usr/bin/python3",
                    str(merge_script),
                    str(target),
                    str(backup),
                    check=False,
                )
                if combined.returncode != 0:
                    shutil.copy2(backup, target)
                    raise ReleaseError("production mapping merge failed after fast-forward")
            else:
                shutil.copy2(backup, target)

    after = _run(root, "git", "rev-parse", "HEAD").stdout.strip()
    if after != commit:
        raise ReleaseError(f"production checkout ended on wrong commit: {root}")
    return {"root": str(root), "before": current, "after": after, "status": "updated"}


def activate_release(
    repo: Path,
    state_root: Path,
    *,
    selector: str,
    actor: str,
    production_roots: Mapping[str, Path],
    notify: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    repo = repo.expanduser().resolve()
    state_root = state_root.expanduser().resolve()
    _path, manifest = _load_release(state_root / "releases", selector)
    events = ReleaseEventStore(state_root / "release-events")
    existing = events.list(manifest["release_id"])
    effective = effective_status(manifest, existing)
    if effective["activation"] == "succeeded":
        return {
            "status": "already_active",
            "release_id": manifest["release_id"],
            "commit": manifest["commit"],
        }
    if effective["status"] != "merged":
        raise ReleaseError("release must be merged before activation")
    plan = manifest.get("activation_plan") or {}
    if plan.get("manual_required"):
        raise ReleaseError(
            "activation requires explicit launchd installer: "
            + ", ".join(plan.get("manual_reasons") or [])
        )
    domains = list(plan.get("production_sync_domains") or [])
    missing = [domain for domain in domains if domain not in production_roots]
    if missing:
        raise ReleaseError(f"production roots not configured for: {missing}")
    unique_targets = {
        str(Path(production_roots[domain]).expanduser().resolve()): Path(
            production_roots[domain]
        )
        for domain in domains
    }
    result = {
        "status": "dry_run",
        "release_id": manifest["release_id"],
        "commit": manifest["commit"],
        "domains": domains,
        "targets": sorted(unique_targets),
        "dashboard_deploy": bool(plan.get("dashboard_deploy")),
    }
    if dry_run:
        return result

    events.append(
        release_id=manifest["release_id"],
        commit=manifest["commit"],
        event_type="activation_started",
        actor=actor,
        detail={"domains": domains, "targets": sorted(unique_targets)},
    )
    try:
        sync_results = [
            _sync_checkout(target, manifest["commit"])
            for target in unique_targets.values()
        ]
        verification = []
        # The Telegram bot can itself run from the production checkout.  A
        # verifier comparing that checkout to itself proves nothing, and a
        # dirty primary workspace may contain files newer than the approved
        # commit.  Always verify against a detached, clean tree at the exact
        # immutable release SHA.
        with tempfile.TemporaryDirectory(prefix="wc-activation-verify-") as raw:
            clean_source = Path(raw) / "source"
            cloned = _run(
                repo,
                "git",
                "clone",
                "--shared",
                "--no-checkout",
                str(repo),
                str(clean_source),
                check=False,
                timeout=300,
            )
            if cloned.returncode != 0:
                raise ReleaseError("cannot create clean activation verifier checkout")
            checked_out = _run(
                clean_source,
                "git",
                "checkout",
                "--detach",
                manifest["commit"],
                check=False,
                timeout=300,
            )
            if checked_out.returncode != 0:
                raise ReleaseError("cannot checkout approved activation commit")
            for domain in domains:
                target = Path(production_roots[domain]).expanduser().resolve()
                check = verify_deployment(clean_source, target, domain)
                if not check["safe_to_activate"]:
                    raise ReleaseError(f"deployment verifier failed for {domain}")
                verification.append(
                    {
                        "domain": domain,
                        "status": check["status"],
                        "target_commit": check["target_commit"],
                    }
                )
        deploy = None
        if plan.get("dashboard_deploy"):
            deploy_root = next(iter(unique_targets.values()), repo)
            deployed = _run(
                deploy_root,
                str(deploy_root / "deploy.sh"),
                check=False,
                timeout=1800,
            )
            if deployed.returncode != 0:
                raise ReleaseError("dashboard deployment failed")
            deploy = {"status": "succeeded", "exit_code": deployed.returncode}
    except (OSError, ReleaseError) as exc:
        failed = events.append(
            release_id=manifest["release_id"],
            commit=manifest["commit"],
            event_type="activation_failed",
            actor="central-wong-choi",
            detail={"error": f"{type(exc).__name__}: {exc}"},
        )
        if notify:
            _notify(
                repo,
                f"❌ 中央旺財 activation 失敗\n{manifest['commit'][:12]}\n{exc}",
                dry_run=False,
            )
        raise ReleaseError(f"activation failed; event={failed['path']}: {exc}") from exc

    completed = events.append(
        release_id=manifest["release_id"],
        commit=manifest["commit"],
        event_type="activation_succeeded",
        actor="central-wong-choi",
        detail={"sync": sync_results, "verification": verification, "deploy": deploy},
    )
    result.update(
        {
            "status": "activated",
            "sync": sync_results,
            "verification": verification,
            "deploy": deploy,
            "activation_event": completed["path"],
        }
    )
    if notify:
        result["telegram"] = _notify(
            repo,
            f"✅ 中央旺財已部署 {manifest['commit'][:12]}\n"
            + "domains："
            + ", ".join(domains or ["control-only"]),
            dry_run=False,
        )
    return result
