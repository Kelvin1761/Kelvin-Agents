#!/usr/bin/env python3
"""通知內容測試。

點解重要：呢個通知係 Kelvin 唔喺電腦前**唯一**知道出事嘅途徑。2026-08-07 發佈
撞到 Cloudflare 25 MiB 上限失敗咗兩晚，log 寫得清清楚楚但冇人睇，兩日之後先由
「點解冇今日賽事」發現。所以一條「發佈失敗」嘅訊息一定要出到，而且一眼睇得明。
"""
from __future__ import annotations

import json
import os
import sys
import unittest.mock
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
    KEYS = ("WC_NOTIFY_NTFY_TOPIC", "WC_NOTIFY_WEBHOOK", "WC_NOTIFY_ONLY_PROBLEMS",
            "WC_NOTIFY_TELEGRAM_TOKEN", "WC_NOTIFY_TELEGRAM_CHAT")

    def setUp(self):
        for k in self.KEYS:
            os.environ.pop(k, None)

    def tearDown(self):
        for k in self.KEYS:
            os.environ.pop(k, None)

    def test_telegram_needs_both_halves(self):
        # 只設 token 唔設 chat id 係一個容易犯又完全靜音嘅錯 —— 要講出嚟。
        os.environ["WC_NOTIFY_TELEGRAM_TOKEN"] = "t"
        self.assertEqual(N.send(run()), ["telegram: 只設咗一半（token 同 chat id 兩樣都要）"])

    def test_telegram_sends_plain_text_not_markdown(self):
        # 場次名同錯誤訊息帶住 `_` `*` `[`，行 Markdown 嘅話 Telegram 會拒收成條
        # 訊息 —— 即係最需要通知嗰陣反而收唔到。
        sent = {}

        def fake_post(url, data, headers):
            sent["url"] = url
            sent["payload"] = json.loads(data.decode("utf-8"))
            return None

        os.environ["WC_NOTIFY_TELEGRAM_TOKEN"] = "tok"
        os.environ["WC_NOTIFY_TELEGRAM_CHAT"] = "42"
        with unittest.mock.patch.object(N, "post", fake_post):
            N.send(run(status="failed", cloudflare_deployment={
                "ok": False, "detail": "file_too_big [25 MiB] *limit*"}))
        self.assertIn("/bottok/sendMessage", sent["url"])
        self.assertEqual(sent["payload"]["chat_id"], "42")
        self.assertNotIn("parse_mode", sent["payload"])
        self.assertIn("25 MiB", sent["payload"]["text"])

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


class AudienceTests(unittest.TestCase):
    """額外收件人只收內容，唔收運維訊息。

    Kelvin 想加一個朋友睇賽事分析。但診斷入面有檔案路徑、commit、log 節錄 ——
    對第三者係雜訊，亦唔應該外傳。所以收件人分兩層，而且預設係最窄嗰層：
    要明確講 `audience="content"` 先會多發。
    """

    def setUp(self):
        for k in ("WC_NOTIFY_TELEGRAM_CHAT", "WC_NOTIFY_TELEGRAM_EXTRA"):
            os.environ.pop(k, None)

    tearDown = setUp

    def test_default_audience_is_the_owner_only(self):
        os.environ["WC_NOTIFY_TELEGRAM_CHAT"] = "111"
        os.environ["WC_NOTIFY_TELEGRAM_EXTRA"] = "222"
        self.assertEqual(N.telegram_targets(), ["111"])

    def test_content_reaches_the_extra_readers(self):
        os.environ["WC_NOTIFY_TELEGRAM_CHAT"] = "111"
        os.environ["WC_NOTIFY_TELEGRAM_EXTRA"] = "222, 333"
        self.assertEqual(N.telegram_targets("content"), ["111", "222", "333"])

    def test_the_owner_is_never_sent_the_same_message_twice(self):
        os.environ["WC_NOTIFY_TELEGRAM_CHAT"] = "111"
        os.environ["WC_NOTIFY_TELEGRAM_EXTRA"] = "111,222"
        self.assertEqual(N.telegram_targets("content"), ["111", "222"])

    def test_no_extras_configured_changes_nothing(self):
        os.environ["WC_NOTIFY_TELEGRAM_CHAT"] = "111"
        self.assertEqual(N.telegram_targets("content"), ["111"])

    def test_semicolons_and_spaces_are_tolerated(self):
        os.environ["WC_NOTIFY_TELEGRAM_CHAT"] = "111"
        os.environ["WC_NOTIFY_TELEGRAM_EXTRA"] = " 222 ; 333 "
        self.assertEqual(N.telegram_targets("content"), ["111", "222", "333"])


class RunSummaryTests(unittest.TestCase):
    """兩條摘要：早更講變咗乜，晚更講做好咗乜、上咗線冇。"""

    def setUp(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        import au_run_summary
        self.S = au_run_summary

    def test_a_quiet_morning_says_nothing(self):
        # 冇變動嗰朝出一條「一切照舊」係雜訊，而雜訊嘅代價係下次真出事嗰條
        # 會俾人一齊略過。
        self.assertIsNone(self.S.morning({"scratchings_detected": [],
                                          "track_changes_detected": [],
                                          "analysis_changes": []}))

    def test_scratchings_and_going_are_both_reported(self):
        text = self.S.morning({
            "review_day": "2026-08-09",
            "scratchings_detected": [{"meeting": "2026-08-09 Wagga Race 1-7",
                                      "race": 1, "scratched": ["8", "9"],
                                      "emergencies_in": []}],
            "track_changes_detected": [{"meeting": "2026-08-09 Wagga Race 1-7",
                                        "race": 1, "change": ["Soft 5", "Good 4"]}],
            "analysis_changes": []})
        self.assertIn("退出 #8、#9", text)
        self.assertIn("Soft 5 → Good 4", text)

    def test_not_checked_is_not_reported_as_no_movement(self):
        # 舊 run 冇 ranking_moved 呢個 key。報「頭三揀冇郁」等於畀假保證。
        text = self.S.morning({
            "scratchings_detected": [{"meeting": "2026-08-09 X Race 1-7", "race": 1,
                                      "scratched": ["1"], "emergencies_in": []}],
            "track_changes_detected": [],
            "analysis_changes": [{"meeting": "2026-08-09 X Race 1-7"}]})
        self.assertIn("未有記錄", text)
        self.assertNotIn("冇郁", text)

    def test_checked_and_unmoved_says_so(self):
        text = self.S.morning({
            "scratchings_detected": [{"meeting": "2026-08-09 X Race 1-7", "race": 1,
                                      "scratched": ["1"], "emergencies_in": []}],
            "track_changes_detected": [],
            "analysis_changes": [{"meeting": "2026-08-09 X Race 1-7",
                                  "ranking_moved": []}]})
        self.assertIn("冇郁", text)

    def test_a_ranking_move_shows_before_and_after(self):
        text = self.S.morning({
            "scratchings_detected": [], "track_changes_detected": [],
            "analysis_changes": [{"meeting": "2026-08-09 X Race 1-7",
                                  "ranking_moved": [{"race": 3,
                                                     "before": ["1 A", "2 B"],
                                                     "after": ["2 B", "1 A"]}]}]})
        self.assertIn("R3", text)
        self.assertIn("前：1 A / 2 B", text)
        self.assertIn("後：2 B / 1 A", text)

    def test_evening_distinguishes_verified_from_merely_deployed(self):
        base = {"races_added": [{"meeting": "2026-08-10 Dubbo Race 1-7",
                                 "races": [1, 2], "going": "Good 4"}]}
        ok = self.S.evening({**base, "cloudflare_deployment":
                             {"ok": True, "verified": {"ok": True}}})
        self.assertIn("已上線並核實", ok)
        # 「發佈完成」唔等於「上到線」—— 呢個分別救過我哋一次。
        unver = self.S.evening({**base, "cloudflare_deployment": {"ok": True}})
        self.assertIn("核實唔到", unver)
        failed = self.S.evening({**base, "cloudflare_deployment": {"ok": False}})
        self.assertIn("未發佈得到", failed)

    def test_evening_says_nothing_when_no_new_analysis(self):
        self.assertIsNone(self.S.evening({"races_added": []}))
