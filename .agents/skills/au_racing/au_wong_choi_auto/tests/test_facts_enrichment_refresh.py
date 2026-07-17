from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "racing_engine"))

from au_auto_orchestrator import _facts_path_for_logic
from engine_core import enrich_logic_from_facts

MODERN_FACTS = "\n".join(
    [
        "## Race 3",
        "### 馬匹 #7 Example Star (檔位 4) | 騎師: J Doe | 練馬師: T Smith",
        "- **🔗 賽績線**",
        "| 日期 | 賽事 | 名次 | 對手 | 下仗班次 | 對手後續成績 | 強度 |",
        "|---|---|---|---|---|---|---|",
        "| 2026-05-01 | Randwick R5 | 2 | 頭馬: Rival A | Group 3 | 出 2 次: 1 勝 | 強 |",
        "| 1 | 正式 | 2026-05-01 | Randwick | 1400m | Good 4 | 8 | 2 | 升班 | 9-8-2 | 4 | 較快 | Genuine | 34.12 | 後上 | 中等 | Crowded late | 受阻 |",
        "| 2 | 試閘 | 2026-03-28 | Randwick | 1050m | Good 4 | 4 | 1 | Trial | 4-3-1 | 3 | 較快 | Moderate | 33.90 | 跟前 | 低 | - | [-] |",
    ]
)


class FactsPathGlobTests(unittest.TestCase):
    def test_accepts_underscore_and_space_naming(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            logic = folder / "Race_3_Logic.json"
            logic.write_text("{}", encoding="utf-8")

            underscore = folder / "07-15 Race_3_Facts.md"
            underscore.write_text("x", encoding="utf-8")
            self.assertEqual(_facts_path_for_logic(logic, 3), underscore)
            underscore.unlink()

            spaced = folder / "11-01 Race 3 Facts.md"
            spaced.write_text("x", encoding="utf-8")
            self.assertEqual(_facts_path_for_logic(logic, 3), spaced)

    def test_does_not_cross_match_race_numbers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            logic = folder / "Race_1_Logic.json"
            logic.write_text("{}", encoding="utf-8")
            (folder / "11-01 Race 10 Facts.md").write_text("x", encoding="utf-8")
            self.assertIsNone(_facts_path_for_logic(logic, 1))


class FactsSectionRefreshTests(unittest.TestCase):
    def _enrich(self, logic: dict) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            facts_path = Path(tmp) / "11-01 Race 3 Facts.md"
            facts_path.write_text(MODERN_FACTS, encoding="utf-8")
            return enrich_logic_from_facts(logic, facts_path)

    def test_stale_facts_section_is_replaced_from_facts_file(self) -> None:
        logic = {
            "race_analysis": {"race_number": 3},
            "horses": {
                "7": {
                    "horse_name": "Example Star",
                    "_data": {"facts_section": "OLD PRE-REALIGNMENT BLOB WITHOUT MARKERS"},
                }
            },
        }
        enriched = self._enrich(logic)
        section = enriched["horses"]["7"]["_data"]["facts_section"]
        self.assertIn("賽績線", section)
        self.assertIn("試閘", section)
        self.assertNotIn("OLD PRE-REALIGNMENT BLOB", section)

    def test_missing_section_keeps_existing_value(self) -> None:
        logic = {
            "race_analysis": {"race_number": 3},
            "horses": {
                "9": {  # not in the Facts file
                    "horse_name": "Absent Horse",
                    "_data": {"facts_section": "KEEP ME"},
                }
            },
        }
        enriched = self._enrich(logic)
        self.assertEqual(enriched["horses"]["9"]["_data"]["facts_section"], "KEEP ME")


if __name__ == "__main__":
    unittest.main()
