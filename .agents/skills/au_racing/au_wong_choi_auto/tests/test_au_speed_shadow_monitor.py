from __future__ import annotations

import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS.parents[1]))

from au_speed_shadow_monitor import (  # noqa: E402
    build_status,
    config,
    race_key,
    select_complete_date_sample,
    validate_existing_config,
)


def _row(day: str, race: int, *, venue: str = "Randwick",
         baseline_gold: bool = False, candidate_gold: bool = True,
         baseline_good: bool = False, candidate_good: bool = True) -> dict:
    baseline = {
        "gold": baseline_gold,
        "good_positional": baseline_good,
        "pass": False,
        "champion": False,
        "winner_in_top3": False,
    }
    candidate = {
        **baseline,
        "gold": candidate_gold,
        "good_positional": candidate_good,
    }
    return {
        "date": day,
        "venue": venue,
        "race": race,
        "field_size": 10,
        "coverage": 0.75,
        "baseline": baseline,
        "global_add": candidate,
    }


def test_collecting_status_seals_all_outcomes() -> None:
    status = build_status(
        [_row("2026-09-27", 1)],
        reference_races=100,
        reference_conflicts=0,
        target=2,
    )

    assert status["state"] == "collecting"
    assert status["outcomes_visible"] is False
    assert "evaluation" not in status
    assert "field_size_cohorts" not in status
    assert "venue_guardrails" not in status
    assert "baseline" not in str(status)
    assert "candidate" in status["config"]  # formula is public; results are not


def test_terminal_includes_the_whole_threshold_date() -> None:
    rows = [
        _row("2026-09-27", 1),
        _row("2026-09-28", 1),
        _row("2026-09-28", 2),
        _row("2026-09-29", 1),
    ]

    selected = select_complete_date_sample(rows, 2)
    status = build_status(
        rows,
        reference_races=100,
        reference_conflicts=0,
        target=2,
    )

    assert len(selected) == 3
    assert {row["date"] for row in selected} == {"2026-09-27", "2026-09-28"}
    assert status["state"] == "ready_for_manual_stage4_review"
    assert status["outcomes_visible"] is True
    assert status["races_collected"] == 3
    assert status["locked_through_date"] == "2026-09-28"
    assert len(status["locked_race_keys"]) == 3
    assert status["evaluation"]["delta"]["gold"] == 100.0
    assert status["stage4_decision"]["verdict"] == "PRIMARY_WIN"
    assert status["stage4_decision"]["eligible_for_candidate_release"] is True
    assert status["stage4_decision"]["release_proposal"]["status"] == "passed"
    assert len(status["stage4_decision"]["release_proposal"]["proposal_sha256"]) == 64


def test_locked_keys_prevent_later_races_extending_terminal() -> None:
    first = [_row("2026-09-27", 1), _row("2026-09-28", 1)]
    initial = build_status(
        first,
        reference_races=100,
        reference_conflicts=0,
        target=2,
    )
    later = [*first, _row("2026-09-29", 1, candidate_gold=False)]

    locked = build_status(
        later,
        reference_races=101,
        reference_conflicts=0,
        target=2,
        locked_keys=initial["locked_race_keys"],
    )

    assert locked["locked_race_keys"] == initial["locked_race_keys"]
    assert locked["sample_sha256"] == initial["sample_sha256"]
    assert locked["races_collected"] == 2
    assert race_key(later[-1]) not in locked["locked_race_keys"]


def test_config_can_only_change_before_collection_starts() -> None:
    old_config = {**config(), "config_sha256": "old"}
    validate_existing_config({
        "config": old_config,
        "races_collected": 0,
        "outcomes_visible": False,
    })

    try:
        validate_existing_config({
            "config": old_config,
            "races_collected": 1,
            "outcomes_visible": False,
        })
    except ValueError as exc:
        assert "changed after collection started" in str(exc)
    else:
        raise AssertionError("config drift must be rejected after collection starts")


def test_terminal_primary_regression_rejects_candidate_release() -> None:
    rows = [
        _row(
            "2026-09-27",
            race,
            baseline_gold=False,
            candidate_gold=True,
            baseline_good=True,
            candidate_good=False,
        )
        for race in range(1, 6)
    ]

    status = build_status(
        rows,
        reference_races=100,
        reference_conflicts=0,
        target=5,
    )

    decision = status["stage4_decision"]
    assert decision["verdict"] == "REJECT"
    assert decision["reason"] == "primary_regression"
    assert decision["eligible_for_candidate_release"] is False
    assert decision["release_proposal"]["status"] == "rejected"


def test_supported_watch_venue_regression_blocks_automatic_gate() -> None:
    rows = []
    for day_index in range(5):
        day = f"2026-10-{day_index + 1:02d}"
        rows.extend(
            _row(
                day,
                race,
                venue="Randwick",
                baseline_gold=True,
                candidate_gold=False,
            )
            for race in range(1, 21)
        )
        rows.extend(
            _row(
                day,
                race,
                venue="Other Track",
                baseline_gold=False,
                candidate_gold=True,
            )
            for race in range(21, 41)
        )

    status = build_status(
        rows,
        reference_races=100,
        reference_conflicts=0,
        target=200,
    )

    decision = status["stage4_decision"]
    assert decision["verdict"] == "REJECT"
    assert decision["reason"] == "cohort_regression"
    assert "venue:Randwick:gold" in decision["guardrails"]["supported_regressions"]
