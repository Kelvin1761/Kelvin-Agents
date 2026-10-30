"""Actual source dates must survive parsers, cache and feature consumption."""
from datetime import date, datetime, timezone, timedelta
import base64
import hashlib
import json
import sqlite3
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

from tennis_wc.database.ranking_reads import RankingReader, cached_rankings
from tennis_wc.providers.official_ranking_provider import (
    OfficialRankingFetchError, OfficialRankingProvider, _parse_atp_uts_rankings,
    _parse_wta_api_rankings, _parse_wta_rankings_html,
)
from tennis_wc.ranking_dates import RankingDateError, normalise_ranking_date, validate_ranking_rows


@pytest.mark.parametrize("value,expected", [
    ("20260105", "2026-01-05"), ("2026-01-05", "2026-01-05"),
    ("2026-02-30", None), ("20260230", None), ("2026-13-01", None), ("today", None), (None, None),
])
def test_calendar_dates_are_normalized_without_inventing_one(value, expected):
    assert normalise_ranking_date(value) == expected


def test_stale_and_future_dates_reject_the_source_without_relabelling_input():
    rows = [{"ranking_date": "2024-12-30"}]
    with pytest.raises(RankingDateError, match="stale source"):
        validate_ranking_rows(rows, "2026-10-30", max_age_hours=168, today=date(2026, 10, 29))
    assert rows == [{"ranking_date": "2024-12-30"}]
    with pytest.raises(RankingDateError, match="after"):
        validate_ranking_rows([{"ranking_date": "2026-10-30"}], "2026-10-30", today=date(2026, 10, 29))
    assert validate_ranking_rows([{"ranking_date": "20260105"}], "2026-01-06")[0]["ranking_date"] == "2026-01-05"


def test_uts_request_uses_independent_source_date_and_pins_the_data_request(monkeypatch):
    provider = OfficialRankingProvider()
    calls = []
    def fetch(url, **kwargs):
        calls.append(url)
        if "rankingsDate?" in url:
            return '"2024-12-30"'
        return json.dumps({"total": 1, "rows": [{"rank": 1, "name": "Jannik Sinner", "playerId": 50810}]})
    monkeypatch.setattr(provider, "_fetch_text", fetch)
    row = provider._fetch_atp_uts("2026-10-30")[0]
    assert row["ranking_date"] == row["raw"]["source_ranking_date"] == "2024-12-30"
    assert parse_qs(urlparse(calls[1]).query)["date"] == ["30-12-2024"]
    assert parse_qs(urlparse(calls[1]).query)["current"] == ["1"]
    assert row["raw"]["source_date_sha256"] == hashlib.sha256(b'"2024-12-30"').hexdigest()
    assert len(provider.ranking_source_evidence) == 2


def test_uts_parser_cannot_use_the_requested_date_as_source_evidence():
    with pytest.raises(OfficialRankingFetchError, match="independently observed"):
        _parse_atp_uts_rankings({"rows": []}, "2026-10-29")
    with pytest.raises(OfficialRankingFetchError, match="after requested"):
        _parse_atp_uts_rankings({"rows": []}, "2026-10-01", source_date="2026-10-26")


@pytest.mark.parametrize("value", [None, "", "not-a-date", "2026-02-30T00:00:00Z"])
def test_wta_api_missing_date_cannot_fall_back_to_card_date(value):
    with pytest.raises(OfficialRankingFetchError, match="rankedAt"):
        _parse_wta_api_rankings([{"player": {"id": 1, "fullName": "Real Player"}, "ranking": 1,
                                  "rankedAt": value}], "2026-10-29")


def test_wta_html_missing_date_cannot_use_card_date():
    with pytest.raises(OfficialRankingFetchError, match="source ranking date"):
        _parse_wta_rankings_html('<tr class="player-row"></tr>', "2026-10-29")


def test_composite_falls_back_from_stale_source_and_keeps_failure_evidence(monkeypatch):
    from tennis_wc.providers import CompositeTennisProvider
    provider = CompositeTennisProvider()
    stale = [{"ranking_date": "2024-12-30"}]
    fresh = [{"ranking_date": "2026-10-26"}]
    provider.official_rankings = SimpleNamespace(fetch_rankings=lambda *a: stale,
                                                ranking_source_evidence=[{"text": "original date body"}])
    provider.sackmann = SimpleNamespace(fetch_rankings=lambda *a: fresh)
    assert provider.fetch_rankings("ATP", "2026-10-29") == fresh
    assert provider.ranking_source_failures[0]["rows"] == stale
    assert provider.ranking_source_evidence == [{"text": "original date body"}]


def connection():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
      CREATE TABLE players(id INTEGER PRIMARY KEY,name TEXT,tour TEXT,current_rank INTEGER,
                           overall_elo REAL,surface_elo_json TEXT,source_provider TEXT,raw_response_id INTEGER);
      CREATE TABLE rankings_history(id INTEGER PRIMARY KEY,player_id INTEGER,ranking_date TEXT,tour TEXT,
                                    rank INTEGER,ranking_points INTEGER,source_provider TEXT,raw_response_id INTEGER);
      CREATE TABLE raw_api_responses(id INTEGER PRIMARY KEY,provider_name TEXT,response_json TEXT);
    """)
    body = json.dumps([{"player_id": "uts:1", "ranking_date": "2026-10-28", "rank": 9,
                        "raw": {"source": "ultimate_tennis_statistics"}}])
    conn.execute("INSERT INTO raw_api_responses VALUES (1,'composite',?)", (body,))
    conn.execute("INSERT INTO raw_api_responses VALUES (2,'tennismylife_history','{}')")
    from tennis_wc.ingestion.ingest_rankings import _rank_seed_elo
    conn.execute("INSERT INTO players VALUES (1,'Alpha Player','ATP',9,?,NULL,'jeff_sackmann',1)", (_rank_seed_elo(9),))
    conn.execute("INSERT INTO rankings_history VALUES (1,1,'2026-10-28','ATP',9,NULL,'composite',1)")
    conn.execute("INSERT INTO rankings_history VALUES (2,1,'2026-10-26','ATP',333,NULL,'tennismylife_history',2)")
    return conn


def test_known_misdated_feed_does_not_hide_valid_older_source_or_change_rows():
    conn = connection()
    before = [tuple(r) for r in conn.execute("SELECT * FROM rankings_history")]
    result = RankingReader(conn).select(1, "2026-10-29")
    assert result["rank"] == 333 and result["raw_response_id"] == 2
    assert result["warnings"] == ["ranking_source_date_unverified"]
    assert [tuple(r) for r in conn.execute("SELECT * FROM rankings_history")] == before
    assert not RankingReader(conn).current_fallback_allowed(1, conn.execute("SELECT * FROM players").fetchone())


def test_compact_calendar_date_is_read_without_backwriting_history():
    conn = connection()
    conn.execute("UPDATE rankings_history SET ranking_date='20260105' WHERE id=2")
    result = RankingReader(conn).select(1, "2026-01-06")
    assert result["rank"] == 333 and result["ranking_date"] == "2026-01-05"
    assert conn.execute("SELECT ranking_date FROM rankings_history WHERE id=2").fetchone()[0] == "20260105"


def test_cache_uses_only_valid_recent_sources_and_cannot_resurrect_bad_feed():
    conn = connection()
    rows = cached_rankings(conn, "ATP", "2026-10-30", max_age_hours=168, today=date(2026, 10, 29))
    assert [r["rank"] for r in rows] == [333]
    conn.execute("UPDATE rankings_history SET ranking_date='2026-10-01' WHERE id=2")
    assert cached_rankings(conn, "ATP", "2026-10-30", max_age_hours=168, today=date(2026, 10, 29)) == []


def test_actual_publication_is_preferred_over_later_tournament_rank_reference():
    conn = connection()
    conn.execute("UPDATE rankings_history SET ranking_date='2026-10-27' WHERE id=2")
    pdf = b"publisher PDF bytes"
    sha = hashlib.sha256(pdf).hexdigest()
    evidence = {"captures": [{"url": OfficialRankingProvider.ATP_NUMERIC_PDF_URL,
                               "sha256": sha, "content_base64": base64.b64encode(pdf).decode()}]}
    normalized = [{"ranking_date": "2026-10-26", "raw": {"source": "atp_official_numeric_pdf",
                   "source_ranking_date": "2026-10-26", "source_url": OfficialRankingProvider.ATP_NUMERIC_PDF_URL,
                   "source_pdf_sha256": sha, "source_capture_raw_id": 3}}]
    conn.execute("INSERT INTO raw_api_responses VALUES (3,'composite',?)", (json.dumps(evidence),))
    conn.execute("INSERT INTO raw_api_responses VALUES (4,'composite',?)", (json.dumps(normalized),))
    conn.execute("INSERT INTO rankings_history VALUES (3,1,'2026-10-26','ATP',200,NULL,'atp_official_numeric_pdf',4)")
    assert RankingReader(conn).select(1, "2026-10-29")["rank"] == 200
    assert cached_rankings(conn, "ATP", "2026-10-29", max_age_hours=168, today=date(2026, 10, 29))[0]["rank"] == 200
    conn.execute("UPDATE raw_api_responses SET response_json='{}' WHERE id=3")
    result = RankingReader(conn).select(1, "2026-10-29")
    assert result["rank"] == 333 and "ranking_source_capture_invalid" in result["warnings"]
    conn.execute("UPDATE rankings_history SET ranking_date='2026-10-01' WHERE id=3")
    assert RankingReader(conn).select(1, "2026-10-29")["rank"] == 333


def test_source_date_metadata_must_match_database_row():
    conn = connection()
    body = json.loads(conn.execute("SELECT response_json FROM raw_api_responses WHERE id=1").fetchone()[0])
    body[0]["raw"].update(source_ranking_date="2026-10-28", source_date_url=OfficialRankingProvider.ATP_UTS_DATE_URL,
                          source_date_sha256="a"*64)
    conn.execute("UPDATE raw_api_responses SET response_json=? WHERE id=1", (json.dumps(body),))
    assert RankingReader(conn).select(1, "2026-10-29")["rank"] == 9
    conn.execute("UPDATE rankings_history SET ranking_date='2026-10-29' WHERE id=1")
    assert RankingReader(conn).select(1, "2026-10-30")["rank"] == 333


def test_unknown_opponent_never_reads_another_players_ranking():
    assert RankingReader(connection()).select(None, "2026-10-29", inclusive=True)["rank"] is None


def test_opponent_lookup_preserves_on_or_before_cutoff_and_source_guard(monkeypatch):
    from tennis_wc.features import opponent_rank_buckets as module
    conn = connection()
    assert RankingReader(conn).select(1, "2026-10-26")["rank"] is None
    assert RankingReader(conn).select(1, "2026-10-26", inclusive=True)["rank"] == 333
    monkeypatch.setattr(module, "get_connection", lambda: conn)
    assert module.get_opponent_rank_at_match_date(1, date(2026, 10, 28)) == 333


def test_native_rank_refresh_preserves_genuine_elo_and_replaces_only_known_bad_prior(monkeypatch):
    from tennis_wc.ingestion import ingest_rankings as module
    conn = connection()
    reader = RankingReader(conn)
    monkeypatch.setattr(module, "existing_player_id", lambda *a: 1)
    row = {"player_id": "uts:1", "player_name": "Alpha Player", "tour": "ATP", "rank": 333,
           "ranking_date": "2026-10-29"}
    assert module._safe_rank_seed("composite", row, reader) == module._rank_seed_elo(333)
    conn.execute("UPDATE players SET overall_elo=1912.123456")
    assert module._safe_rank_seed("composite", row, reader) is None
    conn.execute("UPDATE players SET overall_elo=?", (module._rank_seed_elo(9),))
    conn.execute("CREATE TABLE player_elo_history(player_id INTEGER,surface TEXT,as_of_date TEXT)")
    conn.execute("INSERT INTO player_elo_history VALUES (1,'','2026-10-25')")
    assert module._safe_rank_seed("composite", row, reader) is None


def test_ingestion_preserves_rejected_rows_and_only_refreshes_safe_cache(tmp_path, monkeypatch):
    from conftest import configure_test_db
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.db import get_connection
    from tennis_wc.database.migrations import init_db
    from tennis_wc.ingestion import ingest_rankings as module
    from tennis_wc.ingestion.entity_mapping import get_or_create_player
    from tennis_wc.ingestion.raw_response_store import store_raw_response
    init_db()
    old = [{"player_id": "uts:1", "player_name": "Alpha Player", "tour": "ATP", "rank": 9,
            "ranking_date": "2026-10-28", "raw": {"source": "ultimate_tennis_statistics"}}]
    raw_id = store_raw_response("composite", "/rankings", {}, old, 200, "ranking", "ATP")
    pid = get_or_create_player("composite", "uts:1", "Alpha Player", "ATP", raw_id,
                               current_rank=9, overall_elo=module._rank_seed_elo(9))
    good_id = store_raw_response("tennismylife_history", "/matches", {}, {}, 200, "match_history", "ATP")
    with get_connection() as conn:
        for day,rank,provider,rid in [("2026-10-28",9,"composite",raw_id),
                                       ("2026-10-26",333,"tennismylife_history",good_id)]:
            conn.execute("INSERT INTO rankings_history(player_id,ranking_date,tour,rank,source_provider,raw_response_id,created_at) VALUES (?,?,'ATP',?,?,?,'2026-10-29')",
                         (pid,day,rank,provider,rid))
    rejected = [{**old[0], "ranking_date": "2024-12-30"}]
    provider = SimpleNamespace(provider_name="composite", fetch_rankings=lambda *a: rejected,
                               ranking_source_evidence=[{"url": "date-endpoint", "text": '"2024-12-30"'}])
    monkeypatch.setattr(module, "get_tennis_provider", lambda: provider)
    assert module.ingest_rankings("ATP", "2026-10-29") == 1
    assert module.rankings_cache_fallback("ATP")["cached_latest_ranking_date"] == "2026-10-26"
    with get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM rankings_history").fetchone()[0] == 2
        player = conn.execute("SELECT * FROM players WHERE id=?", (pid,)).fetchone()
        assert player["current_rank"] == 333 and player["raw_response_id"] == raw_id
        assert RankingReader(conn).unverified_seed(player, module._rank_seed_elo)
        evidence = conn.execute("SELECT status_code,response_json FROM raw_api_responses WHERE entity_type='ranking_source_evidence'").fetchone()
        assert evidence[0] == 206 and json.loads(evidence[1])["rejected_rows"] == rejected
        assert json.loads(conn.execute("SELECT response_json FROM raw_api_responses WHERE id=?", (raw_id,)).fetchone()[0]) == old


def test_official_pdf_ingest_links_capture_and_preserves_old_same_day_history(tmp_path, monkeypatch):
    from conftest import configure_test_db
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.db import get_connection
    from tennis_wc.database.migrations import init_db
    from tennis_wc.ingestion import ingest_rankings as module
    from tennis_wc.ingestion.entity_mapping import get_or_create_player
    from tennis_wc.ingestion.raw_response_store import store_raw_response
    init_db()
    legacy = [{"player_id": "uts:1", "player_name": "Alpha Player", "tour": "ATP", "rank": 9,
               "ranking_date": "2026-10-26", "raw": {"source": "ultimate_tennis_statistics"}}]
    old_raw = store_raw_response("composite", "/rankings", {}, legacy, 200, "ranking", "ATP")
    pid = get_or_create_player("composite", "uts:1", "Alpha Player", "ATP", old_raw,
                               current_rank=9, overall_elo=1900.0)
    with get_connection() as conn:
        conn.execute("INSERT INTO rankings_history(player_id,ranking_date,tour,rank,source_provider,raw_response_id,created_at) VALUES (?,'2026-10-26','ATP',9,'composite',?,'2026-10-29')", (pid, old_raw))
        original = tuple(conn.execute("SELECT * FROM rankings_history").fetchone())
    pdf = b"official PDF bytes"
    sha = hashlib.sha256(pdf).hexdigest()
    row = {"player_id": "atp_pdf:alpha-player", "player_name": "Alpha Player", "tour": "ATP", "rank": 200,
           "ranking_date": "2026-10-26", "raw": {"source": "atp_official_numeric_pdf",
           "source_ranking_date": "2026-10-26", "source_url": OfficialRankingProvider.ATP_NUMERIC_PDF_URL,
           "source_pdf_sha256": sha}}
    provider = SimpleNamespace(provider_name="composite", fetch_rankings=lambda *a: [row],
        ranking_source_evidence=[{"url": OfficialRankingProvider.ATP_NUMERIC_PDF_URL, "sha256": sha,
                                  "content_base64": base64.b64encode(pdf).decode()}])
    monkeypatch.setattr(module, "get_tennis_provider", lambda: provider)
    assert module.ingest_rankings("ATP", "2026-10-29") == 1
    assert "source_capture_raw_id" not in row["raw"]
    with get_connection() as conn:
        assert tuple(conn.execute("SELECT * FROM rankings_history WHERE source_provider='composite'").fetchone()) == original
        assert conn.execute("SELECT COUNT(*) FROM rankings_history").fetchone()[0] == 2
        selected = RankingReader(conn).select(pid, "2026-10-29")
        assert selected["rank"] == 200 and selected["source_provider"] == "atp_official_numeric_pdf"
        assert conn.execute("SELECT overall_elo FROM players WHERE id=?", (pid,)).fetchone()[0] == 1900.0
        normalized = json.loads(conn.execute("SELECT response_json FROM raw_api_responses WHERE id=?", (selected["raw_response_id"],)).fetchone()[0])
        assert normalized[0]["raw"]["source_capture_raw_id"] != old_raw


def test_rank_insert_failure_rolls_back_player_and_identity_update(tmp_path, monkeypatch):
    from conftest import configure_test_db
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.db import get_connection
    from tennis_wc.database.migrations import init_db
    from tennis_wc.ingestion import ingest_rankings as module
    from tennis_wc.ingestion.entity_mapping import get_or_create_player
    init_db()
    player_id = get_or_create_player("feed", "alpha", "Alpha Player", "ATP", 1,
                                     current_rank=88, overall_elo=1900.0)
    with get_connection() as conn:
        before = tuple(conn.execute("SELECT * FROM players WHERE id=?", (player_id,)).fetchone())
        mappings_before = [tuple(r) for r in conn.execute("SELECT * FROM provider_entities ORDER BY id")]
        conn.execute("""CREATE TRIGGER fail_ranking BEFORE INSERT ON rankings_history
                        BEGIN SELECT RAISE(ABORT,'injected ranking write failure'); END""")
    row = {"player_id": "alpha-new", "player_name": "Alpha Player", "tour": "ATP", "rank": 12,
           "ranking_date": "2026-10-26", "raw": {}}
    monkeypatch.setattr(module, "get_tennis_provider", lambda: SimpleNamespace(
        provider_name="feed", fetch_rankings=lambda *a: [row]))
    with pytest.raises(sqlite3.IntegrityError, match="injected ranking write failure"):
        module.ingest_rankings("ATP", "2026-10-29")
    with get_connection() as conn:
        assert tuple(conn.execute("SELECT * FROM players WHERE id=?", (player_id,)).fetchone()) == before
        assert [tuple(r) for r in conn.execute("SELECT * FROM provider_entities ORDER BY id")] == mappings_before
        assert conn.execute("SELECT COUNT(*) FROM rankings_history").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM raw_api_responses WHERE endpoint='/rankings'").fetchone()[0] == 1


def test_sackmann_cutoff_does_not_pick_a_future_week_or_drop_rank_501_onward(monkeypatch):
    from tennis_wc.providers.sackmann_ranking_provider import SackmannRankingProvider
    provider = SackmannRankingProvider()
    assert provider._latest_ranking_date([{"ranking_date": "20261026"}], "2026-10-01") is None
    provider._player_cache["ATP"] = {str(i): f"Player Number {i}" for i in range(1, 602)}
    csv = "ranking_date,ranking,player,points\n" + "\n".join(f"20261026,{i},{i},10" for i in range(1, 602))
    monkeypatch.setattr(provider, "_fetch_csv_text", lambda *a, **k: csv)
    rows = provider.fetch_rankings("ATP", "2026-10-29")
    assert len(rows) == 601 and rows[-1]["rank"] == 601


def test_mutable_seed_with_rejected_receipt_cannot_bypass_rank_guard_after_cache_update():
    from tennis_wc.features.feature_builder import _unverified_rank_seed
    conn = connection()
    conn.execute("UPDATE players SET current_rank=333")
    player = conn.execute("SELECT * FROM players WHERE id=1").fetchone()
    assert _unverified_rank_seed(conn, 1, player)
    conn.execute("UPDATE players SET overall_elo=1823.712345")
    assert not _unverified_rank_seed(conn, 1, conn.execute("SELECT * FROM players").fetchone())


@pytest.mark.parametrize("as_of_elo,expected", [(None, None), (1900.0, 1900.0)])
def test_feature_wiring_uses_rank_source_and_preserves_real_asof_elo(monkeypatch, as_of_elo, expected):
    from tennis_wc.features import feature_builder as fb
    conn = connection()
    for name in ("calculate_player_rank_bucket_stats", "calculate_player_elo_bucket_stats",
                 "calculate_tournament_level_stats", "calculate_round_stats", "calculate_big_match_stats",
                 "calculate_bo_format_stats", "calculate_pressure_stats", "calculate_head_to_head_stats"):
        monkeypatch.setattr(fb, name, lambda *a, **k: {})
    monkeypatch.setattr(fb, "_raw_meta", lambda raw_id: {"source_provider": "source", "source_endpoint": "/rankings",
                                                       "raw_response_id": raw_id, "warnings": []})
    monkeypatch.setattr(fb, "_latest_history_prov", lambda *a: {})
    monkeypatch.setattr(fb, "_rest_days", lambda *a, **k: None)
    monkeypatch.setattr(fb, "_elo_as_of", lambda *a: (as_of_elo, as_of_elo, as_of_elo is not None))
    context = {k: {"value": v} for k, v in {"surface": "hard", "level": "ATP_250", "round": "R1", "format": "BO3"}.items()}
    payload = fb._build_player_payload(conn, 1, 2, context, date(2026, 10, 29), persist_derived=False)
    assert payload["current_rank"]["value"] == 333
    assert payload["current_rank"]["provenance"]["raw_response_id"] == 2
    assert payload["current_rank"]["provenance"]["ranking_date"] == "2026-10-26"
    assert payload["overall_elo"]["value"] == expected


def test_current_rank_staleness_uses_effective_date_not_recent_fetch_clock(monkeypatch):
    from tennis_wc.features import data_quality as dq
    monkeypatch.setattr(dq, "assert_no_llm_generated_stats", lambda *a: None)
    effective = "2020-01-06"
    now = datetime.now(timezone.utc)
    snapshot = {"match_context": {"match_date": (now.date()+timedelta(days=1)).isoformat(), "surface": "hard", "level": "ATP_250", "round": "R1"},
                "player_a": {"current_rank": {"value": 9, "provenance": {"source_timestamp": now.isoformat(),
                                            "source_provider": "feed", "ranking_date": effective}}}}
    assert "stale ranking data at player_a.current_rank" in dq.validate_data_freshness(snapshot)["warnings"]
