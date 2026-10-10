from __future__ import annotations

import json
from pathlib import Path

import pytest

from test_release_manager import git, repo as repo_fixture
from shared_wong_choi import release_activation, release_approval, release_automation
from shared_wong_choi.release_events import ReleaseEventStore
from shared_wong_choi.release_manager import ReleaseError, prepare_release


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return repo_fixture.__wrapped__(tmp_path)


def enable(repo: Path) -> None:
    path = repo / release_automation.CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"enabled": True, "authorization": "user request"}))
    git(repo, "add", str(release_automation.CONFIG_PATH))
    git(repo, "commit", "-m", "enable delegated approval")
    git(repo, "push", "origin", "main")


def release(repo: Path, *, notify: bool = False) -> dict:
    (repo / "engine.py").write_text("VALUE = 1\n")
    return prepare_release(
        repo, paths=["engine.py"], message="fix: engine",
        expected_results=["Avoid missing runner history"],
        state_root=repo.parent / "state" / "releases", notify=notify,
    )


def test_delegated_release_merges_exact_commit_and_activates(repo, monkeypatch):
    enable(repo)
    calls = []
    monkeypatch.setattr(release_activation, "activate_release",
                        lambda *args, **kwargs: calls.append(kwargs) or {"status": "activated"})
    result = release(repo)
    assert result["status"] == "merged"
    assert result["automation_status"] == "completed"
    assert result["activation"] == "succeeded"
    assert git(repo.parent / "remote.git", "rev-parse", "main") == result["commit"]
    assert calls[0]["selector"] == result["commit"]
    events = ReleaseEventStore(repo.parent / "state" / "release-events").list(result["release_id"])
    approval = next(e for e in events if e["event_type"] == "approval_granted")
    assert approval["actor"] == "user-delegated:auto-release"
    assert approval["detail"]["authorization"] == "user request"
    manifest = json.loads(Path(result["manifest"]).read_text())
    assert manifest["status"] == "pushed"
    assert manifest["expected_results"] == ["Avoid missing runner history"]


def test_clean_commit_recheck_failure_blocks_automatic_merge(repo, monkeypatch):
    enable(repo)
    base = git(repo, "rev-parse", "origin/main")
    def failed(*args):
        raise ReleaseError("approval recheck gate failed")
    monkeypatch.setattr(release_approval, "_run_gate_in_clean_clone", failed)
    result = release(repo)
    assert result["automation_status"] == "blocked"
    assert "recheck gate failed" in result["error"]
    assert git(repo.parent / "remote.git", "rev-parse", "main") == base


def test_activation_failure_reports_merged_but_incomplete(repo, monkeypatch):
    enable(repo)
    def failed(*args, **kwargs):
        raise ReleaseError("activation failed; rollback complete")
    monkeypatch.setattr(release_activation, "activate_release", failed)
    result = release(repo)
    assert result["status"] == "merged"
    assert result["automation_status"] == "blocked"
    assert result["activation"] != "succeeded"
    assert "rollback complete" in result["error"]


def test_missing_production_roots_blocks_before_merge(repo, monkeypatch):
    enable(repo)
    base = git(repo, "rev-parse", "origin/main")
    source = repo / ".agents/skills/nba/engine.py"
    source.parent.mkdir(parents=True)
    source.write_text("VALUE = 1\n")
    monkeypatch.setattr(release_automation, "production_roots", lambda: {})
    result = prepare_release(repo, paths=[str(source.relative_to(repo))], message="fix: nba",
                             state_root=repo.parent / "state/releases", notify=False)
    assert result["automation_status"] == "blocked"
    assert "nba" in result["error"]
    assert git(repo.parent / "remote.git", "rev-parse", "main") == base


def test_invalid_automation_config_cannot_silently_enable(repo):
    path = repo / release_automation.CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"enabled": "false"}')
    with pytest.raises(ReleaseError, match="boolean"):
        release_automation.release_automation_config(repo)
    path.write_text('{"enabled": true}')
    with pytest.raises(ReleaseError, match="authorization"):
        release_automation.release_automation_config(repo)


def test_telegram_reports_expected_results_and_outcome(repo, monkeypatch):
    from shared_wong_choi import release_manager
    enable(repo)
    messages = []
    monkeypatch.setattr(release_manager, "_notify",
                        lambda repo, message, **kwargs: messages.append(message) or {"ok": True})
    monkeypatch.setattr(release_activation, "activate_release", lambda *a, **k: {"status": "activated"})
    result = release(repo, notify=True)
    assert len(messages) == 2
    assert all("Avoid missing runner history" in m for m in messages)
    assert "/approve" not in "\n".join(messages)
    assert "succeeded" in messages[-1]
    assert result["telegram"]["ok"]


def test_disabling_setting_restores_manual_approval(repo):
    enable(repo)
    path = repo / release_automation.CONFIG_PATH
    path.write_text('{"enabled": false}')
    git(repo, "add", str(release_automation.CONFIG_PATH))
    git(repo, "commit", "-m", "restore manual approval")
    git(repo, "push", "origin", "main")
    base = git(repo, "rev-parse", "origin/main")
    result = release(repo)
    assert result["status"] == "pushed"
    assert result["approval_mode"] == "telegram"
    assert git(repo.parent / "remote.git", "rev-parse", "main") == base


def test_roots_are_derived_from_installed_scripts_without_working_directory(monkeypatch):
    monkeypatch.setattr(release_automation, "DOMAIN_LABELS", {"nba": {"job": ("nba/run.sh",)}})
    monkeypatch.delenv("WC_NBA_PRODUCTION_ROOT", raising=False)
    monkeypatch.setattr(release_automation, "_load_plist", lambda path: (
        {"ProgramArguments": ["/bin/zsh", "/tmp/runtime/nba/run.sh"]}, None))
    assert release_automation.production_roots() == {"nba": Path("/tmp/runtime").resolve()}


def test_conflicting_installed_roots_are_not_guessed(monkeypatch):
    monkeypatch.setattr(release_automation, "DOMAIN_LABELS", {
        "nba": {"one": ("nba/run.sh",), "two": ("nba/run.sh",)}})
    monkeypatch.delenv("WC_NBA_PRODUCTION_ROOT", raising=False)
    monkeypatch.setattr(release_automation, "_load_plist", lambda path: (
        {"ProgramArguments": [f"/tmp/{path.stem}/nba/run.sh"]}, None))
    assert release_automation.production_roots() == {}


def test_generated_hkjc_cache_survives_sync_and_rollback(repo):
    cache = Path(".agents/scripts/hkjc_draw_stats.json")
    (repo / cache).parent.mkdir(parents=True)
    (repo / cache).write_text('{"meeting": "baseline"}')
    git(repo, "add", str(cache))
    git(repo, "commit", "-m", "base draw cache")
    git(repo, "push", "origin", "main")
    base = git(repo, "rev-parse", "HEAD")
    production = repo.parent / "production"
    git(repo.parent, "clone", str(repo.parent / "remote.git"), str(production))
    runtime = '{"meeting": "current", "draw": [1, 2, 3]}'
    (production / cache).write_text(runtime)
    (repo / cache).write_text('{"meeting": "candidate"}')
    git(repo, "add", str(cache))
    git(repo, "commit", "-m", "next version")
    git(repo, "push", "origin", "main")
    commit = git(repo, "rev-parse", "HEAD")
    release_activation._sync_checkout(production, commit)
    assert (production / cache).read_text() == runtime
    release_activation._rollback_checkout(production, base)
    assert (production / cache).read_text() == runtime
