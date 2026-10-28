"""EXP-20261028-12（讓磅認字）同 EXP-20261028-13（級數分 ≥15 場規則剷走、逐項加減）。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
ENGINE_DIR = ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts" / "au_racing_engine"
sys.path.insert(0, str(ENGINE_DIR.parent))

from au_racing_engine.engine_core import _is_handicap_title
from au_racing_engine.renderer import _class_weight_detail_lines
from au_racing_engine.scoring import CLASS_MICRO_WEIGHTS


class HandicapTitleTests(unittest.TestCase):
    def test_handicap_titles(self):
        for title in ("TAB HANDICAP", "SKY RACING BENCHMARK 72 Handic", "XXXX GOLD Class 4 Handicap",
                      "Vinidex & Philmac Rating 0 - 64", "EXCHANGE HOTEL KILCOY RATINGS BAND 0 - 55 Han",
                      "INLAND PETROLEUM COUNTRY BOOSTED MAIDEN HANDI",       # 約 45 字截斷
                      "NEXT RACE DAY - 20TH SEPTEMBER CG&amp;E MAIDEN HA",
                      "Catanachs Jewellers 3YO BM64 H"):
            self.assertTrue(_is_handicap_title(title), title)

    def test_set_weight_and_unknown_titles_are_not_handicaps(self):
        # Warwick Farm 2026-10-28 R1：PLATE 係定磅，負磅由年齡性別定
        for title in ("ASAHI SUPER DRY PLATE", "Hygain Edge Maiden Plate", "RSN Bendigo 945AM 3YO Maiden P",
                      "SOMERSET REGIONAL COUNCIL QTIS Three-Year-Old", "Ladbrokes Bendigo Cup", "", None,
                      "Ladbrokes Odds Surge 3YO Maiden Plate"):
            self.assertFalse(_is_handicap_title(title), title)

    def test_short_title_ending_in_h_is_not_a_truncated_handicap(self):
        self.assertFalse(_is_handicap_title("Grand Ha"))


class ClassRuleTests(unittest.TestCase):
    def test_career15_rules_are_removed(self):
        self.assertFalse(any(k.startswith("career15_") for k in CLASS_MICRO_WEIGHTS))

    def test_detail_lines_show_each_delta(self):
        auto = {"class_weight_detail": {"class": {
            "base": 60.0, "final": 59.18, "notes": ["經驗較薄且上仗未跑入場內頭 25%"],
            "adjustments": [{"delta": -0.82, "factor": "經驗較薄且上仗未跑入場內頭 25%"}]}}}
        lines = _class_weight_detail_lines(auto, "class_score")
        self.assertEqual(lines, ["基礎分 60.0", "經驗較薄且上仗未跑入場內頭 25% -0.82", "級數分 ＝ 59.2（0-100 封頂）"])

    def test_no_rule_fired_says_so(self):
        auto = {"class_weight_detail": {"class": {"base": 60.0, "final": 60.0, "notes": [], "adjustments": []}}}
        self.assertIn("冇規則觸發", _class_weight_detail_lines(auto, "class_score")[1])


if __name__ == "__main__":
    unittest.main()
