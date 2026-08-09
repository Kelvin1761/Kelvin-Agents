from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "racing_engine"))

import au_runtime_micro_ablation as R
from source_alignment import normalize_going


class RuntimeAuditParityTests(unittest.TestCase):
    def test_discovery_includes_scheduler_archive_subdirectory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            live = root / "2026-08-08 Randwick Race 1-1"
            archived = root / "Archive" / "2026-08-07 Seymour Race 1-1"
            live.mkdir(parents=True)
            archived.mkdir(parents=True)
            (live / "Race_1_Logic.json").write_text("{}", encoding="utf-8")
            (archived / "Race_1_Logic.json").write_text("{}", encoding="utf-8")

            materialized, placeholders = R.discover_logic_files(root)

        self.assertEqual(placeholders, [])
        self.assertEqual(
            {path.parent.name for path in materialized},
            {live.name, archived.name},
        )

    def test_archive_temperature_pollution_is_canonicalised(self) -> None:
        self.assertEqual(normalize_going("Synthetic 8"), "Synthetic")
        self.assertEqual(normalize_going("Good 25"), "Good")
        self.assertEqual(normalize_going("Soft 5 (Turf)"), "Soft 5")

    def test_prepare_refreshes_archive_logic_from_matching_facts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            meeting = Path(tmp) / "2026-08-08 Alice Springs Race 1-1"
            meeting.mkdir()
            logic_path = meeting / "Race_1_Logic.json"
            facts_path = meeting / "08-08 Race 1 Facts.md"
            facts_path.write_text(
                "## Race 1\n"
                "### 馬匹 #1 Fresh Evidence (檔位 2) | 騎師: J Doe | 練馬師: T Smith\n",
                encoding="utf-8",
            )
            (meeting / "Meeting_Summary.md").write_text(
                "Date: 2026-08-08\nTrack Condition: Soft 6\n",
                encoding="utf-8",
            )
            logic = {
                "race_analysis": {"race_number": 1, "going": "Unknown"},
                "horses": {"1": {"horse_name": "Fresh Evidence", "_data": {}}},
            }

            prepared, resolved = R.prepare_logic_for_scoring(logic, logic_path)

        self.assertEqual(resolved, facts_path)
        self.assertEqual(prepared["race_analysis"]["going"], "Soft 6")
        self.assertEqual(logic["race_analysis"]["going"], "Unknown")

    def test_score_variant_uses_prepared_horse_and_real_facts_path(self) -> None:
        seen = {}

        class FakeEngine:
            def __init__(self, horse, _context, *, facts_section, facts_path):
                seen.update(
                    horse_name=horse["horse_name"],
                    facts_section=facts_section,
                    facts_path=facts_path,
                )

            def analyze_horse(self):
                return {"ability_score": 77.0}

        original = {
            "race_analysis": {"race_number": 1},
            "horses": {"1": {"horse_name": "Stale", "_data": {}}},
        }
        prepared = {
            "race_analysis": {"race_number": 1},
            "horses": {
                "1": {
                    "horse_name": "Fresh",
                    "_data": {"facts_section": "fresh facts"},
                }
            },
        }
        aligned = [{
            "horse_number": 1,
            "horse": original["horses"]["1"],
            "actual_pos": 2,
            "result_sp_label": 4.0,
        }]
        facts_path = Path("/tmp/08-08 Race 1 Facts.md")
        with patch.object(R, "RacingEngine", FakeEngine):
            rows = R.score_variant(
                original,
                aligned,
                Path("/tmp/Race_1_Logic.json"),
                [],
                prepared_logic=prepared,
                facts_path=facts_path,
            )

        self.assertEqual(rows[0]["score"], 77.0)
        self.assertEqual(seen["horse_name"], "Fresh")
        self.assertEqual(seen["facts_section"], "fresh facts")
        self.assertEqual(seen["facts_path"], facts_path)


if __name__ == "__main__":
    unittest.main()
