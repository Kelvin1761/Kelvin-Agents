"""On-court lineups from ESPN play-by-play (EXP-20261101-01).

A hand-built game pins the three things that decide every number: who is on
court (box starters, substitutions, inferred period starts), when a
possession ends, and the rating arithmetic.
"""
from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

import pytest

NBA_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(NBA_ROOT))
import nba_espn_lineups as P  # noqa: E402
import nba_espn_league as L  # noqa: E402

HOME = [f"h{i}" for i in range(1, 8)]   # h1-h5 start, h6/h7 bench
AWAY = [f"a{i}" for i in range(1, 7)]   # a1-a5 start, a6 bench


def athlete(pid, starter):
    return {"athlete": {"id": pid, "displayName": pid.upper()}, "starter": starter,
            "didNotPlay": False}


def box():
    def side(team_id, abbr, ids):
        return {"team": {"id": team_id, "abbreviation": abbr},
                "statistics": [{"athletes": [athlete(p, i < 5) for i, p in enumerate(ids)]}]}
    return {"players": [side("1", "BOS", HOME), side("2", "NYK", AWAY)]}


def play(kind, team, clock, period=1, who=(), points=0, shooting=False):
    return {"type": {"text": kind}, "team": {"id": team}, "clock": {"displayValue": clock},
            "period": {"number": period}, "participants": [{"athlete": {"id": p}} for p in who],
            "scoringPlay": bool(points), "scoreValue": points, "shootingPlay": shooting}


def game(plays):
    return {"boxscore": box(), "plays": plays}


def test_possessions_end_where_nba_com_ends_them():
    plays = [
        play("Jump Shot", "1", "11:40", who=["h1"], points=2, shooting=True),        # BOS 1
        play("Jump Shot", "2", "11:20", who=["a1"], shooting=True),                   # miss
        play("Offensive Rebound", "2", "11:19", who=["a2"]),
        play("Lost Ball Turnover", "2", "11:10", who=["a2"]),                         # NYK 1
        play("Layup Shot", "1", "10:50", who=["h2"], points=2, shooting=True),
        play("Shooting Foul", "2", "10:50", who=["a3"]),
        play("Substitution", "2", "10:50", who=["a6", "a3"]),
        play("Free Throw - 1 of 1", "1", "10:50", who=["h2"], points=1),              # BOS 2 (and-one)
        play("Shooting Foul", "1", "10:30", who=["h3"]),
        play("Free Throw - 1 of 2", "2", "10:30", who=["a1"], points=1),
        play("Free Throw - 2 of 2", "2", "10:30", who=["a1"]),                        # miss
        play("Defensive Rebound", "1", "10:29", who=["h4"]),                          # NYK 2
        play("Traveling", "1", "10:10", who=["h5"]),                                  # BOS 3
        play("End Period", "2", "0:00"),                                              # NYK 3 (had ball)
    ]
    result = P.parse_game(game(plays))
    rows = result["players"]
    assert result["quality"]["possessions"] == 6
    assert rows["h1"]["off_poss"] == 3 and rows["h1"]["def_poss"] == 3
    # a3 was subbed out between the and-one basket and its free throw: the
    # basket is his, the free throw and the possession end are a6's.
    assert rows["a3"]["def_poss"] == 1 and rows["a6"]["def_poss"] == 2
    assert rows["h1"]["pts_for"] == 5 and rows["h1"]["pts_against"] == 1
    assert rows["a3"]["pts_against"] == 4 and rows["a6"]["pts_against"] == 1


def test_minutes_follow_the_clock_and_substitutions():
    plays = [play("Jump Shot", "1", "6:00", who=["h1"], shooting=True),
             play("Substitution", "1", "6:00", who=["h6", "h1"]),
             play("End Period", "1", "0:00")]
    rows = P.parse_game(game(plays))["players"]
    assert rows["h1"]["minutes"] == 6 and rows["h6"]["minutes"] == 6
    assert rows["h2"]["minutes"] == 12


def test_later_period_starters_are_inferred_from_the_log():
    plays = [
        play("Substitution", "1", "1:00", period=1, who=["h6", "h5"]),
        play("End Period", "1", "0:00", period=1),
        # Period 2: h7 acts without entering, h1 is subbed out without entering;
        # h2, h3 never touch the log and carry over from period 1's closing five.
        play("Jump Shot", "1", "11:30", period=2, who=["h7"], shooting=True),
        play("Substitution", "1", "11:00", period=2, who=["h6", "h1"]),
        play("Technical Foul", "1", "10:00", period=2, who=["h5"]),   # bench tech: ignored
        play("End Period", "1", "0:00", period=2),
    ]
    result = P.parse_game(game(plays))
    assert result["quality"]["bad_periods"] == []
    rows = result["players"]
    # On at the start of period 2: h7, h1 (log) + h2, h3, h4 (carried over).
    assert rows["h7"]["minutes"] == 12 and rows["h1"]["minutes"] == 12 + 1
    assert rows["h5"]["minutes"] == 11, "h5 left at 1:00 of period 1 and the tech does not put him back"
    assert rows["h6"]["minutes"] == 1 + 11


def test_unresolved_period_is_flagged_not_guessed():
    plays = [play("End Period", "1", "0:00", period=1),
             # Six home players act at the start of period 2: impossible.
             *[play("Jump Shot", "1", "11:00", period=2, who=[p], shooting=True) for p in HOME[:6]],
             play("End Period", "1", "0:00", period=2)]
    result = P.parse_game(game(plays))
    assert result["quality"]["bad_periods"] == [2]
    assert result["players"]["h1"]["minutes"] == 12, "period 2 credits no one"


def test_ratings_are_ratios_of_totals_with_the_fitted_scale():
    games = [{"players": {"p": {"name": "P", "minutes": 24, "off_poss": 50, "def_poss": 50,
                                "pts_for": 55, "pts_against": 50}}},
             {"players": {"p": {"name": "P", "minutes": 24, "off_poss": 50, "def_poss": 50,
                                "pts_for": 45, "pts_against": 60}}}]
    row = P.player_ratings(games, possession_scale=1.0)["p"]
    assert (row["OFF_RATING"], row["DEF_RATING"], row["NET_RATING"]) == (100.0, 110.0, -10.0)
    assert row["PACE"] == 100.0 and row["source"] == "espn_pbp"
    scaled = P.player_ratings(games)["p"]
    assert scaled["DEF_RATING"] == round(100 * 110 / (100 * P.PLAYER_POSSESSION_SCALE), 1)


def test_ratings_keyed_by_nba_id_drop_unresolved_names():
    games = [{"players": {"x": {"name": "Known Player", "minutes": 10, "off_poss": 20,
                                "def_poss": 20, "pts_for": 20, "pts_against": 20},
                          "y": {"name": "Nobody", "minutes": 10, "off_poss": 20,
                                "def_poss": 20, "pts_for": 20, "pts_against": 20}}}]
    table = P.player_ratings(games, {"known player": 7})
    assert set(table) == {7}


def test_finished_days_are_fetched_once_with_fresh_after(monkeypatch):
    import nba_espn_http
    seen = []
    monkeypatch.setattr(nba_espn_http, "get_json",
                        lambda url, **kw: seen.append((url, kw.get("fresh_after"))) or {})
    P.fetch_summary("401", date(2026, 10, 28))
    url, fresh = seen[0]
    assert url.endswith("/summary?event=401")
    assert fresh == P.day_close(date(2026, 10, 28)) and fresh.hour == 6


def test_open_day_is_not_cached(monkeypatch):
    import nba_espn_http
    seen = []
    monkeypatch.setattr(nba_espn_http, "get_json",
                        lambda url, **kw: seen.append(kw.get("fresh_after")) or {})
    tomorrow = datetime.now(P.US_EASTERN).date()
    P.fetch_summary("402", tomorrow)
    assert seen == [None]


def test_fill_on_court_ratings_only_touches_matched_rows():
    table = {1: {"OFF_RATING": None, "DEF_RATING": None, "NET_RATING": None, "PACE": None},
             2: {"OFF_RATING": None, "DEF_RATING": None, "NET_RATING": None, "PACE": None}}
    ratings = {1: {"OFF_RATING": 110.0, "DEF_RATING": 105.0, "NET_RATING": 5.0, "PACE": 99.0,
                   "source": "espn_pbp"}}
    assert L.fill_on_court_ratings(table, ratings) == 1
    assert table[1]["DEF_RATING"] == 105.0 and table[1]["on_court_source"] == "espn_pbp"
    assert table[2]["DEF_RATING"] is None


@pytest.fixture(autouse=True)
def _cache(monkeypatch, tmp_path):
    monkeypatch.setenv("WC_NBA_ESPN_LINEUP_DIR", str(tmp_path / "lineups"))
