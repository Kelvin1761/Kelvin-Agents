"""codex_delegate: 揀最新模型、讀額度、節流、唔准喺主 checkout 寫。"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["WC_DELEGATE_ALERTS"] = "0"  # 測試永遠唔發 Telegram
import codex_delegate as cd  # noqa: E402

# 派工開頭嘅型號檢查會真係叫 codex／agy —— 測試一律關咗，個別測試用 REAL_CHECK_VERSIONS 自己測
REAL_CHECK_VERSIONS = cd.check_model_versions
cd.check_model_versions = lambda *a, **k: []

MODELS = [
    {"slug": "gpt-6.2-sol", "visibility": "list"},
    {"slug": "gpt-6.1-sol", "visibility": "list"},
    {"slug": "gpt-6.1-terra", "visibility": "list"},
    {"slug": "gpt-5.6-terra", "visibility": "list"},
    {"slug": "gpt-6.10-terra", "visibility": "hide"},
    {"slug": "gpt-6-luna", "visibility": "list"},
    {"slug": "codex-auto-review", "visibility": "hide"},
]


class LatestModelTest(unittest.TestCase):
    def test_picks_newest_listed_version_per_family(self):
        self.assertEqual(cd.latest_model("sol", MODELS), "gpt-6.2-sol")
        # hidden 6.10 唔計；6.1 > 5.6
        self.assertEqual(cd.latest_model("terra", MODELS), "gpt-6.1-terra")
        self.assertEqual(cd.latest_model("luna", MODELS), "gpt-6-luna")

    def test_numeric_not_lexical_version_order(self):
        models = [{"slug": "gpt-6.9-sol"}, {"slug": "gpt-6.10-sol"}]
        self.assertEqual(cd.latest_model("sol", models), "gpt-6.10-sol")

    def test_fallback_when_family_missing(self):
        self.assertEqual(cd.latest_model("astra", MODELS), cd.FALLBACK_MODELS["astra"])


class ModelCatalogTest(unittest.TestCase):
    def setUp(self):
        cd._CATALOG = None

    def tearDown(self):
        cd._CATALOG = None

    def test_prefers_live_catalog_so_new_models_are_used_at_once(self):
        live = json.dumps({"models": [{"slug": "gpt-7-terra", "visibility": "list"}]})
        with mock.patch.object(cd.subprocess, "run",
                               return_value=mock.Mock(returncode=0, stdout=live, stderr="")):
            self.assertEqual(cd.latest_model("terra"), "gpt-7-terra")

    def test_falls_back_to_cache_file_when_cli_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "models_cache.json").write_text(json.dumps({"models": MODELS}))
            with mock.patch.object(cd, "CODEX_HOME", Path(tmp)), \
                    mock.patch.object(cd.subprocess, "run", side_effect=FileNotFoundError):
                self.assertEqual(cd.latest_model("sol"), "gpt-6.2-sol")

    def test_chore_is_luna_and_writes(self):
        family, _, sandbox = cd.ROLES["chore"]
        self.assertEqual((family, sandbox), ("luna", "workspace-write"))


def _limits(weekly_used, week_left_h, five_used=0.0, now=1_000_000.0):
    return cd.Limits(
        five_hour=cd.Window(five_used, 300, now + 3600),
        weekly=cd.Window(weekly_used, 10080, now + week_left_h * 3600),
        observed_at=now,
    )


class BudgetStateTest(unittest.TestCase):
    NOW = 1_000_000.0

    def test_enough_headroom_is_normal(self):
        # 2026-11-24 實況：65% 用咗，仲有 ~82h → 剩 30pp 撐 3.4 日
        self.assertEqual(cd.budget_state(_limits(65, 82), now=self.NOW)[0], "normal")
        self.assertEqual(cd.budget_state(_limits(0, 168), now=self.NOW)[0], "normal")

    def test_thin_headroom_is_tight(self):
        # 90% 用咗、仲有 2 日：剩 5pp < 8pp
        self.assertEqual(cd.budget_state(_limits(90, 48), now=self.NOW)[0], "tight")

    def test_weekly_cap_stops(self):
        self.assertEqual(cd.budget_state(_limits(96, 10), now=self.NOW)[0], "stop")

    def test_five_hour_cap_stops(self):
        self.assertEqual(cd.budget_state(_limits(10, 150, five_used=90), now=self.NOW)[0], "stop")

    def test_reset_window_counts_as_zero(self):
        limits = cd.Limits(None, cd.Window(99, 10080, self.NOW - 1), self.NOW - 7200)
        self.assertEqual(cd.budget_state(limits, now=self.NOW)[0], "normal")

    def test_unknown_without_data(self):
        self.assertEqual(cd.budget_state(None)[0], "unknown")

    def test_role_gating(self):
        self.assertTrue(cd.role_allowed("grunt", "normal"))
        self.assertFalse(cd.role_allowed("grunt", "tight"))
        self.assertTrue(cd.role_allowed("review", "tight"))
        # Luna 最平，收緊都照派（Kelvin 2026-11-24）
        self.assertTrue(cd.role_allowed("chore", "tight"))
        self.assertTrue(cd.role_allowed("quick", "tight"))
        self.assertFalse(cd.role_allowed("deep", "tight"))
        self.assertFalse(cd.role_allowed("review", "stop"))


class ReadLimitsTest(unittest.TestCase):
    def test_reads_last_rate_limits_from_newest_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            day = Path(tmp) / "2026" / "11" / "24"
            day.mkdir(parents=True)
            old = day / "rollout-old.jsonl"
            new = day / "rollout-new.jsonl"

            def ev(used):
                return json.dumps({"type": "event_msg", "payload": {"type": "token_count", "rate_limits": {
                    "primary": {"used_percent": 3.0, "window_minutes": 300, "resets_at": 2},
                    "secondary": {"used_percent": used, "window_minutes": 10080, "resets_at": 9}}}})

            old.write_text(ev(10) + "\n")
            new.write_text(ev(40) + "\n" + '{"type":"x"}\n' + ev(65) + "\n")
            os.utime(old, (time.time() - 100, time.time() - 100))
            limits = cd.read_limits(Path(tmp))
            self.assertIsNotNone(limits)
            self.assertEqual(limits.weekly.used, 65)
            self.assertEqual(limits.five_hour.window_minutes, 300)

    def test_missing_dir_returns_none(self):
        self.assertIsNone(cd.read_limits(Path("/nonexistent/codex/sessions")))


class RunGuardTest(unittest.TestCase):
    def _args(self, **kw):
        base = dict(role="grunt", prompt_file=None, cd=None, out=None, title=None, model=None,
                    effort=None, reply_limit=300, timeout=10, force=False)
        base.update(kw)
        return type("A", (), base)()

    def test_write_target_rejects_primary_and_its_subdirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            primary = Path(tmp) / "repo"
            (primary / ".agents" / "scripts").mkdir(parents=True)
            self.assertIsNotNone(cd.write_target_problem(primary, primary))
            # Sol 覆核搵到：子目錄以前可以繞過
            self.assertIsNotNone(cd.write_target_problem(primary / ".agents" / "scripts", primary))
            # 唔係 git repo 都唔准寫
            other = Path(tmp) / "plain"
            other.mkdir()
            self.assertIsNotNone(cd.write_target_problem(other, primary))

    def test_write_role_refuses_primary_checkout(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(cd, "PRIMARY_REPO", Path(tmp)), \
                mock.patch.object(cd, "read_limits", return_value=None), \
                mock.patch.object(cd.subprocess, "run") as run:
            self.assertEqual(cd.cmd_run(self._args(cd=tmp)), 2)
            run.assert_not_called()

    def test_force_cannot_override_stop(self):
        with mock.patch.object(cd, "read_limits", return_value=_limits(99, 5, now=time.time())), \
                mock.patch.object(cd.subprocess, "run") as run:
            self.assertEqual(cd.cmd_run(self._args(role="review", force=True)), 3)
            run.assert_not_called()

    def test_tight_blocks_grunt_unless_forced(self):
        with mock.patch.object(cd, "read_limits", return_value=_limits(90, 48, now=time.time())), \
                mock.patch.object(cd.subprocess, "run") as run:
            self.assertEqual(cd.cmd_run(self._args(role="grunt")), 3)
            run.assert_not_called()

    def test_missing_brief_is_usage_error(self):
        with mock.patch.object(cd, "read_limits", return_value=None):
            self.assertEqual(cd.cmd_run(self._args(role="review", prompt_file="/nonexistent/brief.md")), 2)

    def test_success_needs_turn_completed_and_fresh_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.md"
            brief = Path(tmp) / "brief.md"
            brief.write_text("x")
            out.write_text("stale answer from last run")

            def fake_run(cmd, **kw):
                self.assertEqual(cmd[-1], "-")
                self.assertIn("唔准 git commit", kw["input"])
                return mock.Mock(returncode=0, stdout='{"type":"turn.started"}\n', stderr="")

            with mock.patch.object(cd, "read_limits", return_value=None), \
                    mock.patch.object(cd, "_CATALOG", MODELS), \
                    mock.patch.object(cd, "append_ledger", return_value=Path(tmp) / "l"), \
                    mock.patch.object(cd.subprocess, "run", side_effect=fake_run):
                rc = cd.cmd_run(self._args(role="review", prompt_file=str(brief), out=str(out), cd=tmp))
            self.assertEqual(rc, 1)  # 冇 turn.completed、舊輸出已刪
            self.assertFalse(out.exists())

    def test_write_command_opens_dot_dirs_but_never_ephemeral(self):
        with tempfile.TemporaryDirectory() as tmp:
            w = Path(tmp)
            (w / ".agents").mkdir()
            cmd = cd.build_command("grunt", w, w / "o.md", model="gpt-6.1-terra")
            self.assertIn(str(w / ".agents"), cmd)
            self.assertNotIn(str(w / ".claude"), cmd)  # 唔存在就唔加
            self.assertNotIn(str(w / ".git"), cmd)
            self.assertNotIn("--ephemeral", cmd)  # 要留 session 檔先讀到額度
            review = cd.build_command("review", w, w / "o.md", model="gpt-6.2-sol")
            self.assertIn("read-only", review)
            self.assertNotIn("--add-dir", review)


class LedgerTest(unittest.TestCase):
    def test_summary_sums_per_role_and_skips_old_and_bad_lines(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {"WONGCHOI_CONTROL_STATE_ROOT": tmp}):
            now = time.time()
            cd.append_ledger({"ts": now, "role": "review", "ok": True, "input_tokens": 100, "output_tokens": 10})
            cd.append_ledger({"ts": now, "role": "review", "ok": False, "input_tokens": 50, "output_tokens": None})
            cd.append_ledger({"ts": now - 8 * 86400, "role": "review", "ok": True, "input_tokens": 999})
            cd.append_ledger({"ts": now, "role": "grunt", "ok": True, "input_tokens": 7, "output_tokens": 3})
            with (Path(tmp) / cd.LEDGER_NAME).open("a") as fh:
                fh.write("{not json\n")
            summary = cd.ledger_summary()
            self.assertEqual(summary["review"], {"runs": 2, "ok": 1, "input": 150, "output": 10})
            self.assertEqual(summary["grunt"], {"runs": 1, "ok": 1, "input": 7, "output": 3})



class OffloadModeTest(unittest.TestCase):
    NOW = 1_800_000_000.0
    DAY = 86400.0

    def codex(self, used, days_left):
        week = cd.Window(used, 10080, self.NOW + days_left * self.DAY)
        return cd.Limits(None, week, self.NOW)

    def mode(self, codex_state, codex, claude_used, claude_days_left):
        return cd.offload_mode(codex_state, codex, claude_used,
                               self.NOW + claude_days_left * self.DAY, now=self.NOW)[0]

    def test_claude_running_hot_offloads_max(self):
        # 2026-11-24 實況：Claude 42%、時間先過 12%
        self.assertEqual(self.mode("normal", self.codex(50, 4), 42, 6.2), "offload-max")

    def test_on_pace_is_balanced(self):
        self.assertEqual(self.mode("normal", self.codex(50, 4), 30, 5), "balanced")

    def test_codex_stop_means_claude_only(self):
        self.assertEqual(self.mode("stop", self.codex(96, 4), 90, 1), "claude-only")

    def test_both_tight_is_light(self):
        self.assertEqual(self.mode("tight", self.codex(85, 4), 60, 4), "offload-light")

    def test_codex_tight_claude_idle_keeps_claude(self):
        self.assertEqual(self.mode("tight", self.codex(85, 4), 5, 4), "keep-claude")

    def test_codex_about_to_reset_with_headroom_use_it(self):
        # Claude 正常，但 Codex 一日後重置仲剩 45pp
        self.assertEqual(self.mode("normal", self.codex(50, 1), 30, 5), "offload-max")

    def test_claude_critical_even_if_late_in_week(self):
        self.assertEqual(self.mode("normal", self.codex(50, 4), 88, 0.5), "offload-max")

    def test_spend_freely_ignores_pace(self):
        mode = cd.offload_mode("normal", self.codex(50, 4), 42, self.NOW + 6.2 * self.DAY,
                               now=self.NOW, spend_freely=True)[0]
        self.assertEqual(mode, "balanced")

    def test_spend_freely_still_guards_critical(self):
        mode = cd.offload_mode("normal", self.codex(50, 4), 90, self.NOW + 1 * self.DAY,
                               now=self.NOW, spend_freely=True)[0]
        self.assertEqual(mode, "offload-max")

    def test_spend_freely_with_codex_tight_keeps_claude(self):
        mode = cd.offload_mode("tight", self.codex(85, 4), 60, self.NOW + 4 * self.DAY,
                               now=self.NOW, spend_freely=True)[0]
        self.assertEqual(mode, "keep-claude")

    def test_switch_file_expires(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "claude_pacing.json"
            p.write_text(json.dumps({"spend_freely_until": "2030-01-01T00:00:00Z", "reason": "r"}))
            self.assertIsNotNone(cd.spend_freely_until(now=self.NOW, path=p))
            self.assertIsNone(cd.spend_freely_until(now=cd._parse_ts("2030-01-02T00:00:00Z"), path=p))
            p.write_text("garbage")
            self.assertIsNone(cd.spend_freely_until(now=self.NOW, path=p))

    def test_pacing_cli_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.dict(os.environ, {"WONGCHOI_CONTROL_STATE_ROOT": tmp}):
            self.assertEqual(cd.main(["pacing", "--spend-freely-until", "2099-01-01T00:00:00Z"]), 0)
            self.assertIsNotNone(cd.spend_freely_until())
            self.assertEqual(cd.main(["pacing", "--clear"]), 0)
            self.assertIsNone(cd.spend_freely_until())

    def test_status_prints_mode(self):
        import io, contextlib
        buf = io.StringIO()
        with mock.patch.object(cd, "read_limits", return_value=self.codex(50, 4)), \
             mock.patch.object(cd, "spend_freely_until", return_value=None), \
             mock.patch.object(cd, "gemini_catalog", return_value=[]), \
             mock.patch.object(cd, "gemini_paused_until", return_value=None), \
             mock.patch.object(cd, "ledger_summary", return_value={}), \
             mock.patch.object(cd, "latest_model", return_value="m"), \
             contextlib.redirect_stdout(buf):
            cd.main(["status", "--claude-weekly", "42", "--claude-resets", "2099-01-01T00:00:00Z", "--json"])
        self.assertIn("分工模式：", buf.getvalue())
        self.assertIn('"mode"', buf.getvalue())


AGY = ["gemini-4-hydrogen-high", "gemini-4-hydrogen-xhigh", "gemini-4-hydrogen-medium", "gemini-4-hydrogen-low",
       "gemini-3.8-flash-high", "gemini-3.8-flash-medium", "gemini-3.8-flash-low", "claude-sonnet-4-6",
       "gpt-oss-120b-medium"]


class GeminiModelTest(unittest.TestCase):
    def test_picks_latest_non_flash(self):
        self.assertEqual(cd.latest_gemini("high", AGY), "gemini-4-hydrogen-high")
        self.assertEqual(cd.latest_gemini("medium", AGY), "gemini-4-hydrogen-medium")

    def test_never_picks_flash_or_lite(self):
        # Kelvin 2026-11-25：Flash 就退役兼太弱；就算 flash 版本號較新都唔揀
        slugs = ["gemini-5-flash-high", "gemini-5-lite-high", "gemini-4-hydrogen-high"]
        self.assertEqual(cd.latest_gemini("high", slugs), "gemini-4-hydrogen-high")

    def test_follows_new_release(self):
        slugs = AGY + ["gemini-4.1-helium-high"]
        self.assertEqual(cd.latest_gemini("high", slugs), "gemini-4.1-helium-high")

    def test_nearest_effort_when_missing(self):
        self.assertEqual(cd.latest_gemini("xhigh", ["gemini-4-hydrogen-high", "gemini-4-hydrogen-low"]),
                         "gemini-4-hydrogen-high")

    def test_fallback_when_catalog_empty(self):
        self.assertEqual(cd.latest_gemini("high", []), "gemini-4-hydrogen-high")

    def test_quota_error_detection(self):
        self.assertTrue(cd._gemini_quota_error("Resource has been exhausted (e.g. check quota). (Status: 429)"))
        self.assertTrue(cd._gemini_quota_error("RESOURCE_EXHAUSTED"))
        self.assertFalse(cd._gemini_quota_error("timeout after 1429s"))
        self.assertFalse(cd._gemini_quota_error("empty prompt"))


class GeminiRunTest(unittest.TestCase):
    def run_with(self, stdout, returncode=0):
        with tempfile.TemporaryDirectory() as tmp:
            brief = Path(tmp) / "b.md"
            brief.write_text("做嘢")
            out = Path(tmp) / "out" / "r.md"
            fake = mock.Mock(stdout=stdout, stderr="", returncode=returncode)
            with mock.patch.dict(os.environ, {"WONGCHOI_CONTROL_STATE_ROOT": tmp}), \
                 mock.patch.object(cd, "latest_gemini", return_value="gemini-4-hydrogen-high"), \
                 mock.patch.object(cd.subprocess, "run", return_value=fake) as run:
                rc = cd.main(["run", "third", "--cd", tmp, "--prompt-file", str(brief), "--out", str(out)])
                ledger = (Path(tmp) / cd.LEDGER_NAME).read_text().strip().splitlines()
                paused = cd.gemini_paused_until()
                reply = out.read_text() if out.exists() else ""
            cmd = run.call_args[0][0]
            brief_dir = Path(cmd[cmd.index("--add-dir") + 1])
            return rc, json.loads(ledger[-1]), paused, reply, cmd, brief_dir

    def test_success_writes_reply_and_ledger(self):
        rc, entry, paused, reply, cmd, brief_dir = self.run_with(json.dumps(
            {"status": "SUCCESS", "response": "冇問題", "usage": {"input_tokens": 10, "output_tokens": 2}}))
        self.assertEqual(rc, 0)
        self.assertEqual(reply.strip(), "冇問題")
        self.assertEqual(entry["provider"], "gemini")
        self.assertTrue(entry["ok"])
        self.assertIsNone(paused)
        self.assertIn("plan", cmd)            # 唯讀
        self.assertFalse(brief_dir.exists())  # 臨時 brief 清走

    def test_quota_error_pauses(self):
        rc, entry, paused, reply, _, brief_dir = self.run_with(json.dumps(
            {"status": "ERROR", "response": "", "error": "Resource has been exhausted (Status: 429)"}))
        self.assertEqual(rc, 1)
        self.assertFalse(entry["ok"])
        self.assertIsNotNone(paused)
        self.assertFalse(brief_dir.exists())

    def test_paused_refuses(self):
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.dict(os.environ, {"WONGCHOI_CONTROL_STATE_ROOT": tmp}):
            cd.gemini_quota_file().write_text(json.dumps({"exhausted_until": time.time() + 99}))
            self.assertEqual(cd.main(["run", "third", "--prompt-file", __file__]), 3)  # third 冇後備

    def test_garbage_output_is_failure(self):
        rc, entry, *_ = self.run_with("not json\n[1,2]")
        self.assertEqual(rc, 1)
        self.assertFalse(entry["ok"])


class TeamSplitTest(unittest.TestCase):
    """Kelvin 2026-11-25 分工：Hydrogen 做 quick／chore／sprint，Luna／Terra 後備；預算；收貨評分。"""

    def limits(self, used=40.0):
        now = time.time()
        return cd.Limits(None, cd.Window(used, 10080, now + 3 * 86400), now)

    def test_family_spent_and_budget(self):
        lim = self.limits()
        now = time.time()
        entries = [
            {"ts": now - 60, "model": "gpt-6.2-astra", "weekly_pp": 9.0},
            {"ts": now - 50, "model": "gpt-6.2-astra", "weekly_pp": 7.0},
            {"ts": now - 40, "model": "gpt-6.1-terra", "weekly_pp": 2.0},
            {"ts": now - 30, "model": "gpt-6.1-terra", "weekly_pp": None},
            {"ts": now - 8 * 86400, "model": "gpt-6.2-sol", "weekly_pp": 50.0},  # 上個窗
            {"ts": now - 20, "type": "grade", "grade": "accepted", "run_ts": now - 40},
        ]
        spent = cd.family_spent(lim, entries)
        self.assertAlmostEqual(spent["astra"], 16.0)
        self.assertAlmostEqual(spent["terra"], 2.0)
        self.assertNotIn("sol", spent)
        self.assertIn("Astra", cd.over_budget("astra", lim, entries))
        self.assertIsNone(cd.over_budget("terra", lim, entries))
        self.assertIsNone(cd.over_budget("luna", lim, entries))

    def test_grade_summary_maps_to_model(self):
        now = time.time()
        entries = [
            {"ts": 100.0, "model": "gemini-4-hydrogen-high", "ok": True},
            {"ts": 200.0, "model": "gpt-6.1-terra", "ok": True},
            {"ts": now, "type": "grade", "run_ts": 100.0, "grade": "accepted"},
            {"ts": now, "type": "grade", "run_ts": 100.0, "grade": "rework"},
            {"ts": now, "type": "grade", "run_ts": 200.0, "grade": "redo"},
        ]
        g = cd.grade_summary(entries=entries)
        self.assertEqual(g["gemini-4-hydrogen-high"], {"rework": 1})  # 同一次 run 重評，只計最後一次
        self.assertEqual(g["gpt-6.1-terra"], {"redo": 1})

    def test_grade_cli_last(self):
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.dict(os.environ, {"WONGCHOI_CONTROL_STATE_ROOT": tmp}):
            self.assertEqual(cd.main(["grade", "accepted"]), 2)  # 冇 run
            cd.append_ledger({"ts": 1.0, "role": "sprint", "model": "gemini-4-hydrogen-high", "ok": True})
            self.assertEqual(cd.main(["grade", "rework", "--note", "漏 edge case"]), 0)
            self.assertEqual(cd.grade_summary()["gemini-4-hydrogen-high"], {"rework": 1})
            # 評分唔計入委派次數
            self.assertEqual(cd.ledger_summary(days=100000)["sprint"]["runs"], 1)

    def test_quick_falls_back_to_luna_when_gemini_paused(self):
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.dict(os.environ, {"WONGCHOI_CONTROL_STATE_ROOT": tmp}), \
             mock.patch.object(cd, "gemini_unavailable", return_value="Gemini 額度用完"), \
             mock.patch.object(cd, "read_limits", return_value=None), \
             mock.patch.object(cd, "cmd_run_gemini") as gem, \
             mock.patch.object(cd, "latest_model", return_value="gpt-6-luna"), \
             mock.patch.object(cd.subprocess, "run", side_effect=FileNotFoundError):
            brief = Path(tmp) / "b.md"
            brief.write_text("x")
            cd.main(["run", "quick", "--prompt-file", str(brief), "--out", str(Path(tmp) / "o.md")])
            gem.assert_not_called()
            entry = json.loads((Path(tmp) / cd.LEDGER_NAME).read_text().splitlines()[-1])
            self.assertEqual(entry["role"], "quick")
            self.assertEqual(entry["model"], "gpt-6-luna")

    def test_sprint_falls_back_to_terra(self):
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.dict(os.environ, {"WONGCHOI_CONTROL_STATE_ROOT": tmp}), \
             mock.patch.object(cd, "gemini_unavailable", return_value="agy 唔喺 PATH"), \
             mock.patch.object(cd, "read_limits", return_value=None), \
             mock.patch.object(cd, "write_target_problem", return_value=None), \
             mock.patch.object(cd, "changed_files", return_value=[]), \
             mock.patch.object(cd, "latest_model", side_effect=lambda f: f"gpt-x-{f}"), \
             mock.patch.object(cd.subprocess, "run", side_effect=FileNotFoundError):
            brief = Path(tmp) / "b.md"
            brief.write_text("x")
            cd.main(["run", "sprint", "--cd", tmp, "--prompt-file", str(brief), "--out", str(Path(tmp) / "o.md")])
            entry = json.loads((Path(tmp) / cd.LEDGER_NAME).read_text().splitlines()[-1])
            self.assertEqual(entry["role"], "grunt")
            self.assertEqual(entry["model"], "gpt-x-terra")

    def test_provider_codex_rejects_gemini_only_role(self):
        self.assertEqual(cd.main(["run", "third", "--provider", "codex", "--prompt-file", __file__]), 2)

    def test_provider_gemini_rejects_codex_only_role(self):
        self.assertEqual(cd.main(["run", "deep", "--provider", "gemini", "--prompt-file", __file__]), 2)

    def test_stale_window_does_not_lock_budget(self):
        now = time.time()
        stale = cd.Limits(None, cd.Window(90.0, 10080, now - 60), now - 86400)  # 已經重置咗嘅舊窗
        entries = [{"ts": now - 3 * 86400, "model": "gpt-6.2-astra", "weekly_pp": 40.0}]
        self.assertEqual(cd.family_spent(stale, entries), {})
        self.assertIsNone(cd.over_budget("astra", stale, entries))

    def test_third_has_no_fallback(self):
        # 快速獨立檢查冇 Codex 替身 —— B 級覆核唔靠佢，用唔到就唔派
        with mock.patch.object(cd, "gemini_unavailable", return_value="Gemini 額度用完"):
            self.assertEqual(cd.main(["run", "third", "--prompt-file", __file__]), 3)

    def test_model_flag_cannot_bypass_flash_ban(self):
        with mock.patch.object(cd, "gemini_unavailable", return_value=None):
            self.assertEqual(cd.main(["run", "quick", "--model", "gemini-3.8-flash-high", "--prompt-file", __file__]), 2)

    def test_provider_codex_forces_luna(self):
        with mock.patch.object(cd, "gemini_unavailable", return_value=None), \
             mock.patch.object(cd, "cmd_run_gemini", return_value=0) as gem, \
             mock.patch.object(cd, "read_limits", return_value=None), \
             mock.patch.object(cd, "latest_model", return_value="gpt-6-luna"), \
             mock.patch.object(cd, "append_ledger", return_value=Path("/x")), \
             mock.patch.object(cd.subprocess, "run", side_effect=FileNotFoundError):
            cd.main(["run", "quick", "--provider", "codex", "--prompt-file", __file__])
            gem.assert_not_called()

    def test_astra_over_budget_refuses(self):
        lim = self.limits()
        with mock.patch.object(cd, "read_limits", return_value=lim), \
             mock.patch.object(cd, "over_budget", return_value="Astra 今週已用 16pp ≥ 預算 15pp"):
            self.assertEqual(cd.main(["run", "design", "--prompt-file", __file__]), 3)

    def test_gemini_write_mode_uses_accept_edits(self):
        with tempfile.TemporaryDirectory() as tmp:
            brief = Path(tmp) / "b.md"
            brief.write_text("改檔")
            fake = mock.Mock(stdout=json.dumps({"status": "SUCCESS", "response": "改咗"}), stderr="", returncode=0)
            seen = {}

            def run(cmd, **kw):
                seen["cmd"] = cmd
                bf = Path(cmd[cmd.index("--add-dir") + 1]) / "brief.md"
                seen["brief"] = bf.read_text()
                return fake

            with mock.patch.dict(os.environ, {"WONGCHOI_CONTROL_STATE_ROOT": tmp}), \
                 mock.patch.object(cd, "gemini_unavailable", return_value=None), \
                 mock.patch.object(cd, "write_target_problem", return_value=None), \
                 mock.patch.object(cd, "changed_files", return_value=["a.py"]), \
                 mock.patch.object(cd, "latest_gemini", return_value="gemini-4-hydrogen-high"), \
                 mock.patch.object(cd.subprocess, "run", side_effect=run):
                rc = cd.main(["run", "sprint", "--cd", tmp, "--prompt-file", str(brief)])
                entry = json.loads((Path(tmp) / cd.LEDGER_NAME).read_text().splitlines()[-1])
        self.assertEqual(rc, 0)
        self.assertIn("accept-edits", seen["cmd"])
        self.assertIn("冇權行任何 shell 命令", seen["brief"])
        self.assertEqual(entry["changed_files"], 1)

    def test_gemini_write_refuses_primary_checkout(self):
        with mock.patch.object(cd, "gemini_unavailable", return_value=None), \
             mock.patch.object(cd, "write_target_problem", return_value="主 checkout 唔准寫"):
            self.assertEqual(cd.main(["run", "chore", "--prompt-file", __file__]), 2)

    def test_denied_action_with_empty_reply_is_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            brief = Path(tmp) / "b.md"
            brief.write_text("x")
            out = {"status": "SUCCESS", "response": "", "denied_actions": [{"action": "command", "display_name": "Bash"}]}
            fake = mock.Mock(stdout=json.dumps(out), stderr="", returncode=0)
            with mock.patch.dict(os.environ, {"WONGCHOI_CONTROL_STATE_ROOT": tmp}), \
                 mock.patch.object(cd, "gemini_unavailable", return_value=None), \
                 mock.patch.object(cd, "latest_gemini", return_value="gemini-4-hydrogen-low"), \
                 mock.patch.object(cd.subprocess, "run", return_value=fake):
                rc = cd.main(["run", "quick", "--cd", tmp, "--prompt-file", str(brief)])
                entry = json.loads((Path(tmp) / cd.LEDGER_NAME).read_text().splitlines()[-1])
        self.assertEqual(rc, 1)
        self.assertIn("被拒動作", entry["error"])



class RouteTest(unittest.TestCase):
    def lim(self):
        now = time.time()
        return cd.Limits(None, cd.Window(30.0, 10080, now + 3 * 86400), now)

    def r(self, task, state="normal", gem=None, claude=40.0, spend=False, budget=None, bad=None):
        with mock.patch.object(cd, "over_budget", side_effect=lambda fam, lim, entries=None: (budget or {}).get(fam)), \
             mock.patch.object(cd, "model_is_bad", side_effect=lambda m: (bad or {}).get(m)), \
             mock.patch.object(cd, "latest_model", side_effect=lambda f: cd.FALLBACK_MODELS[f]), \
             mock.patch.object(cd, "latest_gemini", return_value="gemini-4-hydrogen-high"):
            return cd.route(task, self.lim(), state, gem, claude, spend)

    def test_default_chain_first_choice(self):
        self.assertEqual((self.r("lookup")["role"], self.r("lookup")["provider"]), ("quick", "gemini"))
        self.assertEqual(self.r("feature")["role"], "sprint")
        self.assertEqual(self.r("review")["role"], "review")
        self.assertEqual(self.r("design")["role"], "design")

    def test_gemini_down_falls_to_codex(self):
        r = self.r("feature", gem="Gemini 額度用完")
        self.assertEqual((r["role"], r["provider"]), ("grunt", "codex"))
        self.assertEqual(len(r["skipped"]), 1)

    def test_sol_over_budget_opus_reviews(self):
        r = self.r("review", budget={"sol": "Sol 超預算"})
        self.assertEqual(r["role"], "opus")

    def test_review_never_falls_to_hydrogen(self):
        for args in ({"state": "stop"}, {"budget": {"sol": "x"}}):
            r = self.r("review", gem=None, **args)
            self.assertNotEqual(r["provider"], "gemini")

    def test_codex_tight_blocks_grunt(self):
        r = self.r("heavy", state="tight")
        self.assertEqual(r["role"], "opus")

    def test_everything_exhausted(self):
        r = self.r("feature", state="stop", gem="x", claude=97.0)
        self.assertIsNone(r["role"])
        self.assertEqual(len(r["skipped"]), 3)

    def test_spend_freely_opus_first_except_independent_checks(self):
        self.assertEqual(self.r("lookup", spend=True)["role"], "opus")
        self.assertEqual(self.r("heavy", spend=True)["role"], "opus")
        self.assertEqual(self.r("review", spend=True)["role"], "review")
        self.assertEqual(self.r("arbitrate", spend=True)["role"], "deep")

    def test_bad_model_is_skipped(self):
        r = self.r("review", bad={"gpt-6.2-sol": "Sol 標咗唔正常"})
        self.assertEqual(r["role"], "opus")
        r = self.r("feature", bad={"gemini-4-hydrogen-high": "Hydrogen 唔正常"})
        self.assertEqual(r["role"], "grunt")

    def test_design_falls_back_to_sol_then_opus(self):
        self.assertEqual(self.r("design", budget={"astra": "x"})["role"], "review")
        self.assertEqual(self.r("design", budget={"astra": "x", "sol": "y"})["role"], "opus")


class HealthTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"WONGCHOI_CONTROL_STATE_ROOT": self.tmp.name})
        self.env.start()
        self.sent = []
        self.alert = mock.patch.object(cd, "alert", side_effect=lambda t: self.sent.append(t) or True)
        self.alert.start()

    def tearDown(self):
        self.alert.stop()
        self.env.stop()
        self.tmp.cleanup()

    def test_two_failures_alert_once_then_recovery(self):
        m = "gpt-6.2-sol"
        entries = [{"ts": 1, "model": m, "ok": False}]
        cd.note_run_health(m, False, "timeout", entries)
        self.assertEqual(self.sent, [])  # 一次唔報
        entries.append({"ts": 2, "model": m, "ok": False})
        cd.note_run_health(m, False, "timeout", entries)
        entries.append({"ts": 3, "model": m, "ok": False})
        cd.note_run_health(m, False, "timeout", entries)
        self.assertEqual(len(self.sent), 1)  # 連續失敗只報一次
        self.assertIn("gpt-6.2-sol", self.sent[0])
        entries.append({"ts": 4, "model": m, "ok": True})
        cd.note_run_health(m, True, None, entries)
        self.assertEqual(len(self.sent), 2)
        self.assertIn("已恢復", self.sent[1])

    def test_other_model_failures_do_not_count(self):
        entries = [{"ts": 1, "model": "gpt-6.1-terra", "ok": False}, {"ts": 2, "model": "gpt-6.2-sol", "ok": False}]
        cd.note_run_health("gpt-6.2-sol", False, "x", entries)
        self.assertEqual(self.sent, [])

    def test_version_change_is_reported(self):
        with mock.patch.object(cd, "latest_model", side_effect=lambda f: cd.FALLBACK_MODELS[f]), \
             mock.patch.object(cd, "model_catalog", return_value=[{"slug": "x"}]), \
             mock.patch.object(cd, "gemini_unavailable", return_value="agy 唔喺 PATH"), \
             mock.patch.object(cd, "gemini_catalog", return_value=[]), \
             mock.patch.object(cd, "shutil_which", return_value=None):
            self.assertEqual(REAL_CHECK_VERSIONS(force=True), [])  # 第一次只記低
        newer = dict(cd.FALLBACK_MODELS, sol="gpt-6.3-sol")
        with mock.patch.object(cd, "latest_model", side_effect=lambda f: newer[f]), \
             mock.patch.object(cd, "model_catalog", return_value=[{"slug": "x"}]), \
             mock.patch.object(cd, "gemini_unavailable", return_value="agy 唔喺 PATH"), \
             mock.patch.object(cd, "gemini_catalog", return_value=[]), \
             mock.patch.object(cd, "shutil_which", return_value=None):
            msgs = REAL_CHECK_VERSIONS(force=True)
        self.assertEqual(len(msgs), 1)
        self.assertIn("gpt-6.2-sol → gpt-6.3-sol", msgs[0])
        self.assertEqual(len(self.sent), 1)

    def test_missing_catalog_alerts_once_a_day(self):
        with mock.patch.object(cd, "latest_model", side_effect=lambda f: cd.FALLBACK_MODELS[f]), \
             mock.patch.object(cd, "model_catalog", return_value=[]), \
             mock.patch.object(cd, "gemini_unavailable", return_value="agy 唔喺 PATH"), \
             mock.patch.object(cd, "gemini_catalog", return_value=[]), \
             mock.patch.object(cd, "shutil_which", return_value=None):
            REAL_CHECK_VERSIONS(today="2026-11-26", force=True)
            REAL_CHECK_VERSIONS(today="2026-11-26", force=True)
            REAL_CHECK_VERSIONS(today="2026-11-27", force=True)
        self.assertEqual(len(self.sent), 2)
        self.assertIn("後備型號", self.sent[0])

    def test_version_check_throttled(self):
        with mock.patch.object(cd, "latest_model", side_effect=lambda f: cd.FALLBACK_MODELS[f]) as lm, \
             mock.patch.object(cd, "model_catalog", return_value=[{"slug": "x"}]), \
             mock.patch.object(cd, "gemini_unavailable", return_value="x"), \
             mock.patch.object(cd, "gemini_catalog", return_value=[]), \
             mock.patch.object(cd, "shutil_which", return_value=None):
            REAL_CHECK_VERSIONS(force=True)
            calls = lm.call_count
            REAL_CHECK_VERSIONS()  # 6 個鐘內唔再查
            self.assertEqual(lm.call_count, calls)
        with mock.patch.dict(os.environ, {"WC_SKIP_VERSION_CHECK": "1"}):
            self.assertEqual(REAL_CHECK_VERSIONS(force=True), [])

    def test_flash_only_catalog_alerts(self):
        with mock.patch.object(cd, "latest_model", side_effect=lambda f: cd.FALLBACK_MODELS[f]), \
             mock.patch.object(cd, "model_catalog", return_value=[{"slug": "x"}]), \
             mock.patch.object(cd, "gemini_unavailable", return_value="x"), \
             mock.patch.object(cd, "gemini_catalog", return_value=["gemini-5-flash-high"]), \
             mock.patch.object(cd, "shutil_which", return_value="/opt/homebrew/bin/agy"):
            msgs = REAL_CHECK_VERSIONS(force=True)
        self.assertTrue(any("冇合格型號" in m for m in msgs))

    def test_failed_alert_is_retried(self):
        self.alert.stop()
        results = iter([False, True])
        with mock.patch.object(cd, "alert", side_effect=lambda t: next(results)) as al:
            m = "gpt-6.2-sol"
            entries = [{"ts": 1, "model": m, "ok": False}, {"ts": 2, "model": m, "ok": False}]
            cd.note_run_health(m, False, "x", entries)
            entries.append({"ts": 3, "model": m, "ok": False})
            cd.note_run_health(m, False, "x", entries)
            entries.append({"ts": 4, "model": m, "ok": False})
            cd.note_run_health(m, False, "x", entries)
            self.assertEqual(al.call_count, 2)  # 第一次發唔到 → 再試；發到之後唔再發
        self.alert.start()

    def test_alert_suppressed_in_tests(self):
        self.alert.stop()
        try:
            self.assertFalse(cd.alert("x"))
        finally:
            self.alert.start()

    def test_probe_missing_cli_is_failure(self):
        rcs = iter([0, 0, 0, 0, 3])
        fake = lambda cmd, **kw: mock.Mock(returncode=0 if cmd[0] == "git" else next(rcs),
                                           stderr="⛔ 唔派：agy 唔喺 PATH。", stdout="")
        with mock.patch.object(cd.subprocess, "run", side_effect=fake), \
             mock.patch.object(cd, "check_model_versions", return_value=[]), \
             mock.patch.object(cd, "_probe_slug", side_effect=lambda a: f"m-{a[0]}"):
            self.assertEqual(cd.main(["health", "--probe"]), 1)
        state = json.loads((Path(self.tmp.name) / "model_probe" / "latest.json").read_text())
        self.assertEqual(state["results"][-1]["status"], "failed")

    def test_probe_all_fail_retries_then_environment_alert(self):
        fake = lambda cmd, **kw: mock.Mock(returncode=0 if cmd[0] == "git" else 1, stderr="timeout after 300s", stdout="")
        with mock.patch.object(cd.subprocess, "run", side_effect=fake) as run, \
             mock.patch.object(cd, "check_model_versions", return_value=[]), \
             mock.patch.object(cd, "_probe_slug", side_effect=lambda a: f"m-{a[0]}"), \
             mock.patch.object(cd.time, "sleep") as sleep:
            self.assertEqual(cd.main(["health", "--probe"]), 1)
        sleep.assert_called_once_with(cd.PROBE_RETRY_WAIT)
        self.assertEqual(sum(1 for c in run.call_args_list if c[0][0][0] != "git"), 2 * len(cd.PROBES))
        self.assertEqual(len(self.sent), 1)
        self.assertIn("同時失敗", self.sent[0])
        state = json.loads((Path(self.tmp.name) / "model_probe" / "latest.json").read_text())
        self.assertTrue(state["environment_failure"])
        self.assertFalse(cd._load_health().get("models"))  # 環境問題唔會將模型標壞

    def test_probe_all_fail_then_recover_on_retry(self):
        rcs = iter([1] * len(cd.PROBES) + [0] * len(cd.PROBES))
        fake = lambda cmd, **kw: mock.Mock(returncode=0 if cmd[0] == "git" else next(rcs), stderr="x", stdout="")
        with mock.patch.object(cd.subprocess, "run", side_effect=fake), \
             mock.patch.object(cd, "check_model_versions", return_value=[]), \
             mock.patch.object(cd, "_probe_slug", side_effect=lambda a: f"m-{a[0]}"), \
             mock.patch.object(cd.time, "sleep"):
            self.assertEqual(cd.main(["health", "--probe"]), 0)
        self.assertEqual(self.sent, [])

    def test_probe_marks_bad_and_recovered(self):
        def go(rc_list):
            rcs = iter(rc_list)
            fake = lambda cmd, **kw: mock.Mock(returncode=0 if cmd[0] == "git" else next(rcs), stderr="boom", stdout="")
            with mock.patch.object(cd.subprocess, "run", side_effect=fake), \
                 mock.patch.object(cd, "check_model_versions", return_value=[]), \
                 mock.patch.object(cd, "_probe_slug", side_effect=lambda a: f"m-{a[0]}"):
                return cd.main(["health", "--probe"])
        self.assertEqual(go([0, 0, 1, 0, 0]), 1)
        self.assertEqual(cd.model_is_bad("m-review") is not None, True)
        self.assertEqual(go([0, 0, 0, 0, 0]), 0)
        self.assertIsNone(cd.model_is_bad("m-review"))
        self.assertIn("已恢復", self.sent[-1])

    def test_skip_run_health_env(self):
        with mock.patch.dict(os.environ, {"WC_SKIP_RUN_HEALTH": "1"}):
            entries = [{"ts": 1, "model": "m", "ok": False}, {"ts": 2, "model": "m", "ok": False}]
            cd.note_run_health("m", False, "x", entries)
        self.assertEqual(self.sent, [])

    def test_probe_writes_state_and_alerts_failures(self):
        rcs = iter([0, 0, 1, 3, 0])
        fake = lambda cmd, **kw: mock.Mock(returncode=0 if cmd[0] == "git" else next(rcs), stderr="boom", stdout="")
        with mock.patch.object(cd.subprocess, "run", side_effect=fake), \
             mock.patch.object(cd, "check_model_versions", return_value=[]), \
             mock.patch.object(cd, "_probe_slug", side_effect=lambda a: f"m-{a[0]}"):
            rc = cd.main(["health", "--probe"])
        self.assertEqual(rc, 1)
        state = json.loads((Path(self.tmp.name) / "model_probe" / "latest.json").read_text())
        self.assertEqual([r["status"] for r in state["results"]], ["ok", "ok", "failed", "skipped", "ok"])
        self.assertIn("Sol", self.sent[-1])

if __name__ == "__main__":
    unittest.main()