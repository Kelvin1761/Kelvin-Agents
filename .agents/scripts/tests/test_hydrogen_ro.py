"""hydrogen_ro.py：Hydrogen 唯一准行嘅唯讀搜尋 wrapper（Kelvin 2026-11-26；Sol 覆核）。"""
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hydrogen_ro as ro  # noqa: E402


class HydrogenRoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve() / "ws"
        (self.root / "pkg").mkdir(parents=True)
        (self.root / "pkg" / "a.py").write_text("def step_dashboard():\n    pass\n")
        (self.root / "bin.dat").write_bytes(b"\0\1def step_dashboard")
        self.secret = Path(self.tmp.name).resolve() / "secret.env"
        self.secret.write_text("TOKEN=step_dashboard\n")
        (self.root / "link.env").symlink_to(self.secret)
        self.cwd = os.getcwd()
        os.chdir(self.root)
        self.env = mock.patch.dict(os.environ, {"WC_HYDROGEN_ROOTS": str(self.root)})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def run_ro(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = ro.main(list(argv))
        return rc, out.getvalue(), err.getvalue()

    def test_grep_finds_text_skips_binary_and_symlink(self):
        rc, out, _ = self.run_ro("grep", "step_dashboard")
        self.assertEqual(rc, 0)
        self.assertIn("pkg/a.py:1:def step_dashboard", out)
        self.assertNotIn("bin.dat", out)
        self.assertNotIn("TOKEN", out)  # symlink 指去 workspace 外，唔跟

    def test_outside_paths_refused(self):
        for argv in (("grep", "x", str(self.secret)), ("grep", "x", "../"), ("ls", "/"), ("wc", "link.env")):
            rc, _, err = self.run_ro(*argv)
            self.assertEqual(rc, 2, argv)
            self.assertIn("workspace", err)

    def test_flags_and_unknown_commands_refused(self):
        self.assertEqual(self.run_ro("grep", "x", "--pre=sh")[0], 2)
        self.assertEqual(self.run_ro("rg", "x")[0], 2)
        self.assertEqual(self.run_ro()[0], 2)

    def test_requires_roots(self):
        with mock.patch.dict(os.environ, {"WC_HYDROGEN_ROOTS": ""}):
            self.assertEqual(self.run_ro("ls")[0], 2)

    def test_ls_and_wc(self):
        rc, out, _ = self.run_ro("ls", "pkg")
        self.assertEqual(rc, 0)
        self.assertIn("a.py", out)
        rc, out, _ = self.run_ro("wc", "pkg/a.py")
        self.assertIn("2 行", out)

    def test_limits(self):
        self.assertEqual(self.run_ro("grep", "a" * 201)[0], 2)
        os.mkfifo(self.root / "pipe")
        rc, out, _ = self.run_ro("grep", "step_dashboard")  # FIFO 唔會卡死
        self.assertEqual(rc, 0)
        self.assertEqual(self.run_ro("wc", "pipe")[0], 2)

    def test_embedded_roots_beat_env(self):
        with mock.patch.object(ro, "EMBEDDED_ROOTS", [str(self.root / "pkg")]), \
             mock.patch.dict(os.environ, {"WC_HYDROGEN_ROOTS": "/"}):
            self.assertEqual(self.run_ro("wc", "bin.dat")[0], 2)
            self.assertEqual(self.run_ro("wc", "pkg/a.py")[0], 0)

    def test_symlink_file_refused_even_inside(self):
        (self.root / "inner_link.py").symlink_to(self.root / "pkg" / "a.py")
        rc, out, _ = self.run_ro("grep", "step_dashboard", "inner_link.py")
        self.assertNotIn("inner_link", out)  # O_NOFOLLOW：唔跟 symlink

    def test_never_spawns_processes(self):
        with mock.patch("subprocess.run") as run, mock.patch("os.system") as system:
            self.run_ro("grep", "def")
            run.assert_not_called()
            system.assert_not_called()


if __name__ == "__main__":
    unittest.main()
