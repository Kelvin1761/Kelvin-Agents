from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SCRIPT_DIR = ROOT / ".agents" / "skills" / "race_compliance_qa" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from race_compliance_scan import parse_result_json


class RaceComplianceScanTests(unittest.TestCase):
    def test_parse_result_json_supports_archive_results_mapping(self) -> None:
        parsed = parse_result_json(
            {
                "meeting": {"name": "Canterbury"},
                "events": {"7": {"event_number": 7}},
                "results": {
                    "7": [
                        {"competitor_number": 3, "horse_name": "Mountain Chatter", "finish_position": 1},
                        {"competitor_number": 13, "horse_name": "Dear Jewel", "finish_position": 2},
                    ]
                },
            }
        )

        self.assertEqual(parsed[7], [(1, 3, "Mountain Chatter"), (2, 13, "Dear Jewel")])


if __name__ == "__main__":
    unittest.main()
