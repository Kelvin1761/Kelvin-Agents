"""Scoped git release automation with immutable status manifests."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from pathlib import PurePosixPath
from typing import Sequence
from urllib.parse import quote
from uuid import uuid4

from .release_policy import ReleasePolicy, activation_plan, classify_release
from .release_events import ReleaseEventStore, effective_status


RELEASE_SCHEMA = "wong-choi-release/v1"
DEFAULT_STATE_ROOT = Path.home() / "WongChoiData" / "WongChoiControl" / "releases"


class ReleaseError(RuntimeError):
    """Raised when a scoped release cannot safely continue."""


@dataclass(frozen=True)
class GitStatus:
    repo: str
    branch: str
    head: str
    upstream: str | None
    origin_main: str | None
    ahead: int | None
    behind: int | None
    dirty_paths: tuple[str, ...]
    staged_paths: tuple[str, ...]
    pushed: bool
    merged_to_main: bool


def _run(
    repo: Path,
    *args: str,
    check: bool = True,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        list(args),
        cwd=repo,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if check and completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise ReleaseError(f"command failed ({' '.join(args)}): {detail}")
    return completed


def _git(repo: Path, *args: str, check: bool = True) -> str:
    return _run(repo, "git", *args, check=check).stdout.strip()


def _nul_paths(value: str) -> tuple[str, ...]:
    return tuple(item for item in value.split("\0") if item)


def changed_paths(repo: Path) -> tuple[str, ...]:
    tracked = _nul_paths(_git(repo, "diff", "--name-only", "-z", "HEAD"))
    untracked = _nul_paths(
        _git(repo, "ls-files", "--others", "--exclude-standard", "-z")
    )
    return tuple(dict.fromkeys((*tracked, *untracked)))


def staged_paths(repo: Path) -> tuple[str, ...]:
    return _nul_paths(_git(repo, "diff", "--cached", "--name-only", "-z"))


def git_status(repo: Path) -> GitStatus:
    repo = repo.resolve()
    branch = _git(repo, "branch", "--show-current")
    head = _git(repo, "rev-parse", "HEAD")
    upstream_result = _run(
        repo,
        "git",
        "rev-parse",
        "--abbrev-ref",
        "--symbolic-full-name",
        "@{upstream}",
        check=False,
    )
    upstream = upstream_result.stdout.strip() if upstream_result.returncode == 0 else None
    origin_result = _run(repo, "git", "rev-parse", "origin/main", check=False)
    origin_main = origin_result.stdout.strip() if origin_result.returncode == 0 else None
    ahead = behind = None
    if upstream:
        counts = _git(repo, "rev-list", "--left-right", "--count", f"{upstream}...HEAD")
        behind, ahead = (int(item) for item in counts.split())
    remote_contains = _git(repo, "branch", "-r", "--contains", head, check=False)
    pushed = bool(remote_contains.strip())
    merged = False
    if origin_main:
        merged = (
            _run(
                repo,
                "git",
                "merge-base",
                "--is-ancestor",
                head,
                "origin/main",
                check=False,
            ).returncode
            == 0
        )
    return GitStatus(
        repo=str(repo),
        branch=branch,
        head=head,
        upstream=upstream,
        origin_main=origin_main,
        ahead=ahead,
        behind=behind,
        dirty_paths=changed_paths(repo),
        staged_paths=staged_paths(repo),
        pushed=pushed,
        merged_to_main=merged,
    )


def _scope_paths(repo: Path, requested: Sequence[str]) -> tuple[str, ...]:
    available = changed_paths(repo)
    selected: list[str] = []
    for raw in requested:
        candidate = PurePosixPath(raw.replace("\\", "/").strip())
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ReleaseError(f"invalid scoped path: {raw!r}")
        clean = candidate.as_posix()
        if clean.startswith("./"):
            clean = clean[2:]
        if not clean or clean == ".":
            raise ReleaseError(f"invalid scoped path: {raw!r}")
        matches = [
            path for path in available if path == clean or path.startswith(clean.rstrip("/") + "/")
        ]
        if not matches:
            raise ReleaseError(f"scoped path has no changes: {raw}")
        selected.extend(matches)
    return tuple(dict.fromkeys(selected))


def _write_manifest(state_root: Path, payload: dict) -> Path:
    state_root.mkdir(parents=True, exist_ok=True)
    path = state_root / (quote(payload["release_id"], safe="._-") + ".json")
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing == payload:
            return path
        raise ReleaseError(f"release manifest conflict: {path}")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    try:
        os.link(temporary, path)
    except FileExistsError as exc:
        raise ReleaseError(f"release manifest already exists: {path}") from exc
    finally:
        temporary.unlink(missing_ok=True)
    return path


def _supersede_ancestor_releases(
    repo: Path,
    state_root: Path,
    *,
    release_id: str,
    branch: str,
    commit: str,
) -> list[str]:
    """Append status events for older pending candidates on the same history."""
    events = ReleaseEventStore(state_root.parent / "release-events")
    superseded: list[str] = []
    for path in sorted(state_root.glob("*.json")) if state_root.exists() else ():
        try:
            prior = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        prior_id = str(prior.get("release_id") or "")
        prior_commit = str(prior.get("commit") or "")
        if (
            prior.get("schema_version") != RELEASE_SCHEMA
            or prior_id == release_id
            or prior.get("branch") != branch
            or effective_status(prior, events.list(prior_id))["status"] != "pushed"
            or not prior_commit
        ):
            continue
        ancestor = _run(
            repo,
            "git",
            "merge-base",
            "--is-ancestor",
            prior_commit,
            commit,
            check=False,
        )
        if ancestor.returncode != 0:
            continue
        events.append(
            release_id=prior_id,
            commit=prior_commit,
            event_type="release_superseded",
            actor="central-release-manager",
            detail={"superseded_by_release_id": release_id, "superseded_by_commit": commit},
        )
        superseded.append(prior_id)
    return superseded


def _notify(repo: Path, message: str, *, dry_run: bool) -> dict:
    script = repo / ".agents/skills/shared_racing/scripts/racing_telegram.py"
    if not script.is_file():
        return {"ok": False, "status": "telegram_script_missing"}
    completed = _run(
        repo,
        sys.executable,
        str(script),
        "--message",
        message,
        "--json",
        *(["--dry-run"] if dry_run else []),
        check=False,
        timeout=30,
    )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {
            "ok": False,
            "status": "telegram_invalid_response",
            "exit_code": completed.returncode,
        }


def _release_message(payload: dict) -> str:
    icon = "✅" if payload["status"] == "merged" else "🟡" if payload["status"] == "pushed" else "❌"
    lines = [
        f"{icon} 中央旺財 Release {payload['release_id']}",
        f"風險：{payload['policy']['risk']} · gate：{payload['policy']['check']}",
        f"commit：{payload['commit'][:12]} · branch：{payload['branch']}",
        f"狀態：{payload['status']} · deploy：{payload['activation']}",
    ]
    if payload["status"] == "pushed":
        lines.append(
            "需要人手批准先merge／activate。\n"
            "覆 /approve 批准，或 /notapprove 拒絕；淨得一個等緊就唔使打 SHA。"
        )
    return "\n".join(lines)


def prepare_release(
    repo: Path,
    *,
    paths: Sequence[str],
    message: str,
    state_root: Path = DEFAULT_STATE_ROOT,
    dry_run: bool = False,
    notify: bool = True,
    allow_unrelated: bool = False,
    activation_base: str | None = None,
) -> dict:
    repo = repo.resolve()
    selected = _scope_paths(repo, paths)
    unrelated = sorted(set(changed_paths(repo)).difference(selected))
    pre_staged = staged_paths(repo)
    if pre_staged and not set(pre_staged).issubset(selected):
        raise ReleaseError(f"staged paths outside release scope: {pre_staged}")
    if unrelated and not allow_unrelated:
        raise ReleaseError(
            "working tree has unrelated changes; use an isolated worktree or explicitly "
            f"allow them: {unrelated}"
        )

    fetched = _run(repo, "git", "fetch", "origin", check=False, timeout=300)
    if fetched.returncode != 0:
        raise ReleaseError("cannot refresh origin before preparing release")
    rollback_target = _git(repo, "rev-parse", "origin/main")
    head = _git(repo, "rev-parse", "HEAD")
    if (
        _run(
            repo,
            "git",
            "merge-base",
            "--is-ancestor",
            rollback_target,
            head,
            check=False,
        ).returncode
        != 0
    ):
        raise ReleaseError("release branch does not descend from fresh origin/main")
    stacked = _nul_paths(
        _git(repo, "diff", "--name-only", "-z", f"{rollback_target}...HEAD")
    )
    release_scope = tuple(dict.fromkeys((*stacked, *selected)))
    policy = classify_release(release_scope)
    activation_target = _git(repo, "rev-parse", activation_base or rollback_target)
    if (
        _run(
            repo,
            "git",
            "merge-base",
            "--is-ancestor",
            activation_target,
            head,
            check=False,
        ).returncode
        != 0
    ):
        raise ReleaseError("activation base is not an ancestor of the release branch")
    activation_stacked = _nul_paths(
        _git(repo, "diff", "--name-only", "-z", f"{activation_target}...HEAD")
    )
    activation_scope = tuple(dict.fromkeys((*activation_stacked, *selected)))
    plan = {
        "schema_version": RELEASE_SCHEMA,
        "status": "dry_run",
        "scope": list(release_scope),
        "selected_scope": list(selected),
        "activation_base": activation_target,
        "activation_scope": list(activation_scope),
        "unrelated_dirty": unrelated,
        "policy": {
            "risk": policy.risk.value,
            "check": policy.check,
            "auto_push": policy.auto_push,
            "auto_merge": policy.auto_merge,
            "auto_activate": policy.auto_activate,
            "reasons": list(policy.reasons),
        },
        "activation_plan": activation_plan(activation_scope),
    }
    if dry_run:
        return plan

    check_args = ["./檢查.sh"]
    if policy.check == "quick":
        check_args.append("--quick")
    checked = _run(repo, *check_args, check=False, timeout=7200)
    if checked.returncode != 0:
        raise ReleaseError(f"{policy.check} gate failed; no files were staged")

    branch = _git(repo, "branch", "--show-current")
    if not branch or branch == "main":
        branch = "codex/release-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        _git(repo, "checkout", "-b", branch)

    _git(repo, "add", "--", *selected)
    staged = staged_paths(repo)
    if set(staged) != set(selected):
        raise ReleaseError(f"staged scope mismatch: expected {selected}, got {staged}")
    diff_check = _run(repo, "git", "diff", "--cached", "--check", check=False)
    if diff_check.returncode != 0:
        raise ReleaseError(f"staged diff check failed: {diff_check.stdout.strip()}")
    _git(repo, "commit", "-m", message)
    commit = _git(repo, "rev-parse", "HEAD")
    pushed = _run(repo, "git", "push", "-u", "origin", branch, check=False, timeout=300)
    push_ok = pushed.returncode == 0

    merged = False
    if push_ok and policy.auto_merge:
        diff_paths = _nul_paths(
            _git(repo, "diff", "--name-only", "-z", "origin/main...HEAD")
        )
        history_policy: ReleasePolicy = classify_release(diff_paths)
        if history_policy.auto_merge:
            merged = (
                _run(
                    repo,
                    "git",
                    "push",
                    "origin",
                    "HEAD:main",
                    check=False,
                    timeout=300,
                ).returncode
                == 0
            )

    created_at = datetime.now(timezone.utc).isoformat()
    release_id = f"wc-release:{commit[:12]}:{created_at.replace(':', '').replace('+', '_')}"
    payload = {
        **plan,
        "release_id": release_id,
        "created_at": created_at,
        "status": "merged" if merged else "pushed" if push_ok else "push_failed",
        "branch": branch,
        "commit": commit,
        "rollback_target": rollback_target,
        "check_exit_code": checked.returncode,
        "push_exit_code": pushed.returncode,
        "activation": "not_started",
    }
    telegram = _notify(repo, _release_message(payload), dry_run=False) if notify else {
        "ok": True,
        "status": "skipped",
    }
    payload["telegram"] = telegram
    manifest = _write_manifest(state_root.expanduser().resolve(), payload)
    payload["manifest"] = str(manifest)
    payload["superseded_releases"] = _supersede_ancestor_releases(
        repo,
        state_root.expanduser().resolve(),
        release_id=release_id,
        branch=branch,
        commit=commit,
    )
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest="command", required=True)
    status = sub.add_parser("status")
    status.add_argument("--json", action="store_true")
    release = sub.add_parser("release")
    release.add_argument("--path", action="append", required=True)
    release.add_argument("--message", required=True)
    release.add_argument("--state-root", type=Path, default=DEFAULT_STATE_ROOT)
    release.add_argument("--dry-run", action="store_true")
    release.add_argument("--no-notify", action="store_true")
    release.add_argument("--allow-unrelated", action="store_true")
    release.add_argument(
        "--activation-base",
        help="Already-deployed commit used only to derive the production activation delta",
    )
    release.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "status":
            result = asdict(git_status(args.repo))
        else:
            result = prepare_release(
                args.repo,
                paths=args.path,
                message=args.message,
                state_root=args.state_root,
                dry_run=args.dry_run,
                notify=not args.no_notify,
                allow_unrelated=args.allow_unrelated,
                activation_base=args.activation_base,
            )
    except ReleaseError as exc:
        result = {"status": "blocked", "error": str(exc)}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") not in {"blocked", "push_failed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
