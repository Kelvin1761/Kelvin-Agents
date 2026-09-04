"""走位匹配嘅去重 key 一定要係賽事身份。

`compute_draw_position_fit` 舊 key 係 `barrier_finish_xw`。兩場真正唔同嘅賽事
只要檔位、名次同疊數一樣就會被當成重複合併走 —— 一隻連勝嘅馬（名次永遠 1）
最容易中招。個表一直有日期／場地／距離，只係 `parse_all_draw_history` 冇帶落嚟。

實測（3,385 個 runner、26 個場次 193 場回測）：改用賽事身份令 40 份 digest 有變，
六個排名指標**全部 bit-identical** —— 所以呢個係免費嘅正確性修正。
（同期量到但**未上線**嘅樣本門檻要 883 份 digest，成本 good −1.04pp。）
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "skills" / "hkjc_racing" / "hkjc_wong_choi" / "scripts"))

from create_hkjc_logic_skeleton import (  # noqa: E402
    compute_draw_position_fit,
    parse_all_draw_history,
)


def row(*, date, venue, distance, barrier, finish, xw):
    return dict(date=date, venue=venue, distance=distance,
                barrier=barrier, finish=finish, xw=xw)


class DedupeKeyIsRaceIdentity(unittest.TestCase):
    def test_two_real_races_that_look_alike_are_both_kept(self):
        """同檔位、同名次、同疊數，但係兩場唔同賽事 —— 兩場都要算。"""
        hist = [
            row(date="01/06/2026", venue="沙田", distance="1200",
                barrier=3, finish=1, xw="(2W2W)"),
            row(date="22/06/2026", venue="沙田", distance="1200",
                barrier=3, finish=1, xw="(2W2W)"),
        ]
        digest = compute_draw_position_fit([], 3, hist)
        self.assertIn("走內(1-2W):2場", digest)

    def test_a_genuine_duplicate_is_still_collapsed(self):
        same = row(date="01/06/2026", venue="沙田", distance="1200",
                   barrier=3, finish=1, xw="(2W2W)")
        digest = compute_draw_position_fit([], 3, [same, dict(same)])
        self.assertIn("走內(1-2W):1場", digest)

    def test_rows_without_a_date_fall_back_to_the_old_key(self):
        """舊 Facts 冇日期欄嗰陣要照跑，唔可以當佢係身份。"""
        hist = [
            dict(barrier=3, finish=1, xw="(2W2W)"),
            dict(barrier=3, finish=1, xw="(2W2W)"),
        ]
        digest = compute_draw_position_fit([], 3, hist)
        self.assertIn("走內(1-2W):1場", digest)

    def test_parse_keeps_race_identity_columns(self):
        block = "\n".join([
            "| # | 日期 | 場地 | 距離 | 班次 | 檔位 | 騎師 | 負磅 | 名次 | 頭馬距離 "
            "| 能量 | L400 | 走位(XW) | 消耗 | 沿途位 | 完成時間 |",
            "| 1 | 26/04/2026 | 沙田 | 1200 | 一級賽 | 3 | 潘頓 | 126 | 1 | 4-1/4 "
            "| 127 | 21.52 | (2W2W) | 中等消耗 | 3-3-1 | 1.07.10 |",
        ])
        rows = parse_all_draw_history(block)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["date"], "26/04/2026")
        self.assertEqual(rows[0]["venue"], "沙田")
        self.assertEqual(rows[0]["distance"], "1200")
        self.assertEqual(rows[0]["barrier"], 3)
        self.assertEqual(rows[0]["xw"], "(2W2W)")

    def test_rows_with_no_wide_data_are_excluded_not_guessed(self):
        """HKJC 有 61.4% 嘅往績行個 XW 欄係 `-`（來源真係冇），要剔走唔要砌。"""
        hist = [
            row(date="01/06/2026", venue="沙田", distance="1200",
                barrier=3, finish=1, xw="-"),
            row(date="22/06/2026", venue="沙田", distance="1200",
                barrier=3, finish=2, xw="(1W1W)"),
        ]
        digest = compute_draw_position_fit([], 3, hist)
        self.assertIn("走內(1-2W):1場", digest)


if __name__ == "__main__":
    unittest.main()
