"""League injury report: parsed per game date, and it can only make availability stricter."""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

NBA_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(NBA_ROOT))
sys.path.insert(0, str(NBA_ROOT / 'nba_daily_auto'))
sys.path.insert(0, str(NBA_ROOT / 'nba_wong_choi' / 'scripts'))
import nba_official_injuries as O
import nba_market_ledger as ledger
import nba_availability_outcomes as outcomes_tool
import generate_nba_reports as reports

X = dict(zip(O.COLUMNS, (23, 119, 200, 264, 425, 585, 666)))


def word(col, top, text):
    return {"x0": X[col] + 1, "top": top, "text": text}


def page(lines, header=True):
    words = [{"x0": 288, "top": 45, "text": "Injury"}, {"x0": 354, "top": 45, "text": "Report:"}]
    if header:
        words += [{"x0": X[c], "top": 100, "text": c} for c in O.COLUMNS]
    for top, cells in lines:
        words += [word(c, top, t) for c, t in cells.items()]
    words.append({"x0": 400, "top": 580, "text": "Page1of2"})
    return words


REPORT = [
    page([(120, {"GameDate": "10/25/2026", "GameTime": "06:00(ET)", "Matchup": "IND@BKN", "Team": "IndianaPacers",
                 "PlayerName": "Sheppard,Ben", "CurrentStatus": "Out", "Reason": "Injury/Illness-Knee"}),
          (140, {"PlayerName": "Nesmith,Aaron", "CurrentStatus": "Probable"}),
          (160, {"Team": "BrooklynNets", "Reason": "NOTYETSUBMITTED"})]),
    # page 2 has no header and continues the previous team; the title must not overwrite it
    page([(80, {"PlayerName": "JacksonJr.,Jaren", "CurrentStatus": "Questionable"}),
          (100, {"GameDate": "10/26/2026", "Matchup": "IND@MIA", "Team": "IndianaPacers",
                 "Reason": "NOTYETSUBMITTED"})], header=False),
]


def test_parse_keeps_team_and_date_across_pages_and_pages_titles():
    rows, pending = O.parse_words(REPORT)
    assert [(r["player"], r["team"], r["status"], r["game_date"]) for r in rows] == [
        ("Sheppard,Ben", "IND", "Out", "10/25/2026"), ("Nesmith,Aaron", "IND", "Probable", "10/25/2026"),
        ("JacksonJr.,Jaren", "BKN", "Questionable", "10/25/2026")]
    assert {(e["team"], e["game_date"]) for e in pending} == {("BKN", "10/25/2026"), ("IND", "10/26/2026")}


def test_names_and_teams_match_espn_spellings():
    for pdf, espn in [("JacksonJr.,Jaren", "Jaren Jackson Jr."), ("McConnell,T.J.", "T.J. McConnell"),
                      ("WalkerIV,Lonnie", "Lonnie Walker IV"), ("Dončić,Luka", "Luka Doncic"),
                      ("Ivanov,Ivan", "Ivan Ivanov")]:
        assert O.name_key(pdf) == O.name_key(espn)
    assert (O.team_abbr("LAClippers"), O.team_abbr("PortlandTrailBlazers"), O.team_abbr("Nope")) == ("LAC", "POR", None)


def test_for_team_is_per_game_date():
    rows, pending = O.parse_words(REPORT)
    bundle = {"status": "available", "rows": rows, "not_submitted": pending}
    today = O.for_team(bundle, "IND", dt.date(2026, 10, 25))
    assert today["submitted"] and O.level_for(today, "Ben Sheppard") == "out"
    assert O.level_for(today, "Aaron Nesmith") == "ok" and O.level_for(today, "Pascal Siakam") is None
    tomorrow = O.for_team(bundle, "IND", dt.date(2026, 10, 26))
    assert tomorrow["status"] == "available" and tomorrow["submitted"] is False and not tomorrow["players"]
    assert O.for_team(bundle, "GSW", dt.date(2026, 10, 25))["status"] == "team_not_in_report"
    assert O.level_for({"status": "unavailable"}, "Ben Sheppard") is None


def test_report_time_and_fetch_failures_are_recorded(tmp_path):
    url = "https://ak-static.cms.nba.com/referee/injury/Injury-Report_2026-10-25_08_15PM.pdf"
    assert O.report_time(url).isoformat() == "2026-10-26T00:15:00+00:00"
    def broken(*a, **k):
        raise OSError("offline")
    out = O.fetch_latest("2026-27", tmp_path / "c.json", get=broken)
    assert out["status"] == "unavailable" and "offline" in out["error"]


def card(name):
    ext = {"name": name, "advanced": {"USG_PCT": 22}, "gamelog": {"PTS": [20, 22, 18, 24, 26, 20, 23, 19, 21, 25],
                                                                  "MIN": [32] * 10}}
    return reports.build_player_card(name, "IND", {"lines": {"10": "1.8"}}, ext, "points", engine_mode="legacy")


def test_league_report_only_tightens_availability():
    rows, pending = O.parse_words(REPORT)
    league = {"IND": O.for_team({"status": "available", "rows": rows, "not_submitted": pending}, "IND",
                                dt.date(2026, 10, 25))}
    league["IND"]["players"]["jarenjackson"] = {"player": "JacksonJr.,Jaren", "status": "Questionable",
                                                "level": "dtd", "reason": ""}   # league only, ESPN silent
    espn = {"IND": {"Ben Sheppard": "Day-To-Day", "Aaron Nesmith": "Day-To-Day"}}
    cards = [card("Ben Sheppard"), card("Aaron Nesmith"), card("Jaren Jackson Jr."), card("Other Guy")]
    legs = {c["player"]: c for c in reports.build_leg_candidates(cards, injuries=espn, official_injuries=league)}
    assert "Ben Sheppard" not in legs                       # ESPN DTD + league Out -> out
    assert legs["Aaron Nesmith"]["day_to_day"] is True        # league Probable never clears ESPN DTD
    assert legs["Jaren Jackson Jr."]["day_to_day"] is True    # league Questionable alone -> DTD
    assert legs["Other Guy"]["day_to_day"] is False
    same = {c["player"]: c["day_to_day"] for c in reports.build_leg_candidates(cards, injuries=espn)}
    assert same["Ben Sheppard"] is True and same["Jaren Jackson Jr."] is False   # without the league report


def test_availability_rows_join_both_sources():
    rows, pending = O.parse_words(REPORT)
    league = {"IND": O.for_team({"status": "available", "rows": rows, "not_submitted": pending,
                                 "report_time": "t"}, "IND", dt.date(2026, 10, 25))}
    out = ledger.availability_rows({"injuries": {"IND": {"Ben Sheppard": "Day-To-Day", "Rookie Guy": "Out"}},
                                    "official": league}, {"snapshot_id": "s", "game_tag": "IND_BKN"}, {})
    by = {r["name_key"]: r for r in out}
    assert by["bensheppard"]["espn_level"] == "dtd" and by["bensheppard"]["official_level"] == "out"
    assert by["aaronnesmith"]["espn_status"] is None and by["aaronnesmith"]["official_status"] == "Probable"
    assert by["rookieguy"]["official_status"] is None and by["rookieguy"]["espn_level"] == "out"
    assert ledger._row_key(out[0])[0] == "availability_obs"


def test_outcomes_count_who_actually_played(tmp_path):
    day = "2026-10-26"
    base = {"target_date": day, "game_tag": "IND_BKN", "snapshot_id": "s1", "snapshot_role": "production",
            "snapshot_created_at": f"{day}T08:00:00+00:00", "post_tip": False, "late_write": False,
            "tip_unknown": False}
    rows = ledger.availability_rows({"injuries": {"IND": {"Ben Sheppard": "Day-To-Day",
                                                           "Aaron Nesmith": "Day-To-Day"}}}, base, {})
    (tmp_path / "ledger").mkdir()
    (tmp_path / "ledger" / f"{day}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    folder = tmp_path / f"{day} NBA Analysis"; folder.mkdir()
    brief = {"_version": "RESULTS_BRIEF_V1", "games": [{
        "status": "Final", "away": {"team": "IND"}, "home": {"team": "BKN"},
        "players": [{"name": "Aaron Nesmith", "team": "IND", "minutes": "24:10"},
                    {"name": "Ben Sheppard", "team": "IND", "minutes": "", "comment": "DNP"}]}]}
    (folder / "Results_Brief_2026-10-25.json").write_text(json.dumps(brief))
    got = outcomes_tool.outcomes(tmp_path, [tmp_path], None, None)
    assert {r["player"]: r["played"] for r in got} == {"Ben Sheppard": False, "Aaron Nesmith": True}
    assert outcomes_tool.summarise(got)["by_espn_status"]["Day-To-Day"] == {"n": 2, "played": 1, "play_rate": 0.5}
