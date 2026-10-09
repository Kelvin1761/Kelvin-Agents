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

    def test_midday_refresh_only_refreshes_and_owns_its_slot(self):
        # 用獨立 slot：唔傳 --slot 會食咗 10:00 morning 嗰格（control plane 按 mode 推 slot）。
        args = self._plist("com.antigravity.au-wong-choi.midday")["ProgramArguments"]
        self.assertTrue(args[1].endswith("/run_au_daily_schedule.sh"))
        self.assertEqual(args[2], "morning")
        slot = args[args.index("--slot") + 1]
        self.assertNotEqual(slot, "10:00")
        self.assertIn("--skip-review", args)
        self.assertIn("--skip-analysis", args)

    def test_auxiliary_jobs_use_the_environment_wrapper(self):
        for label, task in (("com.antigravity.au-wong-choi.healthcheck", "healthcheck"),
                            ("com.antigravity.au-wong-choi.bot", "bot")):
            args = self._plist(label)["ProgramArguments"]
            self.assertTrue(args[1].endswith("/run_au_auxiliary.sh"))
            self.assertEqual(args[2], task)

    def test_scheduled_runner_waits_for_remote_dns_before_self_update(self):
        runner = (HERE / "run_au_daily_schedule.sh").read_text(encoding="utf-8")
        gate = runner.index('"$NETWORK_READINESS"')
        update = runner.index("git fetch --quiet origin")
        self.assertLess(gate, update)
        for host in ("github.com", "wongchoi-dashboard.pages.dev",
                     "www.sportsbet.com.au"):
            self.assertIn(f"--host {host}", runner)


if __name__ == "__main__":
    unittest.main()
