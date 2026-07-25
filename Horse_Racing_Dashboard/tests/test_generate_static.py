import sys
import unittest
from pathlib import Path
from unittest.mock import patch


DASHBOARD_DIR = Path(__file__).resolve().parents[1]
if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))

import generate_static  # noqa: E402


class GenerateStaticTests(unittest.TestCase):
    def test_generate_html_always_replaces_cached_sports_feed(self):
        fresh_feed = {
            "schema_version": 2,
            "validation_status": "valid",
            "sports": {
                "nba": {"analysis_run_id": "nba:fresh", "recommendations": []},
                "tennis": {"analysis_run_id": "tennis:fresh", "recommendations": []},
            },
        }
        data = {
            "meetings": [],
            "races": {},
            "consensus": {},
            "roi": {},
            "sports_feed": {
                "schema_version": 2,
                "sports": {"nba": {"analysis_run_id": "nba:stale"}},
            },
        }

        with patch.object(generate_static, "build_multisport_feed", return_value=fresh_feed):
            html = generate_static.generate_html(data)

        self.assertEqual(data["sports_feed"], fresh_feed)
        self.assertIn("nba:fresh", html)
        self.assertNotIn("nba:stale", html)


if __name__ == "__main__":
    unittest.main()
