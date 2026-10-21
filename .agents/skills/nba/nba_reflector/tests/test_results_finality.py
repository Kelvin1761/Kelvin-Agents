"""Finality of a game in the Results Brief must not depend on ScoreboardV3.

ScoreboardV3 reports gameStatus None / scores None / statusText = tip-off time
for every date of the 2026-27 feed, so the ledger never settled. ESPN (matched
by canonical team abbreviations) decides; a box-score completeness rule is the
fallback; the legacy >=2-day rule is last. A live/partial box score is never final.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
NBA_ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(NBA_ROOT / "nba_daily_auto"))
sys.path.insert(0, str(NBA_ROOT))
import fetch_nba_results as f  # noqa: E402
import nba_market_ledger as ledger  # noqa: E402

FIX = HERE / "fixtures"
BOX = json.loads((FIX / "boxscore_0022600001_final.json").read_text(encoding="utf-8"))
ESPN = f.espn_index(json.loads((FIX / "espn_scoreboard_20261020.json").read_text(encoding="utf-8"))["events"])
STALE_GAME = {"gameId": "0022600001", "gameStatus": None, "gameStatusText": "3:00 pm ET",
              "homeTeam": {"teamTricode": "DET", "teamName": "Pistons", "score": None},
              "awayTeam": {"teamTricode": "BOS", "teamName": "Celtics", "score": None}}


def box(home_pts=121, away_pts=113, minutes="240:00", players=True):
    b = copy.deepcopy(BOX)
    inner = b["boxScoreTraditional"]
    inner["homeTeam"]["statistics"].update(points=home_pts, minutes=minutes)
    inner["awayTeam"]["statistics"].update(points=away_pts, minutes=minutes)
    if not players:
        inner["homeTeam"]["players"] = []
        inner["awayTeam"]["players"] = []
    return b


# ── box-score completeness rule ─────────────────────────────────────────────
@pytest.mark.parametrize("minutes,home,away,expected", [
    ("240:00", 121, 113, True),      # regulation final (the real BOS@DET box score)
    ("265:00", 125, 123, True),      # one OT, decided
    ("290:00", 130, 128, True),      # two OT, decided
    ("240:00", 110, 110, False),     # tied at 240 -> OT follows, not final
    ("265:00", 118, 118, False),     # tied after OT1 -> another OT
    ("231:30", 98, 90, False),       # live, mid-period
    ("250:00", 120, 115, False),     # live, mid-overtime (not on a 25-minute boundary)
    ("120:00", 60, 55, False),       # half time
    ("", 121, 113, False),           # no minutes
])
def test_box_score_completeness_rule(minutes, home, away, expected):
    assert f.box_score_is_complete(box(home, away, minutes)) is expected


def test_empty_box_score_is_never_final():
    assert f.box_score_is_complete(box(players=False)) is False
    assert f.box_score_is_complete(None) is False
    assert f.box_score_is_complete({}) is False


# ── ordered finality decision ───────────────────────────────────────────────
def test_espn_final_with_box_score_is_final_with_espn_source():
    final, scores, source = f.decide_finality("BOS", "DET", box(), ESPN, boxscore_may_settle=False)
    assert (final, scores, source) == (True, (113, 121), "espn")


def test_espn_final_but_no_box_score_is_not_settled():
    final, scores, source = f.decide_finality("BOS", "DET", None, ESPN, False)
    assert (final, scores, source) == (False, None, "espn_final_no_boxscore")
    final, _, source = f.decide_finality("BOS", "DET", box(players=False), ESPN, False)
    assert final is False and source == "espn_final_no_boxscore"


def test_espn_says_live_overrides_a_complete_looking_box_score():
    live = {("BOS", "DET"): {"completed": False, "status": "STATUS_IN_PROGRESS", "detail": "Q4", "away_score": 100, "home_score": 99}}
    final, _, source = f.decide_finality("BOS", "DET", box(), live, boxscore_may_settle=True)
    assert (final, source) == (False, "espn_not_final")


def test_espn_and_box_score_disagree_is_not_final():
    final, _, source = f.decide_finality("BOS", "DET", box(home_pts=119), ESPN, False)
    assert (final, source) == (False, "espn_boxscore_score_mismatch")


def test_espn_unreachable_falls_back_to_completeness_rule():
    assert f.decide_finality("BOS", "DET", box(), None, False) == (True, (113, 121), "boxscore_completeness")
    final, _, source = f.decide_finality("BOS", "DET", box(minutes="231:30"), None, False)
    assert (final, source) == (False, "unresolved")           # live game stays non-final


def test_espn_has_no_matching_event_uses_fallbacks():
    other = {("LAL", "GSW"): {"completed": True, "status": "STATUS_FINAL", "detail": "Final", "away_score": 1, "home_score": 2}}
    assert f.decide_finality("BOS", "DET", box(), other, False)[2] == "boxscore_completeness"


def test_legacy_two_day_rule_is_last_resort():
    incomplete = box(minutes="231:30")
    assert f.decide_finality("BOS", "DET", incomplete, None, True) == (True, (113, 121), "boxscore_age")
    assert f.decide_finality("BOS", "DET", incomplete, None, False)[0] is False


def test_espn_abbreviations_are_canonicalised():
    idx = f.espn_index([{"status": {"type": {"completed": True, "name": "STATUS_FINAL", "detail": "Final"}},
                         "competitions": [{"competitors": [
                             {"homeAway": "home", "score": "100", "team": {"abbreviation": "NY"}},
                             {"homeAway": "away", "score": "106", "team": {"abbreviation": "PHI"}}]}]}])
    assert ("PHI", "NYK") in idx and idx[("PHI", "NYK")]["completed"] is True


# ── process_game: stale scoreboard + ESPN final ─────────────────────────────
def test_stale_scoreboard_with_espn_final_gives_final_brief_with_provenance(monkeypatch):
    monkeypatch.setattr(f, "fetch_boxscore", lambda game_id: box())
    result = f.process_game(copy.deepcopy(STALE_GAME), boxscore_may_settle=False, espn=ESPN)
    assert result["status"] == "Final" and result["status_source"] == "espn"
    assert result["scoreboard_status_text"] == "3:00 pm ET"
    assert (result["away"]["score"], result["home"]["score"], result["winner"]) == (113, 121, "DET")
    assert result["players"]


def test_stale_scoreboard_live_game_stays_non_final(monkeypatch):
    monkeypatch.setattr(f, "fetch_boxscore", lambda game_id: box(minutes="231:30"))
    result = f.process_game(copy.deepcopy(STALE_GAME), boxscore_may_settle=False, espn=None)
    assert "final" not in result["status"].lower() and result["status_source"] == "unresolved"
    assert result["away"]["score"] is None


def test_scoreboard_with_scores_is_untouched(monkeypatch):
    monkeypatch.setattr(f, "fetch_boxscore", lambda game_id: box())
    game = copy.deepcopy(STALE_GAME)
    game["gameStatusText"] = "Final"
    game["homeTeam"]["score"], game["awayTeam"]["score"] = 121, 113
    result = f.process_game(game, boxscore_may_settle=False, espn=ESPN)
    assert result["status"] == "Final" and result["status_source"] == "scoreboard"


# ── the ledger now settles on such a brief (scratch ledger only) ─────────────
def test_ledger_settles_legs_from_a_final_brief(tmp_path, monkeypatch):
    monkeypatch.setattr(f, "fetch_boxscore", lambda game_id: box())
    game = f.process_game(copy.deepcopy(STALE_GAME), boxscore_may_settle=False, espn=ESPN)
    brief = tmp_path / "Results_Brief_2026-10-20.json"
    brief.write_text(json.dumps({"_version": "RESULTS_BRIEF_V1", "games": [game]}), encoding="utf-8")
    root = tmp_path / "ledger"
    rows = [{"row_type": "model_obs", "game_tag": "BOS_DET", "player": "Jalen Duren", "market": "pts",
             "line": line, "side": "over", "target_date": "2026-10-21"} for line in (15.0, 25.0)]
    rows.append({"row_type": "model_obs", "game_tag": "PHI_NYK", "player": "X Y", "market": "pts",
                 "line": 10.0, "side": "over", "target_date": "2026-10-21"})
    ledger.append_rows(root, "2026-10-21", rows)
    out = ledger.settle("2026-10-21", brief, root=root)
    assert out == {"candidates": 3, "appended": 2}          # PHI_NYK not in this brief: retried later
    settled = {r["line"]: r["outcome"] for r in ledger.read_rows(root, "2026-10-21") if r["row_type"] == "settlement"}
    assert settled == {15.0: "hit", 25.0: "miss"}            # Duren scored 22


def test_ledger_skips_a_non_final_brief(tmp_path, monkeypatch):
    monkeypatch.setattr(f, "fetch_boxscore", lambda game_id: box(minutes="231:30"))
    game = f.process_game(copy.deepcopy(STALE_GAME), boxscore_may_settle=False, espn=None)
    brief = tmp_path / "Results_Brief_2026-10-20.json"
    brief.write_text(json.dumps({"_version": "RESULTS_BRIEF_V1", "games": [game]}), encoding="utf-8")
    root = tmp_path / "ledger"
    ledger.append_rows(root, "2026-10-21", [{"row_type": "model_obs", "game_tag": "BOS_DET", "player": "Jalen Duren",
                                             "market": "pts", "line": 15.0, "side": "over", "target_date": "2026-10-21"}])
    assert ledger.settle("2026-10-21", brief, root=root)["appended"] == 0
