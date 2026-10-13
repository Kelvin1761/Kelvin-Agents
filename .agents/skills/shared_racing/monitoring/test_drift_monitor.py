"""Tests for read-only provenance, incomplete cohorts and advisory isolation."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import drift_monitor as monitor

HOOK_PATH = monitor.REPO / ".agents/skills/shared_racing/post_success_hooks/scripts/drift_monitor_hook.py"
spec = importlib.util.spec_from_file_location("drift_test_hook", HOOK_PATH)
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


class MonitorTests(unittest.TestCase):
    def test_reader_preserves_missing_and_original_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "2026-10-13 Newcastle Race 1-8" / "Race_1_Logic.json"
            path.parent.mkdir()
            raw = json.dumps({"race_analysis": {"distance": "1200m", "going": "Soft 5"},
                              "horses": {"1": {"python_auto": {"feature_scores": {"form_score": 65}}}}}).encode()
            path.write_bytes(raw)
            rows, manifest = monitor.read_rows([path])
            self.assertEqual(rows[0]["venue"], "Newcastle")
            self.assertIsNone(rows[0]["trainer_score"])
            self.assertEqual(rows[0]["going_family"], "soft")
            self.assertEqual(path.read_bytes(), raw)
            self.assertEqual(len(manifest[0]["sha256"]), 64)
            with self.assertRaisesRegex(ValueError, "Duplicate race"):
                monitor.read_rows([path, path])

    def test_no_pooled_fallback_for_sparse_or_unknown_cohort(self):
        row = {"venue": "Newcastle", "distance_band": "sprint", "going_family": "good", "field_bucket": "<=8"}
        with patch.object(monitor, "compare", side_effect=AssertionError("Must not run")):
            self.assertEqual(monitor.cohort_report([row] * 100, [row] * 49)[0]["status"], "insufficient_data")
            unknown = dict(row, going_family="unknown")
            self.assertEqual(monitor.cohort_report([unknown] * 100, [unknown] * 50)[0]["status"], "insufficient_data")

    def test_hook_timeout_and_disabled_do_not_raise(self):
        with patch.dict("os.environ", {"WC_DISABLE_DRIFT_MONITOR": "1"}):
            self.assertEqual(hook.run_drift_advisory("au", Path("meeting"))["status"], "disabled")
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(hook, "REPO", Path(temp)), patch.object(Path, "is_file", return_value=True), \
                 patch.dict("os.environ", {"WC_DISABLE_DRIFT_MONITOR": "0"}), \
                 patch.object(hook.subprocess, "run", side_effect=hook.subprocess.TimeoutExpired("monitor", 60)):
                self.assertEqual(hook.run_drift_advisory("au", Path("meeting"))["status"], "unavailable")

    def test_added_offset_is_detected_but_missing_not_called_stable(self):
        rows = [{k: float(i % 25 + 45) for k in monitor.FEATURES} for i in range(150)]
        shifted = [dict(r, trainer_score=r["trainer_score"] + 4) for r in rows]
        fields = monitor.compare(rows, shifted)
        self.assertEqual(fields["trainer_score"]["status"], "drift")
        self.assertEqual(fields["form_score"]["status"], "stable")
        missing = [dict(r, trainer_score=None) for r in rows]
        self.assertEqual(monitor.compare(rows, missing)["trainer_score"]["status"], "insufficient_data")


if __name__ == "__main__":
    unittest.main()
