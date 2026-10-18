"""試閘證據喺報告集中喺試閘備戰（用戶 2026-10-16）；騎練維度入面嘅試閘項目照計分、只係一併顯示。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from au_racing_engine import renderer  # noqa: E402


def test_jt_trial_items_listed_under_preparation_with_scoring_home():
    auto = {"preparation_detail": {"base": 60.0, "adjustments": [], "final": 60.0},
            "jt_fit_detail": {"adjustments": [
                {"factor": "現役騎師已透過試閘熟習此駒", "delta": 2.57, "evidence": "J 試閘策此駒2次"},
                {"factor": "現役騎師曾策騎此駒 3 次正式賽", "delta": 0.93, "evidence": ""}]}}
    lines = renderer._jt_detail_lines(auto, "preparation_score")
    trial = [line for line in lines if "熟習此駒" in line]
    assert trial and trial[0].startswith("（喺騎練訊號計分）") and "+2.6" in trial[0]
    assert not any("正式賽" in line for line in lines)


def test_jockey_dimension_lines_unchanged():
    auto = {"jt_fit_detail": {"base": 60.0, "adjustments": [
        {"factor": "現役騎師已透過試閘熟習此駒", "delta": 2.57, "evidence": ""}], "final": 62.57}}
    lines = renderer._jt_detail_lines(auto, "jockey_horse_fit_score")
    assert not any(line.startswith("（喺騎練訊號計分）") for line in lines)
