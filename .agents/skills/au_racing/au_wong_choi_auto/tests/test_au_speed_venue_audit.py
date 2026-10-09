from __future__ import annotations

import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS.parents[1]))

from au_speed_venue_audit import (  # noqa: E402
    build_asof_standards,
    date_adjusted_ci,
    date_adjusted_residual,
    parse_run,
    rankings,
    runner_speed_best3,
)


def test_speed_standard_is_strictly_point_in_time() -> None:
    observations = [
        {"track": "Track", "date": f"2026-01-{day:02d}", "race": day,
         "distance": 1200, "condition": "Good", "winning_time": 70.0 + day}
        for day in range(1, 12)
    ]
    standards = build_asof_standards(observations, ["2026-01-10", "2026-01-12"])

    assert ("Track", 1200) not in standards["2026-01-10"][0]  # only nine prior races
    assert standards["2026-01-12"][0][("Track", 1200)] == 76.0


def test_runner_speed_drops_target_day_and_needs_three_runs() -> None:
    base = {("Track", 1200): 72.0}
    lines = [
        "Track R1 2026-01-01 1200m cond:Good margin:0.0L WinningTime:1:12.000",
        "Track R2 2026-01-02 1200m cond:Good margin:1.0L WinningTime:1:12.000",
        "Track R3 2026-01-03 1200m cond:Good margin:2.0L WinningTime:1:12.000",
        "Track R4 2026-01-10 1200m cond:Good margin:0.0L WinningTime:1:00.000",
    ]

    value = runner_speed_best3("\n".join(lines), (base, {}, 10), "2026-01-10")

    assert value is not None
    assert value < 0  # margins make the horse slower than the 72s standard


def _race(gap: float) -> dict:
    runners = []
    for number, score, speed in (
        (1, 70.0, 5.0), (2, 69.0, 4.0), (3, 68.0, 3.0),
        (4, 67.0, 1.0), (5, 67.0 - gap, 2.0),
    ):
        runners.append({"key": str(number), "number": number, "score": score,
                        "speed": speed, "pace_figure": 60.0, "position": number})
    return {"runners": runners}


def test_boundary_candidates_never_move_the_top_three() -> None:
    result = rankings(_race(0.25))

    assert result["boundary_all"][:3] == result["baseline"][:3]
    assert result["boundary_close"][:3] == result["baseline"][:3]
    assert result["boundary_all"][3:5] == ["5", "4"]
    assert result["boundary_close"][3:5] == ["5", "4"]


def test_close_boundary_refuses_a_clear_base_gap() -> None:
    result = rankings(_race(0.75))

    assert result["boundary_all"][3:5] == ["5", "4"]
    assert result["boundary_close"] == result["baseline"]


def test_parser_accepts_subminute_time_and_optional_margin_suffix() -> None:
    run = parse_run(
        "Track R1 2026-01-01 900m cond:Good margin:1.5 starters:8 WinningTime:58.420"
    )

    assert run is not None
    assert run["winning_time"] == 58.42
    assert run["margin"] == 1.5


def test_venue_residual_controls_for_the_same_dates() -> None:
    all_rows = [
        {"date": "2026-01-01", "baseline": {"gold": True}},
        {"date": "2026-01-01", "baseline": {"gold": False}},
        {"date": "2026-01-02", "baseline": {"gold": True}},
        {"date": "2026-01-02", "baseline": {"gold": True}},
    ]
    venue_rows = [all_rows[0], all_rows[2]]

    # Venue = 100%; same-date expected = mean(50%, 100%) = 75%.
    assert date_adjusted_residual(venue_rows, all_rows, "gold") == 25.0
    assert date_adjusted_ci(venue_rows, all_rows, "gold") == (0.0, 50.0)
