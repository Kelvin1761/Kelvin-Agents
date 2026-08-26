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

    def test_central_read_only_commands_are_on_the_whitelist(self):
        for command in ("/status", "/git", "/models", "/evidence", "/release"):
            self.assertIn(command, B.COMMANDS)
        self.assertIn("/au_status", B.COMMANDS)
        self.assertIn("/approve", B.COMMANDS_WITH_ARG)

    def test_central_commands_render_machine_status_without_shell_input(self):
        payload = {
            "status": "attention",
            "attention": ["release_pending_approval"],
            "git": {
                "primary": {
                    "branch": "codex/test",
                    "head": "abcdef1234567890",
                    "dirty_paths": [],
                    "pushed": True,
                    "merged_to_main": False,
                },
                "production": {},
            },
            "releases": {
                "pending_approval": [
                    {
                        "commit": "abcdef1234567890",
                        "risk": "model",
                        "branch": "codex/model",
                    }
                ]
            },
            "evidence": {
                "status": "ok",
                "counts": {
                    "model_release": 4,
                    "prediction": 10,
                    "decision": 10,
                    "settlement": 8,
                },
                "errors": [],
            },
            "domains": {
                name: {
                    "latest_run": None,
                    "model_release": {
                        "release_stage": "production",
                        "code_commit": "abcdef1234567890",
                    },
                }
                for name in ("au", "hkjc", "tennis", "nba")
            },
        }
        with unittest.mock.patch.object(B, "_central_payload", return_value=payload):
            self.assertIn("codex/test", B.cmd_git())
            self.assertIn("AU：production", B.cmd_models())
            self.assertIn("prediction 10", B.cmd_evidence())
            self.assertIn("abcdef123456", B.cmd_release())

    def test_approval_rejects_non_sha_without_calling_release_code(self):
        self.assertIn("格式", B.cmd_approve("HEAD; rm -rf anything"))

    def test_approval_calls_fixed_api_with_strict_commit_only(self):
        result = {
            "status": "merged",
            "commit": "abcdef1234567890",
        }
        fake_module = unittest.mock.Mock()
        fake_module.approve_release.return_value = result
        activation_module = unittest.mock.Mock()
        activation_module.activate_release.return_value = {"status": "activated"}
        manager_module = unittest.mock.Mock()
        manager_module.ReleaseError = RuntimeError
        with unittest.mock.patch.dict(
            sys.modules,
            {
                "shared_wong_choi.release_approval": fake_module,
                "shared_wong_choi.release_activation": activation_module,
                "shared_wong_choi.release_manager": manager_module,
            },
        ):
            reply = B.cmd_approve("abcdef123456")
        self.assertIn("已批准", reply)
        kwargs = fake_module.approve_release.call_args.kwargs
        self.assertEqual(kwargs["selector"], "abcdef123456")
        self.assertEqual(kwargs["actor"], "telegram:authorised-chat")
        activation_kwargs = activation_module.activate_release.call_args.kwargs
        self.assertEqual(activation_kwargs["selector"], "abcdef123456")


if __name__ == "__main__":
    unittest.main()
