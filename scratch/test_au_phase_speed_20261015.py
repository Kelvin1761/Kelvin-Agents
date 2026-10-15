"""Phase geometry, paired-cohort correctness and strict date boundary."""

import unittest
from copy import deepcopy

from au_phase_speed_20261015 import phase_geometry, phase_history, phase_lookup, summarize
from test_au_contextual_gps_speed_20261015 import events


class PhaseTests(unittest.TestCase):
    def test_short_and_long_geometries(self):
        for d, adaptive, fraction in ((1000, 400, 400), (1200, 600, 400), (1400, 600, 600), (2000, 1200, 800)):
            points = list(range(200, d + 1, 200))
            splits = [15] + [12] * (len(points) - 1)
            self.assertEqual(phase_geometry(points, splits, "E800")["length"], d - 800)
            self.assertEqual(phase_geometry(points, splits, "Adaptive")["length"], adaptive)
            self.assertEqual(phase_geometry(points, splits, "Fraction")["length"], fraction)

    def test_start_acceleration_removed_from_cruise(self):
        points = [200, 400, 600, 800, 1000]
        slow = phase_geometry(points, [25, 12, 12, 12, 12], "Cruise")
        fast = phase_geometry(points, [10, 12, 12, 12, 12], "Cruise")
        self.assertEqual(slow, fast)
        self.assertEqual(slow["time"], 12)
        self.assertEqual(slow["kmh"], 60)

    def test_irregular_first_section_no_interpolation(self):
        points = [266, 466, 666, 866, 1066, 1266, 1466, 1666]
        phase = phase_geometry(points, [18] + [12] * 7, "E800")
        self.assertEqual(phase["length"], 866)
        self.assertEqual(phase["time"], 54)
        self.assertEqual(phase_geometry(points, [18] + [12] * 7, "Cruise")["length"], 600)

    def test_missing_cruise_is_not_zero_speed(self):
        self.assertIsNone(phase_geometry([400, 600, 800, 1000], [25, 12, 12, 12], "Cruise"))

    def test_total_minus_late_reconciles(self):
        points = [200, 400, 600, 800, 1000, 1200]
        splits = [15, 11, 12, 13, 14, 15]
        for phase, tail in (("E800", 4), ("E600", 3)):
            self.assertEqual(phase_geometry(points, splits, phase)["time"], sum(splits) - sum(splits[-tail:]))

    def test_source_future_dates_do_not_change_lookup(self):
        history = events()
        for event in history:
            for row in event["rows"]:
                row["phases"] = {
                    "E800": {
                        "start": 0,
                        "end": event["distance"] - 800,
                        "length": event["distance"] - 800,
                        "time": row["early"],
                    }
                }
        original, _ = phase_lookup(history, "2026-08-01", "E800")
        future = deepcopy(history[0])
        future["date"] = "2026-08-01"
        future["rows"][0]["phases"]["E800"]["time"] = 9999
        changed, _ = phase_lookup(history + [future], "2026-08-01", "E800")
        self.assertEqual(original, changed)
        self.assertEqual(len(phase_history(history + [future], "2026-08-01", "E800")), 120)

    def test_common_cohort_same_pairs_and_identity(self):
        from au_phase_speed_20261015 import PHASES

        phases = PHASES + ("Total_reference",)
        rows = [
            {"pos": 1, "phase_raw": {p: 2 for p in phases}},
            {"pos": 4, "phase_raw": {p: 1 for p in phases}},
            {"pos": 5, "phase_raw": {p: 0 for p in phases}},
        ]
        rows[2]["phase_raw"]["Cruise"] = None
        report = summarize([{"date": "2026-09-04", "rows": rows}], True)
        self.assertEqual({report[p]["pairs"] for p in phases}, {1})
        self.assertTrue(all(report[p]["auc"] == 1 for p in phases))
        self.assertTrue(all(x["ci95"] == [0, 0] for x in report["paired_differences_vs_E800"].values()))


if __name__ == "__main__":
    unittest.main()
