from datetime import datetime, timezone

import pytest

from tennis_wc import cli


@pytest.mark.parametrize('start,allowed', [
    ('2026-11-05T09:00:01Z', True),
    ('2026-11-05T09:00:00Z', False),
    ('2026-11-05T08:59:59Z', False),
    ('invalid', False),
    ('2026-11-05T10:00:00', False),
    (None, True),
])
def test_operational_pricing_checks_start_at_pricing_time(monkeypatch, start, allowed):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 5, 9, tzinfo=timezone.utc)

    monkeypatch.setattr(cli, 'datetime', Clock)
    calls = []
    result = {'model_probability': 0.6}
    monkeypatch.setattr(cli, 'price_match_snapshot', lambda s: calls.append(s) or result)
    snapshot = {'match_context': {'start_time_utc': {'value': start}}}
    got = cli._price_pregame_snapshot(snapshot)
    assert got == (result if allowed else None)
    assert len(calls) == int(allowed)


def test_operational_pricing_drops_result_if_start_crossed(monkeypatch):
    times = iter([
        datetime(2026, 11, 5, 8, 59, 59, tzinfo=timezone.utc),
        datetime(2026, 11, 5, 9, tzinfo=timezone.utc),
    ])

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return next(times)

    monkeypatch.setattr(cli, 'datetime', Clock)
    monkeypatch.setattr(cli, 'price_match_snapshot', lambda s: {'model_probability': 0.6})
    snapshot = {'match_context': {'start_time_utc': {'value': '2026-11-05T09:00:00Z'}}}
    skipped = []
    assert cli._price_pregame_snapshot(snapshot, skipped) is None
    assert skipped == [{"match_id": None, "reason": "match_started_during_pricing"}]
