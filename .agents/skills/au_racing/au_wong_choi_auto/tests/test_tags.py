"""AU 標籤（`au_racing_engine/tags.py`，Kelvin 2026-11-13：同 HKJC 一樣嘅首本路程、騎練黃金組合…）。純顯示。"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from au_racing_engine import tags  # noqa: E402
from au_racing_engine.engine_core import RacingEngine  # noqa: E402

CTX = {"race_class": "BM70, Handicap", "distance": "1400m", "field_summary": {"count": 10},
       "meeting_intelligence": {"venue": "Eagle Farm", "going": "Good 4"}}


def engine(**data):
    horse = {"horse_name": "T", "horse_number": "1", "barrier": 4, "weight": 57.0,
             "jockey": "A Rider", "trainer": "A Stable", "_data": dict(data)}
    return RacingEngine(horse, dict(CTX), facts_section="")


def labels(out, tone):
    return [t["label"] for t in out[tone]]


def test_specialist_distance_is_a_good_unscored_tag():
    out = engine(track_stats_line="5:1-1-1 | 同程: 4:1-1-1 | 同場同程: 2:0-1-0").analyze_horse()["tags"]
    spec = [t for t in out["good"] if t["key"] == "specialist"]
    assert spec and spec[0]["label"] == "首本路程（1400米 4戰1勝3上名）"
    assert spec[0]["scored"] is False                       # AU 路程分唔入排名


def test_venue_specialist_is_scored_and_covers_track_driver():
    out = engine(track_stats_line="4:2-1-0 | 同程: 1:0-0-0").analyze_horse()["tags"]
    venue = [t for t in out["good"] if t["key"] == "venue_specialist"]
    assert venue and venue[0]["label"].startswith("場地專家（Eagle Farm 4戰2勝3上名")
    assert venue[0]["scored"] is True and venue[0]["impact"] > 0
    assert not any(t["key"] == "dim:track" for t in out["good"] + out["bad"])


def test_golden_combo_from_track_combo_stats():
    eng = engine()
    with mock.patch.object(RacingEngine, "_current_track_combo_stats",
                           return_value={"runs": 12, "wins": 4, "places": 7, "place_rate": 7 / 12}):
        out = eng.analyze_horse()["tags"]
    combo = [t for t in out["good"] if t["key"] == "combo_elite"]
    assert combo and combo[0]["label"] == "騎練黃金組合" and combo[0]["scored"] is False


def test_tags_never_break_scoring():
    eng = engine()
    with mock.patch.object(tags, "_distance_tags", side_effect=RuntimeError("boom")):
        res = eng.analyze_horse()
    assert "_error" in res["tags"] and res["ability_score"] is not None
