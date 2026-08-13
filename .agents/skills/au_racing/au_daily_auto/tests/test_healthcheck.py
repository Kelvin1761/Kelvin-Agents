#!/usr/bin/env python3
"""體檢 —— 唯一一個唔住喺排程 process 入面嘅檢查。

現有嘅補救（補發、補覆盤、補抽）全部靠排程自己行到嗰一步先觸發。個 run 早死、
crash、或者根本冇開，就冇任何嘢會發現。2026-08-05 至 08-10 三次多日空白，每次
都係「有嘢失敗咗，而冇人去問今日到底出咗未」。

判斷睇實物（live JSON、本機評分檔），唔睇 log —— 一個報「成功」嘅 run log 已經
呃過我哋兩次。
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import au_healthcheck as H  # noqa: E402

DAY = "2026-08-10"
VENUES = {"Dubbo", "Kilcoy", "Nowra", "Pakenham Synthetic"}


def patched(live, expect, scored):
    return unittest.mock.patch.multiple(
        H, live_meetings=lambda: live, au_venues_today=lambda day: expect,
        local_scored=lambda day: scored, run_in_progress=lambda: False)


class InProgressTests(unittest.TestCase):
    """個 run 跑緊嘅時候唔可以報「冇上線」。

    實測五次真實晚更：22:00 開工，收工由 23:33 到 01:59，中位數 00:30。任何排喺
    完成之前嘅體檢都會撞正個 run —— 而發佈係最後一步，所以佢**必然**見到「今日
    場次冇喺 live」，跟住去補發佈、俾鎖擋住、send 一條假警報。
    """

    def test_a_running_job_is_not_a_failure(self):
        with unittest.mock.patch.object(H, "run_in_progress", lambda: True):
            self.assertEqual(H.check(DAY)["state"], "in-progress")

    def test_in_progress_short_circuits_before_touching_the_network(self):
        called = []
        with unittest.mock.patch.multiple(
                H, run_in_progress=lambda: True,
                live_meetings=lambda: called.append("live")):
            H.check(DAY)
        self.assertEqual(called, [])


class HealthcheckTests(unittest.TestCase):
    def test_everything_live_is_quiet(self):
        with patched({f"{DAY}|{v}" for v in VENUES}, VENUES, {v: 7 for v in VENUES}):
            self.assertEqual(H.check(DAY)["state"], "ok")

    def test_analysed_but_not_published_is_healable(self):
        # 2026-08-09 晚更真實情況：四個場次分析齊，deploy 死喺 Drive 權限。
        with patched({"2026-08-09|Wagga"}, VENUES, {v: 7 for v in VENUES}):
            r = H.check(DAY)
        self.assertEqual(r["state"], "unpublished")
        self.assertEqual(sorted(r["publishable"]), sorted(VENUES))

    def test_never_analysed_is_not_something_a_healthcheck_should_fix(self):
        # 補呢個要重抽幾百版 —— 唔應該由一個體檢靜靜咁觸發。
        with patched({"2026-08-09|Wagga"}, VENUES, {}):
            self.assertEqual(H.check(DAY)["state"], "unanalysed")

    def test_unreadable_live_is_unknown_not_missing(self):
        # 讀唔到 live 就當「冇發佈」而去補，等於網絡一有事就亂發佈一次。
        with patched(None, VENUES, {v: 7 for v in VENUES}):
            self.assertEqual(H.check(DAY)["state"], "unknown")

    def test_partially_scored_still_reports_every_missing_venue(self):
        with patched({f"{DAY}|Dubbo"}, VENUES, {"Kilcoy": 7}):
            r = H.check(DAY)
        self.assertEqual(r["publishable"], ["Kilcoy"])
        self.assertIn("Nowra", r["missing"])

    def test_api_failure_falls_back_to_what_we_scored_locally(self):
        # API 唔通嗰陣仍然要捉到「本機有分析但 live 冇」。
        with patched({"2026-08-09|Wagga"}, None, {"Dubbo": 7}):
            r = H.check(DAY)
        self.assertEqual(r["state"], "unpublished")
        self.assertEqual(r["publishable"], ["Dubbo"])

    def test_a_meeting_live_from_another_day_does_not_count(self):
        # 尋日嘅場次仲喺 dashboard 唔代表今日出咗。
        with patched({"2026-08-09|Dubbo"}, {"Dubbo"}, {"Dubbo": 7}):
            self.assertEqual(H.check(DAY)["state"], "unpublished")


if __name__ == "__main__":
    unittest.main()


class AutofixTests(unittest.TestCase):
    """自動補救只可以喺已知模式上動手，而且一個 run 只試一次。

    ⚠️ 兩道限制都係刻意：
      * 估出嚟嘅補救可以令情況變差，仲會遮蓋「呢個係新問題」呢個最重要嘅訊號；
      * 冇「一次」限制嘅話，一個修唔到嘅問題會令每次體檢都重跑一次發佈，
        一日三次，每次 send 一條通知 —— 跟住你就會開始無視啲通知。
    """

    def _logs(self, tmp, runs):
        import json as _json
        logs = Path(tmp) / "logs"
        logs.mkdir(parents=True)
        for i, (name, status, err) in enumerate(runs):
            (logs / name).write_text(_json.dumps({
                "status": status,
                "errors": [{"step": "dashboard", "message": err}] if err else [],
            }), encoding="utf-8")
            os.utime(logs / name, (1000 + i, 1000 + i))
        return logs

    def _patch(self, logs):
        return unittest.mock.patch.multiple(
            H, HERE=logs.parent, ATTEMPTED=logs / "attempted.json")

    def test_a_known_publish_failure_is_picked_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            logs = self._logs(tmp, [
                ("run-a.json", "failed", "已歸檔但仲喺 dashboard：['x']")])
            with self._patch(logs):
                got = H.last_failed_run()
        self.assertIsNotNone(got)

    def test_a_running_log_without_a_live_lock_is_picked_up_as_a_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            logs = self._logs(tmp, [("run-a.json", "running", None)])
            with self._patch(logs):
                got = H.last_failed_run()
        self.assertIsNotNone(got)

    def test_a_crashed_running_log_generates_a_phone_warning(self):
        marked = []
        run = {"status": "running", "started_at": "2026-08-13T10:00:00+10:00"}
        with unittest.mock.patch.object(
                H, "last_failed_run", lambda: (Path("run-crashed.json"), run)), \
             unittest.mock.patch.object(H, "_mark", lambda name: marked.append(name)):
            text = H.autofix_last_failure()
        self.assertIn("冇正常收尾", text)
        self.assertIn("中途死亡", text)
        self.assertEqual(marked, ["run-crashed.json"])

    def test_a_later_successful_run_cancels_the_chase(self):
        # 之後有成功嘅 run，之前嗰個失敗已經冇意義 —— 唔好再修一次。
        with tempfile.TemporaryDirectory() as tmp:
            logs = self._logs(tmp, [
                ("run-a.json", "failed", "已歸檔但仲喺 dashboard：['x']"),
                ("run-b.json", "ok", None)])
            with self._patch(logs):
                self.assertIsNone(H.last_failed_run())

    def test_the_same_run_is_never_attempted_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            logs = self._logs(tmp, [
                ("run-a.json", "failed", "已歸檔但仲喺 dashboard：['x']")])
            with self._patch(logs):
                self.assertIsNotNone(H.last_failed_run())
                H._mark("run-a.json")
                self.assertIsNone(H.last_failed_run())

    def test_an_unknown_error_triggers_no_action(self):
        import au_diagnose as D
        self.assertIsNone(D.remedy_for(
            {"errors": [{"message": "something nobody has seen before"}]}))

    def test_extraction_side_failures_have_no_remedy(self):
        # 補呢啲要重抽幾百版 —— 唔應該由自動修觸發，下次排程本身會接住。
        import au_diagnose as D
        for msg in ("TargetClosedError: page closed",
                    "個站喺 X 明確拒絕",
                    "cache 冇任何賽果"):
            self.assertIsNone(D.remedy_for({"errors": [{"message": msg}]}), msg)

    def test_publish_side_failures_all_map_to_republish(self):
        import au_diagnose as D
        for msg in ("Pages only supports files up to 25 MiB in size",
                    "PermissionError: ... CloudStorage ... /HK_Racing",
                    "已歸檔但仲喺 dashboard：['x']",
                    "2026-08-09|Wagga 一場都冇（races_by_analyst 空)"):
            self.assertEqual(D.remedy_for({"errors": [{"message": msg}]}),
                             "republish", msg)


class AnalysisRecoveryTests(unittest.TestCase):
    def test_unanalysed_day_starts_the_normal_morning_pipeline_once(self):
        started = {}

        class _P:
            def __init__(self, cmd, **kwargs):
                started["cmd"] = cmd
                started["kwargs"] = kwargs

        with tempfile.TemporaryDirectory() as tmp, \
             unittest.mock.patch.multiple(
                 H, HERE=Path(tmp), RUNNER=Path(tmp) / "runner",
                 run_in_progress=lambda: False, _attempted=lambda: set()), \
             unittest.mock.patch.object(H, "_mark", lambda key: started.setdefault("key", key)), \
             unittest.mock.patch.object(H.subprocess, "Popen", _P):
            H.RUNNER.write_text("#!/bin/zsh\n")
            ok, detail = H.start_analysis_recovery(DAY)

        self.assertTrue(ok, detail)
        self.assertEqual(started["key"], f"auto-analysis-{DAY}")
        self.assertEqual(started["cmd"][1:4], ["morning", "--today", DAY])
        self.assertTrue(started["kwargs"]["start_new_session"])

    def test_same_day_is_never_started_twice(self):
        key = f"auto-analysis-{DAY}"
        with unittest.mock.patch.object(H, "_attempted", lambda: {key}):
            ok, detail = H.start_analysis_recovery(DAY)
        self.assertFalse(ok)
        self.assertIn("已經自動補跑過", detail)

    def test_recovery_never_competes_with_a_live_run(self):
        with unittest.mock.patch.object(H, "_attempted", lambda: set()), \
             unittest.mock.patch.object(H, "run_in_progress", lambda: True):
            ok, detail = H.start_analysis_recovery(DAY)
        self.assertFalse(ok)
        self.assertIn("已有 AU run", detail)
