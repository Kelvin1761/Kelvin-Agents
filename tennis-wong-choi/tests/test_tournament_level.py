from __future__ import annotations

from datetime import date

from conftest import configure_test_db


def test_tournament_level_stats_unknown_downgrades(tmp_path, monkeypatch):
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.features.tournament_level import calculate_tournament_level_stats

    init_db()
    result = calculate_tournament_level_stats(1, "UNKNOWN", "Clay", date(2026, 5, 8), "LAST_52_WEEKS")
    assert result["warnings"] == ["unknown_tournament_level"]
    assert result["win_rate"] is None


def test_tournament_level_stats_from_mock_history(tmp_path, monkeypatch):
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.ingestion.entity_mapping import get_internal_entity_id
    from tennis_wc.ingestion.ingest_matches import ingest_default_history
    from tennis_wc.ingestion.ingest_rankings import ingest_rankings
    from tennis_wc.features.tournament_level import calculate_tournament_level_stats

    init_db()
    ingest_rankings("ATP", "2026-05-08")
    ingest_default_history("2026-05-08")
    player_id = get_internal_entity_id("mock", "player", "mock-a")
    result = calculate_tournament_level_stats(player_id, "ATP_1000", "Hard", date(2026, 5, 8), "LAST_52_WEEKS")
    assert result["matches"] > 0
    assert "shrinked_win_rate" in result
