"""The HKJC board shows one card: the latest analysed meeting.

`meeting_detector` already keeps a settled meeting until a newer analysis is
ready, but the incremental publish path does not go through the detector -- it
can only add or replace one meeting -- so nothing ever left the snapshot.
Measured 2026-09-04: 2026-07-12 ShaTin was still on the live board two months
on, beside the freshly merged 2026-09-06 card.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

import generate_static as gs  # noqa: E402


def _snapshot(*meetings):
    return {
        "meetings": [{"date": d, "venue": v, "region": r, "analysts": ["Kelvin"]}
                     for d, v, r in meetings],
        "races": {
            f"{d}|{v}": {
                "meeting": {"date": d, "venue": v, "region": r, "analysts": ["Kelvin"]},
                "races_by_analyst": {"Kelvin": [{"race_number": 1}]},
            }
            for d, v, r in meetings
        },
        "consensus": {f"{d}|{v}|1": {} for d, v, _ in meetings},
        "roi": {},
    }


def _merge(tmp_path, base, date, venue, region):
    path = tmp_path / "base.json"
    path.write_text(json.dumps(base), encoding="utf-8")

    class M:
        pass
    meeting = M()
    meeting.date, meeting.venue = date, venue
    meeting.region = gs.Region.HKJC if region == "hkjc" else gs.Region.AU
    monkey_key = f"{date}|{venue}"
    gs._meeting_from_directory = lambda _d: meeting
    gs._collect_meeting = lambda _m: (
        {"date": date, "venue": venue, "region": region, "analysts": ["Kelvin"]},
        monkey_key,
        {"meeting": {"date": date, "venue": venue, "region": region,
                     "analysts": ["Kelvin"]},
         "races_by_analyst": {"Kelvin": [{"race_number": 1}]}},
        {f"{monkey_key}|1": {}})
    return gs.collect_incremental_au_data(path, tmp_path)


@pytest.fixture(autouse=True)
def _restore():
    original = (gs._meeting_from_directory, gs._collect_meeting)
    yield
    gs._meeting_from_directory, gs._collect_meeting = original


def test_an_older_hkjc_card_is_dropped_when_the_new_one_lands(tmp_path):
    base = _snapshot(("2026-07-12", "ShaTin", "hkjc"), ("2026-09-04", "Wyong", "au"))
    data = _merge(tmp_path, base, "2026-09-06", "ShaTin", "hkjc")
    hkjc = [m for m in data["meetings"] if m["region"] == "hkjc"]
    assert [(m["date"], m["venue"]) for m in hkjc] == [("2026-09-06", "ShaTin")]
    assert "2026-07-12|ShaTin" not in data["races"]
    assert not any(k.startswith("2026-07-12|") for k in data["consensus"])


def test_au_meetings_are_untouched(tmp_path):
    """AU runs several cards the same day; only HKJC is a single-card board."""
    base = _snapshot(("2026-09-04", "Wyong", "au"), ("2026-09-04", "Canberra", "au"))
    data = _merge(tmp_path, base, "2026-09-06", "ShaTin", "hkjc")
    au = sorted(m["venue"] for m in data["meetings"] if m["region"] == "au")
    assert au == ["Canberra", "Wyong"]


def test_a_newer_hkjc_card_is_never_wiped_by_re_publishing_an_older_one(tmp_path):
    base = _snapshot(("2026-09-13", "HappyValley", "hkjc"))
    data = _merge(tmp_path, base, "2026-09-06", "ShaTin", "hkjc")
    hkjc = sorted((m["date"], m["venue"]) for m in data["meetings"] if m["region"] == "hkjc")
    assert hkjc == [("2026-09-06", "ShaTin"), ("2026-09-13", "HappyValley")]


def test_re_merging_the_same_meeting_replaces_rather_than_duplicates(tmp_path):
    base = _snapshot(("2026-09-06", "ShaTin", "hkjc"))
    data = _merge(tmp_path, base, "2026-09-06", "ShaTin", "hkjc")
    assert len([m for m in data["meetings"] if m["region"] == "hkjc"]) == 1
