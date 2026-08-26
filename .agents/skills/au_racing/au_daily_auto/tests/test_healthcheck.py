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
        local_scored=lambda day: scored, run_in_progress=lambda: False,
        quality_issues=lambda day: ([], []))


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

    def test_live_but_incomplete_data_is_degraded_not_green(self):
        with unittest.mock.patch.multiple(
                H, live_meetings=lambda: {f"{DAY}|{v}" for v in VENUES},
                au_venues_today=lambda day: VENUES,
                local_scored=lambda day: {v: 7 for v in VENUES},
                run_in_progress=lambda: False,
                quality_issues=lambda day: (["ingest-results partial"], [])):
            result = H.check(DAY)
        self.assertEqual(result["state"], "degraded")
        self.assertIn("ingest-results", result["issues"][0])

    def test_a_best_effort_lag_alone_is_not_degraded(self):
        """Drive 鏡像落後唔算「資料品質未過」—— 本機係正本，Cloudflare 由本機發。

        混做同一句就係報得比實際嚴重，而報錯輕重同報錯事實一樣會令人唔信通知。
        """
        with unittest.mock.patch.multiple(
                H, live_meetings=lambda: {f"{DAY}|{v}" for v in VENUES},
                au_venues_today=lambda day: VENUES,
                local_scored=lambda day: {v: 7 for v in VENUES},
                run_in_progress=lambda: False,
                quality_issues=lambda day: ([], ["Drive 鏡像落後 2 個檔"])):
            result = H.check(DAY)
        self.assertEqual(result["state"], "ok-with-advisories")
        self.assertEqual(result["advisories"], ["Drive 鏡像落後 2 個檔"])
        self.assertNotIn("issues", result)


class DataQualityTests(unittest.TestCase):
    def _meeting(self, root: Path, *, morning: bool = True,
                 jt: tuple[int, int] = (18, 2), going_refresh: bool = True):
        import json
        folder = root / f"{DAY} Dubbo Race 1-1"
        folder.mkdir(parents=True)
        for label in ("Racecard", "Formguide", "Facts"):
            (folder / f"08-10 Race 1 {label}.md").write_text("ok")
        logic = {"race_analysis": {"going": "Good 4"}}
        if going_refresh:
            logic["race_analysis"]["going_refresh"] = {"official_going": "Good 4"}
        (folder / "Race_1_Logic.json").write_text(json.dumps(logic))
        (folder / "Race_1_Auto_Analysis.md").write_text("ok")
        (folder / "Race_1_Auto_Scoring.csv").write_text("ok")
        label = "2026-08-10T10:05:00|morning-refresh" if morning \
            else "2026-08-09T22:00:00|analysis"
        (folder / "odds_history.json").write_text(json.dumps({"1": {label: {}}}))
        (folder / "Meeting_Summary.md").write_text(
            f"Jockey/trainer LY tokens filled: {jt[0]}; missing: {jt[1]}\n")
        return folder

    def test_complete_meeting_passes_quality_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._meeting(Path(tmp))
            self.assertEqual(H.local_quality_issues(
                DAY, root=Path(tmp), require_morning=True), [])

    def test_stale_odds_missing_going_and_thin_people_are_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._meeting(Path(tmp), morning=False, jt=(6, 6), going_refresh=False)
            issues = H.local_quality_issues(DAY, root=Path(tmp), require_morning=True)
        joined = "\n".join(issues)
        self.assertIn("morning odds", joined)
        self.assertIn("going_refresh", joined)
        self.assertIn("50.0%", joined)

    def _tree(self, tmp, *, drive_has=True, drive_stale=False, latest=False):
        root, mirror = Path(tmp) / "local", Path(tmp) / "drive"
        folder = root / "2026-08-21 Sale Race 1-9"
        folder.mkdir(parents=True)
        (folder / "Race_1_Auto_Analysis.md").write_text("x", encoding="utf-8")
        (root / "AU_Historical_Raw_Race_Results.csv").write_text("a,b\n",
                                                                encoding="utf-8")
        (root / "AU_Backfill_Race_Results.csv").write_text("c,d\n", encoding="utf-8")
        mirror.mkdir()
        if drive_has:
            for src in sorted(root.rglob("*")):
                if not src.is_file():
                    continue
                rel = src.relative_to(root)
                name = rel.name
                if latest and name == "AU_Historical_Raw_Race_Results.csv":
                    rel = rel.with_name("AU_Historical_Raw_Race_Results.latest.csv")
                dst = mirror / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_text("stale" if drive_stale else
                               src.read_text(encoding="utf-8"), encoding="utf-8")
                if not drive_stale:
                    os.utime(dst, (src.stat().st_mtime, src.stat().st_mtime))
        return root, mirror

    def test_a_mirror_that_matches_the_local_copies_is_quiet(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, mirror = self._tree(tmp)
            self.assertEqual(H.mirror_behind("2026-08-21", root=root, mirror=mirror), [])

    def test_a_latest_fallback_sibling_counts_as_mirrored(self):
        # 個別檔寫唔入會退去 `.latest`，consumers 由 wongchoi_paths 取最新嗰份。
        with tempfile.TemporaryDirectory() as tmp:
            root, mirror = self._tree(tmp, latest=True)
            self.assertEqual(H.mirror_behind("2026-08-21", root=root, mirror=mirror), [])

    def test_missing_and_stale_mirror_files_are_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, mirror = self._tree(tmp, drive_has=False)
            behind = H.mirror_behind("2026-08-21", root=root, mirror=mirror)
            self.assertIn("AU_Historical_Raw_Race_Results.csv", behind)
            self.assertIn("2026-08-21 Sale Race 1-9/Race_1_Auto_Analysis.md", behind)

    def test_an_unreadable_mirror_root_answers_dunno_not_zero(self):
        # 「stat 唔到」唔等於「追到」—— 答唔到就要退去睇 log，唔可以報綠燈。
        with tempfile.TemporaryDirectory() as tmp:
            root, _mirror = self._tree(tmp)
            self.assertIsNone(H.mirror_behind(
                "2026-08-21", root=root, mirror=Path(tmp) / "does-not-exist"))

    def test_denied_destination_stat_is_unknown_not_behind(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, mirror = self._tree(tmp)
            real_stat = Path.stat

            def stat(path, *args, **kwargs):
                if str(path).startswith(str(mirror)) and path != mirror:
                    raise PermissionError(1, "Operation not permitted", str(path))
                return real_stat(path, *args, **kwargs)

            with unittest.mock.patch.object(Path, "stat", stat):
                self.assertIsNone(
                    H.mirror_behind("2026-08-21", root=root, mirror=mirror)
                )

    def test_unknown_mirror_stat_defers_to_latest_successful_run(self):
        import json

        with tempfile.TemporaryDirectory() as tmp:
            logs = Path(tmp)
            (logs / "run-morning-test.json").write_text(
                json.dumps({"steps": [
                    {"step": "mirror", "status": "ok", "copied": 93, "failed": 0}
                ]}),
                encoding="utf-8",
            )
            with unittest.mock.patch.object(H, "mirror_behind", return_value=None):
                self.assertIsNone(H.mirror_issue(DAY, log_dir=logs))

    def test_a_stale_failure_log_is_ignored_once_the_mirror_caught_up(self):
        """實物追到 = 唔嗌，就算最近一個 run log 仲寫住失敗。

        2026-08-21 就係咁：10:27 嗰 run 因為 TCC 未授權而 `copied:0`，Kelvin 15:02
        授咗 Full Disk Access，鏡像已經追返 —— 但體檢照嗌足一日。
        """
        import json
        with tempfile.TemporaryDirectory() as tmp:
            root, mirror = self._tree(tmp)
            logs = Path(tmp) / "logs"
            logs.mkdir()
            (logs / "run-morning-test.json").write_text(json.dumps({"steps": [
                {"step": "mirror", "status": "partial", "copied": 0, "failed": 8,
                 "gave_up": True, "first_error": "PermissionError: nope"}]}))
            with unittest.mock.patch.object(
                    H, "mirror_behind", side_effect=lambda *a, **k: []):
                self.assertIsNone(H.mirror_issue("2026-08-21", log_dir=logs))

    def _mirror(self, step: dict) -> str | None:
        import json
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "run-evening-test.json").write_text(
                json.dumps({"steps": [dict(step, step="mirror")]}))
            return H.mirror_issue(log_dir=Path(tmp))

    def test_mirror_that_copied_most_files_is_not_an_alert(self):
        """鏡像係 best-effort —— 「263 入咗、1 個退去 fallback」報上去只係雜訊。

        而雜訊嘅代價就係下次真出事嗰下冇人再睇。本機係正本，Cloudflare 由本機
        發，所以個別檔入唔到 Drive 影響唔到預測同發佈。
        """
        self.assertIsNone(self._mirror(
            {"status": "partial", "copied": 263, "failed": 1,
             "first_error": "PermissionError: [Errno 1] Operation not permitted"}))

    def test_mirror_that_achieved_nothing_is_reported(self):
        issue = self._mirror(
            {"status": "partial", "copied": 0, "failed": 8, "gave_up": True,
             "first_error": "PermissionError: [Errno 1] Operation not permitted"})
        self.assertIn("Drive 鏡像", issue)
        self.assertIn("Operation not permitted", issue)

    def test_mirror_that_gave_up_after_partial_progress_is_reported(self):
        issue = self._mirror(
            {"status": "partial", "copied": 12, "failed": 8, "gave_up": True,
             "first_error": "PermissionError: nope"})
        self.assertIn("Drive 鏡像", issue)

    def test_unconfigured_mirror_is_not_a_problem(self):
        self.assertIsNone(self._mirror({"status": "not-configured"}))

    def test_latest_partial_critical_step_is_reported(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run-evening-test.json"
            path.write_text(json.dumps({"steps": [
                {"step": "ingest-results", "status": "partial",
                 "detail": "reflector fallback only"}]}))
            issue = H.latest_step_issue("ingest-results", log_dir=Path(tmp))
        self.assertIn("partial", issue)
        self.assertIn("reflector fallback", issue)


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

    def test_diagnose_has_a_real_help_cli(self):
        import au_diagnose as D
        with self.assertRaises(SystemExit) as raised:
            D.main(["--help"])
        self.assertEqual(raised.exception.code, 0)


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
