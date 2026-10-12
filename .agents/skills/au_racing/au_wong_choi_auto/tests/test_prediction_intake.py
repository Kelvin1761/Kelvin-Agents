import copy
import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "au_prediction_intake.py"
if not SCRIPT.exists():
    SCRIPT = Path(__file__).with_name("au_prediction_intake.py")
spec = importlib.util.spec_from_file_location("au_prediction_intake", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PredictionIntakeTests(unittest.TestCase):
    def setUp(self):
        def race(day):
            return {"race_id": day + "/track/1", "date": day,
                    "prediction_at": day + "T12:00:00+10:00",
                    "input": {"runner_ids": ["1", "2", "3", "4"], "sources": [
                        {"available_at": day + "T09:00:00+10:00", "audit": "PASS"}]}}
        train, race = race("2026-08-05"), race("2026-08-06")
        labels = {str(n): n for n in range(1, 5)}
        train.update(results_available_at="2026-08-05T13:00:00+10:00", labels=labels,
                     labels_hash=module.content_hash(labels))
        self.manifest = {"schema": "au-paired-predictions/v1", "provenance_audit": "PASS",
                         "training_races": [train], "evaluation_races": [race]}
        self.base_profile = {"fitted": False}
        self.cand_profile = {"fitted": True, "fallback": "baseline"}
        common = {"race_id": race["race_id"], "date": race["date"],
                  "prediction_at": race["prediction_at"], "input_hash": module.content_hash(race["input"]),
                  "ranking": ["1", "2", "3", "4"], "ability": {str(n): 70-n for n in range(1, 5)}}
        self.base = [{**common, "status": "baseline", "profile_hash": module.content_hash(self.base_profile)}]
        self.cand = [copy.deepcopy({**common, "status": "candidate", "profile_hash": module.content_hash(self.cand_profile),
                     "fit": {"training_race_ids": [train["race_id"]], "cutoff": train["date"],
                             "training_hash": module.content_hash([{"race_id": train["race_id"],
                                                                    "input_hash": module.content_hash(train["input"]),
                                                                    "labels_hash": train["labels_hash"]}]),
                             "state": {"parameters": [1, 2]},
                             "state_hash": module.content_hash({"parameters": [1, 2]})}})]

    def validate(self):
        return module.validate_pair(self.manifest, self.base, self.cand,
                                    baseline_profile=self.base_profile, candidate_profile=self.cand_profile)

    def test_valid_daily_prefix(self):
        self.assertEqual(self.validate()["mode"], "walk_forward_oos")

    def test_same_count_different_race_is_rejected(self):
        self.cand[0]["race_id"] = "wrong/track/1"
        with self.assertRaisesRegex(module.PredictionValidationError, "race_identity_changed"):
            self.validate()

    def test_same_day_training_is_rejected(self):
        self.cand[0]["fit"]["training_race_ids"] = [self.cand[0]["race_id"]]
        with self.assertRaisesRegex(module.PredictionValidationError, "strictly_before"):
            self.validate()

    def test_mode_claim_without_fit_is_rejected(self):
        self.cand[0]["mode"] = "walk_forward_oos"
        del self.cand[0]["fit"]
        with self.assertRaisesRegex(module.PredictionValidationError, "needs_walk_forward"):
            self.validate()

    def test_missing_prediction_is_rejected(self):
        self.cand.clear()
        with self.assertRaisesRegex(module.PredictionValidationError, "race_identity_changed"):
            self.validate()

    def test_fallback_requires_baseline_scores_and_order(self):
        self.cand[0]["status"] = "baseline_fallback"
        self.cand[0]["ranking"] = ["2", "1", "3", "4"]
        with self.assertRaisesRegex(module.PredictionValidationError, "fallback_differs"):
            self.validate()

    def test_hash_mismatch_is_rejected(self):
        for field in ("input_hash", "profile_hash"):
            with self.subTest(field=field):
                old = self.cand[0][field]
                self.cand[0][field] = "wrong"
                with self.assertRaisesRegex(module.PredictionValidationError, field + "_changed"):
                    self.validate()
                self.cand[0][field] = old

    def test_future_and_unknown_source_are_rejected(self):
        source = self.manifest["evaluation_races"][0]["input"]["sources"][0]
        source["available_at"] = "2026-08-06T13:00:00+10:00"
        with self.assertRaisesRegex(module.PredictionValidationError, "future_source"):
            self.validate()
        source["audit"] = "FLAG"
        with self.assertRaisesRegex(module.PredictionValidationError, "provenance_flag"):
            self.validate()

    def test_nonfinite_ability_is_rejected(self):
        self.cand[0]["ability"]["1"] = float("nan")
        with self.assertRaisesRegex(module.PredictionValidationError, "nonfinite"):
            self.validate()

    def test_training_hash_is_checked(self):
        self.cand[0]["fit"]["training_hash"] = "wrong"
        with self.assertRaisesRegex(module.PredictionValidationError, "training_hash_changed"):
            self.validate()

    def test_training_results_available_after_prediction_are_rejected(self):
        self.manifest["training_races"][0]["results_available_at"] = "2026-08-06T12:01:00+10:00"
        with self.assertRaisesRegex(module.PredictionValidationError, "training_labels_not_available"):
            self.validate()

    def test_state_payload_must_match_hash(self):
        self.cand[0]["fit"]["state"]["parameters"] = [3, 4]
        with self.assertRaisesRegex(module.PredictionValidationError, "fit_state_hash_changed"):
            self.validate()

    def test_training_labels_must_match_hash(self):
        self.manifest["training_races"][0]["labels"]["1"] = 4
        with self.assertRaisesRegex(module.PredictionValidationError, "training_labels_hash_changed"):
            self.validate()


if __name__ == "__main__":
    unittest.main()
