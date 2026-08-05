import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


DASHBOARD_DIR = Path(__file__).resolve().parents[1]
if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))

import generate_static  # noqa: E402


class DropAuMeetingTests(unittest.TestCase):
    """Archiving a meeting has to be able to take it off the dashboard.

    Before `drop_au_meetings` existed the incremental path could only add or
    replace, so an archived meeting stayed in the published snapshot forever and
    the scheduler's pre-publish check refused to deploy -- correctly. Cloudflare
    sat on a stale snapshot for two nights while four freshly analysed meetings
    waited behind the gate.
    """

    def _snapshot(self, tmp):
        payload = {
            "meetings": [
                {"date": "2026-08-05", "venue": "Belmont", "region": "AU"},
                {"date": "2026-08-05", "venue": "Cranbourne", "region": "AU"},
                {"date": "2026-07-15", "venue": "HappyValley", "region": "HK"},
            ],
            "races": {
                "2026-08-05|Belmont": {"meeting": {"region": "AU"},
                    "races_by_analyst": {"K": [{"race_number": 1}]}},
                "2026-08-05|Cranbourne": {"meeting": {"region": "AU"},
                    "races_by_analyst": {"K": [{"race_number": 1}]}},
                "2026-07-15|HappyValley": {"meeting": {"region": "HK"},
                    "races_by_analyst": {"K": [{"race_number": 1}]}},
            },
            "consensus": {
                "2026-08-05|Belmont|1": {"x": 1},
                "2026-08-05|Cranbourne|1": {"x": 1},
                "2026-07-15|HappyValley|1": {"x": 1},
            },
            "roi": {},
        }
        path = Path(tmp) / "live.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_drops_meeting_races_and_consensus_together(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = generate_static.drop_au_meetings(
                self._snapshot(tmp), ["2026-08-05|Belmont"])
        self.assertEqual([f"{m['date']}|{m['venue']}" for m in out["meetings"]],
                         ["2026-08-05|Cranbourne", "2026-07-15|HappyValley"])
        self.assertNotIn("2026-08-05|Belmont", out["races"])
        # consensus keys 係 `{meeting_key}|...`，要跟埋走，唔可以留孤兒。
        self.assertEqual(sorted(out["consensus"]),
                         ["2026-07-15|HappyValley|1", "2026-08-05|Cranbourne|1"])

    def test_drops_several_and_leaves_the_rest_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = generate_static.drop_au_meetings(
                self._snapshot(tmp),
                ["2026-08-05|Belmont", "2026-08-05|Cranbourne"])
        self.assertEqual(len(out["meetings"]), 1)
        self.assertEqual(out["meetings"][0]["venue"], "HappyValley")

    def test_unknown_key_is_a_no_op_not_a_crash(self):
        # 早更／晚更都會傳「dashboard 上已經冇」嘅 key（例如上一個 run 已經剪走）。
        with tempfile.TemporaryDirectory() as tmp:
            out = generate_static.drop_au_meetings(
                self._snapshot(tmp), ["2026-01-01|Nowhere"])
        self.assertEqual(len(out["meetings"]), 3)

    def test_meta_is_rebuilt_so_the_counts_match_what_remains(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = generate_static.drop_au_meetings(
                self._snapshot(tmp), ["2026-08-05|Belmont"])
        # 剪走 Belmont 之後 AU 應該只剩 Cranbourne 一個場次。meta 冇重建嘅話
        # dashboard 個 header 會報一個唔存在嘅場次數。
        self.assertEqual(out["meta"]["regions"]["AU"]["meetings"], 1)


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
