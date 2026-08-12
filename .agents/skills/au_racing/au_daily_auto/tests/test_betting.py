#!/usr/bin/env python3
"""落注選注規則 —— Kelvin 2026-08-12 定嘅。

⚠️ 實測 7 日 487 注：贏注 ≥2 ROI −23.3%、位注 ≥1.5 −12.1%，最好嗰個變體
（位注 ≥1.5 剔走飛起 >25%）都係 −8.3%。差距係抽水。所以每張落注單都要帶住
「實測為負」呢句 —— 出一張落注單而唔講量到嘅結果，係最容易令人蝕錢嘅做法。
"""
from __future__ import annotations

import sys
import unittest
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
