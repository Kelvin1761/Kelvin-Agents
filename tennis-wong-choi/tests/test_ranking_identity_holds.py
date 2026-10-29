from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from conftest import configure_test_db


def _ranking(key, name, rank):
    return {"player_id": key, "player_name": name, "tour": "ATP", "rank": rank,
            "ranking_date": "2026-10-29", "ranking_points": 100}


def _provider(monkeypatch, module, rows):
    monkeypatch.setattr(module, "get_tennis_provider", lambda: SimpleNamespace(
        provider_name="feed", fetch_rankings=lambda *a: rows,
    ))
    monkeypatch.setattr(module, "_latest_cached_rankings", lambda *a: pytest.fail("identity holds must not be called a cached success"))


def test_identity_conflict_does_not_truncate_safe_ranking_rows(tmp_path, monkeypatch):
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.db import get_connection
    from tennis_wc.database.migrations import init_db
    from tennis_wc.ingestion.entity_mapping import get_or_create_player
    from tennis_wc.ingestion import ingest_rankings as module

    init_db()
    wrong = get_or_create_player("feed", "KE64", "Toby Samuel", "ATP", 0, current_rank=100)
    rows = [_ranking("TF", "Taylor Fritz", 1), _ranking("KE64", "Stefan Kozlov", 2),
            _ranking("AZ", "Alexander Zverev", 3)]
    _provider(monkeypatch, module, rows)
    with pytest.raises(module.RankingIdentityHoldError, match="imported=2 held=1") as raised:
        module.ingest_rankings("ATP", "2026-10-29")
    report = raised.value.report
    assert report["total_rows"] == 3 and report["imported_rows"] == 2
    with get_connection() as conn:
        assert {r[0] for r in conn.execute("SELECT p.name FROM rankings_history r JOIN players p ON p.id=r.player_id")} == {"Taylor Fritz", "Alexander Zverev"}
        unchanged = conn.execute("SELECT name,current_rank,raw_response_id FROM players WHERE id=?", (wrong,)).fetchone()
        assert tuple(unchanged) == ("Toby Samuel", 100, 0)
        raw = conn.execute("SELECT response_json FROM raw_api_responses WHERE id=?", (report["raw_response_id"],)).fetchone()
        assert json.loads(raw[0]) == rows  # preserve the conflicting row too
        hold = conn.execute("SELECT * FROM raw_api_responses WHERE id=?", (report["hold_response_id"],)).fetchone()
        assert hold["endpoint"] == "/rankings/identity-holds" and hold["status_code"] == 206
        saved = json.loads(hold["response_json"])
        assert saved["raw_response_id"] == report["raw_response_id"]
        assert saved["held"][0]["provider_player_id"] == "KE64"
        assert saved["held"][0]["error"].startswith("provider player identity changed")


def test_all_rows_held_is_an_explicit_failure(tmp_path, monkeypatch):
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.db import get_connection
    from tennis_wc.database.migrations import init_db
    from tennis_wc.ingestion.entity_mapping import get_or_create_player
    from tennis_wc.ingestion import ingest_rankings as module

    init_db()
    get_or_create_player("feed", "KE64", "Toby Samuel", "ATP", 0)
    _provider(monkeypatch, module, [_ranking("KE64", "Stefan Kozlov", 2)])
    with pytest.raises(module.RankingIdentityHoldError, match="imported=0 held=1"):
        module.ingest_rankings("ATP", "2026-10-29")
    with get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM rankings_history").fetchone()[0] == 0


def test_unexpected_database_or_programming_error_is_not_swallowed(tmp_path, monkeypatch):
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.ingestion import ingest_rankings as module

    init_db()
    _provider(monkeypatch, module, [_ranking("TF", "Taylor Fritz", 1)])
    def broken(*args, **kwargs):
        raise RuntimeError("database unavailable")
    monkeypatch.setattr(module, "get_or_create_player", broken)
    with pytest.raises(RuntimeError, match="database unavailable"):
        module.ingest_rankings("ATP", "2026-10-29")


@pytest.mark.parametrize("reverse", [False, True])
def test_two_ranked_source_ids_claiming_one_canonical_player_are_both_held(tmp_path, monkeypatch, reverse):
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.db import get_connection
    from tennis_wc.database.migrations import init_db
    from tennis_wc.identity.player_identity import ensure_identity_schema
    from tennis_wc.ingestion.entity_mapping import get_or_create_player
    from tennis_wc.ingestion import ingest_rankings as module

    init_db()
    canonical = get_or_create_player("feed", "long", "Joao Lucas Reis Da Silva", "ATP", 0, current_rank=400)
    short = get_or_create_player("feed", "short", "Joao Silva", "ATP", 0, current_rank=1500)
    with get_connection() as conn:
        ensure_identity_schema(conn)
        conn.execute("UPDATE players SET canonical_player_id=? WHERE id=?", (canonical, short))
        before = [dict(r) for r in conn.execute("SELECT * FROM players ORDER BY id")]
    rows = [_ranking("long", "Joao Lucas Reis Da Silva", 401), _ranking("short", "Joao Silva", 1512)]
    if reverse:
        rows.reverse()
    rows.append(_ranking("TF", "Taylor Fritz", 1))
    _provider(monkeypatch, module, rows)
    with pytest.raises(module.RankingIdentityHoldError, match="imported=1 held=2") as raised:
        module.ingest_rankings("ATP", "2026-10-29")
    assert {h["provider_player_id"] for h in raised.value.report["held"]} == {"long", "short"}
    with get_connection() as conn:
        assert [dict(r) for r in conn.execute("SELECT * FROM players WHERE id IN (?,?) ORDER BY id", (canonical, short))] == before
        assert {r[0] for r in conn.execute("SELECT p.name FROM rankings_history r JOIN players p ON p.id=r.player_id")} == {"Taylor Fritz"}


@pytest.mark.parametrize("same_key", [False, True])
def test_ambiguous_repeated_new_identities_are_not_created(tmp_path, monkeypatch, same_key):
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.db import get_connection
    from tennis_wc.database.migrations import init_db
    from tennis_wc.ingestion import ingest_rankings as module

    init_db()
    rows = [_ranking("one", "Alex Smith", 1), _ranking("one" if same_key else "two", "Alex Smith", 2)]
    _provider(monkeypatch, module, rows)
    with pytest.raises(module.RankingIdentityHoldError, match="imported=0 held=2"):
        module.ingest_rankings("ATP", "2026-10-29")
    with get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM players").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM rankings_history").fetchone()[0] == 0
