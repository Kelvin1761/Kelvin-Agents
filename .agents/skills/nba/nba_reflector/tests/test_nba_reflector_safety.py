from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


TEST_DIR = Path(__file__).resolve().parent
REPO_ROOT = TEST_DIR.parents[4]
SCRIPTS_DIR = TEST_DIR.parent / "scripts"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(SCRIPTS_DIR))

from nba_daily_review_archive import verification_is_complete  # noqa: E402
from verify_props_hits import (  # noqa: E402
    get_player_actual,
    match_report_to_game,
    verify_legs,
)


class NbaReflectorSafetyTests(unittest.TestCase):
    def test_exact_name_wins_before_ambiguous_surname(self) -> None:
        players = [
            {"name": "Jalen Williams", "pts": 30},
            {"name": "Jaylin Williams", "pts": 8},
        ]
        self.assertEqual(get_player_actual(players, "Jaylin Williams")["pts"], 8)
        self.assertIsNone(get_player_actual(players, "Williams"))

    def test_dnp_player_prop_is_void_not_miss(self) -> None:
        verified = verify_legs(
            [{"player": "Player A", "stat": "PTS", "line": 10.0}],
            {
                "final_score": "BOS 100 - 90 LAL",
                "players": [{"name": "Player A", "minutes": "PT0M", "pts": 0}],
            },
        )
        self.assertEqual(verified[0]["status"], "↩️ VOID_DNP")
        self.assertEqual(verified[0]["outcome"], "void")
        self.assertIsNone(verified[0]["cleared"])

    def test_legacy_wsh_report_matches_canonical_was_result(self) -> None:
        game = {"away": {"team": "CHI"}, "home": {"team": "WAS"}}
        self.assertIs(
            match_report_to_game("Game_CHI_WSH_Full_Analysis.md", [game]),
            game,
        )

    def test_archive_gate_requires_every_leg_resolved_or_void(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "verification.json"
            path.write_text(
                json.dumps({
                    "summary": {
                        "total_legs": 3,
                        "hits": 1,
                        "misses": 1,
                        "voids": 1,
                        "unverified": 0,
                    }
                }),
                encoding="utf-8",
            )
            self.assertEqual(verification_is_complete(path), (True, "complete"))
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["summary"].update({"voids": 0, "unverified": 1})
            path.write_text(json.dumps(payload), encoding="utf-8")
            complete, reason = verification_is_complete(path)
            self.assertFalse(complete)
            self.assertEqual(reason, "unverified_legs:1")

    def test_empty_verification_only_passes_explicit_no_bet_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "verification.json"
            path.write_text(
                json.dumps({
                    "summary": {
                        "total_legs": 0,
                        "hits": 0,
                        "misses": 0,
                        "voids": 0,
                        "unverified": 0,
                    }
                }),
                encoding="utf-8",
            )
            self.assertEqual(
                verification_is_complete(path),
                (False, "no_verification_legs"),
            )
            self.assertEqual(
                verification_is_complete(path, allow_empty=True),
                (True, "complete"),
            )


if __name__ == "__main__":
    unittest.main()
