"""合成跑道賽事唔准報草地掛牌（Devonport／Pakenham Synthetic 被 Sportsbet 寫成 Good 3）。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from au_racing_engine.engine_core import normalise_synthetic_going as norm  # noqa: E402


def test_synthetic_venues_report_synthetic():
    assert norm("Pakenham Synthetic", "Good 3") == "Synthetic"
    assert norm("Devonport", "Good 3") == "Synthetic"
    assert norm("Ballarat Synthetic", "") == "Synthetic"
    assert norm("Cranbourne", "Synthetic") == "Synthetic"


def test_turf_and_wet_readings_untouched():
    # 草地場唔郁；合成跑道真係報 Soft/Heavy 都唔郁 —— 濕地 overlay 唔可以因呢個改動變。
    assert norm("Pakenham", "Good 3") == "Good 3"
    assert norm("Flemington", "Soft 5") == "Soft 5"
    assert norm("Pakenham Synthetic", "Soft 5") == "Soft 5"
