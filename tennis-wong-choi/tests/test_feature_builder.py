from __future__ import annotations

from conftest import configure_test_db


def test_run_daily_builds_valid_mock_feature_snapshot(tmp_path, monkeypatch):
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.features.feature_builder import build_feature_snapshots_for_date
    from tennis_wc.ingestion.ingest_matches import ingest_default_history, ingest_upcoming_matches
    from tennis_wc.ingestion.ingest_odds import ingest_odds
    from tennis_wc.ingestion.ingest_rankings import ingest_rankings
    from tennis_wc.ingestion.ingest_tournaments import ingest_tournaments

    init_db()
    ingest_tournaments("2026-05-08", "2026-05-08")
    ingest_rankings("ATP", "2026-05-08")
    ingest_default_history("2026-05-08")
    ingest_upcoming_matches("2026-05-08")
    ingest_odds("2026-05-08")
    snapshots = build_feature_snapshots_for_date("2026-05-08")
    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert "opponent_rank_buckets" in snapshot["player_a"]
    assert "tournament_level_stats" in snapshot["player_a"]
    assert "round_stats" in snapshot["player_a"]
    assert snapshot["data_quality"]["is_valid"]
