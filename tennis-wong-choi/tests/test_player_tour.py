"""Player tours come from evidence that can carry them, not from row labels.

2026-10-30: 19 WTA ranking rows were held every day because merge targets said
ATP, and ~3,000 women were stored ATP. ESPN labelled matches by scoreboard,
TennisExplorer defaulted ITF to ATP, and ingestion copied labels onto players.
"""
from __future__ import annotations

import json

import pytest

from conftest import configure_test_db


def _db(tmp_path, monkeypatch):
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.db import get_connection
    from tennis_wc.database.migrations import init_db
    from tennis_wc.identity.player_identity import ensure_identity_schema

    init_db()
    conn = get_connection()
    ensure_identity_schema(conn)
    return conn


def _player(conn, pid, name, tour, canonical=None):
    conn.execute(
        "INSERT INTO players (id, name, tour, source_provider, created_at, updated_at, canonical_player_id) "
        "VALUES (?,?,?,?,?,?,?)", (pid, name, tour, "test", "now", "now", canonical))


def _key(conn, provider, key, pid, name="x"):
    conn.execute(
        "INSERT INTO provider_entities (provider_name, entity_type, provider_entity_id, internal_entity_id, "
        "entity_name, confidence_score, created_at, updated_at) VALUES (?,?,?,?,?,1,'now','now')",
        (provider, "player", key, pid, name))


def _rank(conn, pid, tour, n=1, source="composite"):
    for i in range(n):
        conn.execute(
            "INSERT INTO rankings_history (player_id, ranking_date, tour, rank, source_provider, "
            "raw_response_id, created_at) VALUES (?,?,?,?,?,0,'now')",
            (pid, f"2026-01-{i + 1:02d}", tour, 100, source))


def _match(conn, a, b, n=1, tour="ATP"):
    for i in range(n):
        for pid, opp, won in ((a, b, 1), (b, a, 0)):
            conn.execute(
                """INSERT INTO player_match_history (provider_match_id, player_id, opponent_id, tour,
                   match_date, tournament_external_id, tournament_level, round, format, won,
                   source_provider, raw_response_id, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,0,'now')""",
                (f"m{a}-{b}-{i}", pid, opp, tour, "2026-02-01", "T", "ITF", "R1", "BO3", won,
                 "tennisexplorer"))


# -- write paths -----------------------------------------------------------

def test_espn_tour_comes_from_the_competition_not_the_scoreboard():
    from tennis_wc.providers.espn_provider import _competition_tour

    assert _competition_tour({"type": {"slug": "womens-singles"}}, "ATP") == "WTA"
    assert _competition_tour({"type": {"slug": "mens-singles"}}, "WTA") == "ATP"
    assert _competition_tour({}, "WTA") == "WTA"


def test_espn_women_on_the_atp_scoreboard_are_labelled_wta():
    from tennis_wc.providers.espn_provider import EspnTennisProvider

    competition = {
        "id": "184353", "date": "2026-10-09T11:05Z", "type": {"slug": "womens-singles"},
        "competitors": [
            {"id": "3730", "athlete": {"displayName": "Iga Swiatek"}, "winner": False},
            {"id": "1", "athlete": {"displayName": "Other Player"}, "winner": True},
        ],
    }
    rows = EspnTennisProvider()._normalise_history_match({"name": "China Open", "id": 959}, competition, "ATP")
    assert {row["tour"] for row in rows} == {"WTA"}


def _header(inner):
    return f'<tr class="head flags"><td class="t-name" colspan="2">{inner}</td></tr>'


def _row(row_id, name, sets, games):
    cells = "".join(f'<td class="score">{g}</td>' for g in games)
    return (f'<tr id="{row_id}" class="one"><td class="t-name"><a href="/player/x/">{name}</a></td>'
            f'<td class="result">{sets}</td>{cells}</tr>')


def test_tennisexplorer_reads_the_draw_from_the_header_not_the_name():
    """Both Bastad draws are "Bastad ITF"; only the header link tells them apart."""
    from tennis_wc.providers.tennisexplorer_provider import parse_results_page

    page = "<table>" + "".join([
        _header('<a href="/bastad-itf/2026/wta-women/">Bastad ITF</a>'),
        _row("r1", "Nilsson L.", "2", ["6", "6"]), _row("r1b", "Other A.", "0", ["1", "2"]),
        _header('<a href="/bastad-itf/2026/atp-men/">Bastad ITF</a>'),
        _row("r2", "Smith B.", "2", ["6", "6"]), _row("r2b", "Jones C.", "0", ["1", "2"]),
        _header('<span class="fl fl-all">&nbsp;</span><span class="type-men2">&nbsp;</span>Futures 2026'),
        _row("r3", "Brown D.", "2", ["6", "6"]), _row("r3b", "Green E.", "0", ["1", "2"]),
        _header('Mystery Cup'),
        _row("r4", "Gray F.", "2", ["6", "6"]), _row("r4b", "White G.", "0", ["1", "2"]),
    ]) + "</table>"
    results, skipped = parse_results_page(page)
    assert skipped == 0
    assert [(r.tournament_name, r.tour) for r in results] == [
        ("Bastad ITF", "WTA"), ("Bastad ITF", "ATP"), ("Futures 2026", "ATP"),
        # An unmarked header must not inherit the previous tournament's tour.
        ("Mystery Cup", None),
    ]


def test_tennisexplorer_corpus_never_defaults_to_atp():
    from tennis_wc.ingestion.ingest_tennisexplorer_history import _tour_of

    assert _tour_of("Bastad ITF", None) == "UNKNOWN"
    assert _tour_of("Bastad ITF", "WTA") == "WTA"
    assert _tour_of("ITF W35 Southaven USA", None) == "WTA"


def test_unknown_label_does_not_erase_a_known_tour(tmp_path, monkeypatch):
    conn = _db(tmp_path, monkeypatch)
    from tennis_wc.ingestion.entity_mapping import get_or_create_player

    _player(conn, 1, "Lea Nilsson", "WTA")
    _key(conn, "composite", "18670", 1, "Lea Nilsson")
    conn.commit()
    assert get_or_create_player("composite", "18670", "Lea Nilsson", "UNKNOWN", 0) == 1
    assert conn.execute("SELECT tour FROM players WHERE id=1").fetchone()[0] == "WTA"


def test_missing_embedded_tour_creates_unknown_not_atp(tmp_path, monkeypatch):
    conn = _db(tmp_path, monkeypatch)
    from tennis_wc.ingestion.ingest_matches import _ensure_player

    pid = _ensure_player("composite", "777", 0, {"name": "New Player", "tour": None})
    assert conn.execute("SELECT tour FROM players WHERE id=?", (pid,)).fetchone()[0] == "UNKNOWN"


def test_spacing_variant_is_the_same_name(tmp_path, monkeypatch):
    """`wta:322417` was "Ye-Xin Ma", then "Yexin Ma"; the target says "Ye Xin Ma"."""
    conn = _db(tmp_path, monkeypatch)
    from tennis_wc.ingestion.entity_mapping import get_or_create_player

    _player(conn, 858, "Ye Xin Ma", "WTA")
    _player(conn, 3441, "Yexin Ma", "WTA", canonical=858)
    _key(conn, "composite", "wta:322417", 3441, "Yexin Ma")
    conn.commit()
    assert get_or_create_player("composite", "wta:322417", "Yexin Ma", "WTA", 0) == 858


def test_one_conflicting_history_row_does_not_abort_the_file(tmp_path, monkeypatch):
    """KE64 held `history_lowtier` from 2026-10-28; every later row was dropped."""
    conn = _db(tmp_path, monkeypatch)
    from tennis_wc.ingestion.ingest_sackmann import TML_PROVIDER_NAME, _ingest_rows

    _player(conn, 1, "Toby Samuel", "ATP")
    _key(conn, TML_PROVIDER_NAME, "KE64", 1, "Toby Samuel")
    conn.commit()
    base = {"tourney_date": "20261001", "tourney_name": "Challenger", "surface": "Hard",
            "tourney_level": "C", "round": "R32", "best_of": "3", "score": "6-1 6-1"}
    rows = [
        {**base, "tourney_id": "2026-1", "match_num": "1", "winner_id": "KE64", "winner_name": "Stefan Kozlov",
         "loser_id": "A1", "loser_name": "Alpha One"},
        {**base, "tourney_id": "2026-1", "match_num": "2", "winner_id": "B2", "winner_name": "Beta Two",
         "loser_id": "C3", "loser_name": "Gamma Three"},
    ]
    stats = _ingest_rows("ATP", rows, raw_id=0, provider=TML_PROVIDER_NAME)
    assert stats["matches"] == 1
    assert len(stats["held"]) == 1 and "Toby Samuel" in stats["held"][0]["error"]


# -- resolver and repair ---------------------------------------------------

def test_ranking_evidence_corrects_a_mislabelled_merge_target(tmp_path, monkeypatch):
    """Lea Nilsson: target 3970 said ATP, its merged WTA-ranked row said WTA."""
    conn = _db(tmp_path, monkeypatch)
    from tennis_wc.identity.player_tour import plan_tour_repairs

    _player(conn, 3970, "Lea Nilsson", "ATP")
    _player(conn, 3840, "Lea Nilsson", "WTA", canonical=3970)
    _key(conn, "composite", "wta:333526", 3840)
    _rank(conn, 3970, "WTA", 3)
    conn.commit()
    plan = plan_tour_repairs(conn)
    assert [(c["player_id"], c["old_tour"], c["new_tour"], c["basis"]) for c in plan["changes"]] == [
        (3970, "ATP", "WTA", "authoritative")]


def test_opponents_carry_the_tour_to_unranked_players(tmp_path, monkeypatch):
    conn = _db(tmp_path, monkeypatch)
    from tennis_wc.identity.player_tour import resolve_tours

    for pid in (1, 2, 3):
        _player(conn, pid, f"Ranked {pid}", "WTA")
        _rank(conn, pid, "WTA")
    _player(conn, 10, "Unranked Ten", "ATP")
    _player(conn, 11, "Unranked Eleven", "ATP")
    for pid in (1, 2, 3):
        _match(conn, 10, pid)
    # 11 only meets 10: labelled in the second round, from 10's inferred tour.
    _match(conn, 11, 10, n=3)
    _player(conn, 12, "Too Few", "ATP")
    _match(conn, 12, 1)
    conn.commit()
    decisions = resolve_tours(conn)["decisions"]
    assert decisions[10].tour == "WTA" and decisions[10].basis == "opponents"
    assert decisions[11].tour == "WTA" and decisions[11].evidence["round"] == 2
    assert 12 not in decisions


def test_mixed_opponent_vote_is_not_a_decision(tmp_path, monkeypatch):
    conn = _db(tmp_path, monkeypatch)
    from tennis_wc.identity.player_tour import resolve_tours

    _player(conn, 1, "Woman One", "WTA"); _rank(conn, 1, "WTA")
    _player(conn, 2, "Man Two", "ATP"); _rank(conn, 2, "ATP")
    _player(conn, 10, "Ambiguous", "ATP")
    _match(conn, 10, 1, n=3)
    _match(conn, 10, 2, n=3)
    conn.commit()
    assert 10 not in resolve_tours(conn)["decisions"]


def test_disagreeing_authoritative_evidence_is_a_conflict_not_a_vote(tmp_path, monkeypatch):
    conn = _db(tmp_path, monkeypatch)
    from tennis_wc.identity.player_tour import resolve_tours

    _player(conn, 1, "Two Tours", "ATP")
    _key(conn, "composite", "uts:1", 1)
    _rank(conn, 1, "WTA", 5)
    conn.commit()
    resolved = resolve_tours(conn)
    assert 1 not in resolved["decisions"]
    assert [d.player_id for d in resolved["conflicts"]] == [1]


def test_a_ranked_player_holding_the_other_tours_matches_is_reported(tmp_path, monkeypatch):
    """Marko Stakusic carries "Stakusic M." women's ITF results."""
    conn = _db(tmp_path, monkeypatch)
    from tennis_wc.identity.player_tour import resolve_tours

    _player(conn, 1, "Marko Stakusic", "ATP"); _rank(conn, 1, "ATP")
    for pid in range(2, 8):
        _player(conn, pid, f"Woman {pid}", "WTA"); _rank(conn, pid, "WTA")
        _match(conn, 1, pid)
    conn.commit()
    mixed = resolve_tours(conn)["mixed_records"]
    assert [m["player_id"] for m in mixed] == [1]


def _feed(conn, fetched_at, rows):
    conn.execute(
        "INSERT INTO raw_api_responses (provider_name, endpoint, request_url_hash, request_params_json, "
        "response_json, status_code, fetched_at, entity_type, entity_external_id, created_at) "
        "VALUES ('composite','/rankings','h','{}',?,200,?,'ranking','WTA',?)",
        (json.dumps(rows), fetched_at, fetched_at))


def test_official_wta_rename_is_applied_audited_and_reverted(tmp_path, monkeypatch):
    """`wta:323403` was "Sunam Jeong" until 2026-09-14 and "Hyojoo Jeong" after."""
    conn = _db(tmp_path, monkeypatch)
    from tennis_wc.identity.player_tour import (
        apply_tour_repairs, plan_tour_repairs, revert_tour_repairs)
    from tennis_wc.ingestion.entity_mapping import get_or_create_player

    _player(conn, 18398, "Sunam Jeong", "UNKNOWN")
    _player(conn, 20965, "Hyojoo Jeong", "WTA", canonical=18398)
    _key(conn, "composite", "wta:323403", 20965)
    _rank(conn, 18398, "WTA", 2)
    _feed(conn, "2026-08-26T00:00:00Z", [{"player_id": "wta:323403", "player_name": "Sunam Jeong"}])
    _feed(conn, "2026-09-14T00:00:00Z", [{"player_id": "wta:323403", "player_name": "Hyojoo Jeong"}])
    # A UTS id that moved between two men is never treated as a rename.
    _player(conn, 50, "Martin Krumich", "ATP")
    _player(conn, 51, "Mats Rosenkranz", "ATP", canonical=50)
    _key(conn, "composite", "uts:45169", 51)
    conn.commit()

    plan = plan_tour_repairs(conn)
    assert [(r["player_id"], r["old_name"], r["new_name"]) for r in plan["renames"]] == [
        (18398, "Sunam Jeong", "Hyojoo Jeong")]
    applied = apply_tour_repairs(conn, plan, "run-1")
    assert applied["rename"] == 1 and applied["tour"] == 1
    assert get_or_create_player("composite", "wta:323403", "Hyojoo Jeong", "WTA", 0) == 18398
    aliases = {r[0] for r in conn.execute(
        "SELECT alias_norm FROM player_aliases WHERE canonical_player_id = 18398")}
    assert {"sunam jeong", "hyojoo jeong"} <= aliases
    log = conn.execute("SELECT action, old_value, new_value FROM player_tour_repairs ORDER BY id").fetchall()
    assert ("tour", "UNKNOWN", "WTA") in [tuple(r) for r in log]

    revert_tour_repairs(conn, "run-1")
    assert tuple(conn.execute("SELECT name, tour FROM players WHERE id=18398").fetchone()) == (
        "Sunam Jeong", "UNKNOWN")


def test_plan_writes_nothing(tmp_path, monkeypatch):
    conn = _db(tmp_path, monkeypatch)
    from tennis_wc.identity.player_tour import plan_tour_repairs

    _player(conn, 1, "Lea Nilsson", "ATP"); _rank(conn, 1, "WTA")
    conn.commit()
    before = conn.total_changes
    assert plan_tour_repairs(conn)["changes"]
    assert conn.total_changes == before
    assert conn.execute("SELECT tour FROM players WHERE id=1").fetchone()[0] == "ATP"


def test_wta_stats_link_to_the_canonical_player_not_a_merged_row(tmp_path, monkeypatch):
    """Before: 334 of 1,431 linked names landed on merged rows; after the tour
    repair, duplicates turned WTA and 848 names looked ambiguous."""
    conn = _db(tmp_path, monkeypatch)
    from tennis_wc.ingestion.ingest_wta_stats import _resolve_player

    _player(conn, 3970, "Lea Nilsson", "WTA")
    _player(conn, 3840, "Lea Nilsson", "WTA", canonical=3970)
    _player(conn, 5, "Two People", "WTA")
    _player(conn, 6, "Two People", "WTA")
    conn.commit()
    assert _resolve_player(conn, "Lea Nilsson") == 3970
    assert _resolve_player(conn, "Two People") is None
