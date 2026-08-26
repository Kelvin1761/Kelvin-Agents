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
import tempfile
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

        with tempfile.TemporaryDirectory() as tmp, \
             unittest.mock.patch.object(B, "RETRY_LOG", Path(tmp) / "retry.out"), \
             unittest.mock.patch.object(au_healthcheck, "run_in_progress",
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

        with tempfile.TemporaryDirectory() as tmp, \
             unittest.mock.patch.object(B, "RETRY_LOG", Path(tmp) / "retry.out"), \
             unittest.mock.patch.object(au_healthcheck, "run_in_progress",
                                        lambda: False), \
             unittest.mock.patch("subprocess.Popen", _P):
            B.cmd_retry()
        self.assertTrue(str(started["cmd"][1]).endswith("run_au_daily_schedule.sh"))
        self.assertIn("evening", started["cmd"])

    def test_retry_is_on_the_whitelist(self):
        self.assertIn("/retry", B.COMMANDS)

    def test_hkjc_commands_use_fixed_production_modes(self):
        started = []

        class _P:
            def __init__(self, cmd, **kw):
                started.append((cmd, kw))

        with tempfile.TemporaryDirectory() as tmp, \
             unittest.mock.patch.object(
                 B, "_hkjc_runner", return_value=Path(tmp) / "run.sh"
             ), \
             unittest.mock.patch("subprocess.Popen", _P):
            runner = Path(tmp) / "run.sh"
            runner.write_text("#!/bin/bash\n", encoding="utf-8")
            with unittest.mock.patch.object(
                B, "HKJC_ANALYSIS_LOG", Path(tmp) / "analysis.out"
            ), unittest.mock.patch.object(
                B, "HKJC_REFLECT_LOG", Path(tmp) / "reflect.out"
            ):
                self.assertIn("已開始", B.cmd_hkjc())
                self.assertIn("已開始", B.cmd_hkjc_reflect())

        self.assertEqual(started[0][0][-2:], ["prerace", "--force"])
        self.assertEqual(started[1][0][-1], "postrace")
        self.assertTrue(started[0][1].get("start_new_session"))
        self.assertTrue(started[1][1].get("start_new_session"))

    def test_hkjc_commands_are_on_the_whitelist(self):
        self.assertIn("/hkjc", B.COMMANDS)
        self.assertIn("/hkjc_reflect", B.COMMANDS)


if __name__ == "__main__":
    unittest.main()
