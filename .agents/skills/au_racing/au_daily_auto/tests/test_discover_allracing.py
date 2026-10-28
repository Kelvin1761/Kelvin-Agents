"""AU discovery must not drop night meetings that NextEvents (~30 races) has not reached.

2026-10-16: Cranbourne, Sunshine Coast and Launceston were excluded as "non-AU"
because the four day meetings filled NextEvents. AllRacing lists the full day.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import au_daily_schedule as S  # noqa: E402


def meeting(name, region, international, class_name):
    return {"name": name, "regionName": region, "isInternational": international,
            "className": class_name, "events": []}


PAYLOAD = {"dates": [{"sections": [
    {"raceType": "horse", "meetings": [
        meeting("Cranbourne", "Australia", False, "Horses - Aus/NZ"),
        meeting("Bathurst", "Australia", False, "Horses - Aus/NZ"),
        meeting("Sunshine Coast", "Australia", False, "Horses - Aus/NZ"),
        meeting("Launceston", "Australia", False, "Horses - Aus/NZ"),
        meeting("Gore", "New Zealand", False, "Horses - Aus/NZ"),
        meeting("Perth", "United Kingdom", True, "Horses - International"),
        meeting("Haydock", "United Kingdom", True, "Horses - International"),
    ]},
    {"raceType": "greyhound", "meetings": [
        meeting("Grafton", "Australia", False, "Greyhound Racing")]},
    {"raceType": "harness", "meetings": [
        meeting("Newcastle", "Australia", False, "Harness Racing")]},
]}]}


def test_only_australian_thoroughbred_meetings():
    assert S.au_thoroughbred_meetings(PAYLOAD) == [
        "Bathurst", "Cranbourne", "Launceston", "Sunshine Coast"]


def test_empty_or_malformed_payload_is_empty():
    assert S.au_thoroughbred_meetings({}) == []
    assert S.au_thoroughbred_meetings(None) == []


def test_index_slugs_match_the_day_list_but_overseas_slugs_do_not():
    venues = S.au_thoroughbred_meetings(PAYLOAD)
    assert S.match_venue("cranbourne", venues) == "Cranbourne"
    assert S.match_venue("sunshine_coast", venues) == "Sunshine Coast"
    assert S.match_venue("launceston", venues) == "Launceston"
    assert S.match_venue("haydock", venues) is None
    assert S.match_venue("perth", venues) is None        # Perth UK; WA Perth races as Ascot/Belmont
    assert S.match_venue("newcastle", venues) is None    # only harness Newcastle today


# ── 2026-10-26: API 有 Newcastle，sportsbetform 索引頁冇 → 以前靜靜消失 ──────
from datetime import datetime  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

SYD = ZoneInfo("Australia/Sydney")


def _event(start):
    return {"startTime": start}


def test_first_starts_take_the_earliest_race_per_au_thoroughbred_meeting():
    payload = {"dates": [{"sections": [{"raceType": "horse", "meetings": [
        {"name": "Newcastle", "regionName": "Australia", "isInternational": False,
         "events": [_event(300), _event(100), _event(200)]},
        {"name": "Perth", "regionName": "United Kingdom", "isInternational": True,
         "events": [_event(1)]},
    ]}]}]}
    assert S.au_meeting_first_starts(payload) == {"Newcastle": 100}


def test_unclaimed_venue_is_retryable_before_the_first_jump_only():
    start = int(datetime(2026, 10, 26, 12, 30, tzinfo=SYD).timestamp())
    before = datetime(2026, 10, 26, 0, 15, tzinfo=SYD)
    after = datetime(2026, 10, 26, 13, 0, tzinfo=SYD)
    assert S.classify_unclaimed("2026-10-26", start, before) == "awaiting_source"
    assert S.classify_unclaimed("2026-10-26", start, after) == "source_never_listed"


def test_unclaimed_without_start_time_falls_back_to_the_race_day():
    now = datetime(2026, 10, 26, 9, 0, tzinfo=SYD)
    assert S.classify_unclaimed("2026-10-26", None, now) == "awaiting_source"
    assert S.classify_unclaimed("2026-10-25", None, now) == "source_never_listed"


def test_new_statuses_change_the_run_outcome_and_are_not_silent():
    assert "awaiting_source" in S.RETRYABLE_STATUSES
    assert "source_never_listed" in S.ATTENTION_STATUSES


def test_evening_summary_names_the_unanalysed_meeting():
    import au_run_summary as R
    run = {"races_added": [{"meeting": "2026-10-26 Queanbeyan Race 1-7", "races": [1]}],
           "meetings_processed": [{"meeting": "2026-10-26 Newcastle",
                                   "status": "awaiting_source"}],
           "cloudflare_deployment": {"verified": {"ok": True}}}
    text = R.evening(run)
    assert "Newcastle" in text and "未有分析" in text
    only = R.evening({"races_added": [], "meetings_processed": run["meetings_processed"]})
    assert only and "Newcastle" in only
