from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from conftest import configure_test_db


def test_feature_without_provenance_fails(tmp_path, monkeypatch):
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.features.data_quality import assert_no_llm_generated_stats

    snapshot = {"feature": {"value": 0.55, "provenance": None}}
    with pytest.raises(ValueError, match="missing provenance"):
        assert_no_llm_generated_stats(snapshot)


def test_llm_source_provider_fails(tmp_path, monkeypatch):
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.features.data_quality import assert_no_llm_generated_stats

    snapshot = {"feature": {"value": 0.55, "provenance": {"source_provider": "llm"}}}
    with pytest.raises(ValueError, match="LLM-generated"):
        assert_no_llm_generated_stats(snapshot)


def test_missing_odds_source_fails(tmp_path, monkeypatch):
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.features.data_quality import validate_data_freshness

    snapshot = {
        "match_context": {"match_date": "2026-05-08", "surface": {"value": "Clay"}, "level": {"value": "ATP_1000"}},
        "market": {"player_a_odds": {"value": 2.0, "provenance": None}},
    }
    result = validate_data_freshness(snapshot)
    assert not result["is_valid"]
    assert any("missing odds provenance" in error or "missing provenance" in error for error in result["errors"])


def test_stale_odds_fails(tmp_path, monkeypatch):
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.features.common import datapoint, provenance
    from tennis_wc.features.data_quality import validate_data_freshness

    # Today's fixture, priced two hours ago: genuinely stale.
    today = datetime.now(timezone.utc)
    old = (today - timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    prov = provenance("mock", "/mock/odds", old, 1)
    snapshot = {
        "match_context": {"match_date": today.date().isoformat(),
                          "surface": {"value": "Clay"}, "level": {"value": "ATP_1000"}},
        "market": {"player_a_odds": datapoint(2.0, prov), "player_b_odds": datapoint(1.8, prov)},
    }
    result = validate_data_freshness(snapshot)
    assert not result["is_valid"]
    assert any("stale odds" in error for error in result["errors"])


def test_backfilled_snapshot_is_judged_against_its_match_not_the_clock(tmp_path, monkeypatch):
    """Rebuilding a May snapshot today must not mark May's odds as stale.

    Every one of the 3,622 snapshots rebuilt on 2026-08-09 scored zero because
    each odds datapoint tripped the wall-clock staleness check, four errors
    floor the score, and derived props are gated off below 65 -- the replay
    fell from 1,133 settled bets to 108 on data that had not changed.
    """
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.features.common import datapoint, provenance
    from tennis_wc.features.data_quality import validate_data_freshness

    # Odds captured the morning of a match three months ago.
    prov = provenance("mock", "/mock/odds", "2026-05-08T09:00:00Z", 1)
    snapshot = {
        "match_context": {"match_date": "2026-05-08", "surface": {"value": "Clay"},
                          "level": {"value": "ATP_1000"}, "round": {"value": "R16"}},
        "market": {"player_a_odds": datapoint(2.0, prov), "player_b_odds": datapoint(1.8, prov)},
    }
    result = validate_data_freshness(snapshot)

    assert not any("stale odds" in error for error in result["errors"]), result["errors"]
    assert result["score"] >= 65


def test_missing_historical_ranking_downgrades_confidence(tmp_path, monkeypatch):
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.features.common import datapoint, provenance
    from tennis_wc.features.data_quality import validate_data_freshness

    prov = provenance("mock", "/mock/historical-matches", datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), 1)
    prov["warnings"] = ["missing_historical_rank"]
    snapshot = {
        "match_context": {"match_date": "2026-05-08", "surface": {"value": "Clay"}, "level": {"value": "ATP_1000"}},
        "market": {"player_a_odds": datapoint(2.0, prov), "player_b_odds": datapoint(1.8, prov)},
        "player_a": {"opponent_rank_buckets": {"TOP_50": {"win_rate": datapoint(0.5, prov)}}},
    }
    result = validate_data_freshness(snapshot)
    assert result["score"] < 100
    assert any("missing_historical_rank" in warning for warning in result["warnings"])


def test_final_decision_no_bet_when_provenance_invalid(tmp_path, monkeypatch):
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.features.data_quality import validate_data_freshness

    snapshot = {
        "match_context": {"match_date": "2026-05-08", "surface": {"value": "Clay"}, "level": {"value": "ATP_1000"}},
        "market": {"player_a_odds": {"value": 2.0, "provenance": {"source_provider": "llm"}}},
    }
    result = validate_data_freshness(snapshot)
    decision = "NO_BET" if not result["is_valid"] else "BET"
    assert decision == "NO_BET"


def test_a_snapshot_rebuilt_the_morning_after_its_match_is_not_stale(tmp_path, monkeypatch):
    """The first threshold was two days, which failed yesterday's fixtures.

    Those are exactly the matches the daily card is built from: on 2026-08-08
    all 47 priced matches scored 0, every derived family lost its value flag,
    and the gate could be open while the card still printed nothing.
    """
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.features.common import datapoint, provenance
    from tennis_wc.features.data_quality import validate_data_freshness

    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date()
    prov = provenance("mock", "/mock/odds", f"{yesterday}T09:00:00Z", 1)
    snapshot = {
        "match_context": {"match_date": yesterday.isoformat(),
                          "surface": {"value": "Hard"},
                          "level": {"value": "ATP_1000"}, "round": {"value": "R32"}},
        "market": {"player_a_odds": datapoint(1.8, prov), "player_b_odds": datapoint(2.0, prov)},
    }
    result = validate_data_freshness(snapshot)

    assert not any("stale odds" in error for error in result["errors"]), result["errors"]
    assert result["score"] >= 65
