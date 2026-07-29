from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
MAIN_SCRIPTS = (
    ROOT
    / ".agents"
    / "skills"
    / "au_racing"
    / "au_wong_choi"
    / "scripts"
)
sys.path.insert(0, str(MAIN_SCRIPTS))

from au_orchestrator import (
    _auto_command,
    _facts_has_horses,
    _find_facts_file,
    _resolve_official_going,
    _venue_from_meeting,
)


class MainOrchestratorTests(unittest.TestCase):
    def test_existing_spaced_facts_file_is_reused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            facts = folder / "07-15 Race 3 Facts.md"
            facts.write_text("facts", encoding="utf-8")
            self.assertEqual(_find_facts_file(folder, 3), facts)

    def test_empty_facts_file_is_not_treated_as_usable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            facts = Path(tmp) / "07-15 Race 3 Facts.md"
            facts.write_text("", encoding="utf-8")
            self.assertFalse(_facts_has_horses(facts))

    def test_multiword_venue_is_preserved(self) -> None:
        self.assertEqual(
            _venue_from_meeting("2026-07-15 Warwick Farm Race 1-7"),
            "Warwick Farm",
        )
        self.assertEqual(
            _venue_from_meeting("2026-07-25_Eagle_Farm_Race_1_9"),
            "Eagle Farm",
        )

    def test_cli_going_wins_over_meeting_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "Meeting_Summary.md").write_text(
                "Track Condition: Soft 5\n",
                encoding="utf-8",
            )
            self.assertEqual(_resolve_official_going(folder, "Good 4"), "Good 4")
            self.assertEqual(_resolve_official_going(folder, None), "Soft 5")

    def test_auto_command_passes_official_going(self) -> None:
        command = _auto_command(Path("/tmp/Race_1_Logic.json"), "Good 4")
        self.assertEqual(command[-2:], ["--going", "Good 4"])


if __name__ == "__main__":
    unittest.main()
