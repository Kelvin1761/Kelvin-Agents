"""A full clean gate checks exactly the commit published, once, without disk trust."""
from __future__ import annotations

import json
import os
import shlex
import time
from dataclasses import replace
from pathlib import Path

import pytest

from test_release_manager import git, repo as base_repo
from shared_wong_choi import release_activation, release_approval, release_gate
from shared_wong_choi.release_automation import CONFIG_PATH, auto_approve_release
from shared_wong_choi.release_manager import ReleaseError, prepare_release


@pytest.fixture
def repo(tmp_path, monkeypatch):
    repo = base_repo.__wrapped__(tmp_path)
    config = repo / CONFIG_PATH
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps({"enabled": True, "authorization": "user request",
                                  "single_clean_gate": True}))
    log = repo.parent / "gate-calls"
    (repo / "檢查.sh").write_text(
        '#!/bin/sh\nprintf "%s %s\\n" "${1:-full}" "$(git rev-parse HEAD)" >> '
        + shlex.quote(str(log)) + '\nexit 0\n')
    git(repo, "add", str(CONFIG_PATH), "檢查.sh")
    git(repo, "commit", "-m", "enable exact candidate gate")
    git(repo, "push", "origin", "main")
    monkeypatch.setattr(release_activation, "activate_release", lambda *a, **k: {"status": "activated"})
    # Fingerprint behaviour is tested separately; most race tests need no pip scans.
    monkeypatch.setattr(release_gate, "environment_fingerprint", lambda _: "environment-a")
    (repo / "engine.py").write_text("VALUE = 1\n")
    return repo


def save(repo, **kwargs):
    return prepare_release(repo, paths=["engine.py"], message="fix: engine",
                           state_root=repo.parent / "state/releases", notify=False, **kwargs)


def calls(repo):
    return (repo.parent / "gate-calls").read_text().splitlines()


def test_normal_release_runs_full_once_on_exact_published_sha(repo):
    result = save(repo)
    assert result["automation_status"] == "completed", result.get("error")
    assert result["full_gate_reused"] is True
    assert calls(repo) == [f"full {result['commit']}", f"--quick {result['commit']}"]
    assert git(repo, "rev-parse", "HEAD") == result["commit"]
    assert git(repo.parent / "remote.git", "rev-parse", "main") == result["commit"]
    assert git(repo, "status", "--porcelain") == ""
    assert Path(result["gate"]["log"]).is_file()
    assert result["gate"]["commit"] == result["commit"]


def test_failed_gate_leaves_head_and_real_index_untouched(repo):
    base = git(repo, "rev-parse", "HEAD")
    (repo / "檢查.sh").write_text("#!/bin/sh\nexit 1\n")
    # Save both intended paths; pre-staged entries must survive a failed gate.
    git(repo, "add", "engine.py")
    before = git(repo, "ls-files", "--stage")
    with pytest.raises(ReleaseError, match="gate failed"):
        prepare_release(repo, paths=["engine.py", "檢查.sh"], message="bad gate",
                        state_root=repo.parent / "state/releases", notify=False)
    assert git(repo, "rev-parse", "HEAD") == base
    assert git(repo, "ls-files", "--stage") == before
    assert not (repo.parent / "state/releases").exists()


@pytest.mark.parametrize("mutation", ["source", "index", "head"])
def test_concurrent_source_index_or_head_write_blocks_publication(repo, monkeypatch, mutation):
    base = git(repo, "rev-parse", "origin/main")
    real = release_approval._run_gate_in_clean_clone
    def changed(*args):
        receipt = real(*args)
        if mutation == "source":
            (repo / "engine.py").write_text("VALUE = 2\n")
        elif mutation == "index":
            git(repo, "add", "engine.py")
        else:
            git(repo, "commit", "--allow-empty", "-m", "concurrent")
        return receipt
    monkeypatch.setattr(release_approval, "_run_gate_in_clean_clone", changed)
    with pytest.raises(ReleaseError, match="changed during gate"):
        save(repo)
    assert git(repo.parent / "remote.git", "rev-parse", "main") == base
    assert not (repo.parent / "state/releases").exists()


def test_unrelated_dirty_file_is_preserved_and_excluded(repo):
    (repo / "unrelated.py").write_text("do not publish\n")
    result = save(repo, allow_unrelated=True)
    assert result["automation_status"] == "completed"
    assert (repo / "unrelated.py").read_text() == "do not publish\n"
    assert "unrelated.py" not in git(repo, "ls-tree", "--name-only", "HEAD")


def test_resuming_from_manifest_never_reuses_an_on_disk_gate_claim(repo):
    prepared = save(repo, auto_approve=False)
    assert calls(repo) == [f"full {prepared['commit']}"]
    result = auto_approve_release(repo, repo.parent / "state", selector=prepared["commit"], notify=False)
    assert result["automation_status"] == "completed"
    assert result["full_gate_reused"] is False
    assert calls(repo) == [f"full {prepared['commit']}"] * 2


@pytest.mark.parametrize("fault", ["expired", "environment", "sha", "check"])
def test_changed_or_expired_receipt_requires_a_full_recheck(repo, monkeypatch, fault):
    receipts = []
    prepared = save(repo, auto_approve=False, _gate_receipts=receipts)
    receipt = receipts[0]
    if fault == "expired":
        receipt = replace(receipt, finished=receipt.finished - 901)
    elif fault == "environment":
        monkeypatch.setattr(release_gate, "environment_fingerprint", lambda _: "environment-b")
    elif fault == "sha":
        receipt = replace(receipt, commit="0" * 40)
    else:
        receipt = replace(receipt, check="quick")
    result = auto_approve_release(repo, repo.parent / "state", selector=prepared["commit"],
                                  notify=False, gate_receipt=receipt)
    assert result["automation_status"] == "completed", result.get("error")
    assert result["full_gate_reused"] is False
    assert calls(repo) == [f"full {prepared['commit']}"] * 2


def test_checkout_mutation_during_clean_gate_cannot_get_a_receipt(repo):
    (repo / "檢查.sh").write_text('#!/bin/sh\necho "VALUE = 999" > engine.py\nexit 0\n')
    base = git(repo, "rev-parse", "HEAD")
    with pytest.raises(ReleaseError, match="changed its candidate checkout"):
        prepare_release(repo, paths=["engine.py", "檢查.sh"], message="mutating gate",
                        state_root=repo.parent / "state/releases", notify=False)
    assert git(repo, "rev-parse", "HEAD") == base


def test_configured_hooks_keep_normal_git_commit_behaviour(repo):
    hooks = repo.parent / "hooks"
    hooks.mkdir()
    marker = repo.parent / "hook-ran"
    hook = hooks / "pre-commit"
    hook.write_text("#!/bin/sh\ntouch " + shlex.quote(str(marker)) + "\n")
    os.chmod(hook, 0o755)
    git(repo, "config", "core.hooksPath", str(hooks))
    result = save(repo)
    assert result["automation_status"] == "completed"
    assert result["gate"]["single_clean_gate"] is False
    assert marker.exists()


def test_environment_fingerprint_changes_with_environment_and_marker(tmp_path, monkeypatch):
    # Probe actual Python/package metadata once, with controlled environment inputs.
    first = release_gate.environment_fingerprint(tmp_path)
    monkeypatch.setenv("WC_GATE_TEST_ENV", "changed")
    second = release_gate.environment_fingerprint(tmp_path)
    assert second != first
    (tmp_path / ".wongchoi_au_data_root").write_text("/new/data/root")
    assert release_gate.environment_fingerprint(tmp_path) != second


def test_replay_runs_one_new_full_gate_and_never_reuses_old_sha(repo):
    from test_release_replay import other_agent_lands
    prepared = save(repo, auto_approve=False)
    other_agent_lands(repo, {"other.py": "OTHER = 1\n"})
    result = auto_approve_release(repo, repo.parent / "state", selector=prepared["commit"], notify=False)
    assert result["automation_status"] == "completed", result.get("error")
    assert result["commit"] != prepared["commit"]
    assert result["full_gate_reused"] is True
    assert calls(repo) == [f"full {prepared['commit']}", f"full {result['commit']}",
                           f"--quick {result['commit']}"]


def test_gate_output_uses_stderr_and_retains_failure_log(repo, capsys):
    (repo / "檢查.sh").write_text("#!/bin/sh\necho specific-failure\nexit 1\n")
    with pytest.raises(ReleaseError, match="log:"):
        release_gate.run_gate(repo, "full")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "specific-failure" in captured.err
    path = captured.err.split(" · log ", 1)[1].splitlines()[0]
    assert Path(path).read_text() == "specific-failure\n"


def test_timeout_kills_the_gate_process_group(repo, monkeypatch):
    escaped = repo.parent / "escaped-worker"
    (repo / "檢查.sh").write_text(
        "#!/bin/sh\n(sleep .6; touch " + shlex.quote(str(escaped)) + ") &\nwait\n")
    monkeypatch.setattr(release_gate, "GATE_TIMEOUT_SECONDS", .1)
    monkeypatch.setattr(release_gate, "GATE_PROGRESS_SECONDS", .05)
    with pytest.raises(ReleaseError, match="timed out"):
        release_gate.run_gate(repo, "full")
    time.sleep(.7)
    assert not escaped.exists()


def test_remote_namespace_conflict_stops_before_expensive_gate(repo):
    base = git(repo, "rev-parse", "HEAD")
    git(repo, "push", "origin", "HEAD:codex")
    git(repo, "checkout", "-b", "codex/new-release")
    with pytest.raises(ReleaseError, match="remote branch namespace conflict"):
        save(repo)
    assert git(repo, "rev-parse", "HEAD") == base
    assert not (repo.parent / "gate-calls").exists()


def test_environment_change_between_probe_and_quick_gate_forces_full(repo, monkeypatch):
    receipts = []
    prepared = save(repo, auto_approve=False, _gate_receipts=receipts)
    real = release_approval._run_gate_in_clean_clone
    def changed(repo, commit, check):
        if check == "quick":
            monkeypatch.setattr(release_gate, "environment_fingerprint", lambda _: "new-environment")
        return real(repo, commit, check)
    monkeypatch.setattr(release_approval, "_run_gate_in_clean_clone", changed)
    result = auto_approve_release(repo, repo.parent / "state", selector=prepared["commit"],
                                  notify=False, gate_receipt=receipts[0])
    assert result["automation_status"] == "completed"
    assert result["full_gate_reused"] is False
    assert calls(repo) == [f"full {prepared['commit']}", f"--quick {prepared['commit']}",
                           f"full {prepared['commit']}"]


def test_prepare_result_uses_the_replayed_manifest_and_gate(repo, monkeypatch):
    from shared_wong_choi import release_candidate
    from test_release_replay import other_agent_lands
    freeze = release_candidate.freeze_candidate
    moved = []
    def move_after_first_gate(*args):
        result = freeze(*args)
        if not moved:
            moved.append(other_agent_lands(repo, {"other.py": "OTHER = 1\n"}))
        return result
    monkeypatch.setattr(release_candidate, "freeze_candidate", move_after_first_gate)
    result = save(repo)
    assert result["automation_status"] == "completed", result.get("error")
    assert result["replayed_from"]
    manifest = json.loads(Path(result["manifest"]).read_text())
    for key in ("commit", "release_id", "branch", "created_at", "rollback_target",
                "activation_base", "scope", "activation_scope", "gate"):
        assert result[key] == manifest[key], key
    assert result["gate"]["commit"] == result["commit"]
    assert result["rollback_target"] == moved[0]
