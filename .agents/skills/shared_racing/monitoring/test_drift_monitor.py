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

    def _runs(self, root, now, ages):
        from datetime import timedelta
        made = {}
        for age in ages:
            stamp = (now - timedelta(days=age)).strftime(hook.STAMP_FORMAT) + "-abcd1234"
            run = root / "au" / "2026-11-01 Rosehill Race 1-8" / stamp
            run.mkdir(parents=True)
            (run / "drift.json").write_text("{}")
            made[age] = run
        return made

    def test_retention_moves_old_reports_to_mounted_archive(self):
        from datetime import datetime, timezone
        now = datetime(2026, 11, 19, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as temp:
            root, archive = Path(temp) / "drift", Path(temp) / "archive"
            runs = self._runs(root, now, [0, 2, 5, 40])
            with patch.object(hook, "_mounted", return_value=True):
                result = hook.prune_old_reports(root, archive, now)
            self.assertEqual(result["moved"], 2)
            self.assertTrue(runs[0].is_dir() and runs[2].is_dir())
            self.assertFalse(runs[5].exists())
            self.assertTrue((archive / runs[5].relative_to(root) / "drift.json").is_file())
            self.assertTrue((archive / runs[40].relative_to(root) / "drift.json").is_file())

    def test_retention_without_disk_keeps_month_then_drops(self):
        from datetime import datetime, timezone
        now = datetime(2026, 11, 19, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as temp:
            root, archive = Path(temp) / "drift", Path("/Volumes/not-a-real-disk-xyz/WongChoi-Archive")
            runs = self._runs(root, now, [1, 10, 31])
            result = hook.prune_old_reports(root, archive, now)
            self.assertEqual((result["moved"], result["kept_unmounted"], result["deleted"]), (0, 1, 1))
            self.assertTrue(runs[1].is_dir() and runs[10].is_dir())
            self.assertFalse(runs[31].exists())
            self.assertFalse(archive.exists())

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
