"""A command that has already exited is judged by its exit code, never by the clock."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared_wong_choi import research_runner  # noqa: E402
from shared_wong_choi.research_runner import (  # noqa: E402
    CommandInvocation,
    CommandState,
    SubprocessResearchExecutor,
)


class ExitedBeforeLoop(SubprocessResearchExecutor):
    """Spawn, then wait for the process to finish before the poll loop starts."""

    def _spawn(self, invocation):
        process = super()._spawn(invocation)
        process.wait()
        return process


class JumpingClock:
    """0 at start, then far past any deadline — the loaded-machine case."""

    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return 0.0 if self.calls == 1 else 1_000.0


def _run(tmp_path, monkeypatch, code):
    monkeypatch.setattr(research_runner.time, "monotonic", JumpingClock())
    invocation = CommandInvocation(
        role="test", index=0, argv=(sys.executable, "-c", code), cwd=tmp_path, env={},
        output_dir=tmp_path, metrics_path=tmp_path / "metrics.json",
    )
    return ExitedBeforeLoop(poll_seconds=0.01, terminate_grace=0.1).run(
        invocation, timeout_seconds=10, production_active=lambda: False)


def test_crash_past_deadline_is_failed_not_timed_out(tmp_path, monkeypatch):
    result = _run(tmp_path, monkeypatch, "import sys; sys.exit(3)")
    assert result.state is CommandState.FAILED
    assert result.returncode == 3


def test_success_past_deadline_is_succeeded(tmp_path, monkeypatch):
    result = _run(tmp_path, monkeypatch, "print('done')")
    assert result.state is CommandState.SUCCEEDED
    assert result.returncode == 0
    assert "done" in result.stdout
