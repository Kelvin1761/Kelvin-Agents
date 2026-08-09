"""Parser and matching tests for the lower-tier (ITF/UTR) result feed."""
from __future__ import annotations

import json

from tennis_wc.providers.tennisexplorer_provider import parse_results_page


def _seed_player(conn, pid, name):
    conn.execute(
        "INSERT INTO players (id, name, tour, source_provider, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?)",
        (pid, name, "WTA", "test", "now", "now"),
    )


def _seed_match(conn, mid, a, b, date="2026-08-06"):
    conn.execute(
        """INSERT INTO matches (id, provider_match_id, tour, match_date, tournament_id,
               player_a_id, player_b_id, round, source_provider, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (mid, f"M{mid}", "WTA", date, 1, a, b, "R1", "sportsbet", "now", "now"),
    )


def _row(row_id: str, name: str, sets: str, games: list[str]) -> str:
    cells = "".join(f'<td class="score">{value}</td>' for value in games)
    return (
        f'<tr id="{row_id}" class="one">'
        f'<td class="t-name"><a href="/player/x/">{name}</a></td>'
        f'<td class="result">{sets}</td>{cells}</tr>'
    )


def _page(*match_html: str, tournament: str = "Kursumlijska Banja 13 ITF") -> str:
    head = (
        '<tr class="head flags"><td class="t-name" colspan="2">'
        f'<a href="/x/2026/wta-women/">{tournament}</a></td></tr>'
    )
    return "<table>" + head + "".join(match_html) + "</table>"


def test_parses_itf_match_with_full_scoreline():
    html = _page(
        _row("r1", "Glushkova D. (2)", "2", ["6", "6", "&nbsp;"]),
        _row("r1b", "Jovanovic M.", "0", ["0", "1", "&nbsp;"]),
    )
    results, skipped = parse_results_page(html)

    assert skipped == 0
    assert len(results) == 1
    result = results[0]
    assert result.tournament_name == "Kursumlijska Banja 13 ITF"
    # The seeding marker must not leak into the name used for matching.
    assert result.player_a_name == "Glushkova D."
    assert result.winner_name == "Glushkova D."
    assert result.sets == [
        {"player_a_games": 6, "player_b_games": 0},
        {"player_a_games": 6, "player_b_games": 1},
    ]
    payload = result.score_payload()
    assert payload["player_a_games"] == 12 and payload["player_b_games"] == 1
    assert payload["player_a_sets"] == 2 and payload["player_b_sets"] == 0
    assert "retired" not in payload


def test_tiebreak_set_is_not_credited_to_the_loser():
    """`7` vs `65` is 7-6(5): read literally, 65 wins the set for the loser.

    On 2026-08-06 this shape covered 88 of 370 scoreboard rows, so getting it
    wrong would have inverted the winner on nearly a quarter of the feed.
    """
    html = _page(
        _row("r2", "Norrie C.", "2", ["5", "7", "6"]),
        _row("r2b", "De Minaur A.", "1", ["7", "65", "1"]),
    )
    results, skipped = parse_results_page(html)

    assert skipped == 0
    assert results[0].sets[1] == {"player_a_games": 7, "player_b_games": 6}
    assert results[0].winner_name == "Norrie C."


def test_scoreline_disagreeing_with_the_set_tally_is_refused():
    html = _page(
        _row("r3", "Player A", "2", ["6", "3", "&nbsp;"]),
        _row("r3b", "Player B", "0", ["4", "6", "&nbsp;"]),
    )
    results, skipped = parse_results_page(html)

    assert results == []
    assert skipped == 1


def test_walkover_without_games_is_returned_as_retired_so_props_can_void():
    html = _page(
        _row("r4", "Ivashka I.", "1", ["&nbsp;", "&nbsp;"]),
        _row("r4b", "Mayot H.", "0", ["&nbsp;", "&nbsp;"]),
    )
    results, skipped = parse_results_page(html)

    assert skipped == 0
    assert results[0].retired is True
    payload = results[0].score_payload()
    assert payload["retired"] is True
    # No grid means no games total; a zero here would look like a real 0-0.
    assert payload["player_a_games"] is None


def test_surname_initial_names_match_full_names():
    from tennis_wc.ingestion.name_matching import match_pair_score, same_player_name

    assert same_player_name("Glushkova D.", "Denislava Glushkova")
    score, direction = match_pair_score(
        "Jovanovic M.", "Glushkova D.", "Denislava Glushkova", "Mirjana Jovanovic"
    )
    assert direction == "swapped" and score >= 1.84
    # A different given name with the same surname must NOT match.
    assert not same_player_name("Glushkova D.", "Maria Glushkova")
    # Multi-word surnames keep working.
    assert same_player_name("Alex de Minaur", "de Minaur A.")


def test_ingest_refuses_ambiguous_fixture_pairs(tmp_path, monkeypatch):
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.ingestion import ingest_tennisexplorer
    from tennis_wc.providers.tennisexplorer_provider import ParsedResult

    init_db()
    conn = get_connection()
    _seed_player(conn, 1, "Denislava Glushkova")
    _seed_player(conn, 2, "Mirjana Jovanovic")
    # The same pair stored twice on the same date: which one the result belongs
    # to is unknowable, so neither may be settled.
    _seed_match(conn, 1, 1, 2, date="2026-08-06")
    _seed_match(conn, 2, 1, 2, date="2026-08-06")
    conn.commit()

    result = ParsedResult(
        tournament_name="Kursumlijska Banja 13 ITF",
        player_a_name="Glushkova D.",
        player_b_name="Jovanovic M.",
        player_a_sets=2,
        player_b_sets=0,
        sets=[{"player_a_games": 6, "player_b_games": 0},
              {"player_a_games": 6, "player_b_games": 1}],
    )

    class _Stub:
        def fetch_results_for_date(self, match_date):
            return ([result], 0) if match_date == "2026-08-06" else ([], 0)

    summary = ingest_tennisexplorer.ingest_tennisexplorer_results(
        "2026-08-06", provider=_Stub()
    )
    assert summary["ambiguous"] == 1
    assert summary["imported"] == 0
    assert conn.execute("SELECT COUNT(*) FROM match_results").fetchone()[0] == 0


def test_ingest_writes_scoreline_in_the_fixture_player_order(tmp_path, monkeypatch):
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.ingestion import ingest_tennisexplorer
    from tennis_wc.providers.tennisexplorer_provider import ParsedResult

    init_db()
    conn = get_connection()
    _seed_player(conn, 1, "Mirjana Jovanovic")
    _seed_player(conn, 2, "Denislava Glushkova")
    _seed_match(conn, 1, 1, 2, date="2026-08-06")
    conn.commit()

    # The scoreboard lists Glushkova first; the fixture stores her second.
    result = ParsedResult(
        tournament_name="Kursumlijska Banja 13 ITF",
        player_a_name="Glushkova D.",
        player_b_name="Jovanovic M.",
        player_a_sets=2,
        player_b_sets=0,
        sets=[{"player_a_games": 6, "player_b_games": 0},
              {"player_a_games": 6, "player_b_games": 1}],
    )

    class _Stub:
        def fetch_results_for_date(self, match_date):
            return ([result], 0) if match_date == "2026-08-06" else ([], 0)

    summary = ingest_tennisexplorer.ingest_tennisexplorer_results(
        "2026-08-06", provider=_Stub()
    )
    assert summary["imported"] == 1

    row = conn.execute(
        "SELECT winner_player_id, score_json FROM match_results WHERE match_id = 1"
    ).fetchone()
    assert row["winner_player_id"] == 2  # Glushkova, stored as player_b
    payload = json.loads(row["score_json"])
    assert payload["player_a_sets"] == 0 and payload["player_b_sets"] == 2
    assert payload["sets"][0] == {"player_a_games": 0, "player_b_games": 6}
    assert payload["player_a_games"] == 1 and payload["player_b_games"] == 12


def test_props_settle_from_an_imported_lower_tier_scoreline(tmp_path, monkeypatch):
    """End to end: an ITF result now grades a games prop that used to hang."""
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.ingestion import ingest_tennisexplorer
    from tennis_wc.props.settlement import settle_props
    from tennis_wc.providers.tennisexplorer_provider import ParsedResult

    init_db()
    conn = get_connection()
    _seed_player(conn, 1, "Denislava Glushkova")
    _seed_player(conn, 2, "Mirjana Jovanovic")
    _seed_match(conn, 1, 1, 2, date="2026-08-06")
    conn.execute(
        "INSERT INTO prop_tracker (prop_key, match_id, match_date, match_label, "
        "market_key, line, selection, decimal_odds, model_prob, side, prop_scope, "
        "subject_player_id, stake_units, is_value, result_status, recorded_at, "
        "updated_at) "
        "VALUES ('k1', 1, '2026-08-06', 'x', 'player_total_games_a', 9.5, 'over', "
        "1.9, 0.6, 'over', 'player_games', 1, 1.0, 1, 'PENDING', 'now', 'now')"
    )
    conn.commit()

    class _Stub:
        def fetch_results_for_date(self, match_date):
            if match_date != "2026-08-06":
                return ([], 0)
            return ([ParsedResult(
                tournament_name="Kursumlijska Banja 13 ITF",
                player_a_name="Glushkova D.",
                player_b_name="Jovanovic M.",
                player_a_sets=2,
                player_b_sets=0,
                sets=[{"player_a_games": 6, "player_b_games": 0},
                      {"player_a_games": 6, "player_b_games": 1}],
            )], 0)

    ingest_tennisexplorer.ingest_tennisexplorer_results("2026-08-06", provider=_Stub())
    assert settle_props(conn)["graded"] == 1
    row = conn.execute(
        "SELECT result_status, actual_value FROM prop_tracker WHERE prop_key = 'k1'"
    ).fetchone()
    assert row["result_status"] == "WON"  # 12 games won, line 9.5
    assert row["actual_value"] == 12
