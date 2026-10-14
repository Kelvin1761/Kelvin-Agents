"""Padding detection must count prose rather than decimal report fragments."""

import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_nba_output.py"
SPEC = importlib.util.spec_from_file_location("nba_padding_validator", SCRIPT)
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


class PaddingSentenceBoundariesTests(unittest.TestCase):
    def test_distinct_decimal_mc_rows_are_not_padding(self):
        content = "\n".join(
            f"📊 **MC 模擬 (10,000次)**: 命中率 **81.{suffix}%** | Edge **4.{suffix}%**"
            for suffix in range(10, 19)
        )
        self.assertEqual(validator.check_fw04_padding(content), [])

    def test_distinct_decimal_odds_and_averages_are_not_padding(self):
        content = "\n".join(
            f"球員里程碑 **@1.{suffix}:**\n📊 數據: L10 `[4, 7, 5, 4, 7, 7, 5, 7, 10, 5]` | AVG 6.{suffix}"
            for suffix in range(40, 49)
        )
        self.assertEqual(validator.check_fw04_padding(content), [])

    def test_repeated_chinese_prose_is_blocked(self):
        sentence = "呢位球員近期嘅實際表現同場上角色都非常穩定，因此今場嘅攻守形勢值得深入分析"
        self.assertTrue(validator.check_fw04_padding((sentence + "。") * 4))

    def test_repeated_english_prose_is_blocked(self):
        sentence = "This player has a consistent role and an unusually strong recent performance"
        self.assertTrue(validator.check_fw04_padding((sentence + ". ") * 4))

    def test_identical_numeric_rows_are_still_blocked(self):
        row = "📊 **MC 模擬 (10,000次)**: 命中率 **81.49%** | Edge **4.12%**"
        self.assertTrue(validator.check_fw04_padding("。".join([row] * 4)))


if __name__ == "__main__":
    unittest.main()
