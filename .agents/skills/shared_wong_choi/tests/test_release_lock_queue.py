"""Delegated releases queue for the approval lock instead of failing (plan §4 D).

Before: a second release that found `auto-release.lock` busy failed at once with
"another automatic release is running" and sat pending until someone resumed it by hand.
Now it waits (bounded), says who it is waiting for, and on timeout prints the resume command.
"""
from __future__ import annotations

import fcntl
import json
import threading
import time
from pathlib import Path

import pytest

from test_release_replay import auto, other_agent_lands, pending_release, remote_main, state
from test_release_replay import repo as replay_repo
from shared_wong_choi import release_approval, release_automation
from shared_wong_choi.release_approval import pending_releases


@pytest.fixture
def repo(tmp_path: Path, monkeypatch) -> Path:
    return replay_repo.__wrapped__(tmp_path, monkeypatch)


def hold_lock(state_root: Path, seconds: float, *, holder: dict | None = None) -> threading.Thread:
    """Another release holding the approval lock, from a separate open file (= separate flock)."""
    ready = threading.Event()

    def run():
        path = state_root / "auto-release.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            if holder is not None:
                (state_root / "auto-release.lock.json").write_text(json.dumps(holder))
            ready.set()
            time.sleep(seconds)
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    assert ready.wait(5)
    return thread


@pytest.fixture
def quick_queue(monkeypatch):
    monkeypatch.setattr(release_automation, "LOCK_POLL_SECONDS", 0.05)


def test_busy_lock_is_waited_for_then_the_release_merges(repo, monkeypatch, quick_queue):
    monkeypatch.setattr(release_automation, "LOCK_WAIT_SECONDS", 10)
    prepared = pending_release(repo, monkeypatch, {"engine.py": "VALUE = 1\n"})
    holder = hold_lock(state(repo), 0.6)
    result = auto(repo, prepared["commit"])
    holder.join()
    assert result["automation_status"] == "completed", result.get("error")
    assert remote_main(repo) == result["commit"]
    assert result["lock_waited_seconds"] >= 0.5


def test_main_moving_while_queued_is_replayed(repo, monkeypatch, quick_queue):
    """The common real case: the release we waited for merged first."""
    monkeypatch.setattr(release_automation, "LOCK_WAIT_SECONDS", 10)
    prepared = pending_release(repo, monkeypatch, {"engine.py": "VALUE = 1\n"})
    holder = hold_lock(state(repo), 0.6)
    other_agent_lands(repo, {"other.py": "OTHER = 1\n"})
    result = auto(repo, prepared["commit"])
    holder.join()
    assert result["automation_status"] == "completed", result.get("error")
    assert result["replayed_from"] == [prepared["commit"]]


def test_wait_is_bounded_and_says_who_and_how_to_resume(repo, monkeypatch, quick_queue):
    monkeypatch.setattr(release_automation, "LOCK_WAIT_SECONDS", 0.3)
    prepared = pending_release(repo, monkeypatch, {"engine.py": "VALUE = 1\n"})
    base = remote_main(repo)
    holder = hold_lock(state(repo), 2.0, holder={"commit": "abc123def456", "message": "feat: other",
                                                 "pid": 4242, "acquired_at": "2026-10-21T00:00:00+00:00"})
    result = auto(repo, prepared["commit"])
    holder.join()
    assert result["automation_status"] == "blocked"
    error = result["error"]
    assert "another automatic release is running" in error
    assert "abc123def456" in error and "feat: other" in error
    assert f"auto_approve_release.py --commit {prepared['commit']}" in error
    assert remote_main(repo) == base
    assert prepared["commit"] in {item["commit"] for item in pending_releases(state(repo), repo)}


def test_holder_record_is_written_while_held_and_cleared_after(repo, monkeypatch, quick_queue):
    prepared = pending_release(repo, monkeypatch, {"engine.py": "VALUE = 1\n"})
    record = state(repo) / "auto-release.lock.json"
    seen = {}
    real = release_approval.approve_release

    def spy(*args, **kwargs):
        seen.update(json.loads(record.read_text()))
        return real(*args, **kwargs)

    monkeypatch.setattr(release_approval, "approve_release", spy)
    result = auto(repo, prepared["commit"])
    assert result["automation_status"] == "completed", result.get("error")
    assert seen["commit"] == prepared["commit"] and seen["pid"] > 0 and seen["acquired_at"]
    assert not record.exists()


def test_stale_holder_record_from_a_dead_process_does_not_block(repo, monkeypatch, quick_queue):
    """flock dies with its process; a left-over record must not be mistaken for a live holder."""
    monkeypatch.setattr(release_automation, "LOCK_WAIT_SECONDS", 0.3)
    prepared = pending_release(repo, monkeypatch, {"engine.py": "VALUE = 1\n"})
    record = state(repo) / "auto-release.lock.json"
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps({"commit": "dead", "pid": 999999}))
    result = auto(repo, prepared["commit"])
    assert result["automation_status"] == "completed", result.get("error")
    assert result["lock_waited_seconds"] == 0


def test_default_wait_covers_a_full_gate():
    """The holder may run a full gate (and replays); a wait shorter than one gate just recreates the old failure."""
    assert release_automation.LOCK_WAIT_SECONDS >= 7200
