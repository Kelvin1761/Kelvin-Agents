"""Bare /approve resolution and explicit rejection.

`approval_rejected` existed in the event schema from the start but nothing ever
emitted it, so a release Kelvin did not want stayed "pending" forever and kept
`release_pending_approval` in Central's attention list. These tests pin the two
halves of the fix: resolving an empty selector, and recording a rejection
without touching main.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT.parent))

from shared_wong_choi.release_approval import (  # noqa: E402
    approve_release,
    pending_releases,
    reject_release,
    resolve_pending_selector,
)
from shared_wong_choi.release_events import ReleaseEventStore, effective_status  # noqa: E402
from shared_wong_choi.release_manager import ReleaseError, prepare_release  # noqa: E402


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, text=True, capture_output=True, check=True
    )
    return result.stdout.strip()


def _repo(tmp_path: Path, slot: str = "a") -> tuple[Path, Path]:
    """One checkout plus the shared control state root.

    ``slot`` gives a second, independent checkout that pushes to its own
    remote but records into the same state root — the real shape when two
    agent worktrees each prepare a release.
    """
    remote = tmp_path / f"remote-{slot}.git"
    repo = tmp_path / f"repo-{slot}"
    git(tmp_path, "init", "--bare", str(remote))
    git(tmp_path, "clone", str(remote), str(repo))
    git(repo, "config", "user.name", "Rejection Test")
    git(repo, "config", "user.email", "wc@example.test")
    gate = repo / "檢查.sh"
    gate.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    os.chmod(gate, 0o755)
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    git(repo, "add", "README.md", "檢查.sh")
    git(repo, "commit", "-m", "base")
    git(repo, "branch", "-M", "main")
    git(repo, "push", "-u", "origin", "main")
    return repo, tmp_path / "state"


def _release(repo: Path, state: Path, name: str) -> dict:
    source = repo / "src" / f"{name}.py"
    source.parent.mkdir(exist_ok=True)
    source.write_text("VALUE = 1\n", encoding="utf-8")
    return prepare_release(
        repo,
        paths=[f"src/{name}.py"],
        message=f"feat: {name}",
        state_root=state / "releases",
        notify=False,
        allow_unrelated=True,
    )


def test_bare_selector_resolves_the_single_pending_release(tmp_path: Path) -> None:
    repo, state = _repo(tmp_path)
    release = _release(repo, state, "engine")
    assert resolve_pending_selector(state, "") == release["commit"]
    assert resolve_pending_selector(state, release["commit"][:12]) == release["commit"][:12]


def test_bare_selector_refuses_to_guess_between_two_pending(tmp_path: Path) -> None:
    repo_a, state = _repo(tmp_path, "a")
    repo_b, _ = _repo(tmp_path, "b")
    first = _release(repo_a, state, "engine")
    second = _release(repo_b, state, "mapper")
    assert {item["commit"] for item in pending_releases(state)} == {
        first["commit"],
        second["commit"],
    }
    with pytest.raises(ReleaseError) as excinfo:
        resolve_pending_selector(state, "")
    # Both candidates must be named: an operator on a phone cannot look them up.
    assert first["commit"][:12] in str(excinfo.value)
    assert second["commit"][:12] in str(excinfo.value)


def test_bare_selector_refuses_when_nothing_is_pending(tmp_path: Path) -> None:
    _repo(tmp_path)
    with pytest.raises(ReleaseError, match="no release is waiting"):
        resolve_pending_selector(tmp_path / "state", "")


def test_rejection_records_an_event_and_leaves_main_alone(tmp_path: Path) -> None:
    repo, state = _repo(tmp_path)
    before_main = git(repo, "rev-parse", "origin/main")
    release = _release(repo, state, "engine")
    result = reject_release(
        repo, state, selector=release["commit"], actor="test", reason="dev 回歸", notify=False
    )
    assert result["status"] == "rejected"
    git(repo, "fetch", "origin")
    assert git(repo, "rev-parse", "origin/main") == before_main
    # The commit and its branch survive; rejection is a decision, not a delete.
    assert git(repo, "rev-parse", f"origin/{release['branch']}") == release["commit"]
    events = ReleaseEventStore(state / "release-events").list(release["release_id"])
    rejected = [e for e in events if e["event_type"] == "approval_rejected"]
    assert len(rejected) == 1
    assert rejected[0]["detail"]["reason"] == "dev 回歸"
    assert effective_status(
        {"status": "pushed", "activation": "not_started"}, events
    )["status"] == "rejected"


def test_rejected_release_stops_being_pending(tmp_path: Path) -> None:
    repo_a, state = _repo(tmp_path, "a")
    repo_b, _ = _repo(tmp_path, "b")
    first = _release(repo_a, state, "engine")
    second = _release(repo_b, state, "mapper")
    reject_release(repo_a, state, selector=first["commit"], actor="test", notify=False)
    assert [item["commit"] for item in pending_releases(state)] == [second["commit"]]
    # With one left, the bare selector becomes unambiguous again.
    assert resolve_pending_selector(state, "") == second["commit"]


def test_rejecting_twice_is_a_no_op(tmp_path: Path) -> None:
    repo, state = _repo(tmp_path)
    release = _release(repo, state, "engine")
    reject_release(repo, state, selector=release["commit"], actor="test", notify=False)
    again = reject_release(
        repo, state, selector=release["commit"], actor="test", notify=False
    )
    assert again["status"] == "already_rejected"
    events = ReleaseEventStore(state / "release-events").list(release["release_id"])
    assert sum(1 for e in events if e["event_type"] == "approval_rejected") == 1


def test_merged_release_cannot_be_rejected(tmp_path: Path) -> None:
    repo, state = _repo(tmp_path)
    release = _release(repo, state, "engine")
    approve_release(
        repo, state, selector=release["commit"], actor="test", notify=False
    )
    with pytest.raises(ReleaseError, match="already merged"):
        reject_release(repo, state, selector=release["commit"], actor="test", notify=False)


def test_release_already_in_main_stops_blocking_a_bare_approve(tmp_path: Path) -> None:
    """A release merged out-of-band must not hold the bare selector hostage.

    Observed on 2026-09-03: a 2026-09-02 manifest sat at ``pushed`` while its
    commit was already an ancestor of origin/main, so Central reported two
    pending releases for ever and ``/approve`` with no SHA could never resolve.
    """
    repo_a, state = _repo(tmp_path, "a")
    repo_b, _ = _repo(tmp_path, "b")
    stale = _release(repo_a, state, "engine")
    live = _release(repo_b, state, "mapper")
    # Merge the first one without recording an approval event, exactly as the
    # real gap happened.
    git(repo_a, "push", "origin", f"{stale['commit']}:main")
    git(repo_a, "fetch", "origin")

    without_repo = {item["commit"] for item in pending_releases(state)}
    assert without_repo == {stale["commit"], live["commit"]}

    with_repo = {item["commit"] for item in pending_releases(state, repo_a)}
    assert with_repo == {live["commit"]}
    assert resolve_pending_selector(state, "", repo_a) == live["commit"]


def test_a_release_that_reached_main_is_never_recorded_as_rejected(tmp_path: Path) -> None:
    """Its code is live; calling it "rejected" would be a false record."""
    repo, state = _repo(tmp_path)
    release = _release(repo, state, "engine")
    git(repo, "push", "origin", f"{release['commit']}:main")
    git(repo, "fetch", "origin")
    assert pending_releases(state, repo) == []
    with pytest.raises(ReleaseError, match="no release is waiting"):
        resolve_pending_selector(state, "", repo)
