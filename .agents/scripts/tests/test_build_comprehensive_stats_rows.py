"""Appended result rows carry the full race_results schema (2026-10-25 fix)."""
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
SPEC = importlib.util.spec_from_file_location("build_comprehensive_stats_rows_test", MODULE_PATH)
bcs = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(bcs)

# Columns of the materialized race_results_{season}.csv (SeasonTag is added by pit_backtest).
SNAPSHOT_COLUMNS = [
    "Date", "Month", "Season", "RaceNo", "RaceClass", "Venue", "Track", "Course", "Going",
    "Distance", "Horse", "Jockey", "Trainer", "Draw", "Rank", "Win", "Place", "Odds",
    "OddsBucket", "Profit", "ActualWt", "WtBucket", "HorseWt", "FinishTimeSec", "RunStyle",
    "RunningPos", "HorseID", "Sire", "DamSire", "Origin",
]

# Shape of the live writer's payload: the header table is a Python repr string.
RACE = {
    "racedate": "2026-07-15",
    "race_no": 1,
    "venue": "HappyValley",
    "sectional_times": str([
        ["第 1 場 (858)", "", ""],
        ["第五班 - 1650米 - (40-0)", "場地狀況 :", "好地"],
        ["摩法神采讓賽", "賽道 :", '草地 - "C" 賽道'],
    ]),
    "results": [
        {"pos": "1", "horse_no": "3", "horse_name": "川河型駒(J080)", "jockey": "莫雷拉",
         "trainer": "游達榮", "actual_wt": "133", "horse_wt": "1095", "draw": "2",
         "running_positions": "4 7 5 1", "finish_time": "1:40.05", "win_odds": "11"},
        {"pos": "WV", "horse_no": "9", "horse_name": "退出馬(K001)", "jockey": "", "trainer": ""},
    ],
}


class ResultRowSchemaTests(unittest.TestCase):
    def test_row_matches_snapshot_schema_and_values(self) -> None:
        header = bcs.race_header(RACE)
        row = bcs.result_row("2026-07-15", "1", RACE, RACE["results"][0], header)
        self.assertEqual(list(row), SNAPSHOT_COLUMNS)
        self.assertEqual(row["RaceClass"], "Class 5")
        self.assertEqual(row["Going"], "好地")           # snapshot builder wrote the race title here
        self.assertEqual(row["Course"], '草地 - "C" 賽道')  # …and the race name here
        self.assertEqual((row["Venue"], row["Track"], row["Distance"]), ("跑馬地", "Turf", 1650.0))
        self.assertAlmostEqual(row["FinishTimeSec"], 100.05)
        self.assertEqual((row["Draw"], row["ActualWt"], row["HorseWt"]), (2.0, 133.0, 1095.0))
        self.assertEqual((row["RunningPos"], row["RunStyle"]), ("4 7 5 1", "Midpack"))
        self.assertEqual((row["HorseID"], row["RaceNo"]), ("J080", 1.0))
        self.assertEqual((row["Month"], row["Season"]), ("2026-07", "25/26"))
        self.assertEqual((row["OddsBucket"], row["WtBucket"]), ("Mid (10-20)", "Heavy (131+)"))
        self.assertEqual((row["Win"], row["Place"], row["Profit"]), (1, 1, 10.0))

    def test_non_finisher_is_skipped(self) -> None:
        self.assertIsNone(bcs.result_row("2026-07-15", "1", RACE, RACE["results"][1], bcs.race_header(RACE)))

    def test_unknown_class_stays_empty_for_supplements(self) -> None:
        race = dict(RACE, sectional_times=[["測試賽 - 1200米", "場地狀況 :", "好地"]])
        self.assertIsNone(bcs.race_header(race)["RaceClass"])

    def test_season_boundary(self) -> None:
        self.assertEqual(bcs.hkjc_season("2026-08-31"), "25/26")
        self.assertEqual(bcs.hkjc_season("2026-09-06"), "26/27")

    def test_appended_rows_have_no_empty_coverage_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_root = Path(tmp)
            day = db_root / "hkjc results 2025 26" / "2026-07-15"
            day.mkdir(parents=True)
            (day / "full_day_results.json").write_text(json.dumps({"1": RACE}, ensure_ascii=False), encoding="utf-8")
            seasons = {"25_26": {"csv": "x.csv", "results_dir": "hkjc results 2025 26", "base_required": False}}
            with mock.patch.object(bcs, "DB_ROOT", db_root), mock.patch.object(bcs, "SEASONS", seasons):
                rows, added = bcs.append_new_meetings("25_26", pd.DataFrame(columns=bcs.BASE_COLUMNS))
        self.assertEqual(added, ["2026-07-15"])
        self.assertEqual(len(rows), 1)
        for column in bcs.COVERAGE_COLUMNS:
            self.assertTrue(rows[column].notna().all(), column)


class CoverageRegressionTests(unittest.TestCase):
    @staticmethod
    def _rows(dead_from: str) -> pd.DataFrame:
        dates = pd.date_range("2025-09-01", "2026-10-21", freq="7D").strftime("%Y-%m-%d")
        frame = pd.DataFrame({column: 1.0 for column in bcs.COVERAGE_COLUMNS}, index=range(len(dates)))
        frame["Date"] = dates
        frame.loc[frame.Date >= dead_from, "FinishTimeSec"] = None
        return frame

    def test_long_dead_column_is_flagged(self) -> None:
        # Five dead months used to dilute a pooled baseline under the alarm line.
        problems = bcs.coverage_regressions(self._rows("2026-05-13"))
        self.assertEqual(len(problems), 1)
        self.assertTrue(problems[0].startswith("FinishTimeSec"))

    def test_healthy_rows_pass(self) -> None:
        self.assertEqual(bcs.coverage_regressions(self._rows("2099-01-01")), [])


if __name__ == "__main__":
    unittest.main()
