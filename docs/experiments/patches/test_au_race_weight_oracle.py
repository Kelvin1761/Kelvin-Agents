"""Soundness checks for the retrospective oracle, separate from live scoring."""
import sys
from pathlib import Path
import unittest
import json
import tempfile
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import au_race_weight_oracle as oracle


class OracleTests(unittest.TestCase):
    def test_cloud_respects_coefficient_budget_and_bounds(self):
        for tier in oracle.TIERS:
            values = oracle.cloud(tier, 128, np.random.default_rng(7))
            np.testing.assert_allclose(values.sum(axis=1), oracle.BUDGET)
            for k, (lo, hi) in enumerate(oracle.bounds(tier)):
                self.assertTrue((values[:, k] >= lo - 1e-10).all())
                self.assertTrue((values[:, k] <= hi + 1e-10).all())

    def test_lp_witness_really_satisfies_gold_and_good(self):
        x = np.zeros((6, len(oracle.BASE)))
        x[:, 0] = [10, 9, 8, 3, 2, 1]
        pos = np.array([1, 2, 3, 4, 5, 6])
        rows = [{"n": i + 1, "pos": int(p)} for i, p in enumerate(pos)]
        for tier in oracle.TIERS:
            weights, _ = oracle.joint_witness(x, np.zeros(6), pos, tier)
            self.assertIsNotNone(weights)
            metrics = oracle.metrics(rows, x @ weights)
            self.assertTrue(metrics["gold"] and metrics["good"])

    def test_dominance_can_need_negative_weights(self):
        x = np.zeros((6, len(oracle.BASE)))
        x[:, 0] = [1, 2, 3, 8, 9, 10]
        pos = np.array([1, 2, 3, 4, 5, 6])
        weights, status = oracle.joint_witness(x, np.zeros(6), pos, "positive")
        self.assertIsNone(weights)
        self.assertEqual(status, "infeasible_at_margin")
        weights, _ = oracle.joint_witness(x, np.zeros(6), pos, "signed")
        self.assertLess(weights[0], 0)

    def test_constant_features_and_wrong_overlay_are_not_rescuable(self):
        x = np.zeros((6, len(oracle.BASE)))
        pos = np.array([1, 2, 3, 4, 5, 6])
        for tier in oracle.TIERS:
            weights, _ = oracle.joint_witness(x, np.arange(6), pos, tier)
            self.assertIsNone(weights)

    def test_gold_is_top4_capture_not_winner_presence(self):
        rows = [{"n": i + 1, "pos": p} for i, p in enumerate([1, 5, 2, 3, 4])]
        result = oracle.metrics(rows, np.array([5, 4, 3, 2, 1]))
        self.assertTrue(result["gold"])
        self.assertFalse(result["good"])
        rows[3]["pos"], rows[4]["pos"] = 4, 3
        self.assertFalse(oracle.metrics(rows, np.array([5, 4, 3, 2, 1]))["gold"])

    def test_replica_rejects_wrong_overlay(self):
        race = {"meeting": "synthetic", "race": 1, "rows": [
            {"n": i, "ability": 80, "features": {},
             "matrix": {k: 60 for k in oracle.DIMS}, "overlay": 0}
            for i in range(4)]}
        with self.assertRaisesRegex(ValueError, "Replica failed"):
            oracle.arrays(race)

    def test_same_day_never_crosses_split(self):
        races = [{"date": f"2026-08-{day:02d}"} for day in range(1, 21) for _ in range(3)]
        dev, terminal = oracle.date_partitions(races)
        self.assertFalse({races[i]["date"] for i in dev} & {races[i]["date"] for i in terminal})

    def test_full_order_lp_is_correct(self):
        x = np.zeros((6, len(oracle.BASE)))
        x[:, 0] = [6, 5, 4, 3, 2, 1]
        comparisons = list(zip(range(5), range(1, 6)))
        weights = oracle.solve_comparisons(x, np.zeros(6), comparisons, "positive")
        self.assertTrue((np.diff(x @ weights) < 0).all())

    def test_terminal_results_never_enter_diagnostics(self):
        races = []
        for day in range(10, 16):
            rows = [{"n": n, "pos": n, "ability": 60 + oracle.BASE[0] * (7 - n),
                     "features": {}, "overlay": 0,
                     "matrix": {key: 60 + (7 - n if k == 0 else 0)
                                for k, key in enumerate(oracle.DIMS)}}
                    for n in range(1, 7)]
            if day == 15:
                rows[0]["pos"] = "MUST NEVER BE VALIDATED OR SCORED"
                rows[0]["ability"] = None
            races.append({"date": f"2026-08-{day}", "meeting": f"meeting-{day}",
                          "race": 1, "rows": rows})
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp) / "data.json"
            data.write_text(json.dumps({"races": races}))
            out = Path(temp) / "out"
            with patch.object(sys, "argv", ["oracle", "--data", str(data), "--out", str(out), "--samples", "4"]):
                oracle.main()
            report = json.loads((out / "diagnostics.json").read_text())
            self.assertEqual(report["design"]["terminal_races"], 1)
            self.assertEqual(report["summary"]["races"], 5)
            self.assertNotIn("2026-08-15", {r["date"] for r in report["races"]})


if __name__ == "__main__":
    unittest.main()
