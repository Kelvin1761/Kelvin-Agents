"""EXP-20261127-02：S2 leaf 混合、回退開關、冇表唔混合。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from au_racing_engine import sb_full_time as S2  # noqa: E402


def test_blend_is_half_pace_figure_half_speed(monkeypatch):
    monkeypatch.delenv("WC_AU_S2_LIVE", raising=False)
    new, d = S2.blend(70.0, {"sb_full_time": {"z": 1.0, "status": "ok"}})
    assert new == pytest.approx(0.5 * 70 + 0.5 * 70) and d["original"] == 70.0
    new, _ = S2.blend(70.0, {"sb_full_time": {"z": 0.0, "status": "no_history"}})
    assert new == pytest.approx(65.0)          # 冇全程速度 = 60，照混（同研究一樣）


def test_no_prepare_or_switch_off_keeps_original(monkeypatch):
    monkeypatch.delenv("WC_AU_S2_LIVE", raising=False)
    assert S2.blend(70.0, {}) == (70.0, None)
    monkeypatch.setenv("WC_AU_S2_LIVE", "0")
    assert S2.blend(70.0, {"sb_full_time": {"z": 1.0}}) == (70.0, None)


def test_prepare_without_table_blends_neutral_and_clears_stale(tmp_path, monkeypatch):
    monkeypatch.delenv("WC_AU_S2_LIVE", raising=False)
    logic = {"horses": {"1": {"horse_name": "A"}}}
    logic["horses"]["1"]["sb_full_time"] = {"z": 2.5, "status": "ok"}      # 上次評分留低嘅舊值
    assert S2.prepare_field(logic, tmp_path, 1, "2026-11-28", "1200m", "Good 4", events_path=tmp_path / "nope.gz") is False
    # 冇表：舊 z 清走、全場 z 0 照混（唔可以淨乘權重）
    assert logic["horses"]["1"]["sb_full_time"] == {"raw": None, "z": 0.0, "status": "no_table"}
    assert S2.blend(70.0, logic["horses"]["1"])[0] == 65.0


def test_weight_multiplier_matches_dimension():
    from au_racing_engine.dimensions import _S2_MULT
    assert _S2_MULT == S2.WEIGHT_MULT == pytest.approx(0.177 / 0.108)
