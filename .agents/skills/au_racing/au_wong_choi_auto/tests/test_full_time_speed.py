"""Prospective source availability, full-field scoring and replay contract."""

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from au_racing_engine.full_time_speed import (  # noqa:E402
    prepare_field,
    read_bundle,
    context_lookup,
    contribution,
    MODEL_VERSION,
    FULL_TIME_SPEED_GAIN,
)
from au_time_sources import publish_bundle  # noqa:E402
from au_racing_engine.engine_core import RacingEngine  # noqa:E402
from au_eval import default_scorer, configured_scorer  # noqa:E402
from au_racing_engine.validation import _validate_auto_namespace  # noqa:E402


def events():
    output = []
    for i in range(120):
        day = f"2026-08-{1 + i // 12:02}"
        key = ("ipswich", day, i % 12 + 1, 1200)
        rows = [
            {
                "horse": f"horse{j}",
                "distance": 1200,
                "time": 75 + j * 0.5,
                "key": key,
                "source": "https://www.racingqueensland.com.au/sample#R01.xml",
            }
            for j in range(3)
        ]
        output.append(
            {
                "key": key,
                "date": day,
                "track": "ipswich",
                "distance": 1200,
                "going": "good",
                "rating": "4",
                "rail": "0",
                "class": "BM64",
                "rows": rows,
                "total": 75.5,
            }
        )
    return output


class FullTimeTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.facts = self.root / "09-04 Race 1 Facts.md"
        self.bundle = self.root / "latest.json"
        publish_bundle(
            events(), [], self.bundle, valid_from="2026-09-04", now=datetime(2026, 9, 3, tzinfo=timezone.utc)
        )
        text = "RACE 1 — 1200m\n"
        for i in range(3):
            text += f"[{i + 1}] Horse{i} ({i + 1})\n"
            for e in reversed(events()[-6:]):
                text += f"Ipswich R{e['key'][2]} {e['date']} 1200m cond:Good4 margin:0\n"
            # Excluded before joining even if a trial identity happens to match.
            text += "Ipswich R1 2026-08-10 1200m cond:Good4 **(TRIAL)**\n"
        (self.root / "09-04 Race 1 Formguide.md").write_text(text)
        self.logic = {
            "race_analysis": {"race_number": 1, "date": "2026-09-04", "distance": 1200, "going": "Good 4"},
            "horses": {
                str(i + 1): {"horse_name": f"Horse{i}", "horse_number": str(i + 1), "barrier": i + 1, "_data": {}}
                for i in range(3)
            },
        }
        self.now = datetime(2026, 9, 4, tzinfo=timezone.utc)

    def tearDown(self):
        self.folder.cleanup()

    def prepare(self):
        return prepare_field(self.logic, self.facts, bundle_path=self.bundle, prediction_at=self.now)

    def test_engine_overlay_is_real_and_exported(self):
        audit = self.prepare()
        self.assertEqual((audit["status"], audit["covered"]), ("ready", 3))
        for horse in self.logic["horses"].values():
            result = RacingEngine(horse, self.logic["race_analysis"]).analyze_horse()
            baseline = deepcopy(self.logic["race_analysis"])
            baseline.pop("full_time_speed")
            old = RacingEngine(horse, baseline).analyze_horse()
            value = contribution(horse, self.logic["race_analysis"])
            self.assertEqual(result["ability_score"], round(old["ability_score"] + value, 4))
            self.assertEqual(result["full_time_speed_feature"], value)
            row = {
                "features": result["feature_scores"],
                "wet": result["wet_form_feature"],
                "proven_class": result["proven_class_feature"],
                "full_time": value,
            }
            self.assertAlmostEqual(default_scorer(row), result["ability_score"], places=3)
            self.assertAlmostEqual(configured_scorer()(row), result["ability_score"], places=3)
            self.assertEqual(_validate_auto_namespace("1", result), [])
        values = [h["full_time_speed"]["contribution"] for h in self.logic["horses"].values()]
        self.assertGreater(values[0], 0)
        self.assertLess(values[-1], 0)
        self.assertEqual(self.logic["horses"]["1"]["full_time_speed"]["runs"], 6)
        self.assertLess(abs(values[0]), 3 * FULL_TIME_SPEED_GAIN)

    def test_replay_uses_original_immutable_capture_after_latest_changes(self):
        audit = self.prepare()
        captured_name = audit["bundle_file"]
        publish_bundle(
            events(), [], self.bundle, valid_from="2026-09-04", now=datetime(2026, 9, 5, tzinfo=timezone.utc)
        )
        with patch("au_racing_engine.full_time_speed.default_bundle_path", return_value=self.bundle):
            replay = prepare_field(self.logic, self.facts, prediction_at=self.now)
        self.assertEqual(replay["status"], "ready")
        self.assertEqual(replay["bundle_file"], captured_name)
        self.assertEqual(replay["captured_at"], audit["captured_at"])

    def test_missing_source_clears_cached_overlay(self):
        self.prepare()
        audit = prepare_field(self.logic, self.facts, bundle_path=self.root / "missing.json", prediction_at=self.now)
        self.assertEqual(audit["status"], "missing_source")
        self.assertNotIn("full_time_speed", self.logic["horses"]["1"])

    def test_source_after_prediction_is_not_used(self):
        audit = prepare_field(
            self.logic, self.facts, bundle_path=self.bundle, prediction_at=datetime(2026, 9, 2, tzinfo=timezone.utc)
        )
        self.assertEqual(audit["status"], "not_available_at_prediction")
        self.assertEqual(audit["covered"], 0)

    def test_historical_predictions_are_not_rewritten(self):
        self.logic["race_analysis"]["date"] = "2026-08-30"
        self.assertEqual(self.prepare()["status"], "not_available_at_prediction")

    def test_corrupt_bundle_fails_closed(self):
        obj = json.loads(self.bundle.read_text())
        obj["events"][0]["total"] = 1
        self.bundle.write_text(json.dumps(obj))
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.prepare()

    def test_future_events_do_not_change_prior_transform(self):
        history = events()
        a, _ = context_lookup(history, "2026-09-04")
        future = deepcopy(history[0])
        future["date"] = "2026-09-04"
        future["total"] = 99999
        b, _ = context_lookup(history + [future], "2026-09-04")
        self.assertEqual(a, b)

    def test_missing_runner_stays_missing_in_field(self):
        self.logic["horses"]["3"]["horse_name"] = "No Matching Horse"
        self.prepare()
        detail = self.logic["horses"]["3"]["full_time_speed"]
        self.assertIsNone(detail["context_index"])
        self.assertEqual(detail["contribution"], 0)

    def test_ambiguous_formguide_horse_fails(self):
        path = self.root / "09-04 Race 1 Formguide.md"
        path.write_text(path.read_text() + "[8] Horse0 (8)\n")
        with self.assertRaisesRegex(ValueError, "ambiguous horse"):
            self.prepare()

    def test_unprepared_or_wrong_hash_overlay_is_neutral(self):
        horse = {
            "full_time_speed": {
                "status": "observed",
                "model_version": MODEL_VERSION,
                "source_hash": "wrong",
                "contribution": 100,
            }
        }
        self.assertEqual(contribution(horse, {}), 0)
        self.prepare()
        self.assertEqual(contribution(horse, self.logic["race_analysis"]), 0)


if __name__ == "__main__":
    unittest.main()


class ActiveSourceFailureTests(unittest.TestCase):
    def test_active_model_missing_whole_cache_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            logic = {"race_analysis": {"date": "2026-10-16", "race_number": 1}, "horses": {}}
            with self.assertRaisesRegex(FileNotFoundError, "refusing to publish"):
                prepare_field(logic, Path(folder) / "Facts.md", bundle_path=Path(folder) / "missing.json")
