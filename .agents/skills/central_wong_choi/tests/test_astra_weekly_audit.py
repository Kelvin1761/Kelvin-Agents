"""Astra 每週審計：揀 commit、跳過／額度／失敗路徑都要寫狀態檔同通知（Kelvin 2026-11-25）。"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import astra_weekly_audit as aa  # noqa: E402

COMMITS = [
    {"sha": "a" * 40, "subject": "feat(au): 改評分", "files": [
        ".agents/skills/au_racing/au_racing_engine/scoring.py", ".agents/skills/au_racing/tests/test_x.py"]},
    {"sha": "b" * 40, "subject": "docs: 實驗記錄", "files": ["docs/experiments/EXP.md"]},
    {"sha": "c" * 40, "subject": "test only", "files": ["x/tests/test_y.py", "Horse_Racing_Dashboard/tests/a.test.mjs"]},
]


class IsCodeTest(unittest.TestCase):
    def test_filters(self):
        self.assertTrue(aa.is_code(".agents/scripts/codex_delegate.py"))
        self.assertTrue(aa.is_code("run.sh"))
        self.assertFalse(aa.is_code(".agents/scripts/tests/test_codex_delegate.py"))
        self.assertFalse(aa.is_code("test_foo.py"))
        self.assertFalse(aa.is_code("docs/plans/x.py"))
        self.assertFalse(aa.is_code("README.md"))


class BriefTest(unittest.TestCase):
    def test_only_code_commits_and_files_listed(self):
        brief = aa.build_brief(COMMITS)
        self.assertIn("aaaaaaaaaa", brief)
        self.assertIn("scoring.py", brief)
        self.assertNotIn("test_x.py", brief)
        self.assertNotIn("bbbbbbbbbb", brief)
        self.assertNotIn("cccccccccc", brief)
        self.assertIn("唔准改檔", brief)


class MainPathsTest(unittest.TestCase):
    def run_main(self, commits, delegate_rc=0, report_text="冇發現"):
        with tempfile.TemporaryDirectory() as tmp:
            sent = []

            def fake_git(*args, cwd=None):
                return "f" * 40 + "\n" if args[0] == "rev-parse" else ""

            def fake_run(cmd, **kw):
                if "run" in cmd and str(aa.DELEGATE) in cmd and report_text is not None:
                    Path(cmd[cmd.index("--out") + 1]).write_text(report_text, encoding="utf-8")
                return mock.Mock(returncode=delegate_rc, stderr="⛔ 唔派：Astra 超預算" if delegate_rc == 3 else "")

            with mock.patch.dict(os.environ, {"WONGCHOI_CONTROL_STATE_ROOT": tmp}), \
                 mock.patch.object(aa, "git", side_effect=fake_git), \
                 mock.patch.object(aa, "weekly_commits", return_value=commits), \
                 mock.patch.object(aa.subprocess, "run", side_effect=fake_run), \
                 mock.patch.object(aa, "notify", side_effect=lambda t, d: sent.append(t)):
                rc = aa.main([])
                state = json.loads((Path(tmp) / "astra_audit" / "latest.json").read_text())
            return rc, state, sent

    def test_no_code_changes_skips(self):
        rc, state, sent = self.run_main(COMMITS[1:])
        self.assertEqual((rc, state["status"]), (0, "no_changes"))
        self.assertIn("冇 code 改動", sent[0])

    def test_success_writes_report_and_notifies(self):
        rc, state, sent = self.run_main(COMMITS, report_text="1. 高：scoring.py:10 吞錯")
        self.assertEqual((rc, state["status"]), (0, "succeeded"))
        self.assertIn("吞錯", sent[0])
        self.assertIn("只係診斷", sent[0])

    def test_quota_refusal_is_skip_not_failure(self):
        rc, state, sent = self.run_main(COMMITS, delegate_rc=3, report_text=None)
        self.assertEqual((rc, state["status"]), (0, "skipped_quota"))
        self.assertIn("額度", sent[0])

    def test_failure_is_reported(self):
        rc, state, sent = self.run_main(COMMITS, delegate_rc=1, report_text=None)
        self.assertEqual((rc, state["status"]), (1, "failed"))
        self.assertIn("失敗", sent[0])


if __name__ == "__main__":
    unittest.main()
