"""Verified production-checkout activation for an approved Wong Choi release."""

from __future__ import annotations

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


def _command_failure(prefix: str, result) -> ReleaseError:
    details = []
    if result.stdout.strip():
        output = result.stdout.strip()
        bounded = output if len(output) <= 2000 else output[:1000] + "…" + output[-1000:]
        details.append("stdout=" + bounded)
    if result.stderr.strip():
        output = result.stderr.strip()
        bounded = output if len(output) <= 2000 else output[:1000] + "…" + output[-1000:]
        details.append("stderr=" + bounded)
    suffix = "; " + "; ".join(details) if details else ""
    return ReleaseError(f"{prefix} (exit {result.returncode}){suffix}")


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


def _backup_mutable_paths(root: Path, backup_root: Path) -> dict[str, Path]:
    backups: dict[str, Path] = {}
    for relative in _dirty_paths(root):
        if relative not in EXPECTED_MUTABLE_PATHS:
            continue
        source = root / relative
        if not source.is_file():
            continue
        backup = backup_root / relative
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, backup)
        backups[relative] = backup
    return backups


def _restore_mutable_paths(root: Path, backups: Mapping[str, Path]) -> None:
    """Union runtime state with the checked-out git version; runtime wins conflicts."""
    for relative, backup in backups.items():
        target = root / relative
        merge_script = root / ".agents/skills/au_racing/au_daily_auto/merge_mapping.py"
        if relative.endswith("sb_archive_meeting_ids.json") and merge_script.is_file():
            # merge_mapping.py defines its first argument as the local/runtime
            # copy and makes it win key conflicts.  Merge into the backup, then
            # publish that union back to the tracked production path.
            combined = _run(
                root,
                "/usr/bin/python3",
                str(merge_script),
                str(backup),
                str(target),
                check=False,
            )
            if combined.returncode != 0:
                shutil.copy2(backup, target)
                raise ReleaseError("production mapping union failed")
            shutil.copy2(backup, target)
        else:
            shutil.copy2(backup, target)


def _sync_checkout(root: Path, commit: str) -> dict[str, Any]:
    root = root.expanduser().resolve()
    if not (root / ".git").exists():
        raise ReleaseError(f"production checkout missing: {root}")
    fetched = _run(root, "git", "fetch", "origin", check=False, timeout=300)
    if fetched.returncode != 0:
        raise ReleaseError(f"production fetch failed: {root}")
    current = _run(root, "git", "rev-parse", "HEAD").stdout.strip()
    dirty = _dirty_paths(root)
    unexpected = sorted(set(dirty).difference(EXPECTED_MUTABLE_PATHS))
    if unexpected:
        raise ReleaseError(f"production checkout has unrelated dirty paths: {unexpected}")
    if current == commit:
        return {"root": str(root), "before": current, "after": current, "status": "already"}
    if not _is_ancestor(root, current, commit):
        raise ReleaseError(f"production checkout cannot fast-forward: {root}")

    with tempfile.TemporaryDirectory(prefix="wc-production-sync-") as raw:
        backup_root = Path(raw)
        backups = _backup_mutable_paths(root, backup_root)
        for relative in backups:
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
        _restore_mutable_paths(root, backups)

    after = _run(root, "git", "rev-parse", "HEAD").stdout.strip()
    if after != commit:
        raise ReleaseError(f"production checkout ended on wrong commit: {root}")
    return {"root": str(root), "before": current, "after": after, "status": "updated"}


def _rollback_checkout(root: Path, commit: str) -> dict[str, Any]:
    """Reset one dedicated production checkout to its captured pre-activation SHA."""
    root = root.expanduser().resolve()
    if not (root / ".git").exists():
        raise ReleaseError(f"production checkout missing during rollback: {root}")
    current = _run(root, "git", "rev-parse", "HEAD").stdout.strip()
    if current == commit:
        return {
            "root": str(root),
            "before": current,
            "after": current,
            "status": "already_rolled_back",
        }
    if not _is_ancestor(root, commit, current):
        raise ReleaseError(
            f"rollback target is not an ancestor of production HEAD: {root}"
        )
    dirty = _dirty_paths(root)
    unexpected = sorted(set(dirty).difference(EXPECTED_MUTABLE_PATHS))
    if unexpected:
        raise ReleaseError(
            f"rollback blocked by unrelated production writes: {unexpected}"
        )

    with tempfile.TemporaryDirectory(prefix="wc-production-rollback-") as raw:
        backups = _backup_mutable_paths(root, Path(raw))
        reset = _run(
            root,
            "git",
            "reset",
            "--hard",
            commit,
            check=False,
            timeout=300,
        )
        if reset.returncode != 0:
            raise ReleaseError(f"production rollback failed: {root}")
        _restore_mutable_paths(root, backups)

    after = _run(root, "git", "rev-parse", "HEAD").stdout.strip()
    if after != commit:
        raise ReleaseError(f"production rollback ended on wrong commit: {root}")
    return {
        "root": str(root),
        "before": current,
        "after": after,
        "status": "rolled_back",
    }


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
        "installers": list(plan.get("installers") or []),
    }
    if dry_run:
        return result

    checkpoints = {
        str(target.expanduser().resolve()): _run(
            target.expanduser().resolve(), "git", "rev-parse", "HEAD"
        ).stdout.strip()
        for target in unique_targets.values()
    }

    events.append(
        release_id=manifest["release_id"],
        commit=manifest["commit"],
        event_type="activation_started",
        actor=actor,
        detail={
            "domains": domains,
            "targets": sorted(unique_targets),
            "checkpoints": checkpoints,
        },
    )
    sync_results: list[dict[str, Any]] = []
    installer_snapshots: list[dict[str, Any]] = []
    snapshot_temp = tempfile.TemporaryDirectory(prefix="wc-installer-snapshots-")
    snapshot_root = Path(snapshot_temp.name)
    try:
        for target in unique_targets.values():
            sync_results.append(_sync_checkout(target, manifest["commit"]))
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
        installer_results = []
        for index, relative in enumerate(plan.get("installers") or []):
            installer_root = next(iter(unique_targets.values()), repo).expanduser().resolve()
            installer = installer_root / relative
            if not installer.is_file():
                raise ReleaseError(f"approved activation installer missing: {relative}")
            snapshot = snapshot_root / f"installer-{index}"
            snapshotted = _run(
                installer_root,
                "/bin/zsh",
                str(installer),
                "--snapshot",
                str(snapshot),
                check=False,
                timeout=120,
            )
            if snapshotted.returncode != 0:
                raise _command_failure(
                    f"activation installer snapshot failed: {relative}", snapshotted
                )
            installer_snapshots.append(
                {
                    "path": relative,
                    "root": str(installer_root),
                    "snapshot": str(snapshot),
                }
            )
            installed = _run(
                installer_root,
                "/bin/zsh",
                str(installer),
                check=False,
                timeout=300,
            )
            if installed.returncode != 0:
                raise _command_failure(
                    f"approved activation installer failed: {relative}", installed
                )
            checked = _run(
                installer_root,
                "/bin/zsh",
                str(installer),
                "--status",
                check=False,
                timeout=60,
            )
            if checked.returncode != 0:
                raise _command_failure(
                    f"activation installer status failed: {relative}", checked
                )
            installer_results.append(
                {
                    "path": relative,
                    "status": "installed_verified",
                    "status_output": checked.stdout.strip()[-2000:],
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
    except Exception as exc:  # rollback must also cover unexpected verifier/installer errors
        external_rollback_results: list[dict[str, Any]] = []
        external_rollback_errors: list[str] = []
        # Restore launchd/external installer state while the candidate installer
        # still exists in the production checkout. The git rollback below may
        # return to a commit from before that installer was introduced.
        for item in reversed(installer_snapshots):
            installer = Path(item["root"]) / item["path"]
            restored = _run(
                Path(item["root"]),
                "/bin/zsh",
                str(installer),
                "--restore",
                item["snapshot"],
                check=False,
                timeout=300,
            )
            if restored.returncode == 0:
                external_rollback_results.append(
                    {"path": item["path"], "status": "restored"}
                )
            else:
                external_rollback_errors.append(
                    f"{item['path']}: installer state restore exit {restored.returncode}"
                )
        rollback_results: list[dict[str, Any]] = []
        rollback_errors: list[str] = []
        for raw_target, before in reversed(list(checkpoints.items())):
            target = Path(raw_target)
            try:
                rollback_results.append(_rollback_checkout(target, before))
            except Exception as rollback_exc:  # preserve and report concurrent writes
                rollback_errors.append(
                    f"{target}: {type(rollback_exc).__name__}: {rollback_exc}"
                )
        all_rollback_errors = [*external_rollback_errors, *rollback_errors]
        rollback_status = "succeeded" if not all_rollback_errors else "blocked"
        failed = events.append(
            release_id=manifest["release_id"],
            commit=manifest["commit"],
            event_type="activation_failed",
            actor="central-wong-choi",
            detail={
                "error": f"{type(exc).__name__}: {exc}",
                "rollback_status": rollback_status,
                "rollback": rollback_results,
                "rollback_errors": rollback_errors,
                "external_rollback": external_rollback_results,
                "external_rollback_errors": external_rollback_errors,
            },
        )
        if notify:
            _notify(
                repo,
                f"❌ 中央旺財 activation 失敗\n{manifest['commit'][:12]}\n{exc}\n"
                + (
                    "✅ production 已退回 activation 前版本"
                    if not all_rollback_errors
                    else "⛔ rollback 被保護閘攔住："
                    + "；".join(all_rollback_errors)[:700]
                ),
                dry_run=False,
            )
        rollback_note = (
            "rollback complete"
            if not all_rollback_errors
            else "rollback incomplete: " + "; ".join(all_rollback_errors)
        )
        snapshot_temp.cleanup()
        raise ReleaseError(
            f"activation failed; {rollback_note}; event={failed['path']}: {exc}"
        ) from exc

    snapshot_temp.cleanup()
    completed = events.append(
        release_id=manifest["release_id"],
        commit=manifest["commit"],
        event_type="activation_succeeded",
        actor="central-wong-choi",
        detail={
            "sync": sync_results,
            "verification": verification,
            "installers": installer_results,
            "deploy": deploy,
        },
    )
    result.update(
        {
            "status": "activated",
            "sync": sync_results,
            "verification": verification,
            "installers": installer_results,
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
