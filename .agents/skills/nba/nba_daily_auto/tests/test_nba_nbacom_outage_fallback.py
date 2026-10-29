"""stats.nba.com outage fallbacks (2026-10-30).

nba.com blocked this machine for 12+ hours on 10-29/30 and no game could be
analysed. Player rosters and game logs now come from ESPN in the exact nba_api
shapes, and the league tables from the newest point-in-time snapshot.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest
import requests

NBA_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(NBA_ROOT))
sys.path.insert(0, str(NBA_ROOT / "nba_data_extractor" / "scripts"))
import nba_espn_stats as E  # noqa: E402
import nba_league_snapshot as S  # noqa: E402
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


# ── league-table snapshots ──────────────────────────────────────────────────
@pytest.fixture
def snapdir(monkeypatch, tmp_path):
    monkeypatch.setenv("WC_NBA_LEAGUE_SNAPSHOT_DIR", str(tmp_path))
    return tmp_path


def test_snapshot_round_trip_restores_int_player_ids(snapdir):
    S.save("player_advanced", "2026-27", "10/28/2026", {1629652: {"USG_PCT": 18.1}})
    data, info = S.load("player_advanced", "2026-27", "10/29/2026")
    assert data == {1629652: {"USG_PCT": 18.1}}
    assert info["snapshot_age_days"] == 1


def test_snapshot_never_reads_a_later_window(snapdir):
    S.save("team_stats", "2026-27", "10/30/2026", {"ATL": {"PACE": 100}})
    assert S.load("team_stats", "2026-27", "10/29/2026") == (None, None)


def test_snapshot_older_than_one_match_day_is_not_used(snapdir):
    S.save("team_stats", "2026-27", "10/27/2026", {"ATL": {"PACE": 100}})
    assert S.load("team_stats", "2026-27", "10/29/2026") == (None, None)


def _date_to(as_of):
    return as_of


def test_backed_saves_on_success_and_serves_snapshot_only_on_outage(snapdir):
    failures = {"n": 0}
    answers = {"10/28/2026": {"ATL": {"PACE": 100}}, "10/29/2026": {}}

    def fetch(season, as_of):
        if as_of == "10/29/2026":
            failures["n"] += 1          # nba.com unreachable
        return answers[as_of]

    wrapped = S.backed(fetch, "team_stats", lambda: failures["n"], _date_to)
    assert wrapped("2026-27", "10/28/2026") == {"ATL": {"PACE": 100}}
    assert wrapped("2026-27", "10/29/2026") == {"ATL": {"PACE": 100}}
    assert wrapped.used and wrapped.used[0]["snapshot_age_days"] == 1


def test_backed_does_not_mask_a_genuinely_empty_feed(snapdir):
    S.save("team_stats", "2026-27", "10/28/2026", {"ATL": {"PACE": 100}})
    wrapped = S.backed(lambda season, as_of: {}, "team_stats", lambda: 0, _date_to)
    assert wrapped("2026-27", "10/29/2026") == {}
    assert wrapped.used == []


# ── extractor: game logs fall back only on a network failure ────────────────
class _Boom:
    def __init__(self, exc):
        self.exc = exc

    def __call__(self, **kwargs):
        raise self.exc


def test_player_log_frame_falls_back_to_espn_when_nbacom_times_out(monkeypatch):
    monkeypatch.setattr(X.playergamelog, "PlayerGameLog", _Boom(requests.exceptions.ReadTimeout("t")))
    monkeypatch.setitem(X.ESPN_IDS, 203507, "3032977")
    monkeypatch.setattr(E, "_get_json", lambda url, get=None, timeout=15: GAMELOG)
    E._GAMELOG_CACHE.clear()
    frame, source = X.player_log_frame(203507, "2026-27", "10/27/2026", "Regular Season")
    assert source == "espn"
    assert list(frame["GAME_DATE"]) == ["OCT 26, 2026", "OCT 24, 2026", "OCT 23, 2026", "OCT 21, 2026"]


def test_player_log_frame_reraises_non_network_errors(monkeypatch):
    monkeypatch.setattr(X.playergamelog, "PlayerGameLog", _Boom(KeyError("resultSets")))
    monkeypatch.setitem(X.ESPN_IDS, 203507, "3032977")
    with pytest.raises(KeyError):
        X.player_log_frame(203507, "2026-27", "10/27/2026", "Regular Season")


def test_player_log_frame_without_espn_id_reraises(monkeypatch):
    monkeypatch.setattr(X.playergamelog, "PlayerGameLog", _Boom(requests.exceptions.ReadTimeout("t")))
    X.ESPN_IDS.pop(999, None)
    with pytest.raises(requests.exceptions.ReadTimeout):
        X.player_log_frame(999, "2026-27", "10/27/2026", "Regular Season")


# ── fail closed: no league tables during an outage = no analysis ────────────
def test_outage_without_snapshot_blocks_the_slate():
    sources = {"team_stats": {"rows": 0}, "player_advanced": {"rows": 0},
               "key_defenders": {"rows": 600}, "team_dvp": {"rows": 30}}
    assert X.missing_league_tables(sources, outage_failures=4) == ["player_advanced", "team_stats"]


def test_snapshot_backed_tables_pass_and_quiet_days_never_block():
    full = {label: {"rows": 30} for label in ("team_stats", "player_advanced", "key_defenders", "team_dvp")}
    assert X.missing_league_tables(full, outage_failures=4) == []
    assert X.missing_league_tables({"team_stats": {"rows": 0}}, outage_failures=0) == []


def test_player_entry_snapshot_round_trip_and_age_rules(snapdir):
    S.save_entry("player_splits", "2026-27", "10/28/2026", 1629652, {"Home_PPG": 12.5})
    assert S.load_entry("player_splits", "2026-27", "10/29/2026", 1629652) == ({"Home_PPG": 12.5}, 1)
    assert S.load_entry("player_splits", "2026-27", "10/27/2026", 1629652) == (None, None)   # later window
    assert S.load_entry("player_splits", "2026-27", "10/30/2026", 1629652) == (None, None)   # too old


def test_splits_fall_back_to_snapshot_only_on_outage(snapdir, monkeypatch):
    S.save_entry("player_splits", "2026-27", "10/27/2026", 77, {"Home_PPG": 9.0})
    monkeypatch.setattr(X.playerdashboardbygeneralsplits, "PlayerDashboardByGeneralSplits",
                        _Boom(requests.exceptions.ReadTimeout("t")))
    got = X.fetch_player_splits(77, "P", season="2026-27", as_of="2026-10-28T23:00Z")
    assert got == {"Home_PPG": 9.0, "snapshot_age_days": 0}
    monkeypatch.setattr(X.playerdashboardbygeneralsplits, "PlayerDashboardByGeneralSplits",
                        _Boom(KeyError("resultSets")))
    assert X.fetch_player_splits(77, "P", season="2026-27", as_of="2026-10-28T23:00Z") is None


def test_fallback_summary_marks_a_fallback_slate():
    package = {"meta": {"data_sources": {"team_stats": {"rows": 30, "snapshot": [{"snapshot_age_days": 1}]},
                                         "team_dvp": {"rows": 30}}},
               "players": {"CLE": [{"gamelog": {"source": "espn"}, "splits": {"snapshot_age_days": 1}},
                                   {"gamelog": {"source": "nba"}, "splits": {}}]}}
    assert X.nbacom_fallback_summary(package) == {
        "active": True, "espn_gamelog_players": 1, "players": 2,
        "snapshot_splits_players": 1, "snapshot_league_tables": ["team_stats"]}
    normal = {"meta": {"data_sources": {}}, "players": {"CLE": [{"gamelog": {"source": "nba"}}]}}
    assert X.nbacom_fallback_summary(normal)["active"] is False
