from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = ROOT / ".agents" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import hkjc_profile_scraper as form_lines


class PointInTimeFormLineTests(unittest.TestCase):
    def test_archive_cutoff_excludes_target_and_opponent_future_results(self) -> None:
        target_entries = [
            {
                "race_link": (
                    "https://racing.hkjc.com/racing/information/English/"
                    "Racing/LocalResults.aspx?RaceDate=2026/07/20&Racecourse=HV&RaceNo=1"
                ),
                "placing": 2,
                "date": "20/07/26",
            },
            {
                "race_link": (
                    "https://racing.hkjc.com/racing/information/English/"
                    "Racing/LocalResults.aspx?RaceDate=2026/06/10&Racecourse=HV&RaceNo=2"
                ),
                "placing": 2,
                "date": "10/06/26",
            },
        ]
        result_rows = [
            {
                "placing": 1,
                "horse_name": "對手甲",
                "horse_id": "HK_2024_X001",
            }
        ]
        opponent_profile = {
            "entries": [
                {"race_date_full": "2026/07/22", "placing": 1, "class_grade": "3"},
                {"race_date_full": "2026/07/10", "placing": 2, "class_grade": "4"},
                {"race_date_full": "2026/06/01", "placing": 1, "class_grade": "4"},
            ]
        }

        with (
            patch.object(form_lines, "scrape_race_result", return_value=result_rows) as result_mock,
            patch.object(form_lines, "scrape_horse_profile", return_value=opponent_profile),
            patch.object(form_lines.time, "sleep"),
        ):
            output = form_lines.compute_form_lines(
                target_entries,
                max_races=5,
                rate_limit=0,
                as_of_date="2026-07-15",
            )

        self.assertEqual(result_mock.call_count, 1)
        self.assertEqual(len(output["queries"]), 1)
        self.assertEqual(output["queries"][0]["race_date"], "2026/06/10")
        joined = "\n".join(output["table_lines"])
        self.assertIn("出 1 次: 0 勝", joined)
        self.assertNotIn("出 2 次", joined)

    def test_invalid_cutoff_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            form_lines.compute_form_lines([], as_of_date="15-Jul-2026")


if __name__ == "__main__":
    unittest.main()
