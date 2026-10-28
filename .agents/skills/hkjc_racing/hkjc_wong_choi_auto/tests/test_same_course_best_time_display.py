"""同程最佳時間（EXP-20261025-08 入分 REJECT）：只顯示、PIT、唔入評分。"""
import sys
import unittest
from pathlib import Path

import pandas as pd

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import hkjc_same_course_times as sct  # noqa: E402
from hkjc_racing_engine import renderer  # noqa: E402

CELL = ("沙田", "Turf", 1200)
HIST = {
    "A001": [("2026-09-01", CELL, 69.50, 69.70), ("2026-09-20", CELL, 69.20, 69.10),
             ("2026-10-19", CELL, 68.00, 68.00),                     # 當日：唔准入
             ("2026-10-26", CELL, 67.00, 67.00)],                    # 未來：唔准入
    "B002": [("2026-08-10", CELL, 69.60, 69.90),
             ("2026-09-01", ("沙田", "Turf", 1400), 81.00, 81.00)],  # 唔同路程：唔計
    "C003": [("2026-09-01", ("跑馬地", "Turf", 1200), 69.00, 69.00)],
}


class FieldBestTimeTests(unittest.TestCase):
    def test_rank_gap_and_point_in_time(self) -> None:
        out = sct.field_best_times("2026-10-19", CELL, {"1": "A001", "2": "B002", "3": "C003"}, HIST)
        self.assertIn("最佳 1:09.10（扣場地快慢 1:09.20，2 仗）", out["1"])
        self.assertIn("全場第 1/2，全場最快", out["1"])
        self.assertIn("全場第 2/2，慢全場最快 0.40s", out["2"])
        self.assertIn("未有往績（全場 2/3 匹有同程時間）", out["3"])
        for text in out.values():
            self.assertTrue(text.endswith("僅供參考，未入評分"))

    def test_bad_inputs_give_nothing(self) -> None:
        self.assertEqual(sct.field_best_times("2026/10/19", CELL, {"1": "A001"}, HIST), {})
        self.assertEqual(sct.field_best_times("2026-10-19", None, {"1": "A001"}, HIST), {})
        self.assertEqual(sct.field_best_times("2026-10-19", CELL, {"1": "A001"}, {}), {})

    def test_race_cell(self) -> None:
        self.assertEqual(sct.race_cell({"venue": "沙田", "track": "AWT", "distance": "1650m"}), ("沙田", "AWT", 1650))
        self.assertEqual(sct.race_cell({"venue": "跑馬地", "track": "Turf", "distance": "1650"}), ("跑馬地", "Turf", 1650))
        self.assertIsNone(sct.race_cell({"venue": "Unknown", "distance": "1200m"}))

    def test_variant_and_standard_use_only_earlier_days(self) -> None:
        rows = []
        # Ten earlier meetings set the standard at 70.0; on 2026-10-01 the whole card runs 1s slow.
        for i in range(10):
            rows.append(dict(Date=f"2026-09-{i + 1:02d}", Venue="沙田", Track="Turf", Distance=1200.0, RaceNo=1.0,
                             RaceClass="Class 4", Horse=f"X(Z{i:03d})", HorseID=f"Z{i:03d}", Rank=1.0, FinishTimeSec=70.0))
        rows.append(dict(Date="2026-10-01", Venue="沙田", Track="Turf", Distance=1200.0, RaceNo=1.0,
                         RaceClass="Class 4", Horse="甲(A001)", HorseID="A001", Rank=1.0, FinishTimeSec=71.0))
        hist = sct.build_history(pd.DataFrame(rows))
        (day, cell, adj, raw), = hist["A001"]
        self.assertEqual((day, cell, raw), ("2026-10-01", CELL, 71.0))
        self.assertAlmostEqual(adj, 70.0)  # slow day removed


class ReportLineTests(unittest.TestCase):
    def test_sectional_anchor_shows_line(self) -> None:
        horse = {"_data": {"same_course_best_time": "沙田草地1200m 最佳 1:09.10｜僅供參考，未入評分"}}
        text = "\n".join(renderer._matrix_fact_lines("sectional", horse))
        self.assertIn("同程最佳時間", text)
        self.assertIn("僅供參考，未入評分", text)

    def test_absent_field_adds_nothing(self) -> None:
        self.assertNotIn("同程最佳時間", "\n".join(renderer._matrix_fact_lines("sectional", {"_data": {}})))


if __name__ == "__main__":
    unittest.main()
