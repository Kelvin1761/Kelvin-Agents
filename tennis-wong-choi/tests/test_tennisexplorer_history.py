"""The lower-tier corpus: build history for players no ATP/WTA file covers."""
from __future__ import annotations


def _setup(tmp_path, monkeypatch):
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection

    init_db()
    return get_connection()


def _result(tournament, winner, loser):
    from tennis_wc.providers.tennisexplorer_provider import ParsedResult

    return ParsedResult(
        tournament_name=tournament,
        player_a_name=winner,
        player_b_name=loser,
        player_a_sets=2,
        player_b_sets=0,
        sets=[{"player_a_games": 6, "player_b_games": 2},
              {"player_a_games": 6, "player_b_games": 3}],
    )


class _Stub:
    def __init__(self, by_date):
        self.by_date = by_date

    def fetch_results_for_date(self, match_date):
        return (self.by_date.get(match_date, []), 0)


def test_both_sides_of_every_match_are_stored(tmp_path, monkeypatch):
    """Elo needs the loser's row too, not just the winner's."""
    from tennis_wc.ingestion import ingest_tennisexplorer_history as corpus

    _setup(tmp_path, monkeypatch)
    stub = _Stub({"2026-03-01": [
        _result("ITF W35 Southaven USA", "Piper Charney", "Jia-Jing Lu"),
    ]})
    summary = corpus.ingest_tennisexplorer_history("2026-03-01", provider=stub)

    assert summary["matches"] == 1 and summary["rows"] == 2
    from tennis_wc.database.db import get_connection

    conn = get_connection()
    rows = conn.execute(
        "SELECT player_id, opponent_id, won, tournament_level, tour "
        "FROM player_match_history ORDER BY won DESC"
    ).fetchall()
    assert [r["won"] for r in rows] == [1, 0]
    assert rows[0]["player_id"] == rows[1]["opponent_id"]
    assert rows[0]["opponent_id"] == rows[1]["player_id"]
    assert rows[0]["tournament_level"] == "ITF"
    assert rows[0]["tour"] == "WTA", "a W35 event is a women's event"


def test_a_rerun_updates_rather_than_duplicating(tmp_path, monkeypatch):
    from tennis_wc.ingestion import ingest_tennisexplorer_history as corpus

    _setup(tmp_path, monkeypatch)
    stub = _Stub({"2026-03-01": [_result("ITF M15 Monastir", "Ivan One", "Petr Two")]})
    corpus.ingest_tennisexplorer_history("2026-03-01", provider=stub)
    corpus.ingest_tennisexplorer_history("2026-03-01", provider=stub)

    from tennis_wc.database.db import get_connection

    assert get_connection().execute(
        "SELECT COUNT(*) FROM player_match_history"
    ).fetchone()[0] == 2


def test_a_known_player_is_reused_instead_of_duplicated(tmp_path, monkeypatch):
    """The corpus must not recreate the 864-duplicate problem it exists to fix."""
    from tennis_wc.ingestion import ingest_tennisexplorer_history as corpus
    from tennis_wc.identity import player_identity

    conn = _setup(tmp_path, monkeypatch)
    player_identity.ensure_identity_schema(conn)
    conn.execute(
        "INSERT INTO players (id, name, tour, source_provider, created_at, updated_at) "
        "VALUES (1, 'Denislava Glushkova', 'WTA', 'sackmann', 'now', 'now')"
    )
    conn.commit()

    # The scoreboard spells her surname-first with an initial.
    stub = _Stub({"2026-03-01": [
        _result("ITF W15 Antalya", "Glushkova D.", "Mirjana Jovanovic"),
    ]})
    summary = corpus.ingest_tennisexplorer_history("2026-03-01", provider=stub)

    from tennis_wc.database.db import get_connection

    conn = get_connection()
    assert summary["players_created"] == 1, "only the opponent is new"
    winner = conn.execute(
        "SELECT player_id FROM player_match_history WHERE won = 1"
    ).fetchone()[0]
    assert winner == 1, "the existing player must be reused, not duplicated"
    assert conn.execute(
        "SELECT COUNT(*) FROM players WHERE name LIKE '%lushkova%'"
    ).fetchone()[0] == 1


def test_a_bad_day_does_not_end_the_corpus_build(tmp_path, monkeypatch):
    from tennis_wc.ingestion import ingest_tennisexplorer_history as corpus

    _setup(tmp_path, monkeypatch)

    class _Flaky:
        def fetch_results_for_date(self, match_date):
            if match_date == "2026-03-02":
                raise RuntimeError("scoreboard timeout")
            return ([_result("ITF M15 Monastir", f"W {match_date}", f"L {match_date}")], 0)

    summary = corpus.ingest_tennisexplorer_history(
        "2026-03-01", "2026-03-03", provider=_Flaky()
    )
    assert summary["dates"] == 2
    assert summary["matches"] == 2
    assert len(summary["errors"]) == 1
    assert summary["errors"][0]["date"] == "2026-03-02"


def test_elo_reads_the_lower_tier_corpus(tmp_path, monkeypatch):
    """The whole point: an ITF-only player must end up with a rating."""
    from tennis_wc.ingestion import ingest_tennisexplorer_history as corpus
    from tennis_wc.modelling.elo_builder import build_sackmann_elo, ELO_PROVIDERS
    from tennis_wc.history import elo_history

    _setup(tmp_path, monkeypatch)
    assert corpus.PROVIDER_NAME in ELO_PROVIDERS

    stub = _Stub({
        "2026-03-01": [_result("ITF M15 Monastir", "Ivan One", "Petr Two")],
        "2026-03-08": [_result("ITF M15 Monastir", "Ivan One", "Petr Two")],
    })
    corpus.ingest_tennisexplorer_history("2026-03-01", "2026-03-08", provider=stub)

    summary = build_sackmann_elo()
    assert summary["players_rated"] == 2

    from tennis_wc.database.db import get_connection

    conn = get_connection()
    winner_id = conn.execute(
        "SELECT id FROM players WHERE name = 'Ivan One'"
    ).fetchone()[0]
    rating = conn.execute(
        "SELECT overall_elo FROM players WHERE id = ?", (winner_id,)
    ).fetchone()[0]
    assert rating > 1500.0, "two wins must lift an ITF player's rating"
    # And the as-of series exists for him too.
    assert elo_history.rating_as_of(conn, winner_id, "2026-03-08") is not None
