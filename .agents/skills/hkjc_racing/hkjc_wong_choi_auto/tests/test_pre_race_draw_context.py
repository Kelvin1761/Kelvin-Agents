from __future__ import annotations

import csv
import sys
from pathlib import Path
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from hkjc_racing_engine.engine_core import RacingEngine  # noqa: E402
from hkjc_racing_engine.rail_draw_context import rail_draw_context_adjustment  # noqa: E402


def _write_history(path: Path) -> None:
    columns = [
        "Date", "RaceNo", "HorseNo", "Venue", "Track", "Going", "Distance",
        "Rail", "FieldSize", "Draw", "FirstCall", "EarlyGroup", "Pos", "Win", "Place",
    ]
    rows = []
    horse = 0
    for rail, places in (("C+3", 60), ("A", 0)):
        for index in range(120):
            horse += 1
            rows.append({
                "Date": f"2025-{1 + (index // 60):02d}-{1 + (index % 20):02d}",
                "RaceNo": 1 + (index % 20),
                "HorseNo": horse,
                "Venue": "跑馬地",
                "Track": "Turf",
                "Going": "好地",
                "Distance": 1650,
                "Rail": rail,
                "FieldSize": 12,
                "Draw": 9 + (index % 3),
                "FirstCall": 8,
                "EarlyGroup": "mid_5_8",
                "Pos": 3 if index < places else 8,
                "Win": 0,
                "Place": 1 if index < places else 0,
            })
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def test_rail_adjustment_is_point_in_time_stable_and_capped(tmp_path: Path) -> None:
    history = tmp_path / "rail.csv"
    _write_history(history)
    context = {
        "race_date": "2026-01-01",
        "venue": "跑馬地",
        "track": "Turf",
        "course": "C+3",
        "distance": "1650m",
    }
    result = rail_draw_context_adjustment(context, 10, dataset_path=history)

    assert result["applied"] is True
    assert result["adjustment"] == 4.0
    assert result["cell_runners"] == 120
    assert result["cell_races"] == 40

    before_history = rail_draw_context_adjustment(
        {**context, "race_date": "2025-01-01"}, 10, dataset_path=history
    )
    assert before_history["applied"] is False
    assert before_history["adjustment"] == 0.0


def test_same_rail_is_partitioned_between_sha_tin_and_happy_valley(tmp_path: Path) -> None:
    history = tmp_path / "venue_split.csv"
    columns = [
        "Date", "RaceNo", "HorseNo", "Venue", "Track", "Going", "Distance",
        "Rail", "FieldSize", "Draw", "FirstCall", "EarlyGroup", "Pos", "Win", "Place",
    ]
    rows = []
    horse = 0
    for venue, rail, places in (
        ("跑馬地", "A", 60), ("跑馬地", "B", 0),
        ("沙田", "A", 0), ("沙田", "B", 60),
    ):
        for index in range(120):
            horse += 1
            rows.append({
                "Date": f"2025-{1 + (index // 60):02d}-{1 + (index % 20):02d}",
                "RaceNo": 1 + (index % 20), "HorseNo": horse, "Venue": venue,
                "Track": "Turf", "Going": "好地", "Distance": 1650, "Rail": rail,
                "FieldSize": 12, "Draw": 9 + (index % 3), "FirstCall": 8,
                "EarlyGroup": "mid_5_8", "Pos": 3 if index < places else 8,
                "Win": 0, "Place": 1 if index < places else 0,
            })
    with history.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader(); writer.writerows(rows)
    common = {"race_date": "2026-01-01", "track": "Turf", "course": "A", "distance": "1650m"}
    hv = rail_draw_context_adjustment({**common, "venue": "跑馬地"}, 10, dataset_path=history)
    st = rail_draw_context_adjustment({**common, "venue": "沙田"}, 10, dataset_path=history)

    assert hv["adjustment"] == 4.0
    assert st["adjustment"] == -4.0
    assert hv["venue"] == "跑馬地"
    assert st["venue"] == "沙田"


def test_shadow_changes_only_race_shape_and_keeps_mainline_unchanged() -> None:
    horse = {
        "horse_name": "測試馬",
        "barrier": "10",
        "jockey": "",
        "trainer": "",
        "last_6_finishes": "4-5-6",
        "trackwork": {},
        "_data": {},
    }
    context = {
        "race_date": "2026-10-07",
        "venue": "跑馬地",
        "track": "Turf",
        "course": "C+3",
        "rail": "C+3",
        "distance": "1650m",
    }
    engine = RacingEngine(horse, context)
    source = {
        "applied": True,
        "adjustment": 3.0,
        "cell_runners": 120,
        "cell_races": 25,
        "parent_runners": 400,
        "reason": "stable_point_in_time_rail_cell",
    }
    with patch(
        "hkjc_racing_engine.engine_core.rail_draw_context_adjustment",
        return_value=source,
    ), patch(
        "draw.rail_draw_context_adjustment",
        return_value=source,
    ):
        baseline = engine.analyze_horse()
        shadow = engine.build_shadow_profile("pre_race_draw_context_v1_generic", base_auto=baseline)

    assert shadow["applied"] is True
    assert baseline["feature_scores"]["draw_score"] == 52.06
    assert shadow["matrix_scores"]["race_shape"] == 49.06
    for key, value in baseline["matrix_scores"].items():
        if key != "race_shape":
            assert shadow["matrix_scores"][key] == value
    with patch(
        "draw.rail_draw_context_adjustment",
        return_value=source,
    ):
        assert engine.analyze_horse()["matrix_scores"] == baseline["matrix_scores"]
