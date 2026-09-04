"""Release 分支名唔准含斜線。

git 嘅 ref 儲存唔容許 `refs/heads/codex` 同 `refs/heads/codex/release-…` 並存。
2026-09-04 呢個 repo 中招：一個已完全 merge 入 main 嘅 `codex` 分支令

  * 本地 `git checkout -b codex/release-…` → fatal: 'refs/heads/codex' exists
  * remote `git push`                      → remote rejected (directory file conflict)

而 `git push --dry-run` 報 "[new branch]" —— D/F 檢查喺 receive 嗰刻才做，
所以 dry-run 過咗，真 push 照失敗。個 release 已經建立、check 過、Telegram
發咗，但 commit 上唔到 remote（`push_exit_code: 1`）。

呢個 repo 其餘 25 個分支全部用 `codex-…` 連字號。
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SRC = ROOT / ".agents" / "skills" / "shared_wong_choi" / "release_manager.py"


class ReleaseBranchName(unittest.TestCase):
    def setUp(self):
        self.source = SRC.read_text(encoding="utf-8")

    def _literal(self):
        m = re.search(r'branch = "(codex[^"]*)" \+ datetime', self.source)
        self.assertIsNotNone(m, "搵唔到 release 分支名嘅字面值；呢個測試要跟住改")
        return m.group(1)

    def test_the_prefix_has_no_slash(self):
        prefix = self._literal()
        self.assertNotIn("/", prefix,
                         "斜線會令任何一個叫 `codex` 嘅分支封死成個命名空間")

    def test_the_prefix_matches_the_repo_convention(self):
        self.assertEqual(self._literal(), "codex-release-")

    def test_the_reason_is_written_down(self):
        """下一個人見到連字號睇落唔靚，一定要搵到點解唔可以改返斜線。"""
        self.assertIn("directory file conflict", self.source)


if __name__ == "__main__":
    unittest.main()
