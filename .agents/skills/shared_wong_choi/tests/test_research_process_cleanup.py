"""A permission error is never proof that an owned process group is gone."""
from __future__ import annotations

import errno
from pathlib import Path
import signal
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared_wong_choi import research_runner as runner


@pytest.mark.parametrize('probes', [[], ['denied'], ['present'], ['denied', 'present']])
def test_cleanup_accepts_only_observed_disappearance_after_permission_race(monkeypatch, probes):
    denied = PermissionError(errno.EPERM, 'fixture permission race')
    calls, sleeps = [], []
    results = iter(probes)
    def killpg(pid, sig):
        calls.append((pid, sig))
        if sig == signal.SIGKILL:
            raise denied
        assert sig == 0, 'no repeat/alternative killing after permission failure'
        result = next(results, 'gone')
        if result == 'denied':
            raise denied
        if result == 'gone':
            raise ProcessLookupError(errno.ESRCH, 'fixture group disappeared')
    monkeypatch.setattr(runner.os, 'killpg', killpg)
    monkeypatch.setattr(runner.time, 'sleep', sleeps.append)
    runner.SubprocessResearchExecutor(terminate_grace=.1)._cleanup_group(
        SimpleNamespace(pid=123456, poll=lambda: 0))
    assert calls == [(123456, signal.SIGKILL)] + [(123456, 0)] * (len(probes) + 1)
    assert sum(sleeps) <= .1


@pytest.mark.parametrize('probe_state', ['denied', 'present'])
def test_persistent_or_unverifiable_group_still_fails_closed(monkeypatch, probe_state):
    denied = PermissionError(errno.EPERM, 'fixture genuine denial')
    calls, sleeps = [], []
    def killpg(pid, sig):
        calls.append(sig)
        if sig == signal.SIGKILL or probe_state == 'denied':
            raise denied
        assert sig == 0
    monkeypatch.setattr(runner.os, 'killpg', killpg)
    monkeypatch.setattr(runner.time, 'sleep', sleeps.append)
    with pytest.raises(PermissionError) as error:
        runner.SubprocessResearchExecutor(terminate_grace=5)._cleanup_group(
            SimpleNamespace(pid=123456, poll=lambda: 0))
    assert error.value is denied
    assert 1 < len(calls) <= 26 and calls.count(signal.SIGKILL) == 1
    assert sum(sleeps) <= .25


def test_permission_denial_while_leader_alive_is_not_downgraded(monkeypatch):
    denied = PermissionError(errno.EPERM, 'fixture live leader')
    calls = []
    def killpg(pid, sig):
        calls.append(sig)
        raise denied
    monkeypatch.setattr(runner.os, 'killpg', killpg)
    with pytest.raises(PermissionError) as error:
        runner.SubprocessResearchExecutor()._cleanup_group(SimpleNamespace(pid=123456, poll=lambda: None))
    assert error.value is denied and calls == [signal.SIGKILL]


@pytest.mark.parametrize('missing', [False, True])
def test_normal_cleanup_does_not_add_probes(monkeypatch, missing):
    calls = []
    def killpg(pid, sig):
        calls.append(sig)
        if missing:
            raise ProcessLookupError(errno.ESRCH, 'fixture already absent')
    monkeypatch.setattr(runner.os, 'killpg', killpg)
    runner.SubprocessResearchExecutor()._cleanup_group(SimpleNamespace(pid=123456, poll=lambda: 0))
    assert calls == [signal.SIGKILL]


def test_concurrent_observers_do_not_impersonate_exclusive_production_owner(tmp_path, monkeypatch):
    import fcntl
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from shared_wong_choi.control import single_run_lock
    from shared_wong_choi.research_registry import ExperimentRegistry
    from test_research_supervision import source_runtime
    runtime = source_runtime(tmp_path)
    lock = runtime.production_lock_paths[0]
    lock.touch()
    instance = runner.ResearchRunner(runtime, ExperimentRegistry(tmp_path / 'registry'))
    entered, release = threading.Event(), threading.Event()
    original = fcntl.flock
    parent = threading.current_thread()
    def paused_probe(fd, operation):
        value = original(fd, operation)
        if operation & fcntl.LOCK_NB and threading.current_thread() is not parent:
            entered.set()
            assert release.wait(5)
        return value
    monkeypatch.setattr(fcntl, 'flock', paused_probe)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(instance._production_active)
        try:
            assert entered.wait(5)
            assert instance._production_active() is False, 'another observer is not a production job'
        finally:
            release.set()
        assert first.result(timeout=5) is False
    # The actual controller owns these files EXCLUSIVELY. Its activity must
    # continue to stop every observer; no production writer is modified.
    with single_run_lock(lock) as acquired:
        assert acquired and instance._production_active() is True
