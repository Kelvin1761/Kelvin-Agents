"""Automatic replay of an expired delegated release (docs/plans/2026-10-21-release-expiry-fast-path.md §4 B+C).

The guarantee that must NOT loosen:
    every commit that lands on main passed the full gate on that exact SHA, on top of the main it lands on.

So these tests check both halves: an expiry with no file overlap now replays and merges by itself,
and everything that used to stop a release (overlap, a failing gate, a non-expiry error, a manual
approval) still stops it.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from test_release_manager import git, repo as repo_fixture
from shared_wong_choi import release_activation, release_approval, release_automation, release_manager
from shared_wong_choi.release_approval import approve_release, pending_releases
from shared_wong_choi.release_manager import ReleaseError, prepare_release

INDEX = "docs/experiments/INDEX.md"


@pytest.fixture
def repo(tmp_path: Path, monkeypatch) -> Path:
    work = repo_fixture.__wrapped__(tmp_path)
    (work / "docs/experiments").mkdir(parents=True)
    (work / INDEX).write_text("# index\n- [EXP-1](a.md)\n", encoding="utf-8")
    config = work / release_automation.CONFIG_PATH
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(json.dumps({"enabled": True, "authorization": "user request"}))
    git(work, "add", INDEX, str(release_automation.CONFIG_PATH))
    git(work, "commit", "-m", "index + delegated approval")
    git(work, "push", "origin", "main")
    monkeypatch.setattr(release_activation, "activate_release",
                        lambda *args, **kwargs: {"status": "activated"})
    return work


def state(repo: Path) -> Path:
    return repo.parent / "state"


def pending_release(repo: Path, monkeypatch, files: dict[str, str]) -> dict:
    """Prepare a delegated release but stop before approval, as if the lock had been busy."""
    for name, text in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    with monkeypatch.context() as m:
        m.setattr(release_manager, "release_automation_config", lambda _repo: {"enabled": False})
        prepared = prepare_release(repo, paths=list(files), message="fix: engine",
                                   state_root=state(repo) / "releases", notify=False)
    assert prepared["status"] == "pushed"
    return prepared


def other_agent_lands(repo: Path, files: dict[str, str], *, attributes: str | None = None) -> str:
    """Another release merges first: main moves under the pending one."""
    other = repo.parent / "other"
    if not other.exists():
        git(repo.parent, "clone", str(repo.parent / "remote.git"), str(other))
        git(other, "config", "user.name", "Other Agent")
        git(other, "config", "user.email", "other@example.test")
    git(other, "pull", "-q", "origin", "main")
    for name, text in files.items():
        path = other / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        git(other, "add", name)
    git(other, "commit", "-m", "other release")
    git(other, "push", "origin", "main")
    return git(other, "rev-parse", "HEAD")


def remote_main(repo: Path) -> str:
    return git(repo.parent / "remote.git", "rev-parse", "main")


def remote_file(repo: Path, name: str) -> str:
    return git(repo.parent / "remote.git", "show", f"main:{name}")


def gated_commits(monkeypatch) -> list[str]:
    seen = []
    real = release_approval._run_gate_in_clean_clone

    def spy(repo, commit, check_name):
        seen.append(commit)
        return real(repo, commit, check_name)

    monkeypatch.setattr(release_approval, "_run_gate_in_clean_clone", spy)
    return seen


def auto(repo: Path, commit: str) -> dict:
    return release_automation.auto_approve_release(repo, state(repo), selector=commit, notify=False)


# ── B: no overlap → replay, gate the NEW sha, merge ─────────────────────────────

def test_disjoint_expiry_replays_gates_the_new_sha_and_merges(repo, monkeypatch):
    prepared = pending_release(repo, monkeypatch, {"engine.py": "VALUE = 1\n"})
    other_agent_lands(repo, {"other.py": "OTHER = 1\n"})
    seen = gated_commits(monkeypatch)
    result = auto(repo, prepared["commit"])
    assert result["automation_status"] == "completed", result.get("error")
    assert result["status"] == "merged"
    assert result["replayed_from"] == [prepared["commit"]]
    assert result["commit"] != prepared["commit"]
    assert remote_main(repo) == result["commit"]
    assert seen == [result["commit"]]                    # the gate ran on exactly what landed
    assert remote_file(repo, "engine.py") == "VALUE = 1"
    assert remote_file(repo, "other.py") == "OTHER = 1"
    assert prepared["commit"] not in {item["commit"] for item in pending_releases(state(repo), repo)}


def test_replay_never_moves_the_callers_checkout(repo, monkeypatch):
    prepared = pending_release(repo, monkeypatch, {"engine.py": "VALUE = 1\n"})
    other_agent_lands(repo, {"other.py": "OTHER = 1\n"})
    head, branch = git(repo, "rev-parse", "HEAD"), git(repo, "branch", "--show-current")
    auto(repo, prepared["commit"])
    assert (git(repo, "rev-parse", "HEAD"), git(repo, "branch", "--show-current")) == (head, branch)
    assert len(git(repo, "worktree", "list").splitlines()) == 1
    assert git(repo, "status", "--porcelain", "--untracked-files=no") == ""


# ── B: everything that stopped a release still stops it ─────────────────────────

def test_overlapping_expiry_still_needs_a_human(repo, monkeypatch):
    prepared = pending_release(repo, monkeypatch, {"engine.py": "VALUE = 1\n"})
    moved = other_agent_lands(repo, {"engine.py": "VALUE = 2\n"})
    result = auto(repo, prepared["commit"])
    assert result["automation_status"] == "blocked"
    assert "approval expired" in result["error"] and "engine.py" in result["error"]
    assert remote_main(repo) == moved
    assert prepared["commit"] in {item["commit"] for item in pending_releases(state(repo), repo)}


def test_gate_failure_on_the_replayed_sha_blocks_the_merge(repo, monkeypatch):
    prepared = pending_release(repo, monkeypatch, {"engine.py": "VALUE = 1\n"})
    moved = other_agent_lands(repo, {"other.py": "OTHER = 1\n"})

    def failed(*_args):
        raise ReleaseError("approval recheck gate failed")

    monkeypatch.setattr(release_approval, "_run_gate_in_clean_clone", failed)
    result = auto(repo, prepared["commit"])
    assert result["automation_status"] == "blocked"
    assert "recheck gate failed" in result["error"]
    assert remote_main(repo) == moved


def test_non_expiry_failure_is_not_replayed(repo, monkeypatch):
    prepared = pending_release(repo, monkeypatch, {"engine.py": "VALUE = 1\n"})
    calls = []
    monkeypatch.setattr(release_automation, "_replay_release",
                        lambda *a, **k: calls.append(a) or "0" * 40)

    def failed(*_args):
        raise ReleaseError("approval recheck gate failed")

    monkeypatch.setattr(release_approval, "_run_gate_in_clean_clone", failed)
    result = auto(repo, prepared["commit"])
    assert result["automation_status"] == "blocked" and calls == []


def test_replays_are_capped(repo, monkeypatch):
    prepared = pending_release(repo, monkeypatch, {"engine.py": "VALUE = 1\n"})
    calls = []
    monkeypatch.setattr(release_automation, "_replay_conflicts", lambda *a, **k: [])
    monkeypatch.setattr(release_automation, "_replay_release",
                        lambda _repo, _state, selector, **_k: calls.append(selector) or prepared["commit"])

    def always_expired(*_args, **_kwargs):
        raise ReleaseError("origin/main changed after release; approval expired")

    monkeypatch.setattr(release_approval, "approve_release", always_expired)
    result = auto(repo, prepared["commit"])
    assert result["automation_status"] == "blocked"
    assert len(calls) == release_automation.MAX_REPLAYS
    assert "replay limit" in result["error"]


def test_manual_approval_is_unchanged(repo, monkeypatch):
    """Only the user-delegated path replays; `approve_release` itself still expires."""
    prepared = pending_release(repo, monkeypatch, {"engine.py": "VALUE = 1\n"})
    other_agent_lands(repo, {"other.py": "OTHER = 1\n"})
    with pytest.raises(ReleaseError, match="approval expired"):
        approve_release(repo, state(repo), selector=prepared["commit"], actor="t", notify=False)


# ── C: docs/experiments/INDEX.md is union-merged ───────────────────────────────

def test_index_overlap_replays_when_index_is_union_merged(repo, monkeypatch):
    other_agent_lands(repo, {".gitattributes": f"{INDEX} merge=union\n"})
    git(repo, "pull", "-q", "origin", "main")
    prepared = pending_release(repo, monkeypatch, {
        "engine.py": "VALUE = 1\n", INDEX: "# index\n- [EXP-1](a.md)\n- [EXP-2](mine.md)\n"})
    other_agent_lands(repo, {INDEX: "# index\n- [EXP-1](a.md)\n- [EXP-3](theirs.md)\n"})
    result = auto(repo, prepared["commit"])
    assert result["automation_status"] == "completed", result.get("error")
    index = remote_file(repo, INDEX)
    assert "EXP-2](mine.md)" in index and "EXP-3](theirs.md)" in index


def test_index_overlap_without_union_attribute_still_blocks(repo, monkeypatch):
    prepared = pending_release(repo, monkeypatch, {
        "engine.py": "VALUE = 1\n", INDEX: "# index\n- [EXP-1](a.md)\n- [EXP-2](mine.md)\n"})
    other_agent_lands(repo, {INDEX: "# index\n- [EXP-1](a.md)\n- [EXP-3](theirs.md)\n"})
    result = auto(repo, prepared["commit"])
    assert result["automation_status"] == "blocked" and INDEX in result["error"]


def test_repo_marks_the_experiment_index_union():
    root = Path(__file__).resolve().parents[4]
    lines = (root / ".gitattributes").read_text(encoding="utf-8").splitlines()
    assert f"{INDEX} merge=union" in lines
