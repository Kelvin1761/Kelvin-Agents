from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT.parent))

from shared_wong_choi.release_activation import activate_release  # noqa: E402
from shared_wong_choi.release_approval import approve_release  # noqa: E402
from shared_wong_choi.release_manager import ReleaseError, prepare_release  # noqa: E402


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, text=True, capture_output=True, check=True
    )
    return result.stdout.strip()


@pytest.fixture
def release_setup(tmp_path: Path) -> tuple[Path, Path, Path, dict]:
    remote = tmp_path / "remote.git"
    repo = tmp_path / "repo"
    git(tmp_path, "init", "--bare", str(remote))
    git(tmp_path, "clone", str(remote), str(repo))
    git(repo, "config", "user.name", "Activation Test")
    git(repo, "config", "user.email", "wc@example.test")
    gate = repo / "檢查.sh"
    gate.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    os.chmod(gate, 0o755)
    wrapper = repo / ".agents/skills/nba/nba_daily_auto/run_nba_daily_schedule.sh"
    wrapper.parent.mkdir(parents=True)
    wrapper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    os.chmod(wrapper, 0o755)
    git(repo, "add", ".")
    git(repo, "commit", "-m", "base")
    git(repo, "branch", "-M", "main")
    git(repo, "push", "-u", "origin", "main")
    production = tmp_path / "production"
    git(tmp_path, "clone", str(remote), str(production))

    wrapper.write_text("#!/bin/sh\necho updated\n", encoding="utf-8")
    state = tmp_path / "state"
    release = prepare_release(
        repo,
        paths=[".agents/skills/nba/nba_daily_auto/run_nba_daily_schedule.sh"],
        message="fix: nba wrapper",
        state_root=state / "releases",
        notify=False,
    )
    approve_release(
        repo,
        state,
        selector=release["commit"][:12],
        actor="telegram:kelvin",
        notify=False,
    )
    return repo, production, state, release


def _verify(_repo: Path, target: Path, domain: str) -> dict:
    return {
        "safe_to_activate": True,
        "status": "aligned",
        "target_commit": git(target, "rev-parse", "HEAD"),
        "domain": domain,
    }


def test_activation_fast_forwards_and_verifies_production(
    release_setup, monkeypatch
) -> None:
    repo, production, state, release = release_setup
    verifier_sources = []

    def verify(source: Path, target: Path, domain: str) -> dict:
        verifier_sources.append(source)
        assert source != repo
        assert source != target
        assert git(source, "rev-parse", "HEAD") == release["commit"]
        return _verify(source, target, domain)

    monkeypatch.setattr(
        "shared_wong_choi.release_activation.verify_deployment", verify
    )
    result = activate_release(
        repo,
        state,
        selector=release["commit"][:12],
        actor="telegram:kelvin",
        production_roots={"nba": production},
        notify=False,
    )
    assert result["status"] == "activated"
    assert git(production, "rev-parse", "HEAD") == release["commit"]
    assert result["verification"] == [
        {"domain": "nba", "status": "aligned", "target_commit": release["commit"]}
    ]
    assert len(verifier_sources) == 1


def test_activation_is_idempotent(release_setup, monkeypatch) -> None:
    repo, production, state, release = release_setup
    monkeypatch.setattr(
        "shared_wong_choi.release_activation.verify_deployment", _verify
    )
    first = activate_release(
        repo,
        state,
        selector=release["commit"][:12],
        actor="telegram:kelvin",
        production_roots={"nba": production},
        notify=False,
    )
    second = activate_release(
        repo,
        state,
        selector=release["commit"][:12],
        actor="telegram:kelvin",
        production_roots={"nba": production},
        notify=False,
    )
    assert first["status"] == "activated"
    assert second["status"] == "already_active"


def test_unrelated_dirty_production_blocks_activation(release_setup) -> None:
    repo, production, state, release = release_setup
    (production / "README.md").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(ReleaseError, match="unrelated dirty"):
        activate_release(
            repo,
            state,
            selector=release["commit"][:12],
            actor="telegram:kelvin",
            production_roots={"nba": production},
            notify=False,
        )
