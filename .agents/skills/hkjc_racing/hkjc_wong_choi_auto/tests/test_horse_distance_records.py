"""EXP-20261018-13：同程往績用賽果庫完整歷史（live latest／回放 PIT 注入），取出賽次數多嗰個。"""
import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from hkjc_racing_engine import live_priors  # noqa: E402
from hkjc_racing_engine.engine_core import RacingEngine  # noqa: E402

FRAME = pd.DataFrame([
    {"Brand": "J208", "Horse": "大至尊", "Distance": 1800, "Starts": 6, "Wins": 1, "Seconds": 2, "Thirds": 0, "Places": 3},
    {"Brand": "", "Horse": "天星", "Distance": 1200.0, "Starts": 11, "Wins": 2, "Seconds": 2, "Thirds": 1, "Places": 5},
])


def engine(name, code, facts_line, race_date="2026-09-06", distance="1800m"):
    horse = {"horse_name": name, "horse_code": code, "season_stats": facts_line}
    return RacingEngine(horse, {"venue": "沙田", "distance": distance, "race_date": race_date})


class HorseDistanceRecordTests(unittest.TestCase):
    def setUp(self):
        self._saved = live_priors._HORSE_DISTANCE

    def tearDown(self):
        live_priors._HORSE_DISTANCE = self._saved

    def _inject(self, as_of="2026-09-06"):
        live_priors._HORSE_DISTANCE = live_priors.HorseDistanceRecords(
            FRAME, temporal_mode="point_in_time", as_of_date=as_of)

    def test_lookup_by_brand_then_name(self):
        records = live_priors.HorseDistanceRecords(FRAME)
        self.assertEqual(records.lookup("J208", "whatever", "1800m")["places"], 3)
        self.assertEqual(records.lookup("", "天星", "1200")["starts"], 11)
        self.assertIsNone(records.lookup("X999", "冇呢匹", "1200m"))

    def test_engine_uses_fuller_history(self):
        self._inject()
        rec = engine("大至尊", "J208", "季內 (0-0-0-1) | 同程 (0-0-0-2) | 同場同程 (0-0-0-1)")._same_distance_record()
        self.assertEqual((rec["starts"], rec["places"]), (6, 3))

    def test_facts_kept_when_database_has_fewer_starts(self):
        self._inject()
        rec = engine("大至尊", "J208", "季內 (0-0-0-0) | 同程 (1-1-1-5) | 同場同程 (0-0-0-0)")._same_distance_record()
        self.assertEqual((rec["starts"], rec["places"]), (8, 3))

    def test_historical_race_without_injection_falls_back_to_facts(self):
        live_priors._HORSE_DISTANCE = live_priors.HorseDistanceRecords(FRAME)  # latest snapshot, not PIT
        rec = engine("大至尊", "J208", "季內 (0-0-0-0) | 同程 (0-0-0-2) | 同場同程 (0-0-0-0)",
                     race_date="2025-01-01")._same_distance_record()
        self.assertEqual((rec["starts"], rec["places"]), (2, 0))

    def test_wrong_date_injection_is_rejected(self):
        self._inject(as_of="2026-09-01")
        rec = engine("大至尊", "J208", "季內 (0-0-0-0) | 同程 (0-0-0-2) | 同場同程 (0-0-0-0)")._same_distance_record()
        self.assertEqual(rec["starts"], 2)


if __name__ == "__main__":
    unittest.main()
