"""Sportsbet sends the start time as an object, not a scalar.

`_parse_datetime` handled None, numbers and strings. Sportsbet sends
``{"milliseconds": 1786892400000}``, so `str(value)` became
``"{'milliseconds': ...}"``, both parse attempts failed, and None came back for
every Sportsbet fixture. Source coverage was 100% -- all 29 events in a single
stored payload carried one -- while `matches.start_time_utc` sat at 27-63%,
filled only by the composite provider's ISO strings.

Nothing failed. "No start time" is a legal value, so the column just looked
sparse. It cost the card any notion of whether a match had already begun.
"""

from __future__ import annotations

from datetime import datetime, timezone

from tennis_wc.ingestion.ingest_odds import _parse_datetime, _row_start_time_utc


EXPECTED = datetime(2026, 8, 16, 15, 0, tzinfo=timezone.utc)


def test_the_sportsbet_object_form_is_parsed():
    assert _parse_datetime({"milliseconds": 1786892400000}) == EXPECTED


def test_the_object_form_reaches_the_column_the_report_reads():
    row = {"startTime": {"milliseconds": 1786892400000}}
    assert _row_start_time_utc(row) == "2026-08-16T15:00:00Z"


def test_a_nested_event_object_is_parsed_too():
    row = {"raw": {"event": {"startTime": {"milliseconds": 1786892400000}}}}
    assert _row_start_time_utc(row) == "2026-08-16T15:00:00Z"


def test_seconds_and_iso_variants_are_tolerated():
    assert _parse_datetime({"seconds": 1786892400}) == EXPECTED
    assert _parse_datetime({"iso": "2026-08-16T15:00:00Z"}) == EXPECTED


def test_an_object_without_a_usable_key_is_none_not_a_crash():
    assert _parse_datetime({"timezone": "Australia/Sydney"}) is None
    assert _parse_datetime({}) is None


def test_the_scalar_forms_still_work():
    """The composite provider's string form is what filled the column at all;
    the new branch must not disturb it."""
    assert _parse_datetime("2026-08-16T15:00:00Z") == EXPECTED
    assert _parse_datetime("2026-08-16T15:00:00+00:00") == EXPECTED
    assert _parse_datetime(1786892400000) == EXPECTED
    assert _parse_datetime(1786892400) == EXPECTED
    assert _parse_datetime(None) is None
    assert _parse_datetime("") is None
    assert _parse_datetime("not a date") is None


def test_a_naive_string_is_read_as_utc():
    assert _parse_datetime("2026-08-16T15:00:00") == EXPECTED
