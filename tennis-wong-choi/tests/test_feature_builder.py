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


def test_odds_coverage_excludes_placeholder_and_duplicate_fixture_rows(tmp_path, monkeypatch):
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.features.feature_builder import odds_coverage_for_date

    init_db()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO tournaments (id,name,tour,external_id,source_provider,created_at,updated_at) "
            "VALUES (1,'Open','ATP','T1','test','now','now')"
        )
        for pid, name in (
            (1, "Real A"),
            (2, "Real B"),
            (3, "Real A"),
            (4, "Real B"),
            (5, "Unknown Player"),
        ):
            conn.execute(
                "INSERT INTO players (id,name,tour,source_provider,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?)",
                (pid, name, "ATP", "test", "now", "now"),
            )
        for mid, a, b in (
            (1, 1, 2),  # canonical real fixture
            (2, 3, 4),  # same names from another provider
            (3, 5, 5),  # old placeholder poison
        ):
            conn.execute(
                """INSERT INTO matches
                   (id,provider_match_id,tour,match_date,tournament_id,player_a_id,
                    player_b_id,round,source_provider,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (mid, f"M{mid}", "ATP", "2026-07-30", 1, a, b, "R1", "test", "now", "now"),
            )
        conn.execute(
            """INSERT INTO odds_snapshots
               (event_id,match_id,bookmaker,market,player_a_odds,player_b_odds,
                source_provider,raw_response_id,fetched_at,created_at)
               VALUES ('E1',1,'Sportsbet','match_winner',1.8,2.0,'sportsbet',0,'now','now')"""
        )
        conn.commit()

    coverage = odds_coverage_for_date("2026-07-30")
    assert coverage["fixtures"] == 1
    assert coverage["priced_matches"] == 1
    assert coverage["priced_ratio"] == 1.0


def test_odds_coverage_reports_the_sportsbet_book_separately(tmp_path, monkeypatch):
    """The 2026-08-24 shape, in miniature.

    Two fixtures come from Sportsbet's own listing (one priced, one not) and
    three come from the ESPN fixture feed for a tournament Sportsbet has no
    market on -- a Grand Slam qualifying draw. The calendar ratio reads 1/5 and
    would block the card; the book ratio reads 1/2, which is what "has the book
    opened" actually asks. A composite fixture that Sportsbet HAS priced counts
    in the book, because a market existing is the whole test.
    """
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.features.feature_builder import odds_coverage_for_date

    init_db()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO tournaments (id,name,tour,external_id,source_provider,created_at,updated_at) "
            "VALUES (1,'Open','ATP','T1','test','now','now')"
        )
        for pid in range(1, 13):
            conn.execute(
                "INSERT INTO players (id,name,tour,source_provider,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?)",
                (pid, f"Player {pid}", "ATP", "test", "now", "now"),
            )
        rows = (
            (1, 1, 2, "sportsbet"),   # listed and priced
            (2, 3, 4, "sportsbet"),   # listed, not priced yet
            (3, 5, 6, "composite"),   # ESPN-only: no Sportsbet market at all
            (4, 7, 8, "composite"),   # ESPN-only
            (5, 9, 10, "composite"),  # ESPN-only
        )
        for mid, a, b, provider in rows:
            conn.execute(
                """INSERT INTO matches
                   (id,provider_match_id,tour,match_date,tournament_id,player_a_id,
                    player_b_id,round,source_provider,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (mid, f"M{mid}", "ATP", "2026-08-24", 1, a, b, "R1", provider, "now", "now"),
            )
        conn.execute(
            """INSERT INTO odds_snapshots
               (event_id,match_id,bookmaker,market,player_a_odds,player_b_odds,
                source_provider,raw_response_id,fetched_at,created_at)
               VALUES ('E1',1,'Sportsbet','match_winner',1.8,2.0,'sportsbet',0,'now','now')"""
        )
        conn.commit()

    coverage = odds_coverage_for_date("2026-08-24")
    assert coverage["fixtures"] == 5
    assert coverage["book_fixtures"] == 2
    assert coverage["priced_matches"] == 1
    assert coverage["priced_ratio"] == 0.2
    assert coverage["book_priced_ratio"] == 0.5


def test_book_fixtures_includes_a_composite_fixture_sportsbet_priced(tmp_path, monkeypatch):
    """Provenance is not the test -- a market is. A fixture ESPN saw first and
    Sportsbet later priced is in the book, and counting it only in the numerator
    would put the ratio above 1.0."""
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.features.feature_builder import odds_coverage_for_date

    init_db()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO tournaments (id,name,tour,external_id,source_provider,created_at,updated_at) "
            "VALUES (1,'Open','ATP','T1','test','now','now')"
        )
        for pid in (1, 2):
            conn.execute(
                "INSERT INTO players (id,name,tour,source_provider,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?)",
                (pid, f"Player {pid}", "ATP", "test", "now", "now"),
            )
        conn.execute(
            """INSERT INTO matches
               (id,provider_match_id,tour,match_date,tournament_id,player_a_id,
                player_b_id,round,source_provider,created_at,updated_at)
               VALUES (1,'M1','ATP','2026-08-24',1,1,2,'R1','composite','now','now')"""
        )
        conn.execute(
            """INSERT INTO odds_snapshots
               (event_id,match_id,bookmaker,market,player_a_odds,player_b_odds,
                source_provider,raw_response_id,fetched_at,created_at)
               VALUES ('E1',1,'Sportsbet','match_winner',1.8,2.0,'sportsbet',0,'now','now')"""
        )
        conn.commit()

    coverage = odds_coverage_for_date("2026-08-24")
    assert coverage["book_fixtures"] == 1
    assert coverage["priced_matches"] == 1
    assert coverage["book_priced_ratio"] == 1.0


def test_priced_matches_dedupes_the_same_way_fixtures_does(tmp_path, monkeypatch):
    """Two providers describing one match is one fixture in the denominator, so
    it has to be one in the numerator too. `COUNT(DISTINCT match_id)` counted it
    twice, which could put the ratio above 1.0 and hide a thin book."""
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.features.feature_builder import odds_coverage_for_date

    init_db()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO tournaments (id,name,tour,external_id,source_provider,created_at,updated_at) "
            "VALUES (1,'Open','ATP','T1','test','now','now')"
        )
        for pid, name in ((1, "Real A"), (2, "Real B"), (3, "Real A"), (4, "Real B")):
            conn.execute(
                "INSERT INTO players (id,name,tour,source_provider,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?)",
                (pid, name, "ATP", "test", "now", "now"),
            )
        for mid, a, b in ((1, 1, 2), (2, 3, 4)):
            conn.execute(
                """INSERT INTO matches
                   (id,provider_match_id,tour,match_date,tournament_id,player_a_id,
                    player_b_id,round,source_provider,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (mid, f"M{mid}", "ATP", "2026-08-24", 1, a, b, "R1", "sportsbet", "now", "now"),
            )
            conn.execute(
                """INSERT INTO odds_snapshots
                   (event_id,match_id,bookmaker,market,player_a_odds,player_b_odds,
                    source_provider,raw_response_id,fetched_at,created_at)
                   VALUES (?,?,'Sportsbet','match_winner',1.8,2.0,'sportsbet',0,'now','now')""",
                (f"E{mid}", mid),
            )
        conn.commit()

    coverage = odds_coverage_for_date("2026-08-24")
    assert coverage["fixtures"] == 1
    assert coverage["priced_matches"] == 1
    assert coverage["priced_ratio"] == 1.0
    assert coverage["book_priced_ratio"] == 1.0
