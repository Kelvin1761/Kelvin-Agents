"""stats.nba.com blocked -> the Results Brief comes from ESPN (2026-10-29).

Akamai refused every nba.com host from this machine for hours on 10-28/29 and
the reflector exited 1 every 15 minutes ("postgame_exit_1"). ESPN is reshaped
into the ScoreboardV3 / BoxScoreTraditionalV3 dicts, so finality and player
extraction run unchanged.
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
    monkeypatch.setattr(f, "fetch_scoreboard", lambda date: [])
    monkeypatch.setattr(f, "fetch_boxscore", lambda gid: (_ for _ in ()).throw(AssertionError("no nba.com call for an espn: id")))
    monkeypatch.setattr(f, "fetch_espn_events", lambda day: (EVENTS, True))
    monkeypatch.setattr(f, "fetch_espn_summary", lambda eid: SUMMARY)
    monkeypatch.setattr(sys, "argv", ["x", "--date", "2026-10-28", "--dir", str(tmp_path)])
    f.main()
    brief = json.loads((tmp_path / "Results_Brief_2026-10-28.json").read_text(encoding="utf-8"))
    game = brief["games"][0]
    assert game["status"] == "Final" and game["status_source"] == "espn"
    assert game["final_score"] == "MIA 129 - 117 ATL"
    assert game["players"]


def test_nba_box_failure_alone_falls_back_per_game(monkeypatch):
    espn = f.espn_index(EVENTS)
    monkeypatch.setattr(f, "fetch_boxscore", lambda gid: None)
    monkeypatch.setattr(f, "fetch_espn_summary", lambda eid: SUMMARY)
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
    monkeypatch.setattr(f, "fetch_scoreboard", lambda date: [])
    monkeypatch.setattr(f, "fetch_espn_events", lambda day: ([], False))
    monkeypatch.setattr(sys, "argv", ["x", "--date", "2026-10-28", "--dir", str(tmp_path)])
    with pytest.raises(SystemExit) as exc:
        f.main()
    assert exc.value.code == 1
