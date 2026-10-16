"""EXP-20261016-77：試閘速度由 L600 環境分搬去試閘備戰（用戶 2026-10-16 決定）。"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import pytest  # noqa: E402

from au_racing_engine.dimensions import MATRIX_FORMULAS  # noqa: E402
from au_racing_engine.engine_core import RacingEngine, performance_pf_metrics, trial_speed_raw  # noqa: E402
from au_racing_engine import renderer  # noqa: E402


def horse(starts, runs):
    return {"horse_name": "T", "horse_number": "1", "career_race_starts": starts,
            "_data": {"pf_metrics": {"pf_runs": runs, "pf_aggregates": {"source": "sportsbet_race_context"}}}}


TRIAL = {"run_kind": "trial", "l600_delta": 0.5, "margin": 2.0, "source": "sportsbet_race_context"}
FORMAL = {"run_kind": "formal", "l600_delta": -0.2, "margin": 1.0, "source": "sportsbet_race_context"}


def test_l600_environment_never_sees_trials():
    runs = performance_pf_metrics(horse(1, [TRIAL, FORMAL]))["pf_runs"]
    assert [r["run_kind"] for r in runs] == ["formal"]


def test_trial_speed_uses_own_l600_and_six_start_cutoff():
    assert trial_speed_raw(horse(2, [TRIAL, FORMAL])) == pytest.approx(0.5 + 2.0 * 0.17)
    assert trial_speed_raw(horse(6, [TRIAL, FORMAL])) is None


def test_preparation_dimension_holds_both_trial_components():
    assert dict(MATRIX_FORMULAS["preparation"]) == {"preparation_score": 0.5, "trial_speed_score": 0.5}


def test_field_relative_score_and_neutral_fallbacks():
    def score(raw_runs, field):
        eng = RacingEngine(horse(2, raw_runs), {"field_summary": field})
        return eng._merged_trial_speed()[0]
    field = {"trial_speed_field_count": 5, "trial_speed_field_mean": 1.84, "trial_speed_field_stdev": 0.5}
    assert score([TRIAL], field) == pytest.approx(60.0 - 20.0 * (0.84 - 1.84) / 0.5)
    assert score([TRIAL], {**field, "trial_speed_field_count": 2}) == 60.0
    assert score([FORMAL], field) == 60.0


def test_renderer_explains_the_trial_speed_component():
    auto = {"trial_speed_detail": {"applies": True, "raw": 0.84, "field_count": 5, "mean": 1.84,
                                   "stdev": 0.5, "z": -2.0, "final": 100.0}}
    lines = renderer._jt_detail_lines(auto, "trial_speed_score")
    assert any("試閘個體 L600" in line for line in lines)
    assert renderer._jt_detail_lines({"trial_speed_detail": {"applies": False}}, "trial_speed_score")[0].startswith("正式賽已有 6 場")
