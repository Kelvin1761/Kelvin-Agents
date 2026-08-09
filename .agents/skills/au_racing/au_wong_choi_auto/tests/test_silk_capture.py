#!/usr/bin/env python3
"""綵衣抓取 —— 用真 markup 釘住，唔用假設嘅 markup。

2026-08-06：`parse_silks` 喺五個場次、380 匹馬身上回 0 個綵衣，而每一版賽事頁其實
有 12 個綵衣 URL。原因係 pattern 寫死 `class="runner-number"`，要求緊接一個收引號，
但真 markup 係 `class="runner-number active"` 同 `class="runner-number bordered
active"`。一個「睇落合理」嘅 pattern 靜靜咁出零 —— 同賠率抓取一模一樣嘅坑，所以
呢度嘅 fixture 全部由真頁面複製出嚟，唔係我砌嘅。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

AU = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(AU))

import claw_sportsbet_form as C  # noqa: E402

# 由 2026-08-06 Gosford 第 1 場真頁面複製（縮短 URL，結構原封不動）
SELECTIONS_BLOCK = '''<div class="selection"> <strong class="selection-label">Selections:</strong>
<span class="selection-runner"> <span>
<img src="//images.puntcdn.com/silks/svg/019cc11d-42b1-7181-b279-5c6720366d74_1.svg" alt="Runners Colours">
<span class="runner-number active">1</span>
</span> </span> <span class="selection-runner"> <span>
<img src="//images.puntcdn.com/silks/svg/019cdf8e-a4be-75d0-a3e8-a1faa021c889_1.svg" alt="Runners Colours">
<span class="runner-number active">2</span>
</span> </span> </div>'''

RUNNER_SILKS_BLOCK = '''<div class="runner-silks">
<img src="//images.puntcdn.com/silks/svg/019cb5e2-fbac-71dd-9b90-3b7e96104fa7_1.svg" alt="Runners Colours">
<span class="runner-number bordered active">7</span>
</div>
<div class="runner-silks">
<img src="//images.puntcdn.com/silks/svg/019cccd7-9728-70cf-a078-42d23d4f1f2a_1.svg" alt="Runners Colours">
<span class="runner-number bordered">8</span>
</div>'''

# 2026-08-09 Ballarat 真頁面：馬號改到綵衣圖片前面。
NUMBER_FIRST_RUNNER_BLOCK = '''<div class="runner-summary clearfix">
<div class="runner-number bordered active">1</div>
<div class="runner-silks">
<img src="//images.puntcdn.com/silks/svg/019cc30a-c4ac-7548-b492-540510074ae0_1.svg">
</div>
</div>'''


class SilkCaptureTests(unittest.TestCase):
    def test_tipped_runners_block(self):
        got = C.parse_silks(SELECTIONS_BLOCK)
        self.assertEqual(sorted(got), [1, 2])

    def test_full_field_block_with_multi_class_number_span(self):
        # `bordered active` 同 `bordered` —— 舊 pattern 兩個都唔中。
        got = C.parse_silks(RUNNER_SILKS_BLOCK)
        self.assertEqual(sorted(got), [7, 8])

    def test_current_number_before_image_markup(self):
        got = C.parse_silks(NUMBER_FIRST_RUNNER_BLOCK)
        self.assertEqual(sorted(got), [1])
        self.assertTrue(got[1].endswith("019cc30a-c4ac-7548-b492-540510074ae0_1.svg"))

    def test_both_blocks_on_one_page(self):
        got = C.parse_silks(SELECTIONS_BLOCK + "\n" + RUNNER_SILKS_BLOCK)
        self.assertEqual(sorted(got), [1, 2, 7, 8])

    def test_protocol_relative_url_is_made_absolute(self):
        # dashboard 個 AU_SILK_URL_RE 過唔到 `//…`，一定要補 `https:`。
        url = C.parse_silks(RUNNER_SILKS_BLOCK)[7]
        self.assertTrue(url.startswith("https://images.puntcdn.com/silks/"))

    def test_an_image_without_a_number_does_not_steal_the_next_runner(self):
        # 舊 pattern 用萬用 `.*?`，一個冇馬號嘅 img 會配到下一匹馬身上，
        # 靜靜咁畀錯馬號一件綵衣。
        html = ('<img src="//images.puntcdn.com/silks/svg/orphan_1.svg" alt="x">'
                '<div>no number here</div>' + RUNNER_SILKS_BLOCK)
        self.assertEqual(sorted(C.parse_silks(html)), [7, 8])

    def test_post_race_page_with_no_silks_returns_empty_not_garbage(self):
        self.assertEqual(C.parse_silks("<div>no silks on a resulted page</div>"), {})


if __name__ == "__main__":
    unittest.main()
