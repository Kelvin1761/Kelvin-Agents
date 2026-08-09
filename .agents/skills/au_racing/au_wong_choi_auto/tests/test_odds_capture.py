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



# ⚠️ 上面嗰個 fixture 係**假設**嘅 markup：class 喺 data-key 之前、值係 span 嘅
# 直接文字、冇 data-odds。佢一直通過，而 parser 喺真實頁面回 0 匹 —— 每個
# Formguide 都寫 `Flucs:$- $-`，冇人察覺。所以再加一個用**真實**markup 嘅 case：
# 屬性次序倒轉、值包喺 <a> 裡面、有 data-odds、而位置賠率嗰批 span 唔喺
# 有 data-number 嘅 <td> 內（靠 market id 接返）。
REAL_WIN = ('<td class="td80 awinprice " data-number="0{n}" data-sort="0{n}">'
            '<span data-event="3397175" data-key="{rid}-Sportsbet-FixedWin"'
            ' data-decimals="2" class="ppodds fixed-win" data-odds="{w}">'
            '<a class="oc-table-link">{w}0</a></span></td>')
REAL_PLACE = ('<span class="ppodds fixed-place" data-decimals="2"'
              ' data-key="{rid}-Sportsbet-FixedPlace" data-event="3397175"'
              ' data-odds="{p}"><a class="oc-table-link">{p}</a></span>')


class RealMarkupTests(unittest.TestCase):
    """由 2026-08-05 真實頁面抄落嚟嘅 markup 形狀。"""

    def _html(self):
        rows = [(1, "32540936", "2", "1.25"), (2, "32540937", "21", "4.2")]
        return ("<table>"
                + "".join(REAL_WIN.format(n=n, rid=r, w=w) for n, r, w, _ in rows)
                + "</table><div>"
                + "".join(REAL_PLACE.format(rid=r, p=p) for _, r, _, p in rows)
                + "</div>")

    def test_attribute_order_and_nested_anchor(self):
        got = C.parse_odds_html(self._html())
        self.assertEqual(got[1]["Sportsbet-FixedWin"], 2.0)
        self.assertEqual(got[2]["Sportsbet-FixedWin"], 21.0)

    def test_place_outside_the_numbered_cell_joins_by_market_id(self):
        got = C.parse_odds_html(self._html())
        self.assertEqual(got[1]["Sportsbet-FixedPlace"], 1.25)
        self.assertEqual(got[2]["Sportsbet-FixedPlace"], 4.2)

if __name__ == "__main__":
    unittest.main()


class SpeedmapRowNumberTests(unittest.TestCase):
    """Speedmap 讀嘅係**行號**，唔係出現次序 —— 呢兩樣係反嘅。

    2026-08-04：舊版用 `enumerate` 攞出現次序。但版面由**大行號**先列出
    （`Finish post 13 3.Smokin' Romans … 1 4.Brayden Star`），所以第一個列出
    嘅係「最後嗰個位置」，被當成 1 = 最前。整個映射反晒。

    實測 58 場：用出現次序同實際 800m 走位嘅相關係 **ρ = −0.180**（方向錯），
    改讀行號之後係 **+0.235**。一個靜靜咁出錯而數字睇落好合理嘅 bug。
    """

    RAW = ("<div>Speed Map</div><div>Predicted settling positions after start</div>"
           "<div>Barriers</div><div>Finish post</div>"
           "<div>13</div><div>3. Smokin' Romans (NZL)</div>"
           "<div>12</div><div>5. Freedom Rally</div>"
           "<div>2</div><div>9. Thedoctoroflove</div>"
           "<div>1</div><div>4. Brayden Star (GBR)</div>"
           "<div>Replay speed map</div><div>Weather</div>")

    def test_row_number_becomes_the_position(self):
        got = C.parse_speedmap(self.RAW)
        self.assertEqual(got[4], 1, "行 1 嘅馬 4 應該係最前")
        self.assertEqual(got[9], 2)
        self.assertEqual(got[5], 12)
        self.assertEqual(got[3], 13, "行 13 嘅馬 3 應該係最後")

    def test_appearance_order_would_have_been_backwards(self):
        """釘死方向：第一個列出嘅馬**唔可以**得到最細嘅位置序。"""
        got = C.parse_speedmap(self.RAW)
        self.assertGreater(got[3], got[4],
                           "第一個列出（馬 3）喺後面，唔可以排喺馬 4 前面")

    def test_a_page_without_the_map_yields_nothing(self):
        self.assertEqual(C.parse_speedmap("<div>Full Form</div>"), {})
