"""ESPN player feeds in the old nba_api shapes (2026-10-30; sole source since EXP-20261101-60).

Rosters are keyed by ESPN athlete id, game logs come back as PlayerGameLog
frames, so the extractor's cut-off, dedup and L10 logic are unchanged.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

NBA_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(NBA_ROOT))
sys.path.insert(0, str(NBA_ROOT / "nba_data_extractor" / "scripts"))
import nba_espn_stats as E  # noqa: E402
import nba_extractor as X  # noqa: E402

GAMELOG = json.loads((Path(__file__).parent / "fixtures" / "espn_gamelog_giannis_2027.json")
                     .read_text(encoding="utf-8"))


# ── ESPN game log in the PlayerGameLog shape ────────────────────────────────
def test_regular_season_rows_match_playergamelog_shape_newest_first():
    rows = E.gamelog_rows(GAMELOG, "Regular Season")
    assert [r["GAME_DATE"] for r in rows] == [
        "OCT 28, 2026", "OCT 26, 2026", "OCT 24, 2026", "OCT 23, 2026", "OCT 21, 2026"]
    first = rows[0]
    assert first["MATCHUP"] == "MIA @ ATL" and first["WL"] == "W"
    assert (first["MIN"], first["PTS"], first["REB"], first["AST"]) == (31, 24, 18, 3)
    assert (first["FGM"], first["FGA"], first["FG3M"], first["FG3A"]) == (11, 18, 0, 2)
    assert first["FG_PCT"] == 0.611
    assert rows[1]["MATCHUP"] == "MIA vs. DAL"


def test_game_date_is_the_us_eastern_day_not_the_utc_day():
    # 2026-10-24T00:00Z tipped at 20:00 ET on Oct 23
    rows = E.gamelog_rows(GAMELOG, "Regular Season")
    assert "OCT 23, 2026" in [r["GAME_DATE"] for r in rows]
    assert "OCT 24, 2026" in [r["GAME_DATE"] for r in rows]   # the 22:00Z game that day


def test_date_to_mirrors_nba_api_date_window():
    rows = E.gamelog_rows(GAMELOG, "Regular Season", date_to=date(2026, 10, 24))
    assert [r["GAME_DATE"] for r in rows] == ["OCT 24, 2026", "OCT 23, 2026", "OCT 21, 2026"]


def test_season_types_are_kept_apart():
    assert len(E.gamelog_rows(GAMELOG, "Pre Season")) == 3
    assert E.gamelog_rows(GAMELOG, "Playoffs") == []


def test_play_in_games_are_not_regular_season_or_playoffs():
    payload = json.loads(json.dumps(GAMELOG))
    block = payload["seasonTypes"][0]
    payload["seasonTypes"].insert(0, {"displayName": "2026-27 Play In Regular Season",
                                      "categories": block["categories"]})
    assert len(E.gamelog_rows(payload, "Regular Season")) == 5     # not 10
    assert E.gamelog_rows(payload, "Playoffs") == []


def test_espn_season_naming():
    assert E.espn_season_year("2026-27") == 2027


# ── ESPN is the only player feed ────────────────────────────────────────────
def test_roster_is_keyed_by_espn_athlete_id_and_marks_rookies():
    payload = {"athletes": [
        {"id": 4433134, "fullName": "Rookie Guard", "position": {"abbreviation": "G"}, "experience": {"years": 0}},
        {"id": 3032977, "fullName": "Giannis Antetokounmpo", "position": {"abbreviation": "F"}, "experience": {"years": 13}},
        {"fullName": "No Id"}]}

    class Response:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return payload
    rows = E.espn_roster("MIA", get=lambda url, timeout=15: Response())
    assert [(r["player_id"], r["player_id_source"], r["experience"]) for r in rows] == [
        ("4433134", "espn", "R"), ("3032977", "espn", "13")], "no id = not a player, never guessed"


def test_player_log_frame_reads_espn_by_athlete_id(monkeypatch):
    seen = []
    monkeypatch.setattr(E, "espn_gamelog_frame",
                        lambda espn_id, season, season_type, day: seen.append((espn_id, season, season_type, day)) or "frame")
    assert X.player_log_frame("3032977", "2026-27", "10/24/2026", "Regular Season") == ("frame", "espn")
    assert seen == [("3032977", "2026-27", "Regular Season", date(2026, 10, 24))]


def test_extractor_has_no_nba_com_path():
    source = (NBA_ROOT / "nba_data_extractor" / "scripts" / "nba_extractor.py").read_text(encoding="utf-8")
    for retired in ("nba_api", "nba_api_breaker", "nba_league_snapshot", "nba_official_injuries", "stats.nba.com/"):
        assert retired not in source, retired
