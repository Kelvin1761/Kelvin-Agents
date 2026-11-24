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
import codex_delegate as cd  # noqa: E402

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
             mock.patch.object(cd, "ledger_summary", return_value={}), \
             mock.patch.object(cd, "latest_model", return_value="m"), \
             contextlib.redirect_stdout(buf):
            cd.main(["status", "--claude-weekly", "42", "--claude-resets", "2099-01-01T00:00:00Z", "--json"])
        self.assertIn("分工模式：", buf.getvalue())
        self.assertIn('"mode"', buf.getvalue())

if __name__ == "__main__":
    unittest.main()
