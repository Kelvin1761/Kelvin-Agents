from __future__ import annotations

import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS.parents[1]))

from au_feature_ab import date_partitions  # noqa: E402
from au_retest_watch import REGISTERED, RESOLVED  # noqa: E402


def _race(date: str, number: int):
    return (date, [(str(number), 60.0, {}, number, number)])


def test_date_partitions_never_split_a_race_day() -> None:
    races = [
        *[_race("2026-08-14", number) for number in range(1, 4)],
        *[_race("2026-08-15", number) for number in range(1, 72)],
        *[_race("2026-08-16", number) for number in range(1, 3)],
        *[_race("2026-08-17", number) for number in range(1, 3)],
        *[_race("2026-08-18", number) for number in range(1, 3)],
        *[_race("2026-08-19", number) for number in range(1, 3)],
    ]

    dev, terminal, folds = date_partitions(races, holdout=0.15, folds=5)

    dev_dates = {race[0] for race in dev}
    terminal_dates = {race[0] for race in terminal}
    assert dev_dates.isdisjoint(terminal_dates)
    assert terminal_dates == {"2026-08-19"}
    fold_dates = [{race[0] for race in fold} for fold in folds]
    for left_index, left in enumerate(fold_dates):
        for right in fold_dates[left_index + 1:]:
            assert left.isdisjoint(right)


def test_date_partitions_keep_the_large_boundary_day_whole() -> None:
    races = [
        *[_race("2026-08-14", number) for number in range(1, 4)],
        *[_race("2026-08-15", number) for number in range(1, 72)],
        _race("2026-08-16", 1),
    ]

    dev, terminal, _ = date_partitions(races, holdout=0.15, folds=2)

    assert sum(race[0] == "2026-08-15" for race in dev) == 71
    assert not any(race[0] == "2026-08-15" for race in terminal)


def test_completed_retests_do_not_keep_firing_the_watch() -> None:
    assert REGISTERED == []
    assert {item["id"] for item in RESOLVED} == {"class_score", "speed_figure"}
