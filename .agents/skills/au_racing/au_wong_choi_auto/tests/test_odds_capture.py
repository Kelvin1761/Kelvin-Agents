#!/usr/bin/env python3
"""賠率抓取 —— 同一條紅線：**唔可以入分析**。

Kelvin 2026-08-04：賠率係做 dashboard 預填同將來策略用，唔做評分輸入。
呢個決定要靠**檔案位置**守住，唔可以靠記性 —— 因為市場排序場內 AUC 0.7393
vs 我哋 0.6530，佢一入分就會主導成個模型，而嗰個係產品定位決定，
唔應該有人手快加咗個 leaf 就靜靜咁發生。
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

AU = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(AU))
ENGINE = AU / "au_wong_choi_auto" / "scripts" / "racing_engine"
sys.path.insert(0, str(ENGINE))

import claw_sportsbet_form as C  # noqa: E402

WIN = ('<td class="td80 awinprice" data-number="0{n}">'
       '<span class="ppodds fixed-win" data-key="{rid}-Sportsbet-FixedWin"'
       ' data-decimals="2">{w}</span></td>')
PLACE = ('<span class="ppodds fixed-place"'
         ' data-key="{rid}-Sportsbet-FixedPlace">{p}</span>')


def _html(rows):
    return "".join(WIN.format(n=n, rid=r, w=w) for n, r, w, _ in rows) + \
           "".join(PLACE.format(rid=r, p=p) for _, r, _, p in rows)


class OddsParseTests(unittest.TestCase):
    def test_win_and_place_join_through_the_runner_id(self):
        """win 格有馬號、place 格冇 —— 兩者靠 data-key 個 runnerId 對返。"""
        got = C.parse_odds_html(_html([(1, "111", "15.00", "3.60"),
                                       (4, "444", "6.00", "2.00")]))
        self.assertEqual(got[1]["Sportsbet-FixedWin"], 15.0)
        self.assertEqual(got[1]["Sportsbet-FixedPlace"], 3.6)
        self.assertEqual(got[4]["Sportsbet-FixedPlace"], 2.0)

    def test_toptote_placeholders_are_not_read_as_prices(self):
        """未開盤嗰陣 TopTote 係 'W' / 'P' 佔位字，唔係賠率。"""
        h = _html([(1, "111", "15.00", "3.60")]) + \
            '<span class="ppodds toptote-win" data-key="111-Sportsbet-TopToteWin">W</span>'
        got = C.parse_odds_html(h)
        self.assertNotIn("Sportsbet-TopToteWin", got[1])

    def test_an_empty_page_yields_nothing_rather_than_erroring(self):
        """curl_cffi 攞到嘅係空 container —— 要出空 dict，唔可以炸。"""
        empty = ('<td data-number="01"><span class="ppodds fixed-win"'
                 ' data-key="111-Sportsbet-FixedWin"></span></td>')
        self.assertEqual(C.parse_odds_html(empty), {})


class OddsStayOutOfScoringTests(unittest.TestCase):
    def test_snapshot_appends_rather_than_overwrites(self):
        """賠率會郁。一個時間點嘅快照有用，一連串先睇得出市場點變。"""
        out = Path(tempfile.mkdtemp())
        races = [(1, {"meta": {"odds": {1: {"Sportsbet-FixedWin": 5.0}}}}, [])]
        C._write_odds_snapshot(races, out, "2026-08-05", "Bairnsdale")
        C._write_odds_snapshot(races, out, "2026-08-05", "Bairnsdale")
        doc = json.loads((out / "Odds.json").read_text())
        self.assertEqual(len(doc["snapshots"]), 2, "第二次要追加，唔係覆蓋")
        self.assertIn("captured_at", doc["snapshots"][0])

    def test_odds_are_written_outside_every_scoring_input(self):
        """引擎讀 `*Facts.md` 同 Logic 嘅 `_data`。賠率一定要喺兩者以外。"""
        out = Path(tempfile.mkdtemp())
        races = [(1, {"meta": {"odds": {1: {"Sportsbet-FixedWin": 5.0,
                                            "Sportsbet-FixedPlace": 2.1}}}}, [])]
        C._write_odds_snapshot(races, out, "2026-08-05", "Bairnsdale")
        written = {p.name for p in out.iterdir()}
        self.assertEqual(written, {"Odds.json"})
        for name in written:
            self.assertFalse(name.endswith("Facts.md"))
            self.assertFalse(name.endswith("_Logic.json"))

    def test_no_engine_leaf_reads_the_odds_file(self):
        """⚠️ 呢條係紅線。有人加咗個 leaf 讀 Odds.json，呢度就要紅。"""
        src = (ENGINE / "engine_core.py").read_text(encoding="utf-8")
        for token in ("Odds.json", "FixedWin", "FixedPlace", "fixed_place"):
            self.assertNotIn(token, src,
                             f"engine_core 唔應該讀賠率（見到 `{token}`）—— "
                             "市場 AUC 0.7393 vs 我哋 0.6530，入咗分就會主導")


if __name__ == "__main__":
    unittest.main()
