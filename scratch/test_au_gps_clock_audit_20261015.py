"""Audit only runners with validated complete GPS splits."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile
from au_gps_clock_audit_20261015 import audit


class ClockAuditTests(unittest.TestCase):
    def test_untracked_winner_does_not_enter_clock_comparison(self):
        xml = '<RaceSummary><FinishTime Time="00:01:01"/><Horses>'
        for name, rank, time in [
            ("h1", 1, "00:01:00"),
            ("h2", 2, "00:01:01"),
            ("h3", 3, "00:01:02"),
            ("untracked", 1, "00:00:01"),
        ]:
            xml += f'<HorseSummary Name="{name}" FinalRank="{rank}" IsFinishTimeOfficial="true"><FinishTime Time="{time}"/></HorseSummary>'
        xml += "</Horses></RaceSummary>"
        with tempfile.TemporaryDirectory() as folder:
            cache = Path(folder)
            path = cache / "meeting.zip"
            with ZipFile(path, "w") as z:
                z.writestr("race.xml", xml)
            source = "https://example.invalid/meeting.zip#race.xml"
            (cache / "xml_manifest.json").write_text(
                json.dumps(
                    [
                        {
                            "file": "meeting.zip",
                            "url": "https://example.invalid/meeting.zip",
                            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        }
                    ]
                )
            )
            events = [{"rows": [{"horse": h, "source": source} for h in ("h1", "h2", "h3")]}]
            with patch("au_gps_clock_audit_20261015.source_events", return_value=(events, {})):
                result = audit(cache)
        self.assertEqual(result["counts"]["races_with_winner_and_header"], 1)
        self.assertEqual(result["header_minus_winner_gps_seconds_quantiles"]["median"], 1)
        self.assertEqual(result["horse_official_flags"]["true"], 3)


if __name__ == "__main__":
    unittest.main()
