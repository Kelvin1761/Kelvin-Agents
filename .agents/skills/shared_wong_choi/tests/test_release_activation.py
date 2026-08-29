from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT.parent))

from shared_wong_choi.release_activation import (  # noqa: E402
    _rollback_checkout,
    _sync_checkout,
    activate_release,
)
from shared_wong_choi.release_approval import approve_release  # noqa: E402
from shared_wong_choi.release_events import ReleaseEventStore  # noqa: E402
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


def test_unrelated_dirty_production_blocks_when_already_on_candidate(
    release_setup, monkeypatch
) -> None:
    repo, production, state, release = release_setup
    monkeypatch.setattr(
        "shared_wong_choi.release_activation.verify_deployment", _verify
    )
    activated = activate_release(
        repo,
        state,
        selector=release["commit"][:12],
        actor="telegram:kelvin",
        production_roots={"nba": production},
        notify=False,
    )
    assert activated["status"] == "activated"

    # Exercise the sync primitive directly because the immutable successful
    # activation event correctly makes activate_release itself idempotent.
    (production / "README.md").write_text("concurrent write\n", encoding="utf-8")
    with pytest.raises(ReleaseError, match="unrelated dirty"):
        _sync_checkout(production, release["commit"])


def test_post_sync_verifier_failure_rolls_back_production(
    release_setup, monkeypatch
) -> None:
    repo, production, state, release = release_setup
    before = git(production, "rev-parse", "HEAD")

    def reject(_source: Path, target: Path, domain: str) -> dict:
        assert git(target, "rev-parse", "HEAD") == release["commit"]
        return {
            "safe_to_activate": False,
            "status": "different",
            "target_commit": release["commit"],
            "domain": domain,
        }

    monkeypatch.setattr(
        "shared_wong_choi.release_activation.verify_deployment", reject
    )
    with pytest.raises(ReleaseError, match="rollback complete"):
        activate_release(
            repo,
            state,
            selector=release["commit"][:12],
            actor="telegram:kelvin",
            production_roots={"nba": production},
            notify=False,
        )

    assert git(production, "rev-parse", "HEAD") == before
    events = ReleaseEventStore(state / "release-events").list(release["release_id"])
    failure = next(item for item in events if item["event_type"] == "activation_failed")
    assert failure["detail"]["rollback_status"] == "succeeded"
    assert failure["detail"]["rollback"][0]["after"] == before


def test_unexpected_verifier_exception_also_rolls_back(
    release_setup, monkeypatch
) -> None:
    repo, production, state, release = release_setup
    before = git(production, "rev-parse", "HEAD")

    def crash(_source: Path, target: Path, _domain: str) -> dict:
        assert git(target, "rev-parse", "HEAD") == release["commit"]
        raise RuntimeError("verifier crashed")

    monkeypatch.setattr(
        "shared_wong_choi.release_activation.verify_deployment", crash
    )
    with pytest.raises(ReleaseError, match="rollback complete"):
        activate_release(
            repo,
            state,
            selector=release["commit"][:12],
            actor="telegram:kelvin",
            production_roots={"nba": production},
            notify=False,
        )

    assert git(production, "rev-parse", "HEAD") == before
    events = ReleaseEventStore(state / "release-events").list(release["release_id"])
    failure = next(item for item in events if item["event_type"] == "activation_failed")
    assert failure["detail"]["error"] == "RuntimeError: verifier crashed"
    assert failure["detail"]["rollback_status"] == "succeeded"


def test_concurrent_unrelated_write_blocks_rollback_without_erasing_it(
    release_setup, monkeypatch
) -> None:
    repo, production, state, release = release_setup

    def dirty_then_reject(_source: Path, target: Path, domain: str) -> dict:
        (target / "README.md").write_text("concurrent operator write\n", encoding="utf-8")
        return {
            "safe_to_activate": False,
            "status": "different",
            "target_commit": release["commit"],
            "domain": domain,
        }

    monkeypatch.setattr(
        "shared_wong_choi.release_activation.verify_deployment", dirty_then_reject
    )
    with pytest.raises(ReleaseError, match="rollback incomplete"):
        activate_release(
            repo,
            state,
            selector=release["commit"][:12],
            actor="telegram:kelvin",
            production_roots={"nba": production},
            notify=False,
        )

    assert git(production, "rev-parse", "HEAD") == release["commit"]
    assert (production / "README.md").read_text(encoding="utf-8") == (
        "concurrent operator write\n"
    )
    events = ReleaseEventStore(state / "release-events").list(release["release_id"])
    failure = next(item for item in events if item["event_type"] == "activation_failed")
    assert failure["detail"]["rollback_status"] == "blocked"
    assert "unrelated production writes" in failure["detail"]["rollback_errors"][0]


def test_forward_sync_and_rollback_union_runtime_mapping(tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    source = tmp_path / "source"
    production = tmp_path / "production"
    git(tmp_path, "init", "--bare", str(remote))
    git(tmp_path, "clone", str(remote), str(source))
    git(source, "config", "user.name", "Mapping Test")
    git(source, "config", "user.email", "wc@example.test")
    mapping = source / ".agents/skills/au_racing/data/sb_archive_meeting_ids.json"
    mapping.parent.mkdir(parents=True)
    mapping.write_text('{"shared": "base", "base_only": 1}\n', encoding="utf-8")
    merger = source / ".agents/skills/au_racing/au_daily_auto/merge_mapping.py"
    merger.parent.mkdir(parents=True)
    merger.write_text(
        "import json,sys\n"
        "from pathlib import Path\n"
        "local,incoming=map(Path,sys.argv[1:3])\n"
        "a=json.loads(local.read_text()); b=json.loads(incoming.read_text())\n"
        "b.update(a)\n"
        "local.write_text(json.dumps(b))\n",
        encoding="utf-8",
    )
    git(source, "add", ".")
    git(source, "commit", "-m", "base mapping")
    git(source, "branch", "-M", "main")
    git(source, "push", "-u", "origin", "main")
    base = git(source, "rev-parse", "HEAD")
    git(tmp_path, "clone", str(remote), str(production))

    mapping.write_text(
        '{"shared": "candidate", "base_only": 1, "candidate_only": 2}\n',
        encoding="utf-8",
    )
    git(source, "add", str(mapping.relative_to(source)))
    git(source, "commit", "-m", "candidate mapping")
    candidate = git(source, "rev-parse", "HEAD")
    git(source, "push", "origin", "HEAD:main")

    runtime_mapping = production / mapping.relative_to(source)
    runtime_mapping.write_text(
        '{"shared": "runtime", "base_only": 1, "runtime_only": 3}\n',
        encoding="utf-8",
    )
    synced = _sync_checkout(production, candidate)
    assert synced["status"] == "updated"
    assert json.loads(runtime_mapping.read_text(encoding="utf-8")) == {
        "shared": "runtime",
        "base_only": 1,
        "candidate_only": 2,
        "runtime_only": 3,
    }

    rolled_back = _rollback_checkout(production, base)
    assert rolled_back["status"] == "rolled_back"
    assert git(production, "rev-parse", "HEAD") == base
    assert json.loads(runtime_mapping.read_text(encoding="utf-8")) == {
        "shared": "runtime",
        "base_only": 1,
        "candidate_only": 2,
        "runtime_only": 3,
    }
