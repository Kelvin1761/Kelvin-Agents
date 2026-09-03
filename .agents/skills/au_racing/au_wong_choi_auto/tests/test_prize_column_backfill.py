"""The Facts prize column, and the 班次水平調整 that depends on it.

`horse_prize_level()` reads Facts column 18. The fact writer only started
emitting it on 2026-07-31, so 12 of the corpus's 14 months lack it and every
replay harness scored the dev window with the adjustment switched off while
production ran with it on. These tests pin the repair and its boundaries.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from au_racing_engine.engine_core import (  # noqa: E402
    PRIZE_COLUMN, backfill_prize_column, horse_prize_level)

HEADER = "| # | 類型 | 日期 | 馬場 | 路程 | 地面 | 檔 | 名次 | 班次落差 | 走位 |"
DIVIDER = "|---|---|---|---|---|---|---|---|---|---|"


def _row(index, date, venue, distance, kind="正式"):
    return (f"| {index} | {kind} | {date} | {venue} | {distance}m | 4 | 3 | "
            f"2/8 (-1.0L) | = | S3→F2 |")


def _facts(*rows):
    return "\n".join([HEADER, DIVIDER, *rows])


FORMGUIDE = """\
[1] Test Horse (3)
9yoG CHESTNUT | Sire: X | Dam: Y

Flemington R6 2026-03-29 1200m cond:4 $176,300 A Rider (2) 56.5kg
1-Test Horse (56.5kg), 2-Other (54kg) 0.4L

Echuca R7 2026-04-18 1000m cond:4 $22,000 A Rider (12) 58kg
1-Someone (54kg), 2-Test Horse (54kg) 0.75L

Sportsbet-Pakenham **(TRIAL)** R3 2026-05-02 800m cond:None $0 A Rider (None) Nonekg
1-Test Horse (Nonekg)

[2] Second Horse (5)
9yoG BAY | Sire: X | Dam: Y

Randwick R4 2026-04-01 1400m cond:4 $60,000 B Rider (1) 57kg
1-Second Horse (57kg)
"""


def _logic(facts_by_number):
    return {"horses": {str(n): {"horse_name": f"H{n}", "_data": {"facts_section": f}}
                       for n, f in facts_by_number.items()}}


@pytest.fixture
def meeting(tmp_path):
    (tmp_path / "05-10 Race 3 Formguide.md").write_text(FORMGUIDE, encoding="utf-8")
    return tmp_path


def test_missing_prize_column_is_restored_from_the_formguide(meeting):
    facts = _facts(_row(1, "2026-03-29", "Flemington R6", 1200),
                   _row(2, "2026-04-18", "Echuca R7", 1000))
    logic = _logic({1: facts})
    assert horse_prize_level(facts) is None  # the defect, before the repair
    assert backfill_prize_column(logic, meeting, 3, "2026-05-10") == 2
    filled = logic["horses"]["1"]["_data"]["facts_section"]
    assert horse_prize_level(filled) is not None
    values = [line.strip("|").split("|")[PRIZE_COLUMN].strip()
              for line in filled.splitlines() if line.startswith("| 1 |")]
    assert values == ["176300"]


def test_runs_on_or_after_the_meeting_are_never_used(meeting):
    """An archive re-scrape can list runs from after the race being replayed."""
    facts = _facts(_row(1, "2026-03-29", "Flemington R6", 1200))
    logic = _logic({1: facts})
    # Meeting date set before the historical run: it must now be out of bounds.
    assert backfill_prize_column(logic, meeting, 3, "2026-01-01") == 0
    assert horse_prize_level(logic["horses"]["1"]["_data"]["facts_section"]) is None


def test_trial_rows_are_left_alone(meeting):
    facts = _facts(_row(1, "2026-05-02", "Sportsbet-Pakenham R3", 800, kind="試閘"))
    logic = _logic({1: facts})
    assert backfill_prize_column(logic, meeting, 3, "2026-05-10") == 0


def test_existing_prize_values_are_not_overwritten(meeting):
    """2026-08 onward already has the column; the repair must not disturb it."""
    cols = [c.strip() for c in
            _row(1, "2026-03-29", "Flemington R6", 1200).strip().strip("|").split("|")]
    while len(cols) <= PRIZE_COLUMN:
        cols.append("-")
    cols[PRIZE_COLUMN] = "999999"
    logic = _logic({1: _facts("| " + " | ".join(cols) + " |")})
    assert backfill_prize_column(logic, meeting, 3, "2026-05-10") == 0
    assert "999999" in logic["horses"]["1"]["_data"]["facts_section"]


def test_each_runner_only_gets_its_own_formguide_block(meeting):
    """Runner 2's Randwick prize must never land on runner 1's row."""
    facts = _facts(_row(1, "2026-04-01", "Randwick R4", 1400))
    logic = _logic({1: facts})
    assert backfill_prize_column(logic, meeting, 3, "2026-05-10") == 0


def test_a_meeting_without_a_matching_formguide_is_a_no_op(tmp_path):
    logic = _logic({1: _facts(_row(1, "2026-03-29", "Flemington R6", 1200))})
    assert backfill_prize_column(logic, tmp_path, 3, "2026-05-10") == 0
    assert backfill_prize_column(logic, None, 3, "2026-05-10") == 0


def test_a_combined_formguide_never_stands_in_for_race_one(tmp_path):
    """`Race 1-10 Formguide.md` also matches a loose `Race\\s*(\\d+)`.

    Runner numbering restarts inside every race of a combined file, so picking
    it up for race 1 attaches race 2's prizes to race 1's runners. Measured on
    three corpus meetings before the filename match was tightened.
    """
    (tmp_path / "03-28 Race 1-10 Formguide.md").write_text(
        "[1] Wrong Horse (3)\n\nRandwick R4 2026-04-01 1400m cond:4 $999,999 B (1) 57kg\n",
        encoding="utf-8")
    logic = _logic({1: _facts(_row(1, "2026-04-01", "Randwick R4", 1400))})
    assert backfill_prize_column(logic, tmp_path, 1, "2026-05-10") == 0

    # The per-race file for the same meeting must still be found.
    (tmp_path / "03-28 Race 1 Formguide.md").write_text(FORMGUIDE, encoding="utf-8")
    logic = _logic({1: _facts(_row(1, "2026-03-29", "Flemington R6", 1200))})
    assert backfill_prize_column(logic, tmp_path, 1, "2026-05-10") == 1
