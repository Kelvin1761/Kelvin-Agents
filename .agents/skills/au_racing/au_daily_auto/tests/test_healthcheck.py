#!/usr/bin/env python3
"""體檢 —— 唯一一個唔住喺排程 process 入面嘅檢查。

現有嘅補救（補發、補覆盤、補抽）全部靠排程自己行到嗰一步先觸發。個 run 早死、
crash、或者根本冇開，就冇任何嘢會發現。2026-08-05 至 08-10 三次多日空白，每次
都係「有嘢失敗咗，而冇人去問今日到底出咗未」。

判斷睇實物（live JSON、本機評分檔），唔睇 log —— 一個報「成功」嘅 run log 已經
呃過我哋兩次。
"""
from __future__ import annotations

import sys
import unittest
import unittest.mock
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import au_healthcheck as H  # noqa: E402

DAY = "2026-08-10"
VENUES = {"Dubbo", "Kilcoy", "Nowra", "Pakenham Synthetic"}


def patched(live, expect, scored):
    return unittest.mock.patch.multiple(
        H, live_meetings=lambda: live, au_venues_today=lambda day: expect,
        local_scored=lambda day: scored)


class HealthcheckTests(unittest.TestCase):
    def test_everything_live_is_quiet(self):
        with patched({f"{DAY}|{v}" for v in VENUES}, VENUES, {v: 7 for v in VENUES}):
            self.assertEqual(H.check(DAY)["state"], "ok")

    def test_analysed_but_not_published_is_healable(self):
        # 2026-08-09 晚更真實情況：四個場次分析齊，deploy 死喺 Drive 權限。
        with patched({"2026-08-09|Wagga"}, VENUES, {v: 7 for v in VENUES}):
            r = H.check(DAY)
        self.assertEqual(r["state"], "unpublished")
        self.assertEqual(sorted(r["publishable"]), sorted(VENUES))

    def test_never_analysed_is_not_something_a_healthcheck_should_fix(self):
        # 補呢個要重抽幾百版 —— 唔應該由一個體檢靜靜咁觸發。
        with patched({"2026-08-09|Wagga"}, VENUES, {}):
            self.assertEqual(H.check(DAY)["state"], "unanalysed")

    def test_unreadable_live_is_unknown_not_missing(self):
        # 讀唔到 live 就當「冇發佈」而去補，等於網絡一有事就亂發佈一次。
        with patched(None, VENUES, {v: 7 for v in VENUES}):
            self.assertEqual(H.check(DAY)["state"], "unknown")

    def test_partially_scored_still_reports_every_missing_venue(self):
        with patched({f"{DAY}|Dubbo"}, VENUES, {"Kilcoy": 7}):
            r = H.check(DAY)
        self.assertEqual(r["publishable"], ["Kilcoy"])
        self.assertIn("Nowra", r["missing"])

    def test_api_failure_falls_back_to_what_we_scored_locally(self):
        # API 唔通嗰陣仍然要捉到「本機有分析但 live 冇」。
        with patched({"2026-08-09|Wagga"}, None, {"Dubbo": 7}):
            r = H.check(DAY)
        self.assertEqual(r["state"], "unpublished")
        self.assertEqual(r["publishable"], ["Dubbo"])

    def test_a_meeting_live_from_another_day_does_not_count(self):
        # 尋日嘅場次仲喺 dashboard 唔代表今日出咗。
        with patched({"2026-08-09|Dubbo"}, {"Dubbo"}, {"Dubbo": 7}):
            self.assertEqual(H.check(DAY)["state"], "unpublished")


if __name__ == "__main__":
    unittest.main()
