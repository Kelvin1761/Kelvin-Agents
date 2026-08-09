#!/usr/bin/env python3
"""覆盤推送 —— 揀馬名單一定要由覆盤報告讀。

2026-08-09：我另寫咗個 script 由排名表推頭幾揀，同覆盤報告對唔上。錯嘅係我 ——
覆盤會**先剔走冇出賽嘅馬再重新排名**，我冇剔，於是攞住三匹退出馬當自己嘅揀馬去
評分，每個數都低估咗。所以呢度只准讀已經計好嘅結果，唔准自己再排一次。
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import au_reflect_notify as R  # noqa: E402

REPORT = """# Unified AU Race Reflector Report

## Race 1
- Performance label: **Gold**
- Model Top 3: #2 Magic Merlin, #5 Maremoto, #6 Strasbelle
- Actual Top 3: 1. #2 Magic Merlin, 2. #4 Linda's Princess, 3. #6 Strasbelle

## Race 2
- Performance label: **1 Hit**
- Model Top 3: #7 Nowhere Man, #1 Also Ran, #3 Third
- Actual Top 3: 1. #9 Bolter, 2. #7 Nowhere Man, 3. #8 Other
"""

RESULTS = """# X Race Results — 2026-08-09

## Race 1
1st: #2 Magic Merlin SP$2.50
2nd: #4 Linda's Princess (0.67L) SP$71.00
3rd: #6 Strasbelle (2.29L) SP$10.00

## Race 2
1st: #9 Bolter SP$15.00
2nd: #7 Nowhere Man (1.10L) SP$4.00
3rd: #8 Other (2.00L) SP$6.00
"""

FORMGUIDE = """RACE 1 — 1500m
[2] Magic Merlin (3)
SpeedPos:  -               WinOdds:   2.6             PlcOdds:   1.3
[5] Maremoto (1)
SpeedPos:  -               WinOdds:   12.0            PlcOdds:   2.8
"""


def meeting(tmp):
    d = Path(tmp) / "2026-08-09 Testville Race 1-2"
    d.mkdir()
    (d / "2026-08-09 Testville Race 1-2_Reflector_Report.md").write_text(
        REPORT, encoding="utf-8")
    (d / "Race_Results_Reflector.md").write_text(RESULTS, encoding="utf-8")
    (d / "08-09 Race 1 Formguide.md").write_text(FORMGUIDE, encoding="utf-8")
    return d


class ReflectNotifyTests(unittest.TestCase):
    def test_only_top_two_picks_that_placed_are_listed(self):
        with tempfile.TemporaryDirectory() as tmp:
            text, c = R.meeting_lines(meeting(tmp))
        # R1: 揀 #2（冠軍）中；#5 冇入前三。R2: 頭揀 #7 跑第二 —— 中。
        self.assertIn("R1 ①Magic Merlin 冠軍", text)
        self.assertNotIn("Maremoto", text)
        self.assertIn("R2 ①Nowhere Man 亞軍", text)
        self.assertEqual(c["top2_hit"], 2)
        self.assertEqual(c["top2_tot"], 4)

    def test_third_pick_is_never_counted_even_when_it_placed(self):
        # #6 Strasbelle 係第三揀而且跑第三 —— 唔屬「頭兩揀」，唔可以偷偷計入。
        with tempfile.TemporaryDirectory() as tmp:
            text, c = R.meeting_lines(meeting(tmp))
        self.assertNotIn("Strasbelle", text)

    def test_every_label_is_shown_so_the_counts_add_up(self):
        # 之前漏咗 `1 Hit`，Casterton 七場只顯示到五場 —— 加唔埋嘅數字會令人
        # 懷疑成份報告。
        with tempfile.TemporaryDirectory() as tmp:
            text, c = R.meeting_lines(meeting(tmp))
        shown = sum(c.get(k, 0) for k in ("Gold", "Good", "Pass", "1 Hit", "Miss"))
        self.assertEqual(shown, c["races"])
        self.assertIn("一中 1", text)

    def test_sp_and_pre_race_place_odds_are_both_shown(self):
        # 兩個唔同時間點嘅數字：SP 係開跑一刻官方贏馬賠率，位賠係分析嗰陣捕捉。
        with tempfile.TemporaryDirectory() as tmp:
            text, _ = R.meeting_lines(meeting(tmp))
        self.assertIn("贏$2.50", text)
        self.assertIn("位$1.3", text)

    def test_a_horse_with_no_captured_place_odds_still_appears(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = meeting(tmp)
            (d / "08-09 Race 1 Formguide.md").unlink()
            text, _ = R.meeting_lines(d)
        self.assertIn("Magic Merlin", text)
        self.assertIn("贏$2.50", text)

    def test_meeting_without_results_is_skipped_not_half_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = meeting(tmp)
            (d / "Race_Results_Reflector.md").unlink()
            self.assertIsNone(R.meeting_lines(d))


class PlacesPaidTests(unittest.TestCase):
    """派幾多個位睇出馬數 —— 唔係一律頭三。

    澳洲規則：8 匹或以上派三個位、5 至 7 匹派兩個位、4 匹或以下淨係贏。所以喺一場
    七匹嘅賽事跑第三根本冇入位。2026-08-09 實測：30 場入面 10 場係短爪，當佢哋
    一律派三位就報大咗 5 個命中，命中率由 57% 虛報成 65%。
    """

    def test_the_australian_thresholds(self):
        self.assertEqual(R.places_paid(12), 3)
        self.assertEqual(R.places_paid(8), 3)
        self.assertEqual(R.places_paid(7), 2)   # 分界線
        self.assertEqual(R.places_paid(5), 2)
        self.assertEqual(R.places_paid(4), 1)   # 冇位置池

    def test_unknown_field_size_falls_back_to_three(self):
        # 數唔到就跟返舊行為。憑空猜一個細數會令命中率虛高 —— 寧願保守。
        self.assertEqual(R.places_paid(None), 3)
        self.assertEqual(R.places_paid(0), 3)

    def test_third_in_a_short_field_is_not_a_place(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = meeting(tmp)
            # R1 得 6 匹 → 只派兩位，而 #6 Strasbelle 跑第三。
            (d / "Race_1_Auto_Analysis.md").write_text(
                "| 出馬數 | 6 |", encoding="utf-8")
            text, c = R.meeting_lines(d)
        self.assertIn("⟨6匹·2位⟩", text)
        self.assertNotIn("Strasbelle", text)

    def test_a_short_field_race_is_marked_so_the_reader_can_see_why(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = meeting(tmp)
            (d / "Race_1_Auto_Analysis.md").write_text(
                "| 出馬數 | 7 |", encoding="utf-8")
            text, _ = R.meeting_lines(d)
        self.assertIn("⟨7匹·2位⟩", text)

    def test_full_field_races_carry_no_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = meeting(tmp)
            (d / "Race_1_Auto_Analysis.md").write_text(
                "| 出馬數 | 10 |", encoding="utf-8")
            text, _ = R.meeting_lines(d)
        self.assertNotIn("位⟩", text)


if __name__ == "__main__":
    unittest.main()
