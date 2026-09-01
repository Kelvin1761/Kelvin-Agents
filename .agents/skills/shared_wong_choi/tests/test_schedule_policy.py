from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT.parent))

from shared_wong_choi.contracts import Domain  # noqa: E402
from shared_wong_choi.schedule_policy import (  # noqa: E402
    CalendarMode,
    FreshnessRole,
    due_runs,
    missed_runs,
    nba_pregame_role,
    refreshable_events,
)


SYDNEY = ZoneInfo("Australia/Sydney")


def test_nba_three_pregame_slots_have_distinct_freshness_roles() -> None:
    warmup = due_runs(datetime(2026, 10, 20, 21, 0, tzinfo=SYDNEY), Domain.NBA)[0]
    production = due_runs(datetime(2026, 10, 21, 0, 30, tzinfo=SYDNEY), Domain.NBA)[0]
    final = due_runs(datetime(2026, 10, 21, 6, 30, tzinfo=SYDNEY), Domain.NBA)[0]

    assert warmup.freshness_role is FreshnessRole.WARMUP
    assert warmup.target_date.isoformat() == "2026-10-21"
    assert warmup.publish_allowed is False
    assert production.freshness_role is FreshnessRole.PRODUCTION
    assert production.publish_allowed is True
    assert final.freshness_role is FreshnessRole.FINAL_REFRESH


def test_shadow_calendar_never_publishes_or_sends_content_card() -> None:
    run = due_runs(
        datetime(2026, 10, 10, 0, 30, tzinfo=SYDNEY),
        Domain.NBA,
        calendar_mode=CalendarMode.SHADOW,
    )[0]
    assert run.publish_allowed is False
    assert run.content_notify_allowed is False


def test_final_refresh_returns_only_events_that_have_not_started() -> None:
    now = datetime(2026, 10, 21, 6, 30, tzinfo=SYDNEY)
    run = due_runs(now, Domain.NBA)[0]
    starts = {
        "BOS_LAL": now - timedelta(minutes=1),
        "NYK_MIA": now + timedelta(hours=2),
    }
    assert refreshable_events(run, starts, now=now) == frozenset({"NYK_MIA"})


def test_missed_run_clock_recovers_each_fixed_slot_once() -> None:
    after = datetime(2026, 10, 20, 20, 0, tzinfo=SYDNEY)
    through = datetime(2026, 10, 21, 7, 0, tzinfo=SYDNEY)
    runs = missed_runs(after, through, Domain.NBA)
    assert [(run.scheduled_slot, run.freshness_role.value) for run in runs] == [
        ("21:00", "warmup"),
        ("21:30", "post_event"),
        ("00:30", "production"),
        ("06:30", "final_refresh"),
    ]


def test_scheduler_converts_utc_clock_to_sydney_including_dst() -> None:
    # 10:00 UTC is 21:00 Sydney after the October DST transition.
    utc = datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc)
    runs = due_runs(utc, Domain.NBA)
    assert runs[0].scheduled_slot == "21:00"
    assert runs[0].target_date.isoformat() == "2026-10-21"


def test_nba_role_for_startup_clock_is_deterministic() -> None:
    assert nba_pregame_role(datetime(2026, 10, 20, 21, 0, tzinfo=SYDNEY)) is FreshnessRole.WARMUP
    assert nba_pregame_role(datetime(2026, 10, 21, 0, 30, tzinfo=SYDNEY)) is FreshnessRole.PRODUCTION
    assert nba_pregame_role(datetime(2026, 10, 21, 6, 30, tzinfo=SYDNEY)) is FreshnessRole.FINAL_REFRESH
