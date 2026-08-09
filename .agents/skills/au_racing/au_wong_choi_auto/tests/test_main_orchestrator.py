from __future__ import annotations

import sys
import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import patch

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
    _extract_meeting,
    _resolve_official_going,
    _sportsbet_meeting_spec,
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

    def test_facts_lookup_ignores_same_named_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "Race_3_Facts.md").mkdir()
            facts = folder / "07-15 Race 3 Facts.md"
            facts.write_text("facts", encoding="utf-8")
            self.assertEqual(_find_facts_file(folder, 3), facts)

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

    def test_sportsbet_url_resolves_complete_tracked_meeting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mapping = Path(tmp) / "meetings.json"
            mapping.write_text(json.dumps({
                "2026-08-08 Alice Springs Race 1-2": {
                    "date": "2026-08-08",
                    "meetingId": "446824",
                    "races": ["3398527", "3398528"],
                }
            }), encoding="utf-8")
            name, meta = _sportsbet_meeting_spec(
                "https://www.sportsbetform.com.au/446824/3398527/",
                mapping,
            )
        self.assertEqual(name, "2026-08-08 Alice Springs Race 1-2")
        self.assertEqual(meta["races"], ["3398527", "3398528"])

    def test_sportsbet_url_runs_full_meeting_extractor_not_probe(self) -> None:
        import au_orchestrator as O

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mapping = root / "meetings.json"
            mapping.write_text(json.dumps({
                "2026-08-08 Alice Springs Race 1-2": {
                    "date": "2026-08-08",
                    "meetingId": "446824",
                    "races": ["3398527", "3398528"],
                }
            }), encoding="utf-8")

            def fake_run(command):
                Path(command[command.index("--out-dir") + 1]).mkdir(parents=True)

            with patch.object(O, "SPORTSBET_MEETING_IDS", mapping), \
                    patch.object(O, "AU_RACING", root), \
                    patch.object(O, "_run", side_effect=fake_run) as run:
                out = _extract_meeting(
                    "https://www.sportsbetform.com.au/446824/3398527/"
                )
        command = run.call_args.args[0]
        self.assertEqual(out.name, "2026-08-08 Alice Springs Race 1-2")
        self.assertIn("--meeting-url", command)
        self.assertIn("3398527,3398528", command)
        self.assertNotIn("--probe", command)


if __name__ == "__main__":
    unittest.main()
