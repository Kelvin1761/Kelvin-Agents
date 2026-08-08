from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "racing_engine"))

from au_auto_orchestrator import _facts_path_for_logic
import build_au_logic
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

    def test_ignores_directory_named_like_facts_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            logic = folder / "Race_1_Logic.json"
            logic.write_text("{}", encoding="utf-8")
            (folder / "Race_1_Facts.md").mkdir()
            real_facts = folder / "05-08 Race 1 Facts.md"
            real_facts.write_text("x", encoding="utf-8")
            self.assertEqual(_facts_path_for_logic(logic, 1), real_facts)


class BuilderEnricherParityTests(unittest.TestCase):
    def test_canonical_builder_is_enrichment_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            facts_path = Path(tmp) / "11-01 Race 3 Facts.md"
            facts_path.write_text(MODERN_FACTS, encoding="utf-8")
            built = build_au_logic.build_logic_from_facts(facts_path)
            enriched = enrich_logic_from_facts(
                copy.deepcopy(built),
                facts_path,
            )
        self.assertEqual(built, enriched)

    def test_track_resources_resolve_from_builder(self) -> None:
        self.assertTrue(build_au_logic.TRACK_RESOURCE_DIR.is_dir())
        profile = build_au_logic._load_track_profile("Warwick Farm", 1100)
        self.assertEqual(profile["venue"], "Warwick Farm")
        self.assertGreater(profile["straight_m"], 0)

    def test_predicted_pace_populates_backward_compatible_alias(self) -> None:
        facts = "\n".join(
            [
                "### 🗺️ 自動步速圖 (Python Facts Model V4)",
                "- **predicted_pace:** 正常",
                "- **pace_confidence:** High",
            ]
        )
        speed_map = build_au_logic._parse_speed_map(facts)
        self.assertEqual(speed_map["predicted_pace"], "正常")
        self.assertEqual(speed_map["expected_pace"], "正常")

    def test_arbitrary_temp_folder_is_not_a_venue(self) -> None:
        self.assertEqual(build_au_logic._venue_from_folder_name("local"), "")
        self.assertEqual(
            build_au_logic._venue_from_folder_name(
                "2026-07-15 Warwick Farm Race 1-7"
            ),
            "Warwick Farm",
        )


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

    def test_missing_section_fails_instead_of_scoring_stale_logic(self) -> None:
        logic = {
            "race_analysis": {"race_number": 3},
            "horses": {
                "9": {  # not in the Facts file
                    "horse_name": "Absent Horse",
                    "_data": {"facts_section": "KEEP ME"},
                }
            },
        }
        with self.assertRaisesRegex(ValueError, "FIELD ALIGNMENT FAILED"):
            self._enrich(logic)

    def test_temp_folder_name_cannot_overwrite_existing_venue(self) -> None:
        logic = {
            "race_analysis": {
                "race_number": 3,
                "meeting_intelligence": {
                    "venue": "Warwick Farm",
                    "going": "Soft 5",
                    "source": "Race_3_Logic.json",
                },
            },
            "horses": {
                "7": {"horse_name": "Example Star", "_data": {}},
            },
        }
        enriched = self._enrich(logic)
        meeting = enriched["race_analysis"]["meeting_intelligence"]
        self.assertEqual(meeting["venue"], "Warwick Farm")
        self.assertNotIn("tmp", meeting["venue"].lower())


if __name__ == "__main__":
    unittest.main()
