from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT.parent))

from shared_wong_choi.release_manager import (  # noqa: E402
    ReleaseError,
    changed_paths,
    git_status,
    prepare_release,
)


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=repo, text=True, capture_output=True, check=True
    )
    return completed.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    git(tmp_path, "init", "--bare", str(remote))
    git(tmp_path, "clone", str(remote), str(work))
    git(work, "config", "user.name", "Wong Choi Test")
    git(work, "config", "user.email", "wc@example.test")
    (work / "README.md").write_text("base\n", encoding="utf-8")
    gate = work / "檢查.sh"
    gate.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    os.chmod(gate, 0o755)
    git(work, "add", "README.md", "檢查.sh")
    git(work, "commit", "-m", "base")
    git(work, "branch", "-M", "main")
    git(work, "push", "-u", "origin", "main")
    return work


def test_status_distinguishes_dirty_committed_pushed_and_merged(repo: Path) -> None:
    clean = git_status(repo)
    assert clean.dirty_paths == ()
    assert clean.pushed is True
    assert clean.merged_to_main is True

    (repo / "README.md").write_text("changed\n", encoding="utf-8")
    assert changed_paths(repo) == ("README.md",)
    dirty = git_status(repo)
    assert dirty.dirty_paths == ("README.md",)


def test_dry_run_classifies_scope_without_mutating(repo: Path) -> None:
    docs = repo / "docs"
    docs.mkdir()
    (docs / "plan.md").write_text("plan\n", encoding="utf-8")
    result = prepare_release(
        repo,
        paths=["docs/plan.md"],
        message="docs: plan",
        state_root=repo / "state",
        dry_run=True,
        notify=False,
    )
    assert result["status"] == "dry_run"
    assert result["policy"]["risk"] == "docs_tests"
    assert git(repo, "rev-parse", "--abbrev-ref", "HEAD") == "main"
    assert not (repo / "state").exists()


def test_scope_preserves_dot_prefixed_agents_directory(repo: Path) -> None:
    source = repo / ".agents" / "skills" / "central" / "main.py"
    source.parent.mkdir(parents=True)
    source.write_text("print('central')\n", encoding="utf-8")

    result = prepare_release(
        repo,
        paths=[".agents/skills/central/main.py"],
        message="feat: central",
        state_root=repo / "state",
        dry_run=True,
        notify=False,
    )

    assert result["scope"] == [".agents/skills/central/main.py"]
    assert result["policy"]["risk"] == "code"


def test_unrelated_or_pre_staged_changes_block_release(repo: Path) -> None:
    (repo / "one.md").write_text("one\n", encoding="utf-8")
    (repo / "two.md").write_text("two\n", encoding="utf-8")
    with pytest.raises(ReleaseError, match="unrelated changes"):
        prepare_release(
            repo,
            paths=["one.md"],
            message="docs: one",
            dry_run=True,
            notify=False,
        )
    git(repo, "add", "two.md")
    with pytest.raises(ReleaseError, match="staged paths outside"):
        prepare_release(
            repo,
            paths=["one.md"],
            message="docs: one",
            dry_run=True,
            notify=False,
            allow_unrelated=True,
        )


def test_docs_release_commits_pushes_and_fast_forwards_main(repo: Path) -> None:
    docs = repo / "docs"
    docs.mkdir()
    (docs / "stage4.md").write_text("stage four\n", encoding="utf-8")
    state_root = repo.parent / "state"

    result = prepare_release(
        repo,
        paths=["docs/stage4.md"],
        message="docs: add stage four",
        state_root=state_root,
        notify=False,
    )

    assert result["status"] == "merged"
    assert result["activation"] == "not_started"
    assert result["telegram"]["status"] == "skipped"
    assert Path(result["manifest"]).is_file()
    assert git(repo, "status", "--porcelain") == ""
    assert git(repo, "rev-parse", "HEAD") == result["commit"]
    assert git(repo.parent / "remote.git", "rev-parse", "main") == result["commit"]


def test_code_release_pushes_branch_but_requires_approval_for_main(repo: Path) -> None:
    source = repo / "src" / "engine.py"
    source.parent.mkdir()
    source.write_text("VALUE = 1\n", encoding="utf-8")
    base = git(repo, "rev-parse", "origin/main")

    result = prepare_release(
        repo,
        paths=["src/engine.py"],
        message="feat: add engine",
        state_root=repo.parent / "state",
        notify=False,
    )

    assert result["status"] == "pushed"
    assert result["policy"]["risk"] == "code"
    assert result["policy"]["auto_merge"] is False
    assert result["rollback_target"] == base
    assert result["selected_scope"] == ["src/engine.py"]
    assert result["activation_base"] == base
    assert git(repo.parent / "remote.git", "rev-parse", "main") == base
    assert git(repo.parent / "remote.git", "rev-parse", result["branch"]) == result["commit"]


def test_stacked_history_is_in_full_scope_and_uses_origin_main_rollback(
    repo: Path,
) -> None:
    git(repo, "checkout", "-b", "stacked")
    source = repo / "src" / "engine.py"
    source.parent.mkdir()
    source.write_text("VALUE = 1\n", encoding="utf-8")
    git(repo, "add", "src/engine.py")
    git(repo, "commit", "-m", "feat: stacked code")
    docs = repo / "docs" / "release.md"
    docs.parent.mkdir()
    docs.write_text("release\n", encoding="utf-8")
    base = git(repo, "rev-parse", "origin/main")

    result = prepare_release(
        repo,
        paths=["docs/release.md"],
        message="docs: describe stacked release",
        state_root=repo.parent / "state",
        notify=False,
    )

    assert result["rollback_target"] == base
    assert result["selected_scope"] == ["docs/release.md"]
    assert set(result["scope"]) == {"src/engine.py", "docs/release.md"}
    assert result["policy"]["risk"] == "code"
    assert result["status"] == "pushed"


def test_activation_base_excludes_already_deployed_manual_installer(repo: Path) -> None:
    git(repo, "checkout", "-b", "deployed-stack")
    installer = repo / "ops" / "install_macos_launchd.sh"
    installer.parent.mkdir()
    installer.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    git(repo, "add", str(installer.relative_to(repo)))
    git(repo, "commit", "-m", "ops: already deployed installer")
    deployed = git(repo, "rev-parse", "HEAD")
    source = repo / "src" / "next.py"
    source.parent.mkdir(exist_ok=True)
    source.write_text("VALUE = 2\n", encoding="utf-8")

    result = prepare_release(
        repo,
        paths=["src/next.py"],
        message="feat: next release",
        state_root=repo.parent / "state",
        dry_run=True,
        notify=False,
        activation_base=deployed,
    )

    assert "ops/install_macos_launchd.sh" in result["scope"]
    assert "ops/install_macos_launchd.sh" not in result["activation_scope"]
    assert result["activation_plan"]["manual_required"] is False
