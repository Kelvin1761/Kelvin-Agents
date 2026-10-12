from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from au_oos_predictions import produce_walk_forward
from au_prediction_intake import content_hash, PredictionValidationError


class DailyProducerTests(unittest.TestCase):
    def setUp(self):
        self.baseline = {"fitted": False}
        self.profile = {"fitted": True, "fallback": "baseline", "algorithm": "test-only",
                        "warmup_min_races": 1, "warmup_min_days": 1}
        def race(day, number):
            labels = {str(n): n for n in range(1, 5)}
            return {"race_id": f"{day}/track/{number}", "date": day,
                    "prediction_at": day + "T12:00:00+10:00", "results_available_at": day + "T18:00:00+10:00",
                    "input": {"runner_ids": ["1", "2", "3", "4"], "sources": [
                        {"audit": "PASS", "available_at": day + "T09:00:00+10:00"}]},
                    "labels": labels, "labels_hash": content_hash(labels)}
        self.manifest = {"schema": "au-paired-predictions/v1", "provenance_audit": "PASS", "training_races": [],
                         "evaluation_races": [race("2026-08-05", 1), race("2026-08-06", 1),
                                              race("2026-08-06", 2), race("2026-08-07", 1)]}
        self.seen = []
        def fit(prefix, profile):
            self.seen.append([r["race_id"] for r in prefix])
            return {"count": len(prefix)}
        self.fit = fit
        def predict(race, state, profile):
            self.assertNotIn("labels", race)
            self.assertNotIn("results_available_at", race)
            return {"ability": {str(n): 70-n for n in range(1, 5)}, "ranking": ["1", "2", "3", "4"]}
        self.predict = predict

    def run_producer(self, **kwargs):
        return produce_walk_forward(self.manifest, baseline_profile=self.baseline, candidate_profile=self.profile,
                                    fit=kwargs.get("fit", self.fit), predict_baseline=self.predict,
                                    predict_candidate=kwargs.get("predict", self.predict))

    def test_fit_once_per_day_without_same_day_labels(self):
        result = self.run_producer()
        self.assertEqual(len(result["candidate"]), 4)
        self.assertEqual(self.seen, [["2026-08-05/track/1"], ["2026-08-05/track/1", "2026-08-06/track/1", "2026-08-06/track/2"]])
        self.assertEqual(result["candidate"][1]["fit"], result["candidate"][2]["fit"])
        self.assertEqual(result["candidate"][0]["status"], "baseline_fallback")

    def test_no_consensus_never_drops_a_window(self):
        result = self.run_producer(fit=lambda *_: None)
        self.assertEqual(len(result["candidate"]), 4)
        self.assertTrue(all(r["status"] == "baseline_fallback" for r in result["candidate"]))

    def test_delayed_prior_results_are_excluded_from_fit(self):
        self.manifest["evaluation_races"][0]["results_available_at"] = "2026-08-07T18:00:00+10:00"
        self.run_producer()
        self.assertEqual(self.seen, [["2026-08-06/track/1", "2026-08-06/track/2"]])

    def test_adapter_mutation_cannot_change_manifest(self):
        before = deepcopy(self.manifest)
        def fit(prefix, profile):
            prefix[0]["labels"]["1"] = 99
            profile["fitted"] = False
            return {"count": len(prefix)}
        self.run_producer(fit=fit)
        self.assertEqual(self.manifest, before)
        self.assertTrue(self.profile["fitted"])

    def test_fit_exception_is_not_silent_fallback(self):
        def broken(*_):
            raise RuntimeError("fit failed")
        with self.assertRaisesRegex(RuntimeError, "fit failed"):
            self.run_producer(fit=broken)

    def test_input_order_does_not_change_predictions(self):
        expected = self.run_producer()
        self.manifest["evaluation_races"].reverse()
        actual = self.run_producer()
        for key in ("baseline", "candidate", "fit_days"):
            self.assertEqual(expected[key], actual[key])
        self.assertNotEqual(expected["manifest_hash"], actual["manifest_hash"])

    def test_future_source_rejected_before_fitter(self):
        self.manifest["evaluation_races"][0]["input"]["sources"][0]["available_at"] = "2026-08-05T13:00:00+10:00"
        with self.assertRaisesRegex(PredictionValidationError, "future_source"):
            self.run_producer()
        self.assertFalse(self.seen)


if __name__ == "__main__":
    unittest.main()
