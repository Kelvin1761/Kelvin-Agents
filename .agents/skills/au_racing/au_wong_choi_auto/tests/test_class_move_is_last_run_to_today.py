"""「今場升降班」一定要係「上一仗 → 今場」，唔可以讀賽績表最新一行嘅「班次」欄。

嗰欄量嘅係「上上仗 → 該仗」：Sir Rupert Clarke Stakes（一級賽）入面，上仗由
All-Star Mile（$2M）跑去 Memsie（$750k）嘅馬被當成「今場降班」+6。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from au_racing_engine.engine_core import RacingEngine, today_class_move  # noqa: E402

HEADER = (
    "| # | 類型／歷史HC | 日期 | 場地 | 路程 | 場地狀況 | 檔位 | 名次 | 班次 | 跑位軌跡 | PI | 段速 "
    "| 早段步速 | L600/RT | 走位跑法 | 走位消耗 | 備註 | 寬恕認定 | 獎金 | Sportsbet原始班次 |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n"
)
ROWS = (
    "| 1 | 正式 | 2026-08-29 | Caulfield R8 | 1400m | Soft | 1 | 11/12 (-5.84L) | ↓↓大幅降班 "
    "| S8→F11 | -3 | 較慢 | - | - | - | - | - | [-] | 750000 | MEMSIE |\n"
    "| 2 | 正式 | 2026-03-07 | Flemington R7 | 1600m | Good | 6 | 1/9 | ↑↑大幅升班 "
    "| S3→F1 | +2 | 較快 | - | - | - | - | - | [-] | 2000000 | ALL-STAR MILE |\n"
)


def _engine(race_prize):
    facts = "- **📋 完整賽績檔案 (全數列出 2 場):**\n" + HEADER + ROWS
    horse = {"horse_name": "Tom Kitten", "horse_number": "1",
             "class_move": "↓↓大幅降班",  # 舊 builder 寫入嘅錯位值
             "_data": {"facts_section": facts}}
    return RacingEngine(horse, {"prize": race_prize, "race_class": "Sir Rupert Clarke Stakes"},
                        facts_section=facts)


class TodayClassMoveTest(unittest.TestCase):
    def test_pure_function(self):
        self.assertEqual(today_class_move(800_000, 750_000), "=")
        self.assertEqual(today_class_move(2_000_000, 750_000), "↑↑大幅升班")
        self.assertEqual(today_class_move(200_000, 750_000), "↓↓大幅降班")
        self.assertEqual(today_class_move(0, 750_000), "")
        self.assertEqual(today_class_move(None, 750_000), "")
        self.assertEqual(today_class_move(500_000, None), "")

    def test_engine_ignores_stored_misaligned_value(self):
        eng = _engine(race_prize=0)
        self.assertEqual(eng._class_move_today(), "")
        self.assertEqual(eng._class_move_display(), "班次資料未明")
        _, note, _ = eng._class_score()
        self.assertNotIn("班次有回落", note)

    def test_engine_uses_last_run_to_today(self):
        self.assertEqual(_engine(race_prize=800_000)._class_move_today(), "=")
        eng = _engine(race_prize=150_000)
        self.assertEqual(eng._class_move_today(), "↓↓大幅降班")
        _, note, _ = eng._class_score()
        self.assertIn("班次有回落", note)


if __name__ == "__main__":
    unittest.main()
