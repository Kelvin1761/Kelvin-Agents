from __future__ import annotations

from datetime import date

from conftest import configure_test_db


def _seed(tmp_path, monkeypatch):
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.store.migrations import init_db
    from tennis_wc.sources.ingest_matches import ingest_default_history
    from tennis_wc.sources.ingest_rankings import ingest_rankings

    init_db()
    ingest_rankings("ATP", "2026-05-08")
    ingest_default_history("2026-05-08")


def test_opponent_rank_buckets_are_nested_and_shrinked(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    from tennis_wc.sources.entity_mapping import get_internal_entity_id
    from tennis_wc.model.features.opponent_rank_buckets import calculate_player_rank_bucket_stats

    player_id = get_internal_entity_id("mock", "player", "mock-a")
    stats = calculate_player_rank_bucket_stats(player_id, "Hard", date(2026, 5, 8), "LAST_52_WEEKS")
    assert stats["TOP_50"]["matches"] >= stats["TOP_25"]["matches"]
    assert "shrinked_win_rate" in stats["TOP_50"]
    assert stats["TOP_50"]["sample_size"] == stats["TOP_50"]["matches"]
