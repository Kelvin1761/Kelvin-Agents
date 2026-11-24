"""job_freshness：新鮮／過期／自癒／最新 run 寫住 failed／未登記照睇退出碼。"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import job_freshness as jf  # noqa: E402


class JobFreshnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.t = Path(self.tmp.name)
        self._reg = dict(jf.REGISTRY)
        jf.REGISTRY.clear()
        jf.REGISTRY.update({
            "x.log": ([str(self.t / "x.log")], 2),
            "x.manifest": ([str(self.t / "runs" / "*" / "attempt-*.json")], 2),
        })

    def tearDown(self):
        jf.REGISTRY.clear()
        jf.REGISTRY.update(self._reg)
        self.tmp.cleanup()

    def test_fresh_log_with_nonzero_exit_is_only_warn(self):
        (self.t / "x.log").write_text("hi")                      # 失敗嗰次都會寫 log，證明唔到自癒
        self.assertEqual(jf.classify("x.log", 75)[0], "warn")

    def test_newest_manifest_succeeded_heals_nonzero_exit(self):
        d = self.t / "runs" / "2026-11-24"
        d.mkdir(parents=True)
        (d / "attempt-2.json").write_text(json.dumps({"state": "succeeded"}))
        level, msg = jf.classify("x.manifest", 75)
        self.assertEqual(level, "ok")
        self.assertIn("已自癒", msg)

    def test_stale_output_is_bad_even_with_exit_zero(self):
        p = self.t / "x.log"
        p.write_text("hi")
        old = time.time() - 5 * 3600
        os.utime(p, (old, old))
        self.assertEqual(jf.classify("x.log", 0)[0], "bad")

    def test_missing_output_is_bad(self):
        level, msg = jf.classify("x.log", 0)
        self.assertEqual(level, "bad")
        self.assertIn("從未寫過", msg)

    def test_newest_manifest_failed_is_bad(self):
        d = self.t / "runs" / "2026-11-24"
        d.mkdir(parents=True)
        (d / "attempt-1.json").write_text(json.dumps({"state": "succeeded"}))
        time.sleep(0.01)
        (d / "attempt-2.json").write_text(json.dumps({"status": "failed"}))
        level, msg = jf.classify("x.manifest", 1)
        self.assertEqual(level, "bad")
        self.assertIn("failed", msg)

    def test_unregistered_falls_back_to_exit_code(self):
        self.assertEqual(jf.classify("hkjc-wong-choi.live", 0), ("ok", "hkjc-wong-choi.live"))
        self.assertEqual(jf.classify("hkjc-wong-choi.live", 3)[0], "warn")

    def test_every_installed_plist_is_registered_or_explained(self):
        labels = {p.stem.removeprefix("com.antigravity.")
                  for p in (Path.home() / "Library" / "LaunchAgents").glob("com.antigravity.*.plist")}
        known = set(self._reg) | set(jf.UNREGISTERED_REASON)
        self.assertFalse(labels - known, f"新 launchd job 未登記輸出：{sorted(labels - known)}")


if __name__ == "__main__":
    unittest.main()
