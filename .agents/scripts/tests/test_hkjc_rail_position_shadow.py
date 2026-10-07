from __future__ import annotations

import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import hkjc_rail_position_shadow as shadow  # noqa: E402


def _row(date: str, venue: str, race: int, draw: int, place: int, early: str) -> dict:
    return {
        "Date": date,
        "RaceNo": race,
        "Venue": venue,
        "Track": "Turf",
        "Going": "好地",
        "Distance": 1200,
        "Rail": "C" if venue == "跑馬地" else "B",
        "FieldSize": 12,
        "Draw": draw,
        "EarlyGroup": early,
        "Place": place,
    }


def test_shadow_audit_never_claims_live_scoring_change() -> None:
    rows = [
        _row("2026-09-01", "沙田", 1, 1, 1, "front_1_4"),
        _row("2026-09-01", "沙田", 1, 9, 0, "back_9_plus"),
        _row("2026-09-02", "跑馬地", 1, 1, 0, "mid_5_8"),
        _row("2026-09-02", "跑馬地", 1, 9, 1, "back_9_plus"),
    ]

    report = shadow.analyse(rows)

    assert report["contract"]["mode"] == "shadow_only"
    assert report["contract"]["live_score_changed"] is False
    assert report["contract"]["actual_first_call_usage"] == "diagnostic_only"
    assert report["formula_decision"]["status"] == "KEEP_SHARED_7D_WITH_VENUE_COMPONENTS"


def test_expected_place_rate_uses_each_race_field_size() -> None:
    rows = [_row("2026-09-02", "跑馬地", 1, draw, int(draw <= 3), "front_1_4") for draw in range(1, 13)]

    report = shadow.analyse(rows)
    inner = next(item for item in report["venue_draw"] if item["key"] == ["跑馬地", "inner_1_4"])

    assert inner["place_rate"] == 0.75
    assert inner["expected_place_rate"] == 0.25
    assert inner["stable"] is False


def test_distance_and_draw_groups_are_explicit() -> None:
    assert shadow.distance_band(1200) == "sprint_1000_1200"
    assert shadow.distance_band(1650) == "middle_1400_1650"
    assert shadow.distance_band(1800) == "route_1800_plus"
    assert shadow.draw_group(4) == "inner_1_4"
    assert shadow.draw_group(8) == "middle_5_8"
    assert shadow.draw_group(9) == "outer_9_plus"
    assert shadow.field_size_band(10) == "small_10_or_less"
    assert shadow.field_size_band(12) == "medium_11_12"
    assert shadow.field_size_band(14) == "large_13_plus"
    assert shadow.going_group("好至快地") == "firm_fast"
    assert shadow.going_group("黏地") == "yielding_wet"
