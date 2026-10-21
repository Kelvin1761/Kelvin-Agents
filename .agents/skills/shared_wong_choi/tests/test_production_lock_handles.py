import copy
import fcntl
import os
from dataclasses import asdict

import pytest

from shared_wong_choi.research_runner import ResearchRuntime, ResearchRunner
from shared_wong_choi.research_registry import ExperimentRegistry


def fixture(tmp_path, count=4):
    paths = tuple(tmp_path / f"production-{i}.lock" for i in range(count))
    for path in paths:
        path.touch()
    runtime = ResearchRuntime(state_root=tmp_path, warm_root=tmp_path,
                              production_lock_paths=paths)
    return runtime, ResearchRunner(runtime, ExperimentRegistry(tmp_path / 'registry')), paths


def test_handles_are_reused_but_every_call_still_probes_all_locks(tmp_path, monkeypatch):
    runtime, runner, paths = fixture(tmp_path)
    opened, probes = [], []
    original_open, original_flock = os.open, fcntl.flock
    def open_file(path, flags, *args, **kwargs):
        opened.append(path)
        return original_open(path, flags, *args, **kwargs)
    def flock(fd, flags):
        probes.append(flags)
        return original_flock(fd, flags)
    monkeypatch.setattr(os, 'open', open_file)
    monkeypatch.setattr(fcntl, 'flock', flock)
    for _ in range(6):
        assert runner._production_active() is False
    assert opened == list(paths)
    assert probes == [fcntl.LOCK_SH | fcntl.LOCK_NB, fcntl.LOCK_UN] * 24
    # Observers leave no shared lock behind between probes.
    for path in paths:
        with path.open('a') as owner:
            original_flock(owner.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            assert runner._production_active() is True
            original_flock(owner.fileno(), fcntl.LOCK_UN)
    assert runner._production_active() is False
    runtime._production_lock_handles.close()
    assert runtime._production_lock_handles.handles == {}


@pytest.mark.parametrize('removed', [False, True])
def test_replaced_or_deleted_path_cannot_hide_existing_writer(tmp_path, removed):
    runtime, runner, paths = fixture(tmp_path, 1)
    path = paths[0]
    assert runner._production_active() is False
    with path.open('a') as owner:
        fcntl.flock(owner.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        path.rename(tmp_path / 'old.lock')
        if not removed:
            path.touch()
        assert runner._production_active() is True
        fcntl.flock(owner.fileno(), fcntl.LOCK_UN)
    if not removed:
        # A namespace change itself interrupts once before a fresh probe.
        assert runner._production_active() is True
    assert runner._production_active() is False
    runtime._production_lock_handles.close()


def test_permission_loss_is_rechecked_after_handle_was_cached(tmp_path, monkeypatch):
    runtime, runner, paths = fixture(tmp_path, 1)
    assert runner._production_active() is False
    monkeypatch.setattr(os, 'access', lambda *_args, **_kwargs: False)
    assert runner._production_active() is True
    runtime._production_lock_handles.close()


def test_symlink_replacement_is_not_certified_by_old_handle(tmp_path):
    runtime, runner, paths = fixture(tmp_path, 1)
    assert runner._production_active() is False
    paths[0].rename(tmp_path / 'old.lock')
    paths[0].symlink_to(tmp_path / 'old.lock')
    assert runner._production_active() is True
    runtime._production_lock_handles.close()


def test_cache_is_bounded_without_omitting_uncached_lock_paths(tmp_path):
    runtime, runner, paths = fixture(tmp_path, 20)
    assert runner._production_active() is False
    assert len(runtime._production_lock_handles.handles) == 16
    with paths[-1].open('a') as owner:
        fcntl.flock(owner.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert runner._production_active() is True
    assert runner._production_active() is False
    runtime._production_lock_handles.close()


def test_copy_gets_fresh_handles_and_runtime_serialization_has_no_cached_fds(tmp_path):
    runtime, runner, paths = fixture(tmp_path, 1)
    assert runner._production_active() is False
    assert '_production_lock_handles' not in asdict(runtime)
    shallow = copy.copy(runtime)
    assert shallow._production_lock_handles.handles == {}
    duplicate = copy.deepcopy(runtime)
    assert duplicate._production_lock_handles.handles == {}
    other = ResearchRunner(duplicate, runner.registry)
    assert other._production_active() is False
    runtime._production_lock_handles.close()
    assert other._production_active() is False
    duplicate._production_lock_handles.close()


def test_stale_fd_number_never_closes_an_unrelated_reused_descriptor(tmp_path):
    runtime, runner, paths = fixture(tmp_path, 1)
    assert runner._production_active() is False
    fd, _identity = runtime._production_lock_handles.handles[str(paths[0])]
    os.close(fd)
    unrelated = os.open(tmp_path / 'unrelated', os.O_CREAT | os.O_RDWR, 0o600)
    try:
        assert runner._production_active() is True
        os.fstat(unrelated)
        assert runner._production_active() is False
    finally:
        os.close(unrelated)
        runtime._production_lock_handles.close()


def test_unlock_error_closes_observer_handle_instead_of_holding_shared_lock(
        tmp_path, monkeypatch):
    runtime, runner, paths = fixture(tmp_path, 1)
    original = fcntl.flock
    def fail_unlock(fd, operation):
        if operation == fcntl.LOCK_UN:
            raise OSError('simulated unlock failure')
        return original(fd, operation)
    monkeypatch.setattr(fcntl, 'flock', fail_unlock)
    assert runner._production_active() is True
    assert runtime._production_lock_handles.handles == {}
    with paths[0].open('a') as owner:
        original(owner.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        original(owner.fileno(), fcntl.LOCK_UN)


def test_path_change_during_initial_open_fails_closed_and_does_not_cache_old_file(
        tmp_path, monkeypatch):
    runtime, runner, paths = fixture(tmp_path, 1)
    original = os.open
    moved = [False]
    def replace_during_open(path, flags, *args, **kwargs):
        fd = original(path, flags, *args, **kwargs)
        if str(path) == str(paths[0]) and not moved[0]:
            paths[0].rename(tmp_path / 'prior.lock')
            paths[0].touch()
            moved[0] = True
        return fd
    monkeypatch.setattr(os, 'open', replace_during_open)
    assert runner._production_active() is True
    assert runtime._production_lock_handles.handles == {}
    assert runner._production_active() is False
    runtime._production_lock_handles.close()


def test_secondary_thread_cannot_certify_replaced_cached_namespace(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    runtime, runner, paths = fixture(tmp_path, 1)
    assert runner._production_active() is False
    with paths[0].open('a') as owner:
        fcntl.flock(owner.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        paths[0].rename(tmp_path / 'prior.lock')
        paths[0].touch()
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(runner._production_active).result(timeout=5) is True
        fcntl.flock(owner.fileno(), fcntl.LOCK_UN)
    assert runner._production_active() is True
    assert runner._production_active() is False
    runtime._production_lock_handles.close()
