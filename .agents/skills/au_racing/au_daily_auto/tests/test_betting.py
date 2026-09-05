#!/usr/bin/env python3
"""落注選注規則 —— Kelvin 2026-08-12 定嘅。

⚠️ 實測 7 日 487 注：贏注 ≥2 ROI −23.3%、位注 ≥1.5 −12.1%，最好嗰個變體
（位注 ≥1.5 剔走飛起 >25%）都係 −8.3%。差距係抽水。所以每張落注單都要帶住
「實測為負」呢句 —— 出一張落注單而唔講量到嘅結果，係最容易令人蝕錢嘅做法。
"""
from __future__ import annotations

import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import au_betting as B  # noqa: E402


class DecideTests(unittest.TestCase):
    """六個 case 全部由 Kelvin 親自舉例。"""

    def test_short_top_pick_is_skipped_and_the_second_taken(self):
        got = B.decide([(1, "A", 1.4), (2, "B", 2.5)])
        self.assertEqual([x[1] for x in got], ["B"])

    def test_two_mid_priced_picks_take_only_the_top(self):
        got = B.decide([(1, "A", 2.6), (2, "B", 2.2)])
        self.assertEqual([x[1] for x in got], ["A"])

    def test_one_above_the_spread_takes_both(self):
        got = B.decide([(1, "A", 2.6), (2, "B", 3.5)])
        self.assertEqual([x[1] for x in got], ["A", "B"])

    def test_both_long_takes_both(self):
        got = B.decide([(1, "A", 4.0), (2, "B", 6.0)])
        self.assertEqual(len(got), 2)

    def test_both_too_short_is_no_bet(self):
        self.assertEqual(B.decide([(1, "A", 1.8), (2, "B", 1.9)]), [])

    def test_short_second_pick_leaves_the_top_alone(self):
        got = B.decide([(1, "A", 3.2), (2, "B", 1.5)])
        self.assertEqual([x[1] for x in got], ["A"])

    def test_only_the_top_two_are_ever_considered(self):
        # 第三揀就算賠率靚都唔可以入選 —— 策略講明只考慮頭兩選。
        got = B.decide([(1, "A", 1.2), (2, "B", 1.3), (3, "C", 9.0)])
        self.assertEqual(got, [])

    def test_the_boundary_is_inclusive(self):
        # 「賠率細過 2 唔落」→ 啱啱 2.0 係落。呢個邊界要釘死，唔可以靠讀。
        self.assertEqual(len(B.decide([(1, "A", 2.0), (2, "B", 1.9)])), 1)

    def test_flat_stakes(self):
        # 注碼一變就唔係測揀馬，而係測注碼分配。
        self.assertEqual(B.STAKE, 1.0)


class WatchBandTests(unittest.TestCase):
    """差少少就夠門檻嘅要列做「留意」。

    Kelvin 2026-08-12：位賠 1.85–2.0 嘅頭兩選，開跑前有機會浮上 2.0 變成一注，
    所以晚更同早更兩張都要出。實測 7 日 28 注：入位 60.7%、ROI +15.3% —— 但
    28 注太細，而且**上下兩個相鄰帶都係負**（1.70–1.85 −24.9%、2.00–2.50 −11.2%），
    一個夾喺兩個負數之間嘅孤立正數格，多數係雜訊，唔可以當成「呢批要落」。
    """

    def test_the_band_is_between_watch_low_and_the_bet_threshold(self):
        got = B.watch([(1, "A", 1.9), (2, "B", 2.1)])
        self.assertEqual([x[1] for x in got], ["A"])   # 2.1 已經係一注，唔算留意

    def test_below_the_band_is_not_watched(self):
        self.assertEqual(B.watch([(1, "A", 1.84), (2, "B", 1.5)]), [])

    def test_the_lower_edge_is_inclusive(self):
        # 1.85 係常見價位，唔可以跌出兩邊。
        self.assertEqual(len(B.watch([(1, "A", 1.85), (2, "B", 1.0)])), 1)

    def test_the_upper_edge_belongs_to_the_bet_list(self):
        self.assertEqual(B.watch([(1, "A", 2.0), (2, "B", 1.0)]), [])
        self.assertEqual(len(B.decide([(1, "A", 2.0), (2, "B", 1.0)])), 1)

    def test_only_the_top_two_are_watched(self):
        # 第三揀浮上 2.0 都唔會變成一注，所以唔應該出現喺留意名單。
        self.assertEqual(B.watch([(1, "A", 1.0), (2, "B", 1.0), (3, "C", 1.9)]), [])

    def test_a_race_can_carry_both_a_bet_and_a_watch(self):
        picks = [(1, "A", 3.5), (2, "B", 1.9)]
        self.assertEqual(len(B.decide(picks)), 1)
        self.assertEqual(len(B.watch(picks)), 1)


class BettingMessageTests(unittest.TestCase):
    def test_bet_and_watch_lines_both_show_the_horse_number(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "2026-08-13 Dubbo Race 1-1"
            folder.mkdir()
            rows = [{"race": 1,
                     "picks": [(7, "Lucky Horse", 3.5),
                               (12, "Watch Horse", 1.9)],
                     "bets": [(7, "Lucky Horse", 3.5)],
                     "watch": [(12, "Watch Horse", 1.9)]}]
            with unittest.mock.patch.object(B, "_folders", lambda day: [folder]), \
                 unittest.mock.patch.object(
                     B, "meeting_bets",
                     lambda folder, which: (rows, [], ["morning-rebuild"])):
                text = B.bet_list("2026-08-13", "last")

        self.assertIn("R1 ①#7 Lucky Horse @3.5", text)
        self.assertIn("R1 👀②#12 Watch Horse @1.9", text)


RESULTS = """# Warrnambool Race Results — 2026-09-03

## Race 1
1st: #2 Budjik Boy SP$4.00
2nd: #4 Johnny Be Good (1.50L) SP$11.00
3rd: #11 Spanish Snitzel (1.70L) SP$101.00
4th: #9 Arizona Luck (3.45L) SP$5.50
"""


class SettlementTests(unittest.TestCase):
    """退出馬要退注。

    ⚠️ 「賽果檔冇呢隻馬」有兩個成因，一個要退錢、一個係我哋唔知結果，唔可以
    兩個都當輸。實測 2026-08-13→09-04：452 注入面 11 注係遲退出（早更之後先
    退），全部當咗輸一個單位，令個 ROI 報衰 2.0pp（−19.5% 其實係 −17.5%）。
    報衰同報好一樣壞 —— 兩樣都會令人唔信條數。
    """

    def _settle(self, bets, *, results=RESULTS, tags=("morning-rebuild",)):
        import au_reflect_notify as R  # noqa: PLC0415
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "2026-09-03 Warrnambool Race 1-2"
            folder.mkdir()
            (folder / "Race_Results_Reflector.md").write_text(results,
                                                              encoding="utf-8")
            rows = [{"race": race, "picks": [], "bets": picks, "watch": []}
                    for race, picks in bets]
            with unittest.mock.patch.object(B, "_folders", lambda day: [folder]), \
                 unittest.mock.patch.object(
                     B, "meeting_bets",
                     lambda f, which: (rows, [], list(tags))), \
                 unittest.mock.patch.object(R, "field_size", lambda f, r: 10):
                return B.settle("2026-09-03")

    def test_a_runner_missing_from_a_settled_race_is_refunded_not_lost(self):
        text = self._settle([(1, [(4, "Johnny Be Good", 2.5),
                                  (99, "Scratched Horse", 3.0)])])
        self.assertIn("1 注退回", text)
        self.assertIn("Scratched Horse", text)
        self.assertIn("1 注 · 中 1", text)      # 分母淨返一注，唔係兩注
        self.assertIn("ROI +150.0%", text)      # 2.5 回收 / 1 注

    def test_a_race_with_no_results_at_all_is_unsettled_not_lost(self):
        # 場次根本冇賽果 = 抽取未到，同「呢隻馬退出」係兩件事。
        text = self._settle([(1, [(4, "Johnny Be Good", 2.5)]),
                             (2, [(1, "No Results Yet", 4.0)])])
        self.assertIn("1 注仲未有賽果", text)
        self.assertIn("1 注 · 中 1", text)

    def test_a_plain_loser_is_still_a_loser(self):
        # 退注邏輯唔可以順手救埋跑輸嗰啲 —— #9 跑第 4，10 匹派三位。
        text = self._settle([(1, [(9, "Arizona Luck", 2.5)])])
        self.assertNotIn("注退回", text)
        self.assertIn("ROI -100.0%", text)

    def test_a_non_morning_snapshot_is_called_out(self):
        text = self._settle([(1, [(4, "Johnny Be Good", 2.5)])],
                            tags=("analysis",))
        self.assertIn("非早更快照", text)
        self.assertIn("analysis", text)

    def test_a_morning_snapshot_says_nothing(self):
        text = self._settle([(1, [(4, "Johnny Be Good", 2.5)])])
        self.assertNotIn("非早更快照", text)


class SnapshotTagTests(unittest.TestCase):
    """早更到底跑咗未，權威證據係 snapshot 個 tag，唔係個時間。

    2026-08-27 至 08-29 三日，control plane 將 10:00 嗰程當 `duplicate_skipped`
    跳過（`heal()` 霸咗個 slot，已修），於是「落注單（當朝定價）」出嘅其實係前
    一晚嘅價 —— 而張單上面完全睇唔出。嗰三日 5.5% 注落咗喺冇出賽嘅馬，有早更
    嘅日子只係 1.5%。
    """

    def test_tags_are_read_off_the_snapshot_key(self):
        self.assertEqual(B.snapshot_tag("2026-09-04T10:12:25|morning-rebuild"),
                         "morning-rebuild")
        self.assertEqual(B.snapshot_tag("2026-09-04T00:01:06"), "unknown")

    def test_only_the_two_morning_tags_count(self):
        self.assertTrue(B.is_morning("2026-09-04T10:12:25|morning-rebuild"))
        self.assertTrue(B.is_morning("2026-09-04T10:12:25|morning-refresh"))
        self.assertFalse(B.is_morning("2026-09-04T00:01:06|analysis"))
        self.assertFalse(B.is_morning("2026-09-04T00:01:06|backfill-test"))

    def test_the_bet_list_header_stops_claiming_morning_pricing(self):
        rows = [{"race": 1, "picks": [(7, "A", 3.5)],
                 "bets": [(7, "A", 3.5)], "watch": []}]
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "2026-08-27 Seymour Race 1-1"
            folder.mkdir()
            with unittest.mock.patch.object(B, "_folders", lambda day: [folder]), \
                 unittest.mock.patch.object(
                     B, "meeting_bets",
                     lambda f, which: (rows, ["2026-08-26 23:06"], ["analysis"])):
                stale = B.bet_list("2026-08-27", "last")
            with unittest.mock.patch.object(B, "_folders", lambda day: [folder]), \
                 unittest.mock.patch.object(
                     B, "meeting_bets",
                     lambda f, which: (rows, ["2026-08-27 10:04"],
                                       ["morning-rebuild"])):
                fresh = B.bet_list("2026-08-27", "last")
        self.assertIn("用緊前一晚嘅價", stale)
        self.assertIn("早更未跑到", stale)
        self.assertIn("當朝定價", fresh)
        self.assertNotIn("早更未跑到", fresh)
