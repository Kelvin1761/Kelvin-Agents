from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import unified_reflector_core as core


class UnifiedReflectorPathTests(unittest.TestCase):
    def test_direct_hkjc_meeting_path_is_used_without_archive_lookup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            meeting_dir = Path(tmp) / "2026-07-08_HappyValley"
            meeting_dir.mkdir()

            self.assertEqual(core.resolve_meeting_dir("hkjc", meeting_ref=str(meeting_dir)), meeting_dir.resolve())

    def test_reports_stay_in_the_supplied_meeting_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            meeting_dir = Path(tmp) / "moved-meeting"
            meeting_dir.mkdir()

            self.assertEqual(
                core.default_report_path("hkjc", meeting_dir),
                meeting_dir.resolve() / "HKJC_Reflection_Report.md",
            )
            self.assertEqual(
                core.default_report_path("au", meeting_dir),
                meeting_dir.resolve() / "moved-meeting_Reflector_Report.md",
            )

    def test_hkjc_extraction_does_not_sync_database_unless_requested(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            meeting_dir = Path(tmp) / "2026-07-08_HappyValley"
            meeting_dir.mkdir()

            def fake_extract(command: list[str], _label: str) -> None:
                Path(command[3]).write_text("{}", encoding="utf-8")

            with (
                mock.patch.object(core, "run_logged_command", side_effect=fake_extract),
                mock.patch.object(core, "_import_hkjc_sync") as sync_import,
            ):
                results_file = core.ensure_results_file(
                    "hkjc",
                    meeting_dir,
                    "https://example.test/results",
                    force_extract=True,
                )

            self.assertEqual(results_file.parent, meeting_dir.resolve())
            self.assertTrue(results_file.exists())
            sync_import.assert_not_called()


if __name__ == "__main__":
    unittest.main()
