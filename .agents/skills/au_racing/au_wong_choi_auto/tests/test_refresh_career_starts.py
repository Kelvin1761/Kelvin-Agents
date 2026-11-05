"""EXP-20261105-08：重播一定要由 facts_section 重抽生涯場數，唔可以信 Logic 存咗嘅舊值。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts"))

from au_racing_engine.data_prep import refresh_career_starts  # noqa: E402


class RefreshCareerStartsTests(unittest.TestCase):
    def test_stale_zero_is_replaced(self) -> None:
        # 2026-08-08 Alice Springs 真實形狀：Facts 寫 `生涯: 7`，Logic 存住 0／DEBUT。
        logic = {"horses": {"1": {"career_race_starts": 0, "career_tag": "DEBUT",
                                  "_data": {"facts_section": "  - 生涯: 7\n  - 生涯標記: `DEBUT` (生涯 0 場)\n"}}}}
        self.assertEqual(refresh_career_starts(logic), 1)
        self.assertEqual(logic["horses"]["1"]["career_race_starts"], 7)
        self.assertEqual(logic["horses"]["1"]["career_tag"], "ESTABLISHED")

    def test_sportsbet_format_and_true_debut(self) -> None:
        logic = {"horses": {"1": {"career_race_starts": 4, "_data": {"facts_section": "  - 生涯: 4 : 0-1-1\n"}},
                            "2": {"career_race_starts": 0, "_data": {"facts_section": "  - 生涯: 0\n"}}}}
        self.assertEqual(refresh_career_starts(logic), 0)
        self.assertEqual(logic["horses"]["2"]["career_tag"], "DEBUT")

    def test_missing_section_left_alone(self) -> None:
        logic = {"horses": {"1": {"career_race_starts": 3, "_data": {}}}}
        self.assertEqual(refresh_career_starts(logic), 0)
        self.assertEqual(logic["horses"]["1"]["career_race_starts"], 3)


if __name__ == "__main__":
    unittest.main()
