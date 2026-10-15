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
