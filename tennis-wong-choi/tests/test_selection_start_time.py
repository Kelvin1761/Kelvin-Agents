"""A recommendation you cannot place is not a recommendation.

Measured on 2026-08-16: 35.9% of the matches on a pushed card had already
started, and 42.3% were unplaceable once an hour's notice was required. The
cause is structural rather than a tuning slip -- ``match_date`` is the Sydney
calendar date and the card went out at 09:24 Sydney, so the first nine hours of
every day were gone before anyone was told. Nothing in the report or betting
layer read ``start_time_utc`` at all.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tennis_wc.props import selection


NOW = datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)


def _leg(identifier, match_id, start, ev=0.20, odds=1.80):
    return {
        "id": identifier,
        "match_id": match_id,
        "market_key": "total_player_aces_5_5",
        "family": "player_aces",
        "prob": 0.62,
        "data_quality": 0.90,
        "odds": odds,
        "edge": 0.07,
        "ev": ev,
        "start_time_utc": start,
    }


def _picks(legs, now=NOW):
    # An open gate: this suite is about the start-time filter, not the
    # evidence gate, so every leg must be a formal candidate on its own.
    gate = {"enabled_families": ["player_aces"]}
    return selection.recommended_picks(
        {"strategy": gate, "value_legs": legs, "combos": []}, now=now
    )


def _stamp(minutes_from_now, suffix="Z"):
    moment = NOW + timedelta(minutes=minutes_from_now)
    return moment.strftime("%Y-%m-%dT%H:%M:%S") + suffix


def test_a_match_already_under_way_is_dropped():
    picks = _picks([_leg("a", 1, _stamp(-30))])
    assert picks["validated_singles"] == []
    assert [leg["id"] for leg in picks["dropped_already_started"]] == ["a"]


def test_a_match_starting_in_minutes_is_dropped_too():
    """You cannot place a bet in the three minutes before the first serve."""
    picks = _picks([_leg("a", 1, _stamp(3))])
    assert picks["validated_singles"] == []
    assert [leg["id"] for leg in picks["dropped_already_started"]] == ["a"]


def test_a_match_with_real_lead_time_survives():
    picks = _picks([_leg("a", 1, _stamp(240))])
    assert [leg["id"] for leg in picks["validated_singles"]] == ["a"]
    assert picks["dropped_already_started"] == []


def test_an_unpublished_start_time_is_not_treated_as_started():
    """Only 27-63% of fixtures carry a start time. Dropping the unknowns would
    throw away most of the card to fix a third of it."""
    for missing in (None, "", 0):
        picks = _picks([_leg("a", 1, missing)])
        assert [leg["id"] for leg in picks["validated_singles"]] == ["a"], missing


def test_an_unparseable_start_time_is_not_treated_as_started():
    picks = _picks([_leg("a", 1, "not-a-timestamp")])
    assert [leg["id"] for leg in picks["validated_singles"]] == ["a"]


def test_production_contract_refuses_an_unverifiable_start_time():
    gate = {
        "enabled_families": ["player_aces"],
        "require_verifiable_start": True,
    }
    picks = selection.recommended_picks(
        {"strategy": gate, "value_legs": [_leg("a", 1, None)], "combos": []},
        now=NOW,
    )

    assert picks["validated_singles"] == []
    assert [leg["id"] for leg in picks["dropped_unverifiable_start"]] == ["a"]


def test_the_trailing_z_that_sqlite_stores_is_parsed():
    """`start_time_utc` is stored as `2026-08-16T15:00:00Z`. A comparison that
    does not handle the Z silently mis-sorts; that exact bug produced a '100%
    already started' reading during the investigation."""
    assert selection._minutes_until_start(
        {"start_time_utc": "2026-08-16T15:00:00Z"}, NOW
    ) == 180.0


def test_a_naive_timestamp_is_read_as_utc_not_local():
    assert selection._minutes_until_start(
        {"start_time_utc": "2026-08-16T15:00:00"}, NOW
    ) == 180.0


def test_the_started_ones_do_not_consume_the_two_pick_budget():
    """Only two singles are ever recommended. If a started match could still
    take one of those slots, the filter would cost a placeable bet instead of
    saving one."""
    legs = [
        _leg("started", 1, _stamp(-30), ev=0.90),
        _leg("also_started", 2, _stamp(-10), ev=0.80),
        _leg("open_a", 3, _stamp(300), ev=0.30),
        _leg("open_b", 4, _stamp(360), ev=0.20),
    ]
    picks = _picks(legs)
    assert [leg["id"] for leg in picks["validated_singles"]] == ["open_a", "open_b"]


def test_minutes_to_start_is_attached_for_the_card_to_print():
    picks = _picks([_leg("a", 1, _stamp(240))])
    assert picks["validated_singles"][0]["minutes_to_start"] == 240.0


def test_two_plus_candidate_gets_soft_price_preference():
    """A qualified 2.00+ leg gets the first card slot even when a shorter
    price has slightly higher model EV.  It is still subject to every normal
    evidence/value check; this only orders survivors of those checks."""
    legs = [
        _leg("short_a", 1, _stamp(240), ev=0.30, odds=1.50),
        _leg("short_b", 2, _stamp(240), ev=0.25, odds=1.80),
        _leg("two_plus", 3, _stamp(240), ev=0.28, odds=2.05),
    ]

    picks = _picks(legs)

    assert [leg["id"] for leg in picks["validated_singles"]] == [
        "two_plus", "short_a",
    ]


def test_positive_short_price_is_still_used_when_no_two_plus_survives():
    legs = [
        _leg("short_a", 1, _stamp(240), ev=0.30, odds=1.50),
        _leg("short_b", 2, _stamp(240), ev=0.25, odds=1.80),
    ]

    picks = _picks(legs)

    assert [leg["id"] for leg in picks["validated_singles"]] == [
        "short_a", "short_b",
    ]


def test_two_plus_does_not_jump_a_materially_better_short_price():
    legs = [
        _leg("short_value", 1, _stamp(240), ev=0.30, odds=1.50),
        _leg("weak_two_plus", 2, _stamp(240), ev=0.10, odds=2.05),
    ]

    picks = _picks(legs)

    assert [leg["id"] for leg in picks["validated_singles"]] == [
        "short_value", "weak_two_plus",
    ]
