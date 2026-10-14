"""unsaved_work_audit: the Stop hook and the 健康.sh scan must see unsaved work."""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import unsaved_work_audit as audit  # noqa: E402


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


class UnsavedWorkAuditTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.remote = root / "remote.git"
        self.repo = root / "repo"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.remote)], check=True)
        subprocess.run(["git", "clone", "-q", str(self.remote), str(self.repo)], check=True,
                       capture_output=True)
        _git(self.repo, "config", "user.email", "t@example.com")
        _git(self.repo, "config", "user.name", "t")
        (self.repo / "a.txt").write_text("a\n", encoding="utf-8")
        _git(self.repo, "add", "a.txt")
        _git(self.repo, "commit", "-q", "-m", "init")
        _git(self.repo, "push", "-q", "origin", "HEAD:main")
        _git(self.repo, "fetch", "-q", "origin")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _hook(self, payload: dict) -> str:
        buf = io.StringIO()
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))), redirect_stdout(buf):
            self.assertEqual(audit.run_hook(), 0)
        return buf.getvalue()

    def test_clean_repo_is_silent(self) -> None:
        self.assertEqual(self._hook({"cwd": str(self.repo)}), "")

    def test_dirty_repo_blocks_once(self) -> None:
        (self.repo / "a.txt").write_text("changed\n", encoding="utf-8")
        out = json.loads(self._hook({"cwd": str(self.repo)}))
        self.assertEqual(out["decision"], "block")
        self.assertIn("1 個檔未 commit", out["reason"])
        # second stop in the same chain must not loop
        self.assertEqual(self._hook({"cwd": str(self.repo), "stop_hook_active": True}), "")

    def test_unpushed_commit_counts(self) -> None:
        (self.repo / "b.txt").write_text("b\n", encoding="utf-8")
        _git(self.repo, "add", "b.txt")
        _git(self.repo, "commit", "-q", "-m", "local only")
        state = audit.inspect(self.repo)
        self.assertEqual(state.unpushed, 1)
        self.assertEqual(state.dirty, [])

    def test_primary_off_main_is_bad(self) -> None:
        _git(self.repo, "switch", "-q", "-c", "codex-release-old")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = audit.run_audit(self.repo, stale_hours=6)
        self.assertEqual(rc, 20)
        self.assertIn("唔喺 main", buf.getvalue())

    def test_ignored_files_are_not_unsaved(self) -> None:
        (self.repo / ".gitignore").write_text(".marker\n", encoding="utf-8")
        _git(self.repo, "add", ".gitignore")
        _git(self.repo, "commit", "-q", "-m", "ignore")
        _git(self.repo, "push", "-q", "origin", "HEAD:main")
        (self.repo / ".marker").write_text("x", encoding="utf-8")
        self.assertEqual(self._hook({"cwd": str(self.repo)}), "")

    def test_non_git_directory_is_silent(self) -> None:
        with tempfile.TemporaryDirectory() as plain:
            self.assertEqual(self._hook({"cwd": plain}), "")


if __name__ == "__main__":
    unittest.main()
