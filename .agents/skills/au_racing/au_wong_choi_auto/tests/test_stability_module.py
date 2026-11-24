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


def test_field_z_sd_floor_live_and_rollback(monkeypatch):
    """EXP-20261124-20：細 SD 場除數 = 0.3065；`WC_AU_FQ_SD_FLOOR_LIVE=0` 回退；SD 大過下限唔郁。"""
    monkeypatch.delenv("WC_AU_FQ_SD_FLOOR_LIVE", raising=False)
    assert stability.field_z(0.5, 4, 8, 0.3, 0.1) == pytest.approx(0.2 / 0.3065)
    assert stability.field_z(1.0, 2, 3, 0.0, 0.5) == pytest.approx(2.0)
    assert stability.field_z(0.5, 4, 8, 0.3, 0.1, floor=0.0) == pytest.approx(2.0)
    monkeypatch.setenv("WC_AU_FQ_SD_FLOOR_LIVE", "0")
    assert stability.field_z(0.5, 4, 8, 0.3, 0.1) == pytest.approx(2.0)


def test_score_without_floor_rebuilds_unfloored_score(monkeypatch):
    monkeypatch.delenv("WC_AU_FQ_SD_FLOOR_LIVE", raising=False)
    d = {"raw": 0.5, "run_count": 4, "field_count": 8, "field_mean": 0.3, "field_stdev": 0.1, "z": 0.65}
    assert stability.score_without_floor({"form_quality_score": 73.05}, d) == pytest.approx(100.0)
    assert stability.score_without_floor({"form_quality_score": 70.0}, {**d, "field_stdev": 0.2}) == pytest.approx(80.0)
    assert stability.score_without_floor({"form_quality_score": 75.0}, {**d, "trip_change": {"delta": -5}}) == pytest.approx(95.0)
    # 海外代理／fallback 唔受下限影響
    assert stability.score_without_floor({"form_quality_score": 66.0}, {**d, "overseas_rating_proxy": True}) == 66.0
    assert stability.score_without_floor({"form_quality_score": 61.0}, {"raw": None}) == 61.0


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
