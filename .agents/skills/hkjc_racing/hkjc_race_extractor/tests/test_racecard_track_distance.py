from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from extract_racecard import parse_surface_track_distance  # noqa: E402


def test_turf_racecard_keeps_rail_and_distance() -> None:
    assert parse_surface_track_distance('草地, "C" 賽道, 2200米, 好地至黏地') == ("草地", "C 賽道", "2200米")


def test_all_weather_racecard_has_no_rail_column() -> None:
    # 舊版按位置讀：賽道 = 1650米、路程 = 空。
    assert parse_surface_track_distance("全天候跑道, 1650米") == ("全天候跑道", "", "1650米")
    assert parse_surface_track_distance("全天候跑道, 1200米, 好地") == ("全天候跑道", "", "1200米")
