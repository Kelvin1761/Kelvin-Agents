"""Settlement must work on the real BoxScoreTraditionalV3 payload shape.

2026-10-21: V3 players have firstName/familyName/nameI and no ``name``; the
extractor read ``name`` so every box-score player became '?' and every leg was
PLAYER_NOT_FOUND (21/21 on the first two finished games of the 2026-27 season).
The payload below mirrors the live shape (fields and values trimmed).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

TEST_DIR = Path(__file__).resolve().parent
REPO_ROOT = TEST_DIR.parents[4]
SCRIPTS_DIR = TEST_DIR.parent / "scripts"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(SCRIPTS_DIR))

from fetch_nba_results import extract_player_stats  # noqa: E402
from verify_props_hits import get_player_actual, verify_legs  # noqa: E402


def v3_player(first, family, name_i, position, minutes, comment="", pts=0, reb=0, ast=0, tpm=0):
    return {
        "personId": 1, "firstName": first, "familyName": family, "nameI": name_i,
        "playerSlug": f"{first}-{family}".lower(), "position": position, "comment": comment,
        "jerseyNum": "",
        "statistics": {"minutes": minutes, "points": pts, "reboundsTotal": reb, "assists": ast,
                       "threePointersMade": tpm, "steals": 0, "blocks": 0, "turnovers": 0},
    }


PAYLOAD = {"boxScoreTraditional": {
    "homeTeam": {"teamTricode": "DET", "teamName": "Pistons", "players": [
        v3_player("Ausar", "Thompson", "A. Thompson", "F", "33:15", pts=12, reb=7, ast=2),
        v3_player("Duncan", "Robinson", "D. Robinson", "G", "27:49", pts=15, tpm=3),
        v3_player("Isaiah", "Joe", "I. Joe", "", "10:02", pts=4),
        v3_player("Chris", "Lanier", "C. Lanier", "", "", comment="DNP - Coach's Decision"),
        v3_player("Eli", "Harkless", "E. Harkless", "", "", comment="Inactive - G League - Two-Way"),
    ]},
    "awayTeam": {"teamTricode": "OKC", "teamName": "Thunder", "players": [
        v3_player("Jalen", "Williams", "J. Williams", "F", "30:00", pts=21, reb=5, ast=4),
        v3_player("Nikola", "Jokić", "N. Jokić", "C", "35:00", pts=30, reb=12, ast=9),
    ]},
}}


class SettlementNamesV3Tests(unittest.TestCase):
    def setUp(self):
        self.players = extract_player_stats(PAYLOAD)
        self.by_name = {p["name"]: p for p in self.players}

    def test_names_are_built_from_first_and_family_name(self):
        self.assertIn("Ausar Thompson", self.by_name)
        self.assertNotIn("?", self.by_name)
        self.assertEqual(len(self.players), 7)

    def test_name_falls_back_to_name_i_then_legacy_name_field(self):
        legacy = {"boxScoreTraditional": {"homeTeam": {"players": [{"name": "Old Shape", "statistics": {}}]}}}
        self.assertEqual(extract_player_stats(legacy)[0]["name"], "Old Shape")
        only_initial = {"boxScoreTraditional": {"homeTeam": {"players": [{"nameI": "X. Y", "statistics": {}}]}}}
        self.assertEqual(extract_player_stats(only_initial)[0]["name"], "X. Y")

    def test_starters_are_players_with_a_position(self):
        self.assertTrue(self.by_name["Ausar Thompson"]["starter"])
        self.assertFalse(self.by_name["Isaiah Joe"]["starter"])

    def test_dnp_and_inactive_players_get_zero_minutes(self):
        self.assertEqual(self.by_name["Chris Lanier"]["minutes"], "0")
        self.assertEqual(self.by_name["Eli Harkless"]["minutes"], "0")
        self.assertEqual(self.by_name["Isaiah Joe"]["minutes"], "10:02")

    def test_legs_settle_against_real_shape_names(self):
        legs = [
            {"player": "Ausar Thompson", "stat": "REB", "line": 6},
            {"player": "Duncan Robinson", "stat": "3PM", "line": 4},
            {"player": "Chris Lanier", "stat": "PTS", "line": 5},
        ]
        out = verify_legs(legs, {"players": self.players, "final_score": "x"})
        self.assertEqual([r["status"] for r in out], ["✅ HIT", "❌ MISS", "↩️ VOID_DNP"])
        self.assertEqual(out[0]["actual"], 7)

    def test_accent_insensitive_name_match(self):
        self.assertEqual(get_player_actual(self.players, "Nikola Jokic")["name"], "Nikola Jokić")

    def test_surname_fallback_needs_a_compatible_first_name(self):
        # Sportsbet lists "Jaylin Williams" (not in the box score); the only Williams
        # there is Jalen. Settling with his stats would be wrong -> not found.
        self.assertIsNone(get_player_actual(self.players, "Jaylin Williams"))
        # nickname variant with the same initial still resolves uniquely
        self.assertEqual(get_player_actual(self.players, "Jal Williams")["name"], "Jalen Williams")
        self.assertEqual(get_player_actual(self.players, "J. Williams")["name"], "Jalen Williams")

    def test_unknown_player_is_not_found(self):
        self.assertIsNone(get_player_actual(self.players, "Nobody Here"))


if __name__ == "__main__":
    unittest.main()
