#!/usr/bin/env python3
from __future__ import annotations

import plistlib
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent


class LaunchdInstallationTests(unittest.TestCase):
    def _plist(self, label: str) -> dict:
        path = HERE / "launchd" / f"{label}.plist.template"
        return plistlib.loads(path.read_bytes())

    def test_every_runtime_job_has_a_reinstallable_template(self):
        labels = (
            "com.antigravity.au-wong-choi.evening",
            "com.antigravity.au-wong-choi.morning",
            "com.antigravity.au-wong-choi.healthcheck",
            "com.antigravity.au-wong-choi.bot",
        )
        installer = (HERE / "install_macos_launchd.sh").read_text(encoding="utf-8")
        for label in labels:
            self.assertEqual(self._plist(label)["Label"], label)
            self.assertIn(label, installer)

    def test_auxiliary_jobs_use_the_environment_wrapper(self):
        for label, task in (("com.antigravity.au-wong-choi.healthcheck", "healthcheck"),
                            ("com.antigravity.au-wong-choi.bot", "bot")):
            args = self._plist(label)["ProgramArguments"]
            self.assertTrue(args[1].endswith("/run_au_auxiliary.sh"))
            self.assertEqual(args[2], task)


if __name__ == "__main__":
    unittest.main()
