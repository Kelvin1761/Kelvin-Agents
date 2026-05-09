from __future__ import annotations

from datetime import date

from conftest import configure_test_db


def test_round_normalisation():
    from tennis_wc.features.round_performance import normalise_round

    assert normalise_round("Quarter Final") == "QF"
    assert normalise_round("Round of 32") == "R32"
    assert normalise_round("Something Else") == "UNKNOWN"


def test_round_stats_from_mock_history(tmp_path, monkeypatch):
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.ingestion.entity_mapping import get_internal_entity_id
    from tennis_wc.ingestion.ingest_matches import ingest_default_history
    from tennis_wc.ingestion.ingest_rankings import ingest_rankings
    from tennis_wc.features.round_performance import calculate_round_stats

    init_db()
    ingest_rankings("ATP", "2026-05-08")
    ingest_default_history("2026-05-08")
    player_id = get_internal_entity_id("mock", "player", "mock-a")
    result = calculate_round_stats(player_id, "Quarter Final", "ATP_1000", "Hard", date(2026, 5, 8), "LAST_52_WEEKS")
    assert result["round"] == "QF"
    assert result["matches"] >= 0
