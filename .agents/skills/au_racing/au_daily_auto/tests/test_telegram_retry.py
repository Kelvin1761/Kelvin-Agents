#!/usr/bin/env python3
"""`/retry` —— 唯一一個有副作用嘅指令。

Kelvin 2026-08-11 明確要求：嗰晚網絡斷咗令五個 08-12 場次冇分析，佢想有得由電話
補跑，唔使開機。

⚠️ 三道限制缺一不可：
  * 只有已授權 chat 叫得到（`main()` 層擋，其他人零回應）；
  * 有 run 跑緊就唔開 —— 兩個 run 同時郁同一批 folder、同一個 Chrome profile、
    同一個 dashboard，正正係把鎖要防嗰件事；
  * 唔會重抽已分析嘅場次，所以亂叫都唔會浪費網絡配額。
"""
from __future__ import annotations

import sys
import unittest
import unittest.mock
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import au_telegram_bot as B  # noqa: E402


class RetryGuardTests(unittest.TestCase):
    def test_refuses_while_a_run_is_in_progress(self):
        import au_healthcheck
        with unittest.mock.patch.object(au_healthcheck, "run_in_progress",
                                        lambda: True):
            reply = B.cmd_retry()
        self.assertIn("唔開第二個", reply)

    def test_starts_detached_when_idle(self):
        import au_healthcheck
        started = {}

        class _P:
            def __init__(self, cmd, **kw):
                started["cmd"] = cmd
                started["kw"] = kw

        with unittest.mock.patch.object(au_healthcheck, "run_in_progress",
                                        lambda: False), \
             unittest.mock.patch("subprocess.Popen", _P):
            reply = B.cmd_retry()
        self.assertIn("已開始", reply)
        # bot 每兩分鐘就退出，所以一定要 detach，否則個 run 會跟住死。
        self.assertTrue(started["kw"].get("start_new_session"))
        self.assertIn("--skip-review", started["cmd"])

    def test_it_is_the_same_path_the_scheduler_uses(self):
        # 唔會行一條特別嘅捷徑 —— 同排程一樣嘅 runner，所以驗證同發佈照做。
        import au_healthcheck
        started = {}

        class _P:
            def __init__(self, cmd, **kw):
                started["cmd"] = cmd

        with unittest.mock.patch.object(au_healthcheck, "run_in_progress",
                                        lambda: False), \
             unittest.mock.patch("subprocess.Popen", _P):
            B.cmd_retry()
        self.assertTrue(str(started["cmd"][1]).endswith("run_au_daily_schedule.sh"))
        self.assertIn("evening", started["cmd"])

    def test_retry_is_on_the_whitelist(self):
        self.assertIn("/retry", B.COMMANDS)


if __name__ == "__main__":
    unittest.main()
