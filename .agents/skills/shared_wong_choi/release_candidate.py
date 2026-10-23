"""Freeze and gate an unpublished candidate without touching the caller's index."""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path


def supported(repo: Path) -> bool:
    from .release_manager import _git, _run

    # Preserve git commit's signing and hook behaviour through the legacy path.
    if _git(repo, "config", "--get", "core.hooksPath", check=False):
        return False
    if _git(repo, "config", "--bool", "--get", "commit.gpgSign", check=False) == "true":
        return False
    hooks = Path(_git(repo, "rev-parse", "--git-path", "hooks"))
    if not hooks.is_absolute():
        hooks = repo / hooks
    if hooks.is_dir() and any(p.is_file() and not p.name.endswith(".sample")
                             and os.access(p, os.X_OK) for p in hooks.iterdir()):
        return False
    if (repo / ".venv").exists() and "PYTHON_BIN" not in os.environ:
        return False
    # A detached checkout can still publish a newly named branch after gating.
    return _run(repo, "git", "rev-parse", "--verify", "HEAD", check=False).returncode == 0


def scoped_tree(repo: Path, head: str, selected: tuple[str, ...]) -> str:
    from .release_manager import ReleaseError

    with tempfile.TemporaryDirectory(prefix="wc-release-index-") as raw:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(raw) / "index")}
        def git(*args):
            result = subprocess.run(["git", *args], cwd=repo, env=env, text=True,
                                    capture_output=True, timeout=120)
            if result.returncode:
                raise ReleaseError(f"candidate snapshot failed: {result.stderr.strip()}")
            return result.stdout.strip()
        git("read-tree", head)
        git("add", "--", *selected)
        git("diff", "--cached", "--check")
        return git("write-tree")


def freeze_candidate(repo: Path, head: str, selected: tuple[str, ...], message: str):
    from .release_approval import _run_gate_in_clean_clone
    from .release_manager import ReleaseError, _git

    index = _git(repo, "ls-files", "--stage", "-z")
    branch = _git(repo, "symbolic-ref", "-q", "HEAD", check=False)
    tree = scoped_tree(repo, head, selected)
    # An unreachable object is not a saved/published branch commit. Failed gates
    # leave HEAD and the real index unchanged, just as the old prepare gate did.
    commit = _git(repo, "commit-tree", tree, "-p", head, "-m", message)
    receipt = _run_gate_in_clean_clone(repo, commit, "full")
    if (_git(repo, "rev-parse", "HEAD") != head
            or _git(repo, "symbolic-ref", "-q", "HEAD", check=False) != branch
            or _git(repo, "ls-files", "--stage", "-z") != index
            or scoped_tree(repo, head, selected) != tree):
        raise ReleaseError("candidate source, HEAD or index changed during gate; nothing published")
    return commit, receipt


def publish_candidate(repo: Path, commit: str, head: str, selected: tuple[str, ...]) -> None:
    from .release_manager import ReleaseError, _git

    tree = _git(repo, "rev-parse", f"{commit}^{{tree}}")
    if not supported(repo):
        raise ReleaseError("Git hook, signing or interpreter configuration changed before publication")
    if scoped_tree(repo, head, selected) != tree:
        raise ReleaseError("candidate source changed before publication; nothing published")
    # Compare-and-swap refuses a concurrent HEAD write; only our selected index
    # entries are then aligned, preserving every unrelated working-tree edit.
    branch_ref = _git(repo, "symbolic-ref", "-q", "HEAD")
    _git(repo, "update-ref", "-m", "release: publish gated candidate", branch_ref, commit, head)
    _git(repo, "reset", "-q", commit, "--", *selected)
