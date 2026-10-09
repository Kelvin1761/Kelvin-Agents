from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[2] / "nba_data_extractor" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import claw_sportsbet_odds as claw  # noqa: E402


class SportsbetExtractionFailureTests(unittest.TestCase):
    def test_cli_no_matches_exits_75_instead_of_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            program = """
import io, runpy, sys
from unittest.mock import patch
script, outdir = sys.argv[1:]
sys.argv = [script, '--outdir', outdir, '--date', '2026-10-08']
with patch('urllib.request.urlopen', side_effect=lambda *a, **k: io.BytesIO(b'{"events":[]}')):
    runpy.run_path(script, run_name='__main__')
"""
            result = subprocess.run(
                [sys.executable, "-c", program, str(SCRIPTS / "claw_sportsbet_odds.py"), tmp],
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(result.returncode, 75, result.stderr)
            self.assertIn("沒有發現任何 NBA 賽事", result.stdout)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_no_matches_returns_retryable_failure_and_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            extractor = claw.SportsbetNBAExtractor(outdir=tmp, target_date="2026-10-08")
            with mock.patch.object(extractor, "fetch_daily_matches", return_value=[]):
                self.assertEqual(extractor.run(), 75)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_empty_extraction_is_retryable_with_or_without_espn_tags(self) -> None:
        for tags in (set(), {"BOS_LAL"}):
            with self.subTest(tags=tags), tempfile.TemporaryDirectory() as tmp:
                extractor = claw.SportsbetNBAExtractor(outdir=tmp, target_date="2026-10-08")
                with mock.patch.object(extractor, "fetch_daily_matches", return_value=[{
                    "tag": "BOS_LAL", "event_local_date": "2026-10-08"
                }]), mock.patch.object(extractor, "_allowed_tags_from_espn", return_value=tags), mock.patch.object(
                    extractor, "traverse_and_extract", return_value={}
                ):
                    self.assertEqual(extractor.run(), 75)
                self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_unresolved_date_without_espn_tags_is_retryable(self) -> None:
        extractor = claw.SportsbetNBAExtractor(target_date="2026-10-08")
        with mock.patch.object(extractor, "fetch_daily_matches", return_value=[{
            "tag": "BOS_LAL", "event_local_date": None
        }]), mock.patch.object(extractor, "_allowed_tags_from_espn", return_value=set()), mock.patch.object(
            extractor, "traverse_and_extract"
        ) as extract:
            self.assertEqual(extractor.run(), 75)
        extract.assert_not_called()

    def test_valid_extraction_returns_success_only_after_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            extractor = claw.SportsbetNBAExtractor(outdir=tmp, target_date="2026-10-08")
            payload = {"target_analysis_date": "2026-10-08"}
            with mock.patch.object(extractor, "fetch_daily_matches", return_value=[{
                "tag": "BOS_LAL", "event_local_date": "2026-10-08"
            }]), mock.patch.object(extractor, "_allowed_tags_from_espn", return_value={"BOS_LAL"}), mock.patch.object(
                extractor, "traverse_and_extract", return_value={"BOS_LAL": payload}
            ):
                self.assertEqual(extractor.run(), 0)
            self.assertEqual(json.loads(
                (Path(tmp) / "Sportsbet_Odds_BOS_LAL.json").read_text(encoding="utf-8")
            ), payload)

    def test_write_failure_returns_retryable_failure(self) -> None:
        extractor = claw.SportsbetNBAExtractor(target_date="2026-10-08")
        with mock.patch.object(extractor, "fetch_daily_matches", return_value=[{
            "tag": "BOS_LAL", "event_local_date": "2026-10-08"
        }]), mock.patch.object(extractor, "_allowed_tags_from_espn", return_value={"BOS_LAL"}), mock.patch.object(
            extractor, "traverse_and_extract", return_value={"BOS_LAL": {}}
        ), mock.patch.object(claw.os, "makedirs", side_effect=OSError("disk unavailable")):
            self.assertEqual(extractor.run(), 75)


if __name__ == "__main__":
    unittest.main()
