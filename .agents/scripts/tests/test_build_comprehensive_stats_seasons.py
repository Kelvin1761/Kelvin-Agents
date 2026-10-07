from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
MODULE_PATH = ROOT / ".agents" / "scripts" / "build_comprehensive_stats.py"
SPEC = importlib.util.spec_from_file_location("build_comprehensive_stats_test", MODULE_PATH)
bcs = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(bcs)


class ComprehensiveStatsSeasonTests(unittest.TestCase):
    def test_results_folder_name_maps_to_stats_key(self) -> None:
        self.assertEqual(bcs.season_key_from_results_dir("hkjc results 2026 27"), "26_27")
        self.assertIsNone(bcs.season_key_from_results_dir("hkjc results latest"))

    def test_discovery_adds_results_only_current_season(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "hkjc results 2026 27").mkdir()
            (root / "unrelated").mkdir()
            seasons = bcs.discover_seasons(root)
        self.assertIn("26_27", seasons)
        self.assertEqual(seasons["26_27"]["results_dir"], "hkjc results 2026 27")
        self.assertFalse(seasons["26_27"]["base_required"])

    def test_results_only_season_builds_master_stats(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_root = root / "database"
            stats_root = db_root / "comprehensive_stats"
            results_root = db_root / "hkjc results 2026 27" / "2026-09-13"
            results_root.mkdir(parents=True)
            payload = {
                "Race_1": {
                    "venue": "ShaTin",
                    "sectional_times": [
                        ["第四班 - 1200米 - (60-40)", "場地狀況 :", "好地"],
                        ["測試讓賽", "賽道 :", '草地 - "A" 賽道'],
                    ],
                    "results": [
                        {
                            "pos": "1",
                            "horse_name": "馬甲",
                            "jockey": "騎師甲",
                            "trainer": "練馬師甲",
                            "win_odds": "4.5",
                        },
                        {
                            "pos": "2",
                            "horse_name": "馬乙",
                            "jockey": "騎師乙",
                            "trainer": "練馬師乙",
                            "win_odds": "3.0",
                        },
                    ],
                }
            }
            (results_root / "full_day_results.json").write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8"
            )
            seasons = {
                "26_27": {
                    "csv": "race_results_26_27.csv",
                    "results_dir": "hkjc results 2026 27",
                    "base_required": False,
                }
            }
            with (
                mock.patch.object(bcs, "DB_ROOT", db_root),
                mock.patch.object(bcs, "STATS_ROOT", stats_root),
                mock.patch.object(bcs, "SEASONS", seasons),
            ):
                built, added = bcs.build_all("26_27")

        self.assertEqual(added, ["2026-09-13"])
        jockey = built["jockey_master_stats.csv"].set_index("Jockey")
        self.assertEqual(int(jockey.loc["騎師甲", "Starts"]), 1)
        self.assertEqual(int(jockey.loc["騎師甲", "Wins"]), 1)
        self.assertEqual(int(jockey.loc["騎師乙", "Places"]), 1)
        distance = built["jockey_distance_stats.csv"].set_index("Jockey")
        self.assertEqual(float(distance.loc["騎師甲", "Distance"]), 1200.0)
        venue_track = built["jockey_venue_track_stats.csv"].set_index("Jockey")
        self.assertEqual(venue_track.loc["騎師甲", "Venue"], "沙田")
        self.assertEqual(venue_track.loc["騎師甲", "Track"], "Turf")

    def test_trainer_recency_snapshot_is_strict_and_date_weighted(self) -> None:
        rows = pd.DataFrame(
            [
                {"Date": "2026-01-01", "Trainer": "練馬師甲", "Win": 1, "Place": 1},
                {"Date": "2026-01-10", "Trainer": "練馬師甲", "Win": 0, "Place": 1},
                {"Date": "2026-01-11", "Trainer": "未來資料", "Win": 1, "Place": 1},
            ]
        )
        snapshot = bcs.build_trainer_recency_snapshot(
            rows,
            as_of_date="2026-01-11",
            half_life_days=10,
        ).set_index("Trainer")

        self.assertNotIn("未來資料", snapshot.index)
        expected_starts = 0.5 ** (10 / 10) + 0.5 ** (1 / 10)
        self.assertAlmostEqual(snapshot.loc["練馬師甲", "Starts"], expected_starts, places=7)
        self.assertEqual(snapshot.loc["練馬師甲", "AsOfDate"], "2026-01-11")
        self.assertEqual(snapshot.loc["練馬師甲", "LatestResultDate"], "2026-01-10")
        self.assertEqual(int(snapshot.loc["練馬師甲", "HalfLifeDays"]), 10)


if __name__ == "__main__":
    unittest.main()
