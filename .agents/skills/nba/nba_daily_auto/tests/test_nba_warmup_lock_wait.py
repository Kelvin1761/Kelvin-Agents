"""19:00 warmup 撞 postgame 鎖：有界等待（其他 mode 照舊即刻跳）。"""
from __future__ import annotations

import fcntl
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

AUTO_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AUTO_DIR))
import nba_daily_schedule as schedule  # noqa: E402


class WarmupLockWaitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "nba_daily_schedule.lock"
        self.holder = self.path.open("a")
        fcntl.flock(self.holder.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)  # 扮 postgame 揸住
        self.waiter = self.path.open("a")

    def tearDown(self):
        self.holder.close()
        self.waiter.close()
        self.tmp.cleanup()

    def test_lock_released_within_bound_lets_warmup_proceed(self):
        threading.Timer(0.3, lambda: fcntl.flock(self.holder.fileno(), fcntl.LOCK_UN)).start()
        t0 = time.monotonic()
        self.assertTrue(schedule.acquire_lock(self.waiter.fileno(), 5, 0.05))
        self.assertLess(time.monotonic() - t0, 3)

    def test_lock_held_past_bound_skips(self):
        t0 = time.monotonic()
        self.assertFalse(schedule.acquire_lock(self.waiter.fileno(), 0.4, 0.05))
        self.assertGreaterEqual(time.monotonic() - t0, 0.35)

    def test_zero_wait_tries_once(self):
        sleeps = []
        self.assertFalse(schedule.acquire_lock(self.waiter.fileno(), 0, sleep=sleeps.append))
        self.assertEqual(sleeps, [])

    def test_poll_interval_and_bound_respected(self):
        clock = [0.0]
        sleeps = []

        def fake_sleep(s):
            sleeps.append(s)
            clock[0] += s

        self.assertFalse(schedule.acquire_lock(self.waiter.fileno(), 600, 15,
                                               sleep=fake_sleep, clock=lambda: clock[0]))
        self.assertEqual(len(sleeps), 40)
        self.assertTrue(all(s == 15 for s in sleeps))
        self.assertEqual(sum(sleeps), 600)

    def test_only_explicit_warmup_waits(self):
        self.assertEqual(schedule.lock_wait_seconds("pregame", "warmup"), 600)
        for mode, role in [("pregame", "production"), ("pregame", "final_refresh"),
                           ("pregame", "auto"), ("postgame", "auto"), ("health", "warmup"),
                           ("mark-no-prediction", "auto")]:
            self.assertEqual(schedule.lock_wait_seconds(mode, role), 0, (mode, role))


if __name__ == "__main__":
    unittest.main()
