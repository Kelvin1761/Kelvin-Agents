"""PBP_Brief from ESPN play-by-play (EXP-20261101-60): same schema, real quarter scores."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import fetch_nba_pbp as p  # noqa: E402


def _play(period, clock, kind, text, home, away, team, people, value=0, made=False, shot=False):
    return {"type": {"text": kind}, "text": text, "period": {"number": period},
            "clock": {"displayValue": clock}, "scoringPlay": made, "scoreValue": value,
            "homeScore": home, "awayScore": away, "team": {"id": team}, "shootingPlay": shot,
            "participants": [{"athlete": {"id": x}} for x in people]}


SUMMARY = {
    "boxscore": {"players": [
        {"team": {"id": "1", "abbreviation": "BOS"},
         "statistics": [{"athletes": [{"athlete": {"id": "10", "displayName": "Home Shooter"}}]}]},
        {"team": {"id": "2", "abbreviation": "NY"},
         "statistics": [{"athletes": [{"athlete": {"id": "20", "displayName": "Away Shooter"}},
                                      {"athlete": {"id": "21", "displayName": "Away Sub"}}]}]}]},
    "plays": [
        _play(1, "11:40", "Jump Shot", "Home Shooter makes jumper", 2, 0, "1", ["10"], 2, True, True),
        _play(1, "10:00", "Three Point Jumper", "Away Shooter makes three point jumper", 2, 3, "2", ["20"], 3, True, True),
        _play(1, "9:00", "Free Throw - 1 of 2", "Away Shooter misses free throw 1 of 2", 2, 3, "2", ["20"], 0, False, True),
        _play(1, "9:00", "Free Throw - 2 of 2", "Away Shooter makes free throw 2 of 2", 2, 4, "2", ["20"], 1, True, True),
        _play(1, "8:00", "Substitution", "Away Sub enters the game for Away Shooter", 2, 4, "2", ["21", "20"]),
        _play(5, "4:00", "Layup Shot", "Home Shooter makes layup", 4, 4, "1", ["10"], 2, True, True),
    ],
}


def test_espn_plays_become_v3_actions():
    actions = p.espn_actions(SUMMARY)
    assert [a["actionType"] for a in actions] == ["2pt", "3pt", "freethrow", "freethrow", "substitution", "2pt"]
    assert actions[1]["teamTricode"] == "NYK" and actions[1]["playerNameI"] == "Away Shooter"
    assert actions[2]["description"].startswith("MISS") and not actions[3]["description"].startswith("MISS")


def test_brief_schema_and_quarters_in_order_with_overtime():
    brief = p.analyze_pbp(p.espn_actions(SUMMARY), "BOS", "NYK")
    assert set(brief) == {"quarter_breakdown", "player_scoring_distribution", "blowout_analysis",
                          "blowout_events_count", "total_actions", "substitution_count"}
    assert list(brief["quarter_breakdown"]) == ["Q1", "OT1"], "OT must follow Q1, not precede it"
    assert brief["quarter_breakdown"]["Q1"] == {"home": 2, "away": 4, "diff": -2}
    assert brief["quarter_breakdown"]["OT1"] == {"home": 2, "away": 0, "diff": 2}
    assert brief["substitution_count"] == 1
    assert brief["player_scoring_distribution"] == {}, "only players with >= 5 points are listed"


def test_no_nba_com_import():
    assert "nba_api" not in (HERE.parent / "scripts" / "fetch_nba_pbp.py").read_text(encoding="utf-8")
