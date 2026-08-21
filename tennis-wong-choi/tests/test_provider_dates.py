"""The provider's date handling, which is the axis the whole schedule turns on.

Phase 0's finding was not that the scraper broke. It was that the only scheduled
job asked Sportsbet for a date whose book was not open yet, and got a legitimate
empty listing back. So "which local date is this fixture on" is the single most
consequential function in the provider: get it wrong by one and the morning pass
asks for the wrong day and comes back empty, which is exactly the failure that
looked like a broken scraper for three days.

None of it was tested. These are the cases that actually occur in the feed.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from tennis_wc.providers.sportsbet_provider import (
    SportsbetOddsProvider, _parse_datetime,
)


@pytest.fixture
def provider():
    # No network is touched: only the pure date helpers are exercised.
    return SportsbetOddsProvider.__new__(SportsbetOddsProvider)


def test_a_utc_evening_is_the_NEXT_day_in_sydney(provider):
    """The case that matters most. European night play is tomorrow in Sydney.

    22:00 UTC is 08:00 the following morning in Sydney (+10). A fixture filed
    under the UTC date would be asked for on the wrong day, and the listing for
    the other day is empty -- indistinguishable from a dead provider.
    """
    assert provider._fixture_local_date(
        {"start_time": "2026-08-11T22:00:00Z"}) == "2026-08-12"


def test_a_sydney_morning_stays_on_its_own_day(provider):
    # 09:00 Sydney == 23:00 UTC the day before.
    assert provider._fixture_local_date(
        {"start_time": "2026-08-11T23:00:00Z"}) == "2026-08-12"
    assert provider._fixture_local_date(
        {"start_time": "2026-08-12T02:00:00Z"}) == "2026-08-12"


def test_the_sydney_day_boundary_is_exact(provider):
    """13:59:59 UTC and 14:00:00 UTC are different Sydney days in August.

    Australia/Sydney is UTC+10 in August (no DST), so midnight lands at 14:00
    UTC. An off-by-one here silently moves a whole evening's fixtures.
    """
    assert provider._fixture_local_date(
        {"start_time": "2026-08-11T13:59:59Z"}) == "2026-08-11"
    assert provider._fixture_local_date(
        {"start_time": "2026-08-11T14:00:00Z"}) == "2026-08-12"


def test_dst_is_handled_by_the_zone_not_a_fixed_offset(provider):
    """Sydney is +11 in January and +10 in August. A hardcoded +10 would put
    January's late fixtures on the wrong day, and the tennis calendar's biggest
    month is January."""
    # 13:30 UTC in January is already the next day in Sydney (+11), but not in
    # August (+10).
    assert provider._fixture_local_date(
        {"start_time": "2026-01-15T13:30:00Z"}) == "2026-01-16"
    assert provider._fixture_local_date(
        {"start_time": "2026-08-15T13:30:00Z"}) == "2026-08-15"


def test_every_key_the_feed_has_used_is_accepted(provider):
    """The feed has changed this key name before; the fallback list is the fix."""
    for key in ("start_time", "startTime", "commence_time", "commenceTime",
                "game_time", "date", "match_date"):
        assert provider._fixture_local_date(
            {key: "2026-08-11T22:00:00Z"}) == "2026-08-12", key


def test_the_first_usable_key_wins_and_an_empty_one_is_skipped(provider):
    # An empty start_time must not shadow a usable commence_time: returning None
    # here drops the fixture, and a dropped fixture is a silent one.
    assert provider._fixture_local_date(
        {"start_time": "", "commence_time": "2026-08-11T22:00:00Z"}) == "2026-08-12"


def test_a_fixture_with_no_recognisable_time_returns_None_rather_than_guessing(provider):
    assert provider._fixture_local_date({}) is None
    assert provider._fixture_local_date({"start_time": "not a date"}) is None
    assert provider._fixture_utc_time({"start_time": None}) is None


def test_the_utc_time_is_emitted_in_the_shape_the_ingester_parses(provider):
    """This string is what lands in matches.start_time_utc, and the close of a
    market cannot be identified without it."""
    assert provider._fixture_utc_time(
        {"start_time": "2026-08-11T22:00:00+00:00"}) == "2026-08-11T22:00:00Z"
    # A local-offset input must be normalised, not passed through.
    assert provider._fixture_utc_time(
        {"start_time": "2026-08-12T08:00:00+10:00"}) == "2026-08-11T22:00:00Z"


def test_millisecond_epochs_are_not_read_as_seconds():
    """A millisecond epoch read as seconds lands in the year 56000, and a date
    that far out is silently outside every window the pipeline asks for."""
    expected = datetime(2026, 8, 6, 7, 6, 40, tzinfo=timezone.utc)
    # The same instant either way -- that IS the point: 1786000000000ms and
    # 1786000000s are the same moment, and the threshold picks the right unit.
    assert _parse_datetime(1786000000000) == expected
    assert _parse_datetime(1786000000) == expected
    # A seconds value read as milliseconds would land in 1970, inside no window.
    assert _parse_datetime(10_000_000_000).year == 2286


def test_a_naive_timestamp_is_treated_as_utc_not_as_local(provider):
    """The feed sometimes omits the zone. Reading it as machine-local would make
    the parsed date depend on where the code runs."""
    assert _parse_datetime("2026-08-11T22:00:00").tzinfo == timezone.utc
    assert provider._fixture_local_date(
        {"start_time": "2026-08-11T22:00:00"}) == "2026-08-12"


def test_a_date_only_value_keeps_its_own_date(provider):
    # Midnight UTC on the 11th is 10:00 on the 11th in Sydney, so a date-only
    # value must not shift a day.
    assert provider._fixture_local_date({"date": "2026-08-11"}) == "2026-08-11"
