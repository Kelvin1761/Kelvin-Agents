"""賽績線表唔准丟續行。

個表係「一場一對手一行」：每場第一個對手嗰行帶住 `#`／日期／賽事／我嘅名次，
亞軍／季軍嘅續行呢四欄空白。`parse_formline_table` 曾經用 `int(cols[1])` 做
「係唔係數據行」嘅測試，於是**每一條續行都被丟掉** —— 實測 37,265 條對手行
只有 14,580 條（39.1%）入到 Logic，跌 60.9%。而
`engine_core._formline_summary()` 個 docstring 寫住「EVERY notable past
opponent」，佢驅動 FL2 60 分封頂同賽績線敘述。

2026-09-06 R3 嘉應高昇：11 條對手行剩 5 條，而丟掉嗰批正正係兩隻
✅✅ 超強組（金鑽貴人、舉步生風），留低嘅係睇落最弱嘅亞軍。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_wong_choi" / "scripts"))

from create_hkjc_logic_skeleton import parse_formline_table


# 真實形狀，抄自 2026-09-06 R3 嘉應高昇 Facts.md
BLOCK = """### 馬號 1 — 嘉應高昇 | 騎師: 潘頓

🔗 **賽績線:**
  **綜合評估:** ✅✅ 極強 (強組比例: 8/9)

| # | 日期 | 賽事 | 我嘅名次 | 對手 | 後續比賽Class | 對手後續成績 | 強度評估 |
|---|------|------|----------|------|---------------|--------------|----------|
| 1 | 26/04/26 | 田 R5 | 1 (-4-1/4) | [2] 里見夢境 (亞軍) | - | 未有出賽 | - |
|  |  |  |  | [3] 精算暴雪 (季軍) | 三級賽 | 出 2 次: 0 勝 | ⚠️ 中組 |
| 2 | 06/04/26 | 田 R7 | 1 (-4-1/4) | [2] 驕陽明駒 (亞軍) | 一級賽 | 出 1 次: 0 勝 | ❌ 弱組 |
|  |  |  |  | [3] 金鑽貴人 (季軍) | 一級賽 二級賽 | 出 2 次: 1 勝 | ✅✅ 超強組 |

💡 **LLM 指示:** 引用此「完整賽績檔案」。
"""


class ContinuationRowsSurvive(unittest.TestCase):
    def test_every_opponent_row_is_kept(self):
        rows = parse_formline_table(BLOCK)
        self.assertEqual(len(rows), 4, [r['opponents'] for r in rows])

    def test_continuation_rows_inherit_the_race(self):
        rows = parse_formline_table(BLOCK)
        self.assertEqual([r['race_num'] for r in rows], ['1', '1', '2', '2'])
        self.assertEqual([r['date'] for r in rows],
                         ['26/04/26', '26/04/26', '06/04/26', '06/04/26'])
        self.assertEqual([r['race_id'] for r in rows],
                         ['田 R5', '田 R5', '田 R7', '田 R7'])
        self.assertEqual([r['my_finish'] for r in rows],
                         ['1 (-4-1/4)', '1 (-4-1/4)', '1 (-4-1/4)', '1 (-4-1/4)'])

    def test_the_strong_opponents_are_the_ones_that_used_to_be_dropped(self):
        """呢個係 bug 嘅實際後果：留低最弱嘅亞軍，丟掉 ✅✅ 超強組嘅季軍。"""
        rows = parse_formline_table(BLOCK)
        by_opp = {r['opponents']: r['strength'] for r in rows}
        self.assertIn('[3] 金鑽貴人 (季軍)', by_opp)
        self.assertEqual(by_opp['[3] 金鑽貴人 (季軍)'], '✅✅ 超強組')
        self.assertIn('[3] 精算暴雪 (季軍)', by_opp)

    def test_class_is_carried_through(self):
        """對手其後參賽嘅班次要入到 Logic —— 呢個係 2026-09-04 量度嘅基礎：
        59.7% 其後跑過分級賽嘅對手被評「弱組／中組」。班次入分試過，REJECT。"""
        rows = parse_formline_table(BLOCK)
        graded = [r for r in rows if '級賽' in r['next_class']]
        self.assertEqual(len(graded), 3)

    def test_header_and_separator_are_not_rows(self):
        rows = parse_formline_table(BLOCK)
        self.assertTrue(all(r['opponents'] not in ('對手', '') for r in rows))

    def test_no_table_returns_empty(self):
        self.assertEqual(parse_formline_table("### 馬號 1 — 測試\n冇賽績線。\n"), [])

    def test_a_leading_continuation_row_is_not_invented(self):
        """未見過任何一場之前嘅續行冇賽事可以承繼，唔可以砌一個出嚼。"""
        orphan = BLOCK.replace('| 1 | 26/04/26 | 田 R5 | 1 (-4-1/4) | [2] 里見夢境 (亞軍) | - | 未有出賽 | - |\n', '')
        rows = parse_formline_table(orphan)
        self.assertTrue(all(r['race_num'] for r in rows), rows)


if __name__ == "__main__":
    unittest.main()
