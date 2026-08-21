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


def test_the_tier_rail_reads_the_level_not_the_display_name():
    """65.8% of TOUR-labelled value bets are on events with no real name.

    Audited 2026-08-11 over every fixture since 2026-05-10: the biggest sources
    of staked bets on the board are called `888-2026` (320 value bets) and
    `188-2026` (232), and the old rule called them TOUR purely because the
    string did not contain "ITF". `tournament_levels.level` knows they are
    ATP_500 and GRAND_SLAM.

    The two rules agree on zero value bets' worth of disagreement wherever the
    level is known, so this changes nothing today. It changes which field is
    load-bearing, and a rail that holds because a string lacked a substring is
    not a rail -- it is the only thing between the model and ITF, which the
    audit measured at Brier +0.0492 worse than the market with P = 0.000.
    """
    from tennis_wc.props.daily import _tier_bettable, _tier_of

    # A name that says nothing; the level says everything.
    assert _tier_of("888-2026", "ATP_500") == "TOUR"
    assert _tier_of("188-2026", "GRAND_SLAM") == "TOUR"
    assert _tier_of("1234-2026", "CHALLENGER") == "CHALLENGER"

    # The level wins over a misleading name, in the direction that protects us.
    assert _tier_of("Some Open", "ITF_M15") == "ITF"
    assert _tier_bettable("Some Open", "ITF_M15") is False

    # No level: fall back to the name, unchanged behaviour.
    assert _tier_of("ITF Cairo", None) == "ITF"
    assert _tier_of("ATP Umag", None) == "TOUR"
    assert _tier_of("Challenger Prague", "UNKNOWN") == "CHALLENGER"

    # Neither: never TOUR. An event nothing places must not be staked, and a
    # bare external id in the name column places nothing.
    assert _tier_of(None, None) == "UNKNOWN"
    assert _tier_bettable(None, None) is False
    assert _tier_of("888-2026", None) == "UNKNOWN"
    assert _tier_of("888-2026", "UNKNOWN") == "UNKNOWN"
    assert _tier_bettable("888-2026", None) is False
