"""Replay an expired release on top of fresh origin/main.

WHY THIS EXISTS
---------------
Approval is deliberately pinned to the main the release was gated against:
`approve_release` refuses unless `origin/main == manifest["rollback_target"]`.
That is the right rule — a release gated against a different main was never
actually verified against what it would land on — but it makes releases
**strictly serial**: the first merge expires every other pending release with
``origin/main changed after release; approval expired``.

2026-09-04 there were five pending. Approving one expired the other four, and
there was no way to recover them: `prepare_release` only builds a manifest from
working-tree changes, so an expired release had to be reconstructed by hand
(clean worktree → cherry-pick → re-gate → re-push → approve → reject the old
manifest), once per release, in order. Four rounds of that is where this
function comes from.

WHAT IT DOES NOT DO
-------------------
It does not approve anything, and it deliberately has no "refresh all" mode.
Refreshing N releases still means N sequential merges, because each merge
expires whatever is left — batching the *preparation* would just produce N
manifests of which N-1 are already expired again. Call it once per release,
approve, then call it for the next one.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .release_approval import _load_release, reject_release
from .release_events import ReleaseEventStore, effective_status
from .release_manager import ReleaseError, _git, _run, prepare_release

# A branch name is never reused. Re-cutting the same name from origin/main makes
# the push a non-fast-forward, `保存.sh` (correctly) does not force, and the run
# ends with a manifest naming a commit the remote does not have -- which then
# fails approval as `push_failed`. Measured the hard way on 2026-09-04.
BRANCH_PREFIX = "wc-refresh"


def _branch_name(commit: str, attempt: int) -> str:
    suffix = "" if attempt <= 1 else f"-r{attempt}"
    return f"{BRANCH_PREFIX}-{commit[:12]}{suffix}"


def _remote_branch_exists(repo: Path, branch: str) -> bool:
    listed = _run(repo, "git", "ls-remote", "--heads", "origin", branch, check=False)
    return bool(listed.stdout.strip())


def _free_branch(repo: Path, commit: str) -> str:
    for attempt in range(1, 20):
        branch = _branch_name(commit, attempt)
        if not _remote_branch_exists(repo, branch):
            return branch
    raise ReleaseError(f"cannot find an unused refresh branch for {commit[:12]}")


def refresh_release(
    repo: Path,
    state_root: Path,
    *,
    selector: str,
    actor: str,
    notify: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Re-prepare one expired release against current origin/main.

    Returns the new manifest plus the id of the old release it supersedes. The
    old manifest is rejected (recorded, never deleted) so it stops showing as
    pending -- otherwise bare ``/approve`` keeps refusing with "N releases are
    waiting".
    """
    repo = repo.expanduser().resolve()
    state_root = state_root.expanduser().resolve()
    _path, manifest = _load_release(state_root / "releases", selector)
    old_commit = str(manifest["commit"])
    events = ReleaseEventStore(state_root / "release-events")
    effective = effective_status(manifest, events.list(manifest["release_id"]))

    if effective["status"] == "rejected":
        raise ReleaseError("release was rejected; prepare a new one instead")

    scope = list(manifest.get("scope") or manifest.get("selected_scope") or [])
    if not scope:
        raise ReleaseError(f"release {old_commit[:12]} recorded no scope to replay")

    fetched = _run(repo, "git", "fetch", "origin", check=False, timeout=300)
    if fetched.returncode != 0:
        raise ReleaseError("cannot refresh origin before replaying release")

    main_sha = _git(repo, "rev-parse", "origin/main")
    if main_sha == manifest["rollback_target"]:
        raise ReleaseError(
            "release has not expired (origin/main still matches its rollback "
            "target); approve it directly instead of refreshing"
        )
    # 「已經喺 main 上面」比「manifest 寫住 merged」更準 —— out-of-band merge
    # 兩者會唔一致，而呢個訊息係讀者真正要知嘅嗰個。
    if _run(repo, "git", "merge-base", "--is-ancestor", old_commit, main_sha,
            check=False).returncode == 0:
        raise ReleaseError(
            f"{old_commit[:12]} is already contained in origin/main; "
            "nothing to refresh"
        )
    if effective["status"] == "merged":
        raise ReleaseError("release is already merged; nothing to refresh")

    # The commit message is the one thing the manifest does not record.
    message = _git(repo, "log", "-1", "--pretty=%s", old_commit)

    plan = {
        "status": "dry_run",
        "supersedes": manifest["release_id"],
        "old_commit": old_commit,
        "old_rollback_target": manifest["rollback_target"],
        "origin_main": main_sha,
        "scope": scope,
        "message": message,
        "risk": (manifest.get("policy") or {}).get("risk"),
    }
    if dry_run:
        plan["branch"] = _branch_name(old_commit, 1)
        return plan

    # Replay rewrites HEAD and the index, so an aborted attempt has to be
    # undoable exactly. That is only true if no tracked file is modified —
    # otherwise the cleanup would have to discard someone else's work.
    tracked_dirty = _run(repo, "git", "status", "--porcelain", "--untracked-files=no",
                         check=False).stdout.strip()
    if tracked_dirty:
        raise ReleaseError(
            "replay needs a clean tracked tree (use an isolated worktree); dirty: "
            + ", ".join(sorted(line[3:] for line in tracked_dirty.splitlines()))
        )

    branch = _free_branch(repo, old_commit)
    original_head = _git(repo, "rev-parse", "HEAD")
    _run(repo, "git", "checkout", "-q", "-B", branch, main_sha)
    picked = _run(repo, "git", "cherry-pick", "-n", old_commit, check=False)
    if picked.returncode != 0:
        conflicts = _run(repo, "git", "diff", "--name-only", "--diff-filter=U",
                         check=False).stdout.split()
        # `cherry-pick --abort` errors out after a `-n` pick (there is no
        # sequencer state to abort), which used to leave the unmerged paths in
        # the index. `--quit` clears whatever state exists, then a hard reset to
        # the captured HEAD undoes the replay — safe because a clean tracked
        # tree is a precondition above.
        _run(repo, "git", "cherry-pick", "--quit", check=False)
        _run(repo, "git", "reset", "--hard", "-q", original_head, check=False)
        raise ReleaseError(
            f"{old_commit[:12]} does not replay cleanly on origin/main"
            + (f"; conflicts: {sorted(conflicts)}" if conflicts else "")
        )
    # prepare_release refuses pre-staged paths it does not own, and cherry-pick
    # -n stages everything it touched.
    _run(repo, "git", "reset", "-q", check=False)

    # `prepare_release` 收嘅 state_root 係 **releases 目錄本身**，而
    # approve/reject 收嘅係上一層嘅 control root。傳錯一層唔會報錯 ——
    # manifest 會寫落 `<root>/releases/releases/`，然後 approve 報
    # 「approval selector matched 0 releases」。
    prepared = prepare_release(
        repo,
        paths=scope,
        message=message,
        state_root=state_root / "releases",
        notify=notify,
        allow_unrelated=True,
    )
    if prepared.get("status") == "blocked":
        raise ReleaseError(f"replay gate failed: {prepared.get('error')}")

    new_commit = str(prepared.get("commit") or "")
    rejected = reject_release(
        repo,
        state_root,
        selector=old_commit,
        actor=actor,
        reason=(
            f"superseded: replayed on origin/main {main_sha[:12]} as "
            f"{new_commit[:12]} (the original manifest expired when main advanced)"
        ),
        notify=False,
    )
    events.append(
        release_id=manifest["release_id"],
        commit=old_commit,
        event_type="release_superseded",
        actor=actor,
        detail={"new_commit": new_commit, "new_release_id": prepared.get("release_id"),
                "branch": branch, "origin_main": main_sha},
    )
    return {
        "status": "refreshed",
        "supersedes": manifest["release_id"],
        "old_commit": old_commit,
        "rejected_old": rejected.get("status"),
        "branch": branch,
        "release": prepared,
    }


COMMIT_SELECTOR = re.compile(r"^[0-9a-f]{12,64}$")
