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
        for command in (
            "/status", "/git", "/models", "/evidence", "/release",
            "/storage", "/dashboard",
        ):
            self.assertIn(command, B.COMMANDS)
        self.assertIn("/au_status", B.COMMANDS)
        self.assertIn("/approve", B.MUTATING_COMMANDS_WITH_ARG)
        self.assertIn("/bootstrap_models", B.MUTATING_COMMANDS_WITH_ARG)

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
        self.assertIn(
            "格式",
            B.cmd_approve(
                "HEAD; rm -rf anything", actor=B.AUTHORISED_TELEGRAM_ACTOR
            ),
        )

    def test_bare_approve_resolves_the_single_pending_release(self):
        """No SHA typed: the bot must ask Central, never assume."""
        fake_module = unittest.mock.Mock()
        fake_module.resolve_pending_selector.return_value = "abcdef123456789a"
        fake_module.approve_release.return_value = {
            "status": "merged", "commit": "abcdef123456789a"}
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
            reply = B.cmd_approve("", actor=B.AUTHORISED_TELEGRAM_ACTOR)
        self.assertIn("已批准", reply)
        self.assertEqual(
            fake_module.approve_release.call_args.kwargs["selector"],
            "abcdef123456789a",
        )

    def test_bare_approve_reports_when_central_refuses_to_guess(self):
        fake_module = unittest.mock.Mock()
        fake_module.resolve_pending_selector.side_effect = RuntimeError(
            "2 releases are waiting; name one explicitly: aaaaaaaaaaaa, bbbbbbbbbbbb"
        )
        manager_module = unittest.mock.Mock()
        manager_module.ReleaseError = RuntimeError
        with unittest.mock.patch.dict(
            sys.modules,
            {
                "shared_wong_choi.release_approval": fake_module,
                "shared_wong_choi.release_activation": unittest.mock.Mock(),
                "shared_wong_choi.release_manager": manager_module,
            },
        ):
            reply = B.cmd_approve("", actor=B.AUTHORISED_TELEGRAM_ACTOR)
        self.assertIn("aaaaaaaaaaaa", reply)
        self.assertIn("bbbbbbbbbbbb", reply)
        fake_module.approve_release.assert_not_called()

    def test_notapprove_treats_free_text_as_reason_not_selector(self):
        fake_module = unittest.mock.Mock()
        fake_module.resolve_pending_selector.return_value = "abcdef123456789a"
        fake_module.reject_release.return_value = {
            "status": "rejected", "commit": "abcdef123456789a"}
        manager_module = unittest.mock.Mock()
        manager_module.ReleaseError = RuntimeError
        with unittest.mock.patch.dict(
            sys.modules,
            {
                "shared_wong_choi.release_approval": fake_module,
                "shared_wong_choi.release_manager": manager_module,
            },
        ):
            reply = B.cmd_notapprove(
                "dev 回歸唔要", actor=B.AUTHORISED_TELEGRAM_ACTOR)
        self.assertIn("已拒絕", reply)
        kwargs = fake_module.reject_release.call_args.kwargs
        self.assertEqual(kwargs["selector"], "abcdef123456789a")
        self.assertEqual(kwargs["reason"], "dev 回歸唔要")
        # Free text must never be smuggled in as the selector.
        self.assertEqual(
            fake_module.resolve_pending_selector.call_args.args[1], "")

    def test_notapprove_is_registered_and_actor_gated(self):
        self.assertIn("/notapprove", B.MUTATING_COMMANDS_WITH_ARG)
        with self.assertRaises(PermissionError):
            B.cmd_notapprove("", actor="telegram:forged")

    def test_governance_actor_only_minted_for_configured_chat(self):
        self.assertEqual(
            B._authenticated_actor("123", "123"),
            B.AUTHORISED_TELEGRAM_ACTOR,
        )
        with self.assertRaises(PermissionError):
            B._authenticated_actor("attacker", "123")
        with self.assertRaises(PermissionError):
            B.cmd_approve("abcdef123456", actor="telegram:forged")
        with self.assertRaises(PermissionError):
            B.cmd_bootstrap_models("abcdef123456", actor="telegram:forged")

    def test_unauthorised_chat_cannot_dispatch_governance_write(self):
        updates = {
            "ok": True,
            "result": [
                {
                    "update_id": 7,
                    "message": {
                        "chat": {"id": "attacker"},
                        "text": "/bootstrap_models abcdef123456",
                    },
                }
            ],
        }
        calls = []

        def fake_api(method, **params):
            calls.append((method, params))
            return updates if method == "getUpdates" else {"ok": True}

        bootstrap = unittest.mock.Mock(return_value="must not run")
        with unittest.mock.patch.dict(
            B.os.environ,
            {
                "WC_NOTIFY_TELEGRAM_CHAT": "owner",
                "WC_NOTIFY_TELEGRAM_TOKEN": "test-token",
            },
            clear=False,
        ), unittest.mock.patch.object(B, "api", side_effect=fake_api), \
             unittest.mock.patch.object(B, "save_offset"), \
             unittest.mock.patch.object(B, "_record_unknown"), \
             unittest.mock.patch.dict(
                 B.MUTATING_COMMANDS_WITH_ARG,
                 {"/bootstrap_models": bootstrap},
             ):
            self.assertEqual(B.main(), 0)

        bootstrap.assert_not_called()
        self.assertEqual([method for method, _params in calls], ["getUpdates"])

    def test_handoff_can_share_production_telegram_offset(self):
        with tempfile.TemporaryDirectory() as tmp:
            shared = Path(tmp) / "telegram-offset.json"
            with unittest.mock.patch.dict(
                B.os.environ,
                {"WC_TELEGRAM_OFFSET_FILE": str(shared)},
                clear=False,
            ):
                B.save_offset(88)
                self.assertEqual(B.load_offset(), 88)
            self.assertEqual(shared.read_text(encoding="utf-8"), '{"offset": 88}')

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
            reply = B.cmd_approve(
                "abcdef123456", actor=B.AUTHORISED_TELEGRAM_ACTOR
            )
        self.assertIn("已批准", reply)
        kwargs = fake_module.approve_release.call_args.kwargs
        self.assertEqual(kwargs["selector"], "abcdef123456")
        self.assertEqual(kwargs["actor"], "telegram:authorised-chat")
        activation_kwargs = activation_module.activate_release.call_args.kwargs
        self.assertEqual(activation_kwargs["selector"], "abcdef123456")

    def test_model_bootstrap_requires_aligned_activated_main_and_empty_registry(self):
        commit = "abcdef1234567890abcdef1234567890abcdef12"
        payload = {
            "evidence": {
                "status": "ok",
                "counts": {"model_release": 0},
            },
            "git": {
                "production": {
                    name: {
                        "head": commit,
                        "status": "clean_runtime_state",
                        "merged_to_main": True,
                    }
                    for name in ("au", "hkjc", "tennis", "nba")
                }
            },
            "releases": {
                "latest": [
                    {
                        "commit": commit,
                        "status": "merged",
                        "activation": "succeeded",
                    }
                ]
            },
            "domains": {
                name: {"model_release": None}
                for name in ("au", "hkjc", "tennis", "nba")
            },
        }
        registry_module = unittest.mock.Mock()
        registry_module.ModelPromotionError = RuntimeError
        registry_module.bootstrap_current_models_once.return_value = {
            "au": {"stage": "production"},
            "hkjc": {"stage": "production"},
            "tennis": {"stage": "shadow"},
            "nba": {"stage": "shadow"},
        }
        with unittest.mock.patch.object(B, "_central_payload", return_value=payload), \
             unittest.mock.patch.dict(
                 sys.modules,
                 {"shared_wong_choi.model_registry": registry_module},
             ):
            reply = B.cmd_bootstrap_models(
                commit[:12], actor=B.AUTHORISED_TELEGRAM_ACTOR
            )
        self.assertIn("已登記", reply)
        kwargs = registry_module.bootstrap_current_models_once.call_args.kwargs
        self.assertEqual(kwargs["code_commit"], commit)
        self.assertEqual(kwargs["approval_id"], B.AUTHORISED_TELEGRAM_ACTOR)

        payload["releases"]["latest"][0]["activation"] = "failed"
        with unittest.mock.patch.object(B, "_central_payload", return_value=payload):
            blocked = B.cmd_bootstrap_models(
                commit[:12], actor=B.AUTHORISED_TELEGRAM_ACTOR
            )
        self.assertIn("activation_succeeded", blocked)

    def test_model_bootstrap_repeat_is_read_only_and_mismatch_fails_closed(self):
        commit = "abcdef1234567890abcdef1234567890abcdef12"
        payload = {
            "evidence": {"status": "ok", "counts": {"model_release": 4}},
            "git": {
                "production": {
                    name: {
                        "head": commit,
                        "status": "clean",
                        "merged_to_main": True,
                    }
                    for name in ("au", "hkjc", "tennis", "nba")
                }
            },
            "releases": {
                "latest": [
                    {
                        "commit": commit,
                        "status": "merged",
                        "activation": "succeeded",
                    }
                ]
            },
            "domains": {
                name: {"model_release": {"code_commit": commit}}
                for name in ("au", "hkjc", "tennis", "nba")
            },
        }
        with unittest.mock.patch.object(B, "_central_payload", return_value=payload):
            reply = B.cmd_bootstrap_models(
                commit[:12], actor=B.AUTHORISED_TELEGRAM_ACTOR
            )
        self.assertIn("冇重複寫入", reply)

        payload["git"]["production"]["nba"]["head"] = "f" * 40
        with unittest.mock.patch.object(B, "_central_payload", return_value=payload):
            blocked = B.cmd_bootstrap_models(
                commit[:12], actor=B.AUTHORISED_TELEGRAM_ACTOR
            )
        self.assertIn("SHA 不一致", blocked)


if __name__ == "__main__":
    unittest.main()
