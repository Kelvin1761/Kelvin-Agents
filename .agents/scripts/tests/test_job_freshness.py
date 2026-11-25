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
        self._plist_dir = jf.PLIST_DIR
        jf.PLIST_DIR = self.t / "LaunchAgents"     # 唔好讀到真 ~/Library/LaunchAgents
        jf.PLIST_DIR.mkdir()
        jf.REGISTRY.clear()
        jf.REGISTRY.update({
            "x.log": ([str(self.t / "x.log")], 2),
            "x.manifest": ([str(self.t / "runs" / "*" / "attempt-*.json")], 2),
        })

    def tearDown(self):
        jf.REGISTRY.clear()
        jf.REGISTRY.update(self._reg)
        jf.PLIST_DIR = self._plist_dir
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

    # ── 新裝、未到第一次排程（2026-11-26 astra-audit 假警報）──
    def _plist(self, label, age_hours, plist_dir=None):
        p = (plist_dir or jf.PLIST_DIR) / f"com.antigravity.{label}.plist"
        p.write_text("<plist/>")
        t = time.time() - age_hours * 3600
        os.utime(p, (t, t))
        return p

    def test_never_written_but_freshly_installed_is_pending_not_bad(self):
        self._plist("x.log", 1)                                   # 上限 2 鐘
        level, msg = jf.classify("x.log", None)
        self.assertEqual(level, "ok")
        self.assertIn("新裝、未到第一次排程", msg)
        self.assertTrue(jf.check("x.log")["pending_first_run"])

    def test_injected_plist_dir_and_now(self):
        other = self.t / "other"
        other.mkdir()
        self._plist("x.log", 1, other)
        self.assertEqual(jf.classify("x.log", 0, plist_dir=other)[0], "ok")
        self.assertEqual(jf.classify("x.log", 0)[0], "bad")       # 預設目錄冇 plist → 照舊
        later = time.time() + 5 * 3600                            # 裝咗 6 鐘 > 上限 2 鐘
        self.assertEqual(jf.classify("x.log", 0, now=later, plist_dir=other)[0], "bad")

    def test_never_written_and_plist_older_than_max_age_is_bad(self):
        self._plist("x.log", 5)
        level, msg = jf.classify("x.log", 0)
        self.assertEqual(level, "bad")
        self.assertIn("從未寫過", msg)

    def test_existing_stale_output_ignores_fresh_plist(self):
        self._plist("x.log", 0.5)                                 # 啱啱重裝 plist 唔可以遮住過期輸出
        p = self.t / "x.log"
        p.write_text("hi")
        old = time.time() - 5 * 3600
        os.utime(p, (old, old))
        self.assertEqual(jf.classify("x.log", 0)[0], "bad")
        self.assertFalse(jf.check("x.log")["pending_first_run"])

    # ── 撞鎖跳過 ──
    def _manifest(self, state, op_status, payload_status):
        d = self.t / "runs" / "2026-11-26"
        d.mkdir(parents=True, exist_ok=True)
        (d / "attempt-1.json").write_text(json.dumps({"state": state, "operations": [
            {"operation": "predict", "status": op_status,
             "detail": {"exit_code": 0, "source_payload": {"status": payload_status}}}]}))

    def test_blocked_skipped_locked_is_warn(self):
        self._manifest("blocked", "skipped_locked", "skipped_locked")
        level, msg = jf.classify("x.manifest", 0)
        self.assertEqual(level, "warn")
        self.assertIn("撞鎖跳過", msg)

    def test_blocked_by_payload_only_is_warn(self):
        self._manifest("blocked", "blocked", "skipped_locked")
        self.assertEqual(jf.classify("x.manifest", 0)[0], "warn")

    def test_other_blocked_or_failed_stay_bad(self):
        self._manifest("blocked", "blocked", "firewall_blocked")
        self.assertEqual(jf.classify("x.manifest", 0)[0], "bad")
        self._manifest("failed", "skipped_locked", "skipped_locked")   # 只有 blocked 先降級
        self.assertEqual(jf.classify("x.manifest", 0)[0], "bad")
        self._manifest("partial", "succeeded", "partial")
        self.assertEqual(jf.classify("x.manifest", 0)[0], "bad")

    def test_unregistered_falls_back_to_exit_code(self):
        self.assertEqual(jf.classify("hkjc-wong-choi.live", 0), ("ok", "hkjc-wong-choi.live"))
        self.assertEqual(jf.classify("hkjc-wong-choi.live", 3)[0], "warn")

    def test_every_installed_plist_is_registered_or_explained(self):
        labels = {p.stem.removeprefix("com.antigravity.")
                  for p in self._plist_dir.glob("com.antigravity.*.plist")}
        known = set(self._reg) | set(jf.UNREGISTERED_REASON)
        self.assertFalse(labels - known, f"新 launchd job 未登記輸出：{sorted(labels - known)}")


if __name__ == "__main__":
    unittest.main()
