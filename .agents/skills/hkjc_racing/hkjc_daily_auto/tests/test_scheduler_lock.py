"""排程鎖唔可以餓死其他 mode。

2026-09-05：`prerace` 因為一個 starter PDF bug 每 30 分鐘重試、每次跑 7 分鐘，
幾乎長期霸住個鎖。舊版一撞就即刻放棄，於是 `watch`（一日四格）同 `postrace`
（一日一格）成日一次都冇跑到 —— 而個訊息淨係「already running」，冇講邊個
霸住，收到 `severity: critical` 都唔知去邊度查。

呢度守三樣：有界等待、講得出邊個霸住、連續被擋要嗌。
個鎖本身唔會拆 —— 佢防止兩條 pipeline 同時寫同一個 meeting folder 同 state。
"""
from __future__ import annotations

import fcntl
import json
import sys
import time
from pathlib import Path
from unittest import mock

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

import hkjc_daily_schedule as sched


@pytest.fixture
def lock_path(tmp_path):
    return tmp_path / "hkjc_daily_state.lock"


def _hold(lock_path: Path, mode: str = "prerace"):
    """開一個真 flock 霸住個鎖（另一個 file description，同真實情況一樣）。"""
    handle = lock_path.open("a", encoding="utf-8")
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    sched._write_holder(lock_path, mode)
    return handle


# ───────────────────────── 有界等待 ─────────────────────────

def test_a_free_lock_is_acquired_immediately(lock_path):
    with lock_path.open("a", encoding="utf-8") as lock:
        waited = sched._acquire_lock(lock, timeout=5)
    assert waited is not None
    assert waited < 1.0


def test_a_held_lock_is_waited_for_then_acquired(lock_path):
    """呢個就係修正嘅重點：舊版喺呢度即刻放棄。"""
    holder = _hold(lock_path)
    import threading
    threading.Timer(0.6, lambda: (fcntl.flock(holder.fileno(), fcntl.LOCK_UN),
                                  holder.close())).start()
    with lock_path.open("a", encoding="utf-8") as lock:
        waited = sched._acquire_lock(lock, timeout=10)
    assert waited is not None, "等得夠耐就應該攞到"
    assert waited >= 0.5


def test_waiting_gives_up_at_the_timeout(lock_path):
    holder = _hold(lock_path)
    try:
        start = time.monotonic()
        with lock_path.open("a", encoding="utf-8") as lock:
            waited = sched._acquire_lock(lock, timeout=1.0)
        assert waited is None
        assert time.monotonic() - start < 5, "唔可以等超過 timeout"
    finally:
        holder.close()


def test_zero_timeout_still_works_like_the_old_behaviour(lock_path):
    """`WC_HKJC_LOCK_WAIT=0` 要回到舊嘅即刻放棄 —— 留返個逃生門。"""
    holder = _hold(lock_path)
    try:
        with lock_path.open("a", encoding="utf-8") as lock:
            assert sched._acquire_lock(lock, timeout=0) is None
    finally:
        holder.close()


# ─────────────────────── 講得出邊個霸住 ───────────────────────

def test_the_holder_is_named(lock_path):
    holder = _hold(lock_path, "prerace")
    try:
        text = sched._describe_holder(lock_path)
        assert "prerace" in text
        assert str(sched.os.getpid()) in text
    finally:
        holder.close()


def test_a_missing_holder_record_still_returns_a_sentence(lock_path):
    """診斷用嘅嘢缺失，唔可以令個訊息變空白。"""
    lock_path.write_text("", encoding="utf-8")
    assert sched._describe_holder(lock_path).strip()


def test_the_holder_record_is_cleared_on_release(lock_path):
    sched._write_holder(lock_path, "prerace")
    assert sched._holder_path(lock_path).exists()
    sched._clear_holder(lock_path)
    assert not sched._holder_path(lock_path).exists()


# ─────────────────────── 被擋要記低同嗌 ───────────────────────

def test_skips_accumulate_per_mode(lock_path):
    assert sched._record_skip(lock_path, "watch", "prerace 霸住") == 1
    assert sched._record_skip(lock_path, "watch", "prerace 霸住") == 2
    assert sched._record_skip(lock_path, "postrace", "prerace 霸住") == 1, \
        "唔同 mode 要分開數"


def test_a_successful_acquire_clears_that_modes_skips(lock_path):
    sched._record_skip(lock_path, "watch", "x")
    sched._record_skip(lock_path, "watch", "x")
    sched._clear_skip(lock_path, "watch")
    assert sched._record_skip(lock_path, "watch", "x") == 1


def test_skips_survive_a_corrupt_file(lock_path):
    sched._skips_path(lock_path).write_text("not json", encoding="utf-8")
    assert sched._record_skip(lock_path, "watch", "x") == 1


def test_the_skip_record_names_the_holder(lock_path):
    sched._record_skip(lock_path, "watch", "prerace（pid 42）霸住，已經跑咗 7 分鐘")
    data = json.loads(sched._skips_path(lock_path).read_text(encoding="utf-8"))
    assert "prerace" in data["watch"]["holder"]


# ─────────────────────── main() 整合 ───────────────────────

def _main(mode, state_file, **env):
    argv = ["--mode", mode, "--state-file", str(state_file)]
    with mock.patch.dict(sched.os.environ, env, clear=False):
        return sched.main(argv)


def test_main_alerts_once_the_starvation_threshold_is_reached(tmp_path):
    state_file = tmp_path / "hkjc_daily_state.json"
    lock = state_file.with_suffix(".lock")
    held = _hold(lock, "prerace")
    try:
        with (
            mock.patch.object(sched, "LOCK_WAIT_SECONDS", 0),
            mock.patch.object(sched, "LOCK_STARVE_ALERT_AFTER", 3),
            mock.patch.object(sched, "notify") as notify,
            mock.patch.object(sched, "emit_control_outcome", side_effect=lambda _a, c: c),
        ):
            for _ in range(2):
                assert _main("watch", state_file) == sched.EXIT_OK
            notify.assert_not_called()          # 頭兩次唔嗌，避免噪音
            _main("watch", state_file)
            notify.assert_called_once()
            message = notify.call_args[0][0]
            assert "連續 3 次" in message
            assert "prerace" in message, "要講得出邊個霸住"
    finally:
        held.close()


def test_main_records_the_holder_in_the_control_outcome(tmp_path):
    state_file = tmp_path / "hkjc_daily_state.json"
    lock = state_file.with_suffix(".lock")
    held = _hold(lock, "prerace")
    try:
        seen = {}
        with (
            mock.patch.object(sched, "LOCK_WAIT_SECONDS", 0),
            mock.patch.object(sched, "notify"),
            mock.patch.object(sched, "set_control_outcome",
                              side_effect=lambda s, **kw: seen.update(kw)),
            mock.patch.object(sched, "emit_control_outcome", side_effect=lambda _a, c: c),
        ):
            _main("watch", state_file)
        assert "prerace" in seen.get("holder", "")
        assert seen.get("consecutive_skips") == 1
    finally:
        held.close()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
