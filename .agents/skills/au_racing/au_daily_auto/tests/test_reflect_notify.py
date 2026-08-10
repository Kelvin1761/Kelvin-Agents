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
- Model Top 5 shortlist: #2 Magic Merlin, #5 Maremoto, #6 Strasbelle, #4 Linda's Princess, #3 Ocean
- Actual Top 3: 1. #2 Magic Merlin, 2. #4 Linda's Princess, 3. #6 Strasbelle

## Race 2
- Performance label: **1 Hit**
- Model Top 3: #7 Nowhere Man, #1 Also Ran, #3 Third
- Model Top 5 shortlist: #7 Nowhere Man, #1 Also Ran, #3 Third, #2 Fourth, #4 Fifth
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
        self.assertIn("R1 ①Magic Merlin", text)
        self.assertIn("冠", text)
        self.assertNotIn("Maremoto", text)
        self.assertIn("R2 ①Nowhere Man", text)
        self.assertEqual(c["top2_hit"], 2)
        self.assertEqual(c["top2_tot"], 4)

    def test_third_pick_is_never_counted_even_when_it_placed(self):
        # #6 Strasbelle 係第三揀而且跑第三 —— 唔屬「頭兩揀」，唔可以偷偷計入。
        with tempfile.TemporaryDirectory() as tmp:
            text, c = R.meeting_lines(meeting(tmp))
        self.assertNotIn("Strasbelle", text)

    def test_top_four_comes_from_the_shortlist_not_the_top_three_line(self):
        """「Model Top 3」只有三匹 —— 由佢取「頭四」會靜靜咁少報。

        實測：由 Top 3 嗰行取頭四，捉齊三甲由 11/38 跌到 2/38。頭四一定要由
        `Model Top 5 shortlist` 取。呢個對數方式（同覆盤報告嘅 Gold 標籤比）
        係唯一捉得到呢類錯嘅方法。
        """
        with tempfile.TemporaryDirectory() as tmp:
            d = meeting(tmp)
            # R1 實際前三 = #2、#4、#6；頭四選（shortlist）= #2、#5、#6、#4 → 捉齊
            _, c = R.meeting_lines(d)
        self.assertEqual(c["gold_races"], 1)

    def test_gold_and_good_can_both_count_the_same_race(self):
        """Kelvin 明確要兩樣都標，唔好互斥。

        ⚠️ 呢個同覆盤報告嘅 `exclusive_label` 唔同（嗰邊 Gold 蓋過 Good）。
        兩個數字唔可以並排比較 —— 定義唔同。
        """
        report = REPORT.replace(
            "- Actual Top 3: 1. #2 Magic Merlin, 2. #4 Linda's Princess, 3. #6 Strasbelle",
            "- Actual Top 3: 1. #2 Magic Merlin, 2. #5 Maremoto, 3. #6 Strasbelle")
        results = RESULTS.replace("2nd: #4 Linda's Princess (0.67L) SP$71.00",
                                  "2nd: #5 Maremoto (0.67L) SP$71.00")
        with tempfile.TemporaryDirectory() as tmp:
            d = meeting(tmp)
            next(d.glob("*_Reflector_Report.md")).write_text(report, encoding="utf-8")
            (d / "Race_Results_Reflector.md").write_text(results, encoding="utf-8")
            _, c = R.meeting_lines(d)
        # 同一場：頭三選全部入位 → 捉齊三甲 ✅，頭兩選都入位 ✅
        self.assertEqual(c["gold_races"], 1)
        self.assertEqual(c["good_races"], 1)

    def test_the_top_three_rate_has_a_sane_denominator(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, c = R.meeting_lines(meeting(tmp))
        # 逐匹入位率：分母 = 場數 × 3（每場計頭三選）
        self.assertEqual(c["top3_tot"], c["races"] * 3)
        self.assertLessEqual(c["top3_hit"], c["top3_tot"])

    def test_both_placed_is_counted_directly_not_from_the_good_label(self):
        """五個評級互斥，Gold 蓋過 Good —— 讀標籤會少報一半。

        2026-08-09 實測：Good 標籤 4/38，但真係兩隻都入位嘅係 8/38。差嗰四場
        全部係已經標咗 Gold。Kelvin 想睇「兩隻都入位」呢件事本身。
        """
        with tempfile.TemporaryDirectory() as tmp:
            d = meeting(tmp)
            # R1 兩隻揀馬（#2 冠軍、#5 冇入位）—— 唔算兩隻都入位
            text, c = R.meeting_lines(d)
        self.assertEqual(c["good_races"], 0)
        self.assertEqual(c["gold_races"], 1)   # 但捉齊三甲照計

    def test_the_header_shows_the_full_distribution(self):
        """四個檔位都要出，唔可以只出好嗰啲。

        之前漏咗一個 label，七場嘅馬場顯示成五場 —— 加唔埋嘅數字會令人懷疑
        成份報告。
        """
        with tempfile.TemporaryDirectory() as tmp:
            text, c = R.meeting_lines(meeting(tmp))
        for word in ("入位率 兩選", "三選", "全走空"):
            self.assertIn(word, text)
        self.assertIn("捉齊三甲", text)
        self.assertIn("兩選皆入位", text)   # 手機版縮短咗「頭」字

    def test_sp_and_pre_race_place_odds_are_both_shown(self):
        # 兩個唔同時間點嘅數字：SP 係開跑一刻官方贏馬賠率，位賠係分析嗰陣捕捉。
        with tempfile.TemporaryDirectory() as tmp:
            text, _ = R.meeting_lines(meeting(tmp))
        # 賠率而家係 贏/位 斜線寫法，圖例喺全日標題講一次。
        self.assertIn("W2.6/P1.3", text)

    def test_a_horse_with_no_captured_place_odds_still_appears(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = meeting(tmp)
            (d / "08-09 Race 1 Formguide.md").unlink()
            text, _ = R.meeting_lines(d)
        self.assertIn("Magic Merlin", text)
        # 冇賽前捕捉 → 只出 SP，唔會夾一個唔同時間點嘅位賠上去。
        self.assertIn("SP2.50", text)

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
        self.assertIn("(6匹2位)", text)
        self.assertNotIn("Strasbelle", text)

    def test_a_short_field_race_is_marked_so_the_reader_can_see_why(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = meeting(tmp)
            (d / "Race_1_Auto_Analysis.md").write_text(
                "| 出馬數 | 7 |", encoding="utf-8")
            text, _ = R.meeting_lines(d)
        self.assertIn("(7匹2位)", text)

    def test_full_field_races_carry_no_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = meeting(tmp)
            (d / "Race_1_Auto_Analysis.md").write_text(
                "| 出馬數 | 10 |", encoding="utf-8")
            text, _ = R.meeting_lines(d)
        self.assertNotIn("匹2位", text)


if __name__ == "__main__":
    unittest.main()


class OddsPairingTests(unittest.TestCase):
    """W/P 一定要同源。

    2026-08-10 Dubbo R5 Castlebar Road：分析時 $20 贏／$5.25 位，開跑 SP $4.20。
    舊寫法把 SP 當贏賠、賽前位賠當位賠擺埋一齊，變成「贏 4.20 / 位 5.25」——
    位賠高過贏賠，睇落似 data 壞。兩個數字各自都對，錯喺夾埋當成一對。
    """

    def test_win_and_place_come_from_the_same_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = meeting(tmp)
            (d / "08-09 Race 1 Formguide.md").write_text(
                "RACE 1\n[2] Magic Merlin (3)\n"
                "SpeedPos:  -               WinOdds:   20.0            PlcOdds:   5.25\n",
                encoding="utf-8")
            text, _ = R.meeting_lines(d)
        self.assertIn("W20.0/P5.25", text)
        # SP 2.50 同賽前 20.0 差好遠 → 應該標出嚟
        self.assertIn("SP2.50", text)
        # 而唔可以出現「贏 2.50 / 位 5.25」呢種夾錯時間點嘅寫法
        self.assertNotIn("2.50/5.25", text)

    def test_sp_is_omitted_when_the_market_barely_moved(self):
        # 唔移動嗰陣 SP 同賽前贏賠差唔多，出佢只係令每行變長。
        with tempfile.TemporaryDirectory() as tmp:
            d = meeting(tmp)
            (d / "08-09 Race 1 Formguide.md").write_text(
                "RACE 1\n[2] Magic Merlin (3)\n"
                "SpeedPos:  -               WinOdds:   2.6             PlcOdds:   1.3\n",
                encoding="utf-8")
            text, _ = R.meeting_lines(d)
        self.assertIn("W2.6/P1.3", text)
        self.assertNotIn("SP2.50", text)

    def test_a_horse_with_no_captured_odds_still_shows_sp(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = meeting(tmp)
            (d / "08-09 Race 1 Formguide.md").unlink()
            text, _ = R.meeting_lines(d)
        self.assertIn("SP2.50", text)
