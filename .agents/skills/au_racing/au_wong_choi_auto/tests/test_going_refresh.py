from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS))

import au_auto_orchestrator
from au_auto_orchestrator import _prepare_logic_data, apply_going_refresh, stored_going


def _logic(going: str = "Soft 5") -> dict:
    return {
        "race_analysis": {
            "race_number": 4,
            "going": going,
            "speed_map": {"going": going, "track_condition": going},
            "meeting_intelligence": {"going": going, "track_summary": f"{going} rail out"},
        },
        "horses": {},
    }


class GoingRefreshTests(unittest.TestCase):
    def test_refresh_overwrites_every_field_the_engine_reads(self) -> None:
        logic = _logic("Soft 5")
        audit = apply_going_refresh(logic, "Good 4")
        race = logic["race_analysis"]
        self.assertEqual(race["going"], "Good 4")
        self.assertEqual(race["speed_map"]["going"], "Good 4")
        self.assertEqual(race["speed_map"]["track_condition"], "Good 4")
        self.assertEqual(race["meeting_intelligence"]["going"], "Good 4")
        self.assertEqual(race["meeting_intelligence"]["track_summary"], "Good 4")
        self.assertEqual(stored_going(logic), "Good 4")
        self.assertTrue(audit["changed"])
        self.assertTrue(audit["family_changed"])  # Soft → Good/Firm
        self.assertEqual(race["going_refresh"]["previous"], "Soft 5")
        self.assertEqual(race["going_refresh"]["applied"], "Good 4")

    def test_same_family_change_is_flagged_but_not_family_changed(self) -> None:
        audit = apply_going_refresh(_logic("Soft 5"), "Soft 7")
        self.assertTrue(audit["changed"])
        self.assertFalse(audit["family_changed"])

    def test_no_change_records_clean_audit(self) -> None:
        audit = apply_going_refresh(_logic("Good 4"), "Good 4")
        self.assertFalse(audit["changed"])
        self.assertFalse(audit["family_changed"])

    def test_missing_sections_are_tolerated(self) -> None:
        logic = {"race_analysis": {"race_number": 1}, "horses": {}}
        audit = apply_going_refresh(logic, "Good 4")
        self.assertEqual(logic["race_analysis"]["going"], "Good 4")
        self.assertEqual(audit["previous"], "")
        self.assertTrue(audit["changed"])

    def test_stored_going_uses_engine_precedence(self) -> None:
        # meeting_intelligence wins over speed_map and race-level going,
        # matching RacingEngine._today_going.
        logic = _logic("Soft 5")
        logic["race_analysis"]["meeting_intelligence"]["going"] = "Heavy 8"
        self.assertEqual(stored_going(logic), "Heavy 8")

    def test_official_going_is_applied_after_facts_enrichment(self) -> None:
        def stale_enrichment(logic_data: dict, _facts_path: Path) -> dict:
            race = logic_data["race_analysis"]
            race["meeting_intelligence"]["going"] = "Soft 5"
            race["going"] = "Soft 5"
            return logic_data

        with tempfile.TemporaryDirectory() as tmp:
            facts_path = Path(tmp) / "Race 4 Facts.md"
            facts_path.write_text("stale facts", encoding="utf-8")
            with patch.object(
                au_auto_orchestrator,
                "enrich_logic_from_facts",
                side_effect=stale_enrichment,
            ):
                prepared, audit = _prepare_logic_data(
                    _logic("Soft 5"),
                    facts_path=facts_path,
                    going_override="Good 4",
                )

        self.assertEqual(stored_going(prepared), "Good 4")
        self.assertEqual(
            prepared["race_analysis"]["meeting_intelligence"]["going"],
            "Good 4",
        )
        self.assertEqual(audit["applied"], "Good 4")


if __name__ == "__main__":
    unittest.main()
