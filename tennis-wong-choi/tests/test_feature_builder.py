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


# --------------------------------------------------------------------------- #
# One unbuildable match must not blind us to the rest (2026-07-25)
# --------------------------------------------------------------------------- #
def _seed_priced_match(conn, mid, tourn_name, tourn_id, *, tour="ATP"):
    conn.execute("INSERT OR IGNORE INTO tournaments (id, name, tour, external_id,"
                 " source_provider, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                 (tourn_id, tourn_name, tour, f"T{tourn_id}", "test", "now", "now"))
    for pid, name in ((mid * 10 + 1, f"A{mid}"), (mid * 10 + 2, f"B{mid}")):
        conn.execute("INSERT OR IGNORE INTO players (id, name, tour, source_provider, created_at, updated_at)"
                     " VALUES (?,?,?,?,?,?)", (pid, name, tour, "test", "now", "now"))
    conn.execute("""INSERT INTO matches (id, provider_match_id, tour, match_date, tournament_id,
                        player_a_id, player_b_id, round, source_provider, created_at, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                 (mid, f"M{mid}", tour, "2026-07-25", tourn_id, mid * 10 + 1, mid * 10 + 2,
                  "R1", "test", "now", "now"))
    conn.execute("""INSERT INTO odds_snapshots (event_id, match_id, bookmaker, market,
                        player_a_odds, player_b_odds, source_provider, raw_response_id,
                        fetched_at, created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?)""",
                 (f"E{mid}", mid, "Sportsbet", "match_winner", 1.8, 2.0, "sportsbet", 0,
                  "now", "now"))


def test_one_unbuildable_match_does_not_abort_the_date(tmp_path, monkeypatch):
    """The builder used to be a bare list comprehension, so the FIRST match that
    raised (e.g. tournament metadata missing) dropped every remaining match for
    the date -- silently. The report just showed a smaller 已分析 count."""
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.features import feature_builder as fb

    init_db()
    with get_connection() as conn:
        _seed_priced_match(conn, 9001, "Bad Open", 7001)
        _seed_priced_match(conn, 9002, "Good Open", 7002)
        _seed_priced_match(conn, 9003, "Also Good Open", 7003)
        conn.commit()

    # the lowest match id blows up -- exactly the case that used to kill the loop
    real = fb.build_match_feature_snapshot

    def flaky(match_id):
        if match_id == 9001:
            raise ValueError("Tournament metadata missing for match 9001")
        return {"match_id": match_id}

    monkeypatch.setattr(fb, "build_match_feature_snapshot", flaky)
    skipped = []
    snaps = fb.build_sportsbet_feature_snapshots_for_date("2026-07-25", skipped=skipped)

    built = {s["match_id"] for s in snaps}
    assert built == {9002, 9003}, "matches after the failure must still be built"
    assert len(skipped) == 1
    assert skipped[0]["match_id"] == 9001
    assert "Tournament metadata missing" in skipped[0]["reason"]
    assert real is not None  # keep the reference used, silences lint


def test_doubles_skips_are_recorded_not_just_dropped(tmp_path, monkeypatch):
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.features import feature_builder as fb

    init_db()
    with get_connection() as conn:
        _seed_priced_match(conn, 9101, "ATP Somewhere Doubles", 7101)
        conn.commit()
    monkeypatch.setattr(fb, "build_match_feature_snapshot", lambda mid: {"match_id": mid})
    skipped = []
    snaps = fb.build_sportsbet_feature_snapshots_for_date("2026-07-25", skipped=skipped)
    assert snaps == []
    assert [s["reason"] for s in skipped] == ["doubles_competition"]


def test_feature_build_coverage_reports_the_gap(tmp_path, monkeypatch):
    """The gap was invisible: 60 priced matches, 38 analysed, nothing said so."""
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.features.feature_builder import feature_build_coverage

    init_db()
    with get_connection() as conn:
        _seed_priced_match(conn, 9201, "Big Open", 7201)
        _seed_priced_match(conn, 9202, "Big Open", 7201)
        _seed_priced_match(conn, 9203, "ATP Pairs Doubles", 7203)
        # only ONE of the two singles matches ever produced a snapshot
        conn.execute("""INSERT INTO feature_snapshots (match_id, player_id, feature_set_version,
                            features_json, provenance_json, data_quality_score, created_at)
                        VALUES (?,?,?,?,?,?,?)""",
                     (9201, 92011, "v1", "{}", "{}", 80, "now"))
        conn.commit()

    cov = feature_build_coverage("2026-07-25")
    assert cov["priced_matches"] == 3
    assert cov["doubles_excluded"] == 1
    assert cov["singles_candidates"] == 2
    assert cov["with_features"] == 1
    assert cov["missing_features"] == 1
    assert cov["missing_by_tournament"] == {"Big Open": 1}
