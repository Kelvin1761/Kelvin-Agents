from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT.parent))

from shared_wong_choi.release_approval import approve_release  # noqa: E402
from shared_wong_choi.release_events import ReleaseEventStore, effective_status  # noqa: E402
from shared_wong_choi.release_manager import ReleaseError, prepare_release  # noqa: E402


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, text=True, capture_output=True, check=True
    )
    return result.stdout.strip()


@pytest.fixture
def prepared(tmp_path: Path) -> tuple[Path, Path, dict]:
    remote = tmp_path / "remote.git"
    repo = tmp_path / "repo"
    git(tmp_path, "init", "--bare", str(remote))
    git(tmp_path, "clone", str(remote), str(repo))
    git(repo, "config", "user.name", "Approval Test")
    git(repo, "config", "user.email", "wc@example.test")
    gate = repo / "檢查.sh"
    gate.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    os.chmod(gate, 0o755)
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    git(repo, "add", "README.md", "檢查.sh")
    git(repo, "commit", "-m", "base")
    git(repo, "branch", "-M", "main")
    git(repo, "push", "-u", "origin", "main")
    source = repo / "src" / "engine.py"
    source.parent.mkdir()
    source.write_text("VALUE = 1\n", encoding="utf-8")
    state = tmp_path / "state"
    release = prepare_release(
        repo,
        paths=["src/engine.py"],
        message="feat: engine",
        state_root=state / "releases",
        notify=False,
    )
    return repo, state, release


def test_approval_rechecks_and_fast_forwards_main(prepared) -> None:
    repo, state, release = prepared
    result = approve_release(
        repo,
        state,
        selector=release["commit"][:12],
        actor="telegram:kelvin",
        notify=False,
    )
    assert result["status"] == "merged"
    assert git(repo.parent / "remote.git", "rev-parse", "main") == release["commit"]
    events = ReleaseEventStore(state / "release-events").list(release["release_id"])
    assert [item["event_type"] for item in events] == ["approval_granted", "merged"]
    assert effective_status(release, events)["status"] == "merged"


def test_repeated_approval_is_idempotent(prepared) -> None:
    repo, state, release = prepared
    first = approve_release(
        repo, state, selector=release["commit"][:12], actor="telegram:kelvin", notify=False
    )
    second = approve_release(
        repo, state, selector=release["commit"][:12], actor="telegram:kelvin", notify=False
    )
    assert first["status"] == "merged"
    assert second["status"] == "already_merged"
    assert len(ReleaseEventStore(state / "release-events").list(release["release_id"])) == 2


def test_main_change_expires_approval(prepared) -> None:
    repo, state, release = prepared
    other = repo.parent / "other"
    git(repo.parent, "clone", str(repo.parent / "remote.git"), str(other))
    git(other, "config", "user.name", "Other")
    git(other, "config", "user.email", "other@example.test")
    (other / "other.md").write_text("other\n", encoding="utf-8")
    git(other, "add", "other.md")
    git(other, "commit", "-m", "other")
    git(other, "push", "origin", "HEAD:main")

    with pytest.raises(ReleaseError, match="approval expired"):
        approve_release(
            repo,
            state,
            selector=release["commit"][:12],
            actor="telegram:kelvin",
            notify=False,
        )


def test_selector_is_strict(prepared) -> None:
    repo, state, _release = prepared
    with pytest.raises(ReleaseError, match="lowercase git SHA"):
        approve_release(
            repo,
            state,
            selector="HEAD; rm -rf anything",
            actor="telegram:kelvin",
            notify=False,
        )
