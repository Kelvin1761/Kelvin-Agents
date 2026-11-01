"""League tables from ESPN box scores while stats.nba.com is blocked (2026-10-31).

EXP-20261031-01 measured the box-score tables against nba_api's: team pace
within 0.65 (median), defensive rating within 0.85, DEF_RANK within one place,
player true shooting / eFG identical, usage within 0.6.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

NBA_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(NBA_ROOT))
sys.path.insert(0, str(NBA_ROOT / "nba_data_extractor" / "scripts"))
import nba_espn_league as L  # noqa: E402
import nba_api_breaker as B  # noqa: E402
import nba_extractor as X  # noqa: E402

SUMMARY = json.loads((Path(__file__).parent / "fixtures" / "espn_summary_mia_atl_20261028.json")
                     .read_text(encoding="utf-8"))
DAY = date(2026, 10, 28)


@pytest.fixture(autouse=True)
def _cache(monkeypatch, tmp_path):
    monkeypatch.setenv("WC_NBA_ESPN_BOX_DIR", str(tmp_path / "espn_box"))


def test_summary_parses_into_team_totals_and_player_lines():
    game = L.parse_summary(SUMMARY, DAY)
    mia, atl = game["teams"]["MIA"], game["teams"]["ATL"]
    assert (mia["PTS"], atl["PTS"]) == (129, 117)
    assert (mia["FGM"], mia["FGA"], mia["OREB"], mia["TOV"]) == (51, 96, 12, 16)  # team TOV incl. team-credited
    assert mia["PLAYER_TOV"] == 14 and mia["MIN"] == 240
    giannis = next(p for p in game["players"] if p["name"] == "Giannis Antetokounmpo")
    assert (giannis["MIN"], giannis["PTS"], giannis["FGM"], giannis["FGA"], giannis["FTA"]) == (31, 24, 11, 18, 5)
    assert all(p["MIN"] > 0 for p in game["players"]), "DNPs are not lines"


def test_overtime_minutes_come_from_line_scores():
    summary = json.loads(json.dumps(SUMMARY))
    for competitor in summary["header"]["competitions"][0]["competitors"]:
        competitor["linescores"].append({"displayValue": "10"})
    assert L.parse_summary(summary, DAY)["teams"]["MIA"]["MIN"] == 265


def test_team_table_matches_hand_arithmetic():
    game = L.parse_summary(SUMMARY, DAY)
    table = L.team_advanced([game])
    mia, atl = game["teams"]["MIA"], game["teams"]["ATL"]
    poss_mia = 0.98 * (96 + 0.44 * 23 - 12 + 16)
    assert table["MIA"]["OFF_RATING"] == round(100 * 129 / poss_mia, 1)
    assert table["MIA"]["DEF_RATING"] == table["ATL"]["OFF_RATING"]
    assert table["MIA"]["PACE"] == table["ATL"]["PACE"]
    assert {table["MIA"]["DEF_RANK"], table["ATL"]["DEF_RANK"]} == {1, 2}
    assert table["MIA"]["source"] == "espn_box"
    assert mia["MIN"] == atl["MIN"] == 240


def test_player_table_keys_by_nba_id_and_drops_unresolved_names():
    game = L.parse_summary(SUMMARY, DAY)
    table = L.player_advanced([game], {"giannis antetokounmpo": 203507})
    assert list(table) == [203507]
    row = table[203507]
    assert row["TS_PCT"] == round(100 * 24 / (2 * (18 + 0.44 * 5)), 1)
    assert row["EFG_PCT"] == round(100 * 11 / 18, 1)       # 0 threes made
    assert row["OFF_RATING"] is None and row["PIE"] is None   # not reproducible from a box


def test_season_games_reads_only_the_window_and_caches_closed_days():
    calls = []

    class Resp:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self.payload

    def get(url, timeout=None):
        calls.append(url)
        if "scoreboard" in url:
            day = url.split("dates=")[1][:8]
            events = [{"id": "401909881", "season": {"type": 2},
                       "status": {"type": {"completed": True}}}] if day == "20261028" else []
            return Resp({"events": events})
        return Resp(SUMMARY)

    games = L.season_games("2026-27", "10/28/2026", get=get)
    assert len(games) == 1 and games[0]["date"] == "2026-10-28"
    assert not any("dates=20261029" in url for url in calls), "no day after the window"
    first = len(calls)
    L.season_games("2026-27", "10/28/2026", get=get)
    assert len(calls) == first, "closed days and final games are never fetched twice"


def test_extractor_fills_only_during_an_outage(monkeypatch):
    game = L.parse_summary(SUMMARY, DAY)
    monkeypatch.setattr(L, "season_games", lambda *a, **k: [game])
    monkeypatch.setattr(L, "nba_name_index", lambda: {"giannis antetokounmpo": 203507})
    lineup_game = {"players": {"3032977": {"name": "Giannis Antetokounmpo", "minutes": 31,
                                           "off_poss": 64, "def_poss": 63, "pts_for": 70,
                                           "pts_against": 66}}}
    monkeypatch.setattr(X.nba_espn_lineups, "season_lineups", lambda *a, **k: [lineup_game])
    sources = {"team_stats": {"rows": 0}, "player_advanced": {"rows": 0},
               "key_defenders": {"rows": 0}, "team_dvp": {"rows": 0}}
    monkeypatch.setattr(B, "failure_count", lambda: 0)
    ts, adv = X.espn_league_fallback("2026-27", "2026-10-29", sources, {}, {})
    assert ts == {} and adv == {}, "no outage: an empty feed stays empty"
    monkeypatch.setattr(B, "failure_count", lambda: 3)
    ts, adv = X.espn_league_fallback("2026-27", "2026-10-29", sources, {}, {})
    assert set(ts) == {"MIA", "ATL"} and list(adv) == [203507]
    assert adv[203507]["DEF_RATING"] == round(100 * 66 / (63 * 1.016), 1), "on-court rating from lineups"
    assert sources["player_advanced"]["on_court_filled"] == 1
    assert sources["team_stats"]["source"] == "espn_box" and sources["team_stats"]["rows"] == 2
    assert X.missing_league_tables(sources, 3) == [], "tracking-only tables may be empty"
    assert X.missing_league_tables({**sources, "team_stats": {"rows": 0}}, 3) == ["team_stats"]


def test_source_status_reports_blocked_until_a_success(tmp_path, monkeypatch):
    monkeypatch.setenv("WC_NBA_STAT_SOURCE", "nbacom")
    monkeypatch.setenv("WC_NBA_API_BREAKER_FILE", str(tmp_path / "breaker.json"))
    monkeypatch.setitem(B._state, "noted_ok", False)
    assert B.source_status()["state"] == "ok"
    B._trip("blocked")
    status = B.source_status()
    assert status["state"] == "blocked" and status["blocked_since"]
    B.record_success()
    assert B.source_status()["state"] == "ok" and B.source_status()["last_ok"]


def test_splits_from_gamelog_match_nba_groups_with_preseason_spacing():
    # EXP-20261031-01: 518/549 players identical to nba.com's splits; nba.com
    # counts rest from any previous game, preseason included.
    import pandas as pd
    cols = ["GAME_DATE", "MATCHUP", "PTS", "REB", "AST", "MIN"]
    rs = pd.DataFrame([["OCT 21, 2026", "CHA vs. WAS", 10, 4, 2, 30],
                       ["OCT 23, 2026", "CHA @ MIA", 20, 6, 4, 34],
                       ["OCT 24, 2026", "CHA vs. ATL", 30, 8, 6, 36]], columns=cols)
    pre = pd.DataFrame([["OCT 17, 2026", "CHA vs. NYK", 5, 1, 1, 20]], columns=cols)
    got = X.splits_from_gamelog(rs, pre)
    assert got["Home_PPG"] == 20.0 and got["Road_PPG"] == 20.0 and got["Home_MPG"] == 33.0
    assert got["rest_splits"] == {"3 Days Rest": {"PPG": 10.0, "RPG": 4.0, "GP": 1},
                                  "1 Days Rest": {"PPG": 20.0, "RPG": 6.0, "GP": 1},
                                  "0 Days Rest": {"PPG": 30.0, "RPG": 8.0, "GP": 1}}
    without_pre = X.splits_from_gamelog(rs)
    assert "3 Days Rest" not in without_pre["rest_splits"], "an opener with no earlier game has no rest group"
    assert X.splits_from_gamelog(rs.iloc[0:0]) is None


def test_team_context_in_espn_mode_never_calls_nba_com(tmp_path, monkeypatch):
    """S_v2/S_v3 opponent context comes from the same ESPN box scores (2026-11-01).

    Before this, nba_team_context still asked stats.nba.com's LeagueGameLog, so
    during the block 22% of MS2/MS3 legs had no opponent context and all three
    forward tests read INVALID_DATA.
    """
    import nba_team_context as tc
    monkeypatch.setenv("WC_NBA_STAT_SOURCE", "espn")

    class Resp:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self.payload

    def get(url, timeout=None):
        if "scoreboard" in url:
            day = url.split("dates=")[1][:8]
            events = [{"id": "401909881", "season": {"type": 2},
                       "status": {"type": {"completed": True}}}] if day in ("20261028", "20251028") else []
            return Resp({"events": events})  # 2025-10-28 stands in for last season's league average
        return Resp(SUMMARY)

    def nba_com(**_):
        raise AssertionError("stats.nba.com must not be called in ESPN mode")

    import nba_api.stats.endpoints.leaguegamelog as lgl
    monkeypatch.setattr(lgl, "LeagueGameLog", nba_com)
    bundle = tc.fetch_bundle("2026-27", "2025-26", "10/28/2026", tmp_path / "ctx.json", get=get)
    regular = bundle["tables"]["Regular Season"]
    assert regular["status"] == "available" and regular["source"] == "espn_box"
    assert sorted(r["TEAM_ABBREVIATION"] for r in regular["rows"]) == ["ATL", "MIA"]
    context = tc.opponent_context(bundle, "ATL", date(2026, 10, 29))
    assert context["status"] == "available"
    assert context["allowed"]["PTS"] == [129.0]  # what ATL allowed = MIA's points
    assert tc.opponent_context(bundle, "ATL", DAY)["allowed"]["PTS"] == []  # strictly before the cutoff day
