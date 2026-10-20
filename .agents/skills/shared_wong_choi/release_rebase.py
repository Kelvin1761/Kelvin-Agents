"""Let an expired release follow main when the two cannot interact.

WHY THIS EXISTS
---------------
`approve_release` pins approval to the exact main a release was gated against,
so every merge expires every other pending release. That is correct — a
release is only verified against the tree it will land on — but it serialised
work that never touches the same code: an HKJC release and an NBA release had
to queue behind each other, and each expiry stopped the delegated pipeline
until someone ran `central_wong_choi.py refresh` by hand. On 2026-10-21 all ten
pending releases were expired and none could be approved.

WHAT IT DOES
------------
When approval expires, `rebase_blockers` compares what main changed since the
release's rollback target with what the release changes. Only when they share
no file, no production domain, and neither side touches code without a single
owning domain (shared packages, root scripts, the gate itself) does the
release get replayed — through the existing `refresh_release`, in a throwaway
worktree so no real checkout's HEAD moves.

WHAT IT DOES NOT RELAX
----------------------
The replayed release is a new immutable commit with its own manifest, gated by
`prepare_release` on the combined tree, then re-gated in a clean clone by
`approve_release`, which still requires `origin/main == rollback_target`.
"Disjoint files" is not evidence that the combination works: this repo's most
expensive failures (the package rename, the swallowed PF ImportError) were each
green in isolation. Skipping the combined-tree gate would be the unsafe change.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any, Iterable

from .release_manager import ReleaseError, _git, _run
from .release_policy import _is_docs_or_tests, _normalise, activation_plan

# The two refusals in `approve_release` that mean "main moved", as opposed to a
# failed gate or a bad selector. Anything else must never trigger a replay.
EXPIRY_MARKERS = (
    "origin/main changed after release; approval expired",
    "origin/main changed while approval gate was running",
)

# Each replay costs two full gates; main moving three times inside that window
# means the queue needs a person, not a fourth attempt.
MAX_AUTO_REBASES = 3

DASHBOARD = "dashboard"


def is_expiry(error: BaseException) -> bool:
    return any(marker in str(error) for marker in EXPIRY_MARKERS)


def _ownership(paths: Iterable[str]) -> tuple[set[str], list[str]]:
    """Domains a change set can affect, plus code paths no single domain owns."""
    normalised = [_normalise(path) for path in paths]
    plan = activation_plan(normalised)
    domains = set(plan["production_sync_domains"])
    if plan["dashboard_deploy"]:
        domains.add(DASHBOARD)
    ownerless = []
    for path in normalised:
        if _is_docs_or_tests(path):
            continue
        single = activation_plan([path])
        if not single["production_sync_domains"] and not single["dashboard_deploy"]:
            ownerless.append(path)
    return domains, ownerless


def rebase_blockers(release_paths: Iterable[str], main_paths: Iterable[str]) -> list[str]:
    """Why a release must not follow main automatically; empty means it may.

    Shared packages map to every domain in `activation_plan`, so a shared change
    on either side always collides. Paths that map to no domain at all (root
    scripts, `檢查.sh`, config) are blocked rather than treated as harmless,
    because "nobody owns it" usually means "everybody imports it".
    """
    release_paths = sorted({_normalise(p) for p in release_paths})
    main_paths = sorted({_normalise(p) for p in main_paths})
    if not release_paths:
        return ["release recorded no scope"]
    blockers = []
    overlap = sorted(set(release_paths) & set(main_paths))
    if overlap:
        blockers.append(f"same files changed on main: {overlap}")
    release_domains, release_ownerless = _ownership(release_paths)
    main_domains, main_ownerless = _ownership(main_paths)
    shared = sorted(release_domains & main_domains)
    if shared:
        blockers.append(f"same production domains changed on main: {shared}")
    if release_ownerless:
        blockers.append(f"release touches code with no single owning domain: {release_ownerless}")
    if main_ownerless:
        blockers.append(f"main changed code with no single owning domain: {main_ownerless}")
    return blockers


def main_delta(repo: Path, base: str, head: str = "origin/main") -> list[str]:
    changed = _git(repo, "diff", "--name-only", "-z", f"{base}..{head}")
    return [path for path in changed.split("\0") if path]


def release_paths(manifest: dict[str, Any]) -> list[str]:
    return list(manifest.get("scope") or manifest.get("selected_scope") or [])


def refresh_in_isolated_worktree(
    repo: Path, state_root: Path, *, selector: str, actor: str
) -> dict[str, Any]:
    """Run `refresh_release` without moving the HEAD of any real checkout.

    `refresh_release` checks out a new branch and resets on failure. The
    delegated pipeline runs from whichever checkout invoked `保存.sh`, so doing
    that in place would leave the invoker on a `wc-refresh-*` branch.
    """
    from .release_refresh import refresh_release

    scratch = Path(tempfile.mkdtemp(prefix="wc-release-rebase-"))
    worktree = scratch / "checkout"
    added = _run(repo, "git", "worktree", "add", "--detach", "-q", str(worktree),
                 "origin/main", check=False, timeout=300)
    if added.returncode != 0:
        shutil.rmtree(scratch, ignore_errors=True)
        raise ReleaseError("auto-rebase could not create an isolated worktree")
    try:
        # Data-root markers are untracked; without them the gate inside the
        # worktree would read and write the wrong data root.
        for marker in repo.glob(".wongchoi_*root"):
            shutil.copy2(marker, worktree / marker.name)
        result = refresh_release(worktree, state_root, selector=selector, actor=actor,
                                 notify=False, auto_approve=False)
    finally:
        _run(repo, "git", "worktree", "remove", "--force", str(worktree), check=False)
        shutil.rmtree(scratch, ignore_errors=True)
    branch = result.get("branch")
    if branch:
        # The pushed remote branch is the record; the local ref is scratch.
        _run(repo, "git", "branch", "-D", "-q", branch, check=False)
    return result
