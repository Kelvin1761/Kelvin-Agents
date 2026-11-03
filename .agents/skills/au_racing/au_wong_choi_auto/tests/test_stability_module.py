"""EXP-20261103-09／10：狀態與穩定性單一模組；兩條「−4」情境扣分已剷。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from au_racing_engine import stability  # noqa: E402
from au_racing_engine.engine_core import RacingEngine  # noqa: E402


def test_composite_is_the_old_mix():
    assert stability.composite(80, 50) == pytest.approx(60 + 0.6 * 20 - 0.4 * 10)


def test_field_z_needs_two_runs_three_horses_and_spread():
    assert stability.field_z(1.0, 2, 3, 0.0, 0.5) == pytest.approx(2.0)
    assert stability.field_z(1.0, 1, 3, 0.0, 0.5) is None
    assert stability.field_z(1.0, 2, 2, 0.0, 0.5) is None
    assert stability.field_z(1.0, 2, 3, 0.0, 0.0) is None
    assert stability.field_z(None, 2, 3, 0.0, 0.5) is None


def test_trip_change():
    assert stability.trip_change(1600, 1200) == (-5.0, "增程")
    assert stability.trip_change(1200, 1600) == (-5.0, "縮程")
    assert stability.trip_change(1400, 1200) == (0.0, "")
    assert stability.trip_change(1400, None) == (0.0, "")


def test_score_without_proxy_matches_both_paths():
    feats = {"form_score": 70, "performance_quality_score": 65}
    assert stability.score_without_proxy(feats, {}) == pytest.approx(stability.composite(70, 65))
    detail = {"raw": 1.0, "run_count": 3, "field_count": 5, "field_mean": 0.0, "field_stdev": 1.0,
              "trip_change": {"delta": -5.0}}
    assert stability.score_without_proxy(feats, detail) == pytest.approx(75.0)


def test_no_minus_four_context_penalties():
    src = Path(RacingEngine.analyze_horse.__code__.co_filename).read_text(encoding="utf-8")
    assert "小收 −4" not in src
