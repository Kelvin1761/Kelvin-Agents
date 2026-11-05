"""2026-08-23 Sportsbet market restructure, non-ace families (EXP-20261015-05).

Three things broke at once and each was silent:
  * handicap selections lost their brackets ("Name -3.5", was "Name (-3.5)"),
    so no game/set/first-set handicap selection matched a player;
  * "<Player> Total Games 12.5" became "<Player> Total Games" (line only on the
    selection), so player totals fell into match_total_games -- and were priced
    there as MATCH totals at a 12.5 line;
  * the event page stopped server-rendering every tab except "Top Markets", so
    most of those markets were never stored at all.
Temp DB only.
"""
from __future__ import annotations

import pytest

DATE = "2026-10-10"


@pytest.fixture()
def db(tmp_path, monkeypatch):
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.db import get_connection
    from tennis_wc.database.migrations import init_db

    init_db()
    conn = get_connection()
    conn.execute(
        """INSERT INTO players (id, name, tour, source_provider, created_at, updated_at)
           VALUES (1,'Ben Shelton','ATP','t','now','now'),
                  (2,'Karen Khachanov','ATP','t','now','now'),
                  (3,'Opp One','ATP','t','now','now')"""
    )
    conn.execute(
        """INSERT INTO matches (id, provider_match_id, tour, match_date, tournament_id,
               player_a_id, player_b_id, round, source_provider, created_at,
               updated_at, start_time_utc)
           VALUES (60,'M60','ATP',?,1,1,2,'R1','t','now','now','2026-10-10T08:00:00Z')""",
        (DATE,),
    )
    conn.execute(
        "INSERT INTO predictions (match_id, feature_set_version, selection_player_id, "
        "selection_name, model_probability, decision, stake_units, confidence, risk, "
        "pricing_json, created_at) VALUES (60, 'v1', 1, 'Ben Shelton', 0.64, 'NO_BET', "
        "0, 50, 'low', '{}', 'now')"
    )
    rows = [
        ("game_handicap", "Game Handicap", "Ben Shelton -3.5", -3.5, 1.90),
        ("game_handicap", "Game Handicap", "Karen Khachanov +3.5", 3.5, 1.90),
        # Alternative lists both orientations of each line.
        ("game_handicap", "Alternative Game Handicap", "Ben Shelton -3.5", -3.5, 2.05),
        ("game_handicap", "Alternative Game Handicap", "Karen Khachanov +3.5", 3.5, 1.75),
        ("game_handicap", "Alternative Game Handicap", "Ben Shelton -1.5", -1.5, 1.55),
        ("game_handicap", "Alternative Game Handicap", "Karen Khachanov +1.5", 1.5, 2.40),
        ("game_handicap", "Alternative Game Handicap", "Ben Shelton +1.5", 1.5, 1.08),
        ("game_handicap", "Alternative Game Handicap", "Karen Khachanov -1.5", -1.5, 7.00),
        ("game_handicap", "Set 2 Game Handicap", "Ben Shelton -1.5", -1.5, 1.9),
        ("game_handicap", "Set 2 Game Handicap", "Karen Khachanov +1.5", 1.5, 1.9),
        ("set_handicap", "Set Handicap", "Ben Shelton -1.5", -1.5, 2.20),
        ("set_handicap", "Set Handicap", "Karen Khachanov +1.5", 1.5, 1.65),
        ("total_games", "Ben Shelton Total Games", "Over 12.5", 12.5, 1.85),
        ("total_games", "Ben Shelton Total Games", "Under 12.5", 12.5, 1.85),
        ("total_games", "Match Total Games", "Over 22.5", 22.5, 1.90),
        ("total_games", "Match Total Games", "Under 22.5", 22.5, 1.80),
    ]
    for key, name, sel, line, odds in rows:
        conn.execute(
            """INSERT INTO market_odds_snapshots (event_id, match_id, bookmaker, market_key,
                   market_name, selection_name, selection_side, line, odds,
                   source_provider, raw_response_id, fetched_at, created_at)
               VALUES ('E60', 60, 'sportsbet', ?, ?, ?, NULL, ?, ?, 'sportsbet', 0,
                       '2026-10-09T23:00:00Z', '2026-10-09T23:00:00Z')""",
            (key, name, sel, line, odds),
        )
    conn.commit()
    return conn


META = {"a_name": "Ben Shelton", "b_name": "Karen Khachanov"}


def _row(key, name, sel, line, odds):
    return {"match_id": 60, "market_key": key, "market_name": name,
            "selection_name": sel, "line": line, "odds": odds}


def test_unbracketed_handicaps_pair_main_market_then_balanced():
    from tennis_wc.pricing.quotes import spreads as _spread_odds

    rows = [
        _row("game_handicap", "Alternative Game Handicap", "Ben Shelton +1.5", 1.5, 1.08),
        _row("game_handicap", "Alternative Game Handicap", "Karen Khachanov -1.5", -1.5, 7.0),
        _row("game_handicap", "Alternative Game Handicap", "Ben Shelton -1.5", -1.5, 1.55),
        _row("game_handicap", "Alternative Game Handicap", "Karen Khachanov +1.5", 1.5, 2.4),
        _row("game_handicap", "Alternative Game Handicap", "Ben Shelton -3.5", -3.5, 2.05),
        _row("game_handicap", "Alternative Game Handicap", "Karen Khachanov +3.5", 3.5, 1.75),
        _row("game_handicap", "Game Handicap", "Ben Shelton -3.5", -3.5, 1.9),
        _row("game_handicap", "Game Handicap", "Karen Khachanov +3.5", 3.5, 1.9),
        _row("game_handicap", "Set 2 Game Handicap", "Ben Shelton -0.5", -0.5, 1.9),
        _row("game_handicap", "Set 2 Game Handicap", "Karen Khachanov +0.5", 0.5, 1.9),
    ]
    out = _spread_odds(rows, META, "player_game_handicap")
    assert set(out) == {1.5, 3.5}
    one = out[1.5]
    assert one["a"] == {"odds": 1.55, "handicap": -1.5}, "balanced pair, not the 1.08/7.0 one"
    assert one["b"] == {"odds": 2.4, "handicap": 1.5}
    three = out[3.5]
    assert three["market_name"] == "Game Handicap", "main market before Alternative"
    assert three["a"]["odds"] == 1.9 and three["a_name"] == "Ben Shelton -3.5"

    first_set = _spread_odds(
        [_row("game_handicap", "Set 1 Game Handicap", "Ben Shelton -1.5", -1.5, 1.8),
         _row("game_handicap", "Set 1 Game Handicap", "Karen Khachanov +1.5", 1.5, 2.0)],
        META, "player_first_set_game_handicap")
    assert list(first_set) == [1.5]


def test_bracketed_handicaps_keep_their_old_meaning():
    from tennis_wc.pricing.quotes import spreads as _spread_odds

    rows = [
        _row("game_handicap", "Game Handicap 3.5", "Ben Shelton (-3.5)", -3.5, 1.9),
        _row("game_handicap", "Game Handicap 3.5", "Karen Khachanov (+3.5)", 3.5, 1.9),
    ]
    out = _spread_odds(rows, META, "player_game_handicap")
    assert out[3.5]["a"] == {"odds": 1.9, "handicap": -3.5}
    assert out[3.5]["a_name"] == "Ben Shelton (-3.5)"


@pytest.mark.parametrize("name,family", [
    ("Ben Shelton Total Games", "player_total_games"),           # since 2026-08-23
    ("Adam Walton Total Games 13.5", "player_total_games"),      # before
    ("Match Total Games", "match_total_games"),
    ("Alternative Total Games", "match_total_games"),
    ("Alternative Total Games 22 5", "match_total_games"),
    ("Set 1 Total Games", "match_total_games"),
    ("Alternative Set 1 Total Games", "match_total_games"),
])
def test_total_games_family(name, family):
    from tennis_wc.pricing.families import family_for_market

    assert family_for_market("total_games", name) == family


def _page(event_id=7, groups=("Top Markets", "Game Handicap Markets",
                              "Individual Point Markets", "Total Games Markets")):
    grouping_ids = [f"{event_id}|{i}" for i in range(len(groups))]
    return {
        "entities": {"sportsbook": {
            "events": {str(event_id): {
                "name": "Ben Shelton v Karen Khachanov", "competitionId": 1,
                "marketIds": [100], "marketGroupingIds": grouping_ids,
                "numMarkets": 5, "startTime": {"milliseconds": 1791695400000},
            }},
            "markets": {"100": {"id": 100, "name": "Match Betting", "outcomeIds": [1, 2]}},
            "outcomes": {
                "1": {"id": 1, "name": "Ben Shelton", "winPrice": {"num": 800, "den": 1000}},
                "2": {"id": 2, "name": "Karen Khachanov", "winPrice": {"num": 1000, "den": 1000}},
            },
            "competitions": {"1": {"name": "ATP Shanghai"}},
            "marketGroupings": {
                gid: {"name": name, "httpLink": f"Sportsbook/Sports/Events/{event_id}/MarketGroupings/{i}/Markets"}
                for i, (gid, name) in enumerate(zip(grouping_ids, groups))
            },
        }}
    }


def _group_market(market_id, name, selections):
    return {"id": market_id, "name": name, "selections": [
        {"id": i, "name": sel, "statusCode": status,
         "price": {"winPrice": odds, "winPriceNum": round((odds - 1) * 1000), "winPriceDen": 1000}}
        for i, (sel, odds, status) in enumerate(selections)
    ]}


def test_event_fetch_adds_the_unrendered_market_tabs(monkeypatch):
    from tennis_wc.providers import sportsbet_scrape_provider as mod

    provider = mod.SportsbetScrapeProvider()
    payload = _page()
    monkeypatch.setattr(provider, "_fetch_html", lambda url: "<html/>")
    monkeypatch.setattr(provider, "_extract_preloaded_state", lambda html: payload)
    fetched = []

    def fetch_json(url):
        fetched.append(url)
        if url.endswith("/1/Markets"):
            return [
                _group_market(200, "Game Handicap",
                              [("Ben Shelton -3.5", 1.9, "A"), ("Karen Khachanov +3.5", 1.9, "A")]),
                _group_market(100, "Match Betting",
                              [("Ben Shelton", 1.8, "A"), ("Karen Khachanov", 2.0, "A")]),
            ]
        if url.endswith("/3/Markets"):
            raise TimeoutError("tab did not load")
        raise AssertionError(f"skipped tab fetched: {url}")

    monkeypatch.setattr(provider, "_fetch_json", fetch_json)
    monkeypatch.delenv("TENNIS_SPORTSBET_MARKET_GROUPS", raising=False)
    row = provider.fetch_event_odds("https://www.sportsbet.com.au/betting/tennis/x/y-7", ["all"])
    names = [m["market_name"] for m in row["markets"]]
    assert names == ["Match Betting", "Game Handicap"], "deduplicated by market id"
    gh = row["markets"][1]
    assert gh["market_key"] == "game_handicap"
    assert [(s["selection_name"], s["line"], s["odds"]) for s in gh["selections"]] == [
        ("Ben Shelton -3.5", -3.5, 1.9), ("Karen Khachanov +3.5", 3.5, 1.9)]
    cov = row["market_coverage"]
    assert cov["num_markets"] == 5 and cov["page_markets"] == 1
    assert cov["group_markets_added"] == 1 and cov["groups_fetched"] == 1
    assert cov["groups_failed"] == ["Total Games Markets: TimeoutError"]
    assert set(cov["groups_skipped"]) == {"Top Markets", "Individual Point Markets"}
    assert len(fetched) == 2

    monkeypatch.setenv("TENNIS_SPORTSBET_MARKET_GROUPS", "0")
    fetched.clear()
    row = provider.fetch_event_odds("https://www.sportsbet.com.au/betting/tennis/x/y-7", ["all"])
    assert fetched == [] and "market_coverage" not in row


def test_suspended_group_selections_are_not_prices():
    from tennis_wc.providers.sportsbet_scrape_provider import SportsbetScrapeProvider

    market = SportsbetScrapeProvider()._group_market(_group_market(
        300, "Set Handicap",
        [("Ben Shelton -1.5", 2.2, "A"), ("Karen Khachanov +1.5", 1.65, "S")]))
    assert market is None, "one live selection is not a two-way market"
