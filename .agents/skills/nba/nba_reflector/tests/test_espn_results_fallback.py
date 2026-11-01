"""The Results Brief comes from ESPN only (2026-10-29 fallback, sole source 2026-11-01).

Akamai refused every nba.com host from this machine for hours on 10-28/29 and
the reflector exited 1 every 15 minutes ("postgame_exit_1"). ESPN is reshaped
into the ScoreboardV3 / BoxScoreTraditionalV3 dicts, so finality and player
extraction run unchanged (EXP-20261101-60).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
NBA_ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(NBA_ROOT))
import fetch_nba_results as f  # noqa: E402

FIX = HERE / "fixtures"
SUMMARY = json.loads((FIX / "espn_summary_mia_atl.json").read_text(encoding="utf-8"))
EVENTS = json.loads((FIX / "espn_scoreboard_20261028_mia_atl.json").read_text(encoding="utf-8"))["events"]


def test_espn_box_score_has_the_v3_shape_and_real_totals():
    box = f.espn_boxscore(SUMMARY)
    inner = box["boxScoreTraditional"]
    assert inner["homeTeam"]["teamTricode"] == "ATL"
    assert inner["awayTeam"]["teamTricode"] == "MIA"
    # summed from players, so it must equal the published final
    assert inner["awayTeam"]["statistics"]["points"] == 129
    assert inner["homeTeam"]["statistics"]["points"] == 117


def test_espn_player_rows_extract_like_nba_rows():
    players = f.extract_player_stats(f.espn_boxscore(SUMMARY))
    giannis = next(p for p in players if p["name"] == "Giannis Antetokounmpo")
    assert giannis["team"] == "MIA" and giannis["starter"] is True
    assert giannis["minutes"] == "31:00" and giannis["pts"] == 24
    assert (giannis["fgm"], giannis["fga"], giannis["fg3m"]) == (11, 18, 0)
    dnp = [p for p in players if p["comment"]]
    assert dnp and all(p["minutes"] == "0" for p in dnp), "DNP must void, not score as 0"
    starters = [p for p in players if p["starter"]]
    assert len(starters) == 10


def test_blocked_scoreboard_falls_back_to_espn_and_settles(monkeypatch, tmp_path):
    monkeypatch.setattr(f, "fetch_scoreboard", lambda date, events=None: f.espn_scoreboard_games(events))
    monkeypatch.setattr(f, "fetch_boxscore", lambda gid, day=None: f.espn_boxscore(SUMMARY))
    monkeypatch.setattr(f, "fetch_espn_events", lambda day: (EVENTS, True))
    monkeypatch.setattr(f, "fetch_espn_summary", lambda eid, day=None: SUMMARY)
    monkeypatch.setattr(sys, "argv", ["x", "--date", "2026-10-28", "--dir", str(tmp_path)])
    f.main()
    brief = json.loads((tmp_path / "Results_Brief_2026-10-28.json").read_text(encoding="utf-8"))
    game = brief["games"][0]
    assert game["status"] == "Final" and game["status_source"] == "espn"
    assert game["final_score"] == "MIA 129 - 117 ATL"
    assert game["players"]


def test_nba_box_failure_alone_falls_back_per_game(monkeypatch):
    espn = f.espn_index(EVENTS)
    monkeypatch.setattr(f, "fetch_boxscore", lambda gid, day=None: None)
    monkeypatch.setattr(f, "fetch_espn_summary", lambda eid, day=None: SUMMARY)
    game = {"gameId": "0022600100", "gameStatusText": "7:30 pm ET",
            "homeTeam": {"teamTricode": "ATL", "teamName": "Hawks", "score": None},
            "awayTeam": {"teamTricode": "MIA", "teamName": "Heat", "score": None}}
    result = f.process_game(game, espn=espn)
    assert result["status"] == "Final" and result["home"]["score"] == 117


def test_incremental_merge_does_not_duplicate_a_game_across_sources():
    old = {"game_id": "0022600100", "away": {"team": "MIA"}, "home": {"team": "ATL"}}
    new = {"game_id": "espn:401909881", "away": {"team": "MIA"}, "home": {"team": "ATL"}}
    assert f._matchup(old) == f._matchup(new)


def test_no_scoreboard_anywhere_still_exits_1(monkeypatch, tmp_path):
    import pytest
    monkeypatch.setattr(f, "fetch_scoreboard", lambda date, events=None: f.espn_scoreboard_games(events))
    monkeypatch.setattr(f, "fetch_espn_events", lambda day: ([], False))
    monkeypatch.setattr(sys, "argv", ["x", "--date", "2026-10-28", "--dir", str(tmp_path)])
    with pytest.raises(SystemExit) as exc:
        f.main()
    assert exc.value.code == 1


def test_out_players_from_espn_injuries_void_like_nba_inactives():
    """nba.com listed inactives with a comment (VOID_DNP); ESPN names them under injuries."""
    summary = json.loads(json.dumps(SUMMARY))
    atl = next(t["team"] for t in summary["boxscore"]["players"] if t["team"]["abbreviation"] == "ATL")
    summary["injuries"] = [{"team": atl, "injuries": [
        {"athlete": {"displayName": "Injured Starter"}, "status": "Out"},
        {"athlete": {"displayName": "Maybe Player"}, "status": "Day-To-Day"}]}]
    players = {p["name"]: p for p in f.extract_player_stats(f.espn_boxscore(summary))}
    assert players["Injured Starter"]["minutes"] == "0" and players["Injured Starter"]["team"] == "ATL"
    assert "Maybe Player" not in players, "only Out is inactive; a DTD player who is absent stays unmatched"
    box = f.espn_boxscore(summary)["boxScoreTraditional"]
    assert box["homeTeam"]["statistics"]["points"] == 117, "inactive rows must not change the summed score"


def test_no_nba_com_import_and_espn_goes_through_the_shared_client(monkeypatch):
    source = (HERE.parent / "scripts" / "fetch_nba_results.py").read_text(encoding="utf-8")
    assert "nba_api" not in source and "import requests" not in source
    seen = []
    monkeypatch.setattr(f.nba_espn_http, "get_json",
                        lambda url, **kw: seen.append((url, kw.get("fresh_after"))) or {"events": EVENTS})
    events, ok = f.fetch_espn_events("2026-10-28")
    assert ok and events == EVENTS
    assert seen[0][1] is not None, "a closed day is cached for good"
    assert f.fetch_boxscore("0022600001") is None, "an nba.com game id is never fetched"
