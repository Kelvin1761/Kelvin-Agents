#!/usr/bin/env python3
"""通知內容測試。

點解重要：呢個通知係 Kelvin 唔喺電腦前**唯一**知道出事嘅途徑。2026-08-07 發佈
撞到 Cloudflare 25 MiB 上限失敗咗兩晚，log 寫得清清楚楚但冇人睇，兩日之後先由
「點解冇今日賽事」發現。所以一條「發佈失敗」嘅訊息一定要出到，而且一眼睇得明。
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import au_notify as N  # noqa: E402


def run(**kw):
    base = {"status": "ok", "mode": "evening", "review_day": "2026-08-09",
            "duration_seconds": 600}
    base.update(kw)
    return base


class SummaryTests(unittest.TestCase):
    def test_failed_deploy_is_named_in_the_body(self):
        # 就係呢一句喺 08-07 應該出而冇出。
        _, body = N.summarise(run(status="failed", cloudflare_deployment={
            "ok": False, "detail": "Pages only supports files up to 25 MiB in size"}))
        self.assertIn("發佈：失敗", body)
        self.assertIn("25 MiB", body)

    def test_status_and_mode_are_in_the_title(self):
        title, _ = N.summarise(run(status="failed"))
        self.assertIn("❌", title)
        self.assertIn("晚更", title)

    def test_verified_publish_says_so(self):
        _, body = N.summarise(run(cloudflare_deployment={
            "ok": True, "verified": {"ok": True}}))
        self.assertIn("已核實上線", body)

    def test_publish_that_could_not_be_verified_is_distinguished(self):
        # 「發佈成功」同「發佈成功但核實唔到」係兩件事 —— 後者正正係假綠燈。
        _, body = N.summarise(run(cloudflare_deployment={
            "ok": True, "verified": {"ok": False}}))
        self.assertIn("核實唔到", body)

    def test_no_deploy_at_all_is_not_reported_as_success(self):
        _, body = N.summarise(run())
        self.assertIn("發佈：冇行到", body)

    def test_pending_work_is_listed(self):
        _, body = N.summarise(run(meetings_processed=[
            {"status": "pending_extraction"}, {"status": "analysed"}]))
        self.assertIn("pending_extraction", body)

    def test_engine_drift_is_surfaced(self):
        _, body = N.summarise(run(code_version={"engine_dirty": ["a.py", "b.py"]}))
        self.assertIn("未 commit", body)

    def test_counts_races_not_meetings(self):
        _, body = N.summarise(run(races_added=[{"races": [1, 2, 3]},
                                               {"races": [1, 2]}]))
        self.assertIn("2 個場次", body)
        self.assertIn("5 場", body)


class SendTests(unittest.TestCase):
    def setUp(self):
        for k in ("WC_NOTIFY_NTFY_TOPIC", "WC_NOTIFY_WEBHOOK",
                  "WC_NOTIFY_ONLY_PROBLEMS"):
            os.environ.pop(k, None)

    def test_no_configuration_sends_nothing(self):
        # 唔可以默默把場次資料送去一個冇人揀過嘅第三方服務。
        self.assertEqual(N.send(run()), [])

    def test_only_problems_mode_skips_a_clean_run(self):
        os.environ["WC_NOTIFY_ONLY_PROBLEMS"] = "1"
        os.environ["WC_NOTIFY_NTFY_TOPIC"] = "should-not-be-used"
        self.assertEqual(N.send(run(status="ok")), ["skipped: 只報問題"])

    def test_only_problems_mode_still_reports_a_failure(self):
        os.environ["WC_NOTIFY_ONLY_PROBLEMS"] = "1"
        sent = N.send(run(status="failed"))
        self.assertNotIn("skipped: 只報問題", sent)


if __name__ == "__main__":
    unittest.main()
