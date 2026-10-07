from __future__ import annotations

import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import inject_hkjc_fact_anchors as facts  # noqa: E402


def test_chinese_class_uses_exact_scraped_standard_time(monkeypatch) -> None:
    monkeypatch.setattr(
        facts,
        "_load_scraped_standard_times",
        lambda: {
            "跑馬地_1200_C3": 69.31,
            "跑馬地_1200_C4": 70.42,
        },
    )

    assert facts.get_standard_time("跑馬地", 1200, "第三班") == 69.31
    assert facts.get_standard_time("跑馬地", 1200, "第四班（60-40）") == 70.42


def test_english_and_group_labels_are_normalized() -> None:
    assert facts.normalize_race_class_code("Class 2") == "C2"
    assert facts.normalize_race_class_code("G3") == "G"
    assert facts.normalize_race_class_code("新馬賽") == "GR"


def test_awt_same_venue_distance_uses_surface_normalization() -> None:
    races = [
        {"finish": 1, "distance": 1650, "venue": "沙田 全天候跑道", "date_dt": None},
        {"finish": 3, "distance": 1650, "venue": "沙田泥地", "date_dt": None},
        {"finish": 8, "distance": 1650, "venue": "沙田草地", "date_dt": None},
    ]

    stats = facts.compute_stats(races, today_venue="沙田AWT", today_dist=1650,
                                race_date="2026-09-27")

    assert stats["same_venue_dist"] == [1, 0, 1, 0]


def test_same_distance_stats_merge_full_profile_history_without_duplicates() -> None:
    recent = [
        {
            "date": "01/07/2026",
            "date_dt": facts.parse_date("01/07/2026"),
            "finish": 7,
            "distance": 1200,
            "venue": "沙田",
        },
        {
            "date": "10/12/2025",
            "date_dt": facts.parse_date("10/12/2025"),
            "finish": 4,
            "distance": 1200,
            "venue": "跑馬地",
        },
    ]
    profile = [
        # These two rows duplicate the formguide and must not be counted twice.
        {"date": "01/07/26", "placing": 7, "distance": 1200, "venue_track": "沙田草地A"},
        {"date": "10/12/25", "placing": 4, "distance": 1200, "venue_track": "跑馬地草地C+3"},
        # Older official profile evidence was previously displayed but omitted
        # from the 同程 summary and therefore from distance/risk scoring.
        {"date": "15/10/25", "placing": 1, "distance": 1200, "venue_track": "跑馬地草地B"},
        {"date": "28/09/25", "placing": 1, "distance": 1200, "venue_track": "沙田草地C"},
        {"date": "01/07/25", "placing": 5, "distance": 1200, "venue_track": "沙田草地B+2"},
        {"date": "18/06/25", "placing": 8, "distance": 1200, "venue_track": "跑馬地草地C"},
    ]

    stats = facts.compute_stats(
        recent,
        today_venue="沙田",
        today_dist=1200,
        race_date="2026-10-01",
        profile_entries=profile,
    )

    assert stats["recent_6"] == [7, 4, 1, 1, 5, 8]
    assert stats["same_dist"] == [2, 0, 0, 4]
    assert stats["same_venue_dist"] == [1, 0, 0, 2]
    assert stats["days_since_last"] == 92

    full_history = facts._merge_profile_history_for_stats(recent, profile)
    aptitude = facts.compute_distance_aptitude(full_history, today_dist=1200)
    assert aptitude["today_record"] == [2, 0, 4]
    assert sum(aptitude["today_record"]) == 6
