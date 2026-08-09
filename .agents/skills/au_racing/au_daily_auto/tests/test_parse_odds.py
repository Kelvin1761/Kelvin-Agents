"""`parse_odds_html` 嘅回歸測試 —— 三個實際 markup 陷阱。

2026-08-05 之前呢個 parser 由頭到尾攞到 0 匹，於是每個 Formguide 都寫
`Flucs:$- $-`，而個 bug 完全睇唔出（冇人 assert 過賠率非空）。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from claw_sportsbet_form import parse_odds_html  # noqa: E402

# 真實 markup 嘅三個特徵：
#   1. 屬性次序係 data-event → data-key → data-decimals → class（class 喺後面）
#   2. 賠率包喺一個 <a> 裡面，但 span 自己有 data-odds
#   3. 位置賠率嗰批 span **唔喺**有 data-number 嘅表裡面，靠 market id 接返
REAL = """
<table><tr>
  <td class="td80 awinprice " data-number="01" data-sort="01">
    <span data-event="3397175" data-key="32540936-Sportsbet-FixedWin" data-decimals="2"
          class="ppodds fixed-win" data-odds="2"><a class="oc-table-link">2.00</a></span>
  </td>
</tr><tr>
  <td class="td80 awinprice " data-number="02" data-sort="02">
    <span data-event="3397175" data-key="32540937-Sportsbet-FixedWin" data-decimals="2"
          class="ppodds fixed-win" data-odds="21"><a class="oc-table-link">21.00</a></span>
  </td>
</tr></table>
<div class="cards">
  <span class="ppodds fixed-place" data-decimals="2" data-key="32540936-Sportsbet-FixedPlace"
        data-event="3397175" data-odds="1.25"><a class="oc-table-link">1.25</a></span>
  <span class="ppodds fixed-place" data-decimals="2" data-key="32540937-Sportsbet-FixedPlace"
        data-event="3397175" data-odds="4.2"><a class="oc-table-link">4.20</a></span>
  <span class="ppodds toptote-win" data-key="32540936-Sportsbet-TopToteWin"
        data-event="3397175" data-odds="W"><a>W</a></span>
</div>
"""


class TestParseOdds(unittest.TestCase):
    def test_win_and_place_both_land_on_the_right_runner(self):
        od = parse_odds_html(REAL)
        self.assertEqual(od[1]["Sportsbet-FixedWin"], 2.0)
        self.assertEqual(od[1]["Sportsbet-FixedPlace"], 1.25)
        self.assertEqual(od[2]["Sportsbet-FixedWin"], 21.0)
        self.assertEqual(od[2]["Sportsbet-FixedPlace"], 4.2)

    def test_place_spans_outside_the_numbered_table_are_still_matched(self):
        # 靠 market id 接，唔靠「最近一個 data-number」——後者會令 16 個位置賠率
        # 全部歸咗最後一匹（實測只認到 1 個）。
        od = parse_odds_html(REAL)
        self.assertEqual(sum(1 for v in od.values() if "Sportsbet-FixedPlace" in v), 2)

    def test_placeholder_odds_are_not_prices(self):
        # 未開盤係 "W"/"P" 佔位字。
        od = parse_odds_html(REAL)
        self.assertNotIn("Sportsbet-TopToteWin", od[1])

    def test_empty_and_odds_free_html(self):
        self.assertEqual(parse_odds_html(""), {})
        self.assertEqual(parse_odds_html("<table><tr><td data-number='1'>x</td></tr></table>"), {})

    def test_unnumbered_span_is_dropped_not_guessed(self):
        html = ('<span class="ppodds fixed-win" data-key="999-Sportsbet-FixedWin" '
                'data-odds="3.5"><a>3.50</a></span>')
        self.assertEqual(parse_odds_html(html), {})


if __name__ == "__main__":
    unittest.main()
