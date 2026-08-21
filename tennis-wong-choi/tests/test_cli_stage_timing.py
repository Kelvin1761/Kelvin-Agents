from __future__ import annotations

import pytest


def test_timed_stage_records_a_successful_duration():
    from tennis_wc.cli import _run_timed_stage

    timings = []
    ticks = iter((10.0, 12.3456))

    result = _run_timed_stage(
        "elo_rebuild", lambda: "ok", timings, clock=lambda: next(ticks)
    )

    assert result == "ok"
    assert timings == [{"stage": "elo_rebuild", "status": "ok", "seconds": 2.346}]


def test_timed_stage_records_duration_when_the_stage_fails():
    from tennis_wc.cli import _run_timed_stage

    timings = []
    ticks = iter((3.0, 3.25))

    with pytest.raises(RuntimeError, match="boom"):
        _run_timed_stage(
            "odds",
            lambda: (_ for _ in ()).throw(RuntimeError("boom")),
            timings,
            clock=lambda: next(ticks),
        )

    assert timings == [{"stage": "odds", "status": "failed", "seconds": 0.25}]
