"""Sparse neutral evidence must not trip the constant-field publication gate."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from data_contract import check


class SparseContractTests(unittest.TestCase):
    def violations(self, value, neutral_rate=0.6503, platform="au"):
        baseline = {"fields": {"preparation_score": {
            "neutral_rate": neutral_rate, "mean_within_race_spread": 1.2844,
            "min": 60.0, "max": 64.38}}}
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for race in range(6):
                path = Path(tmp) / f"Race_{race + 1}_Logic.json"
                path.write_text(json.dumps({"horses": {
                    str(i): {"python_auto": {"feature_scores": {
                        "preparation_score": value}}} for i in range(7)}}))
                paths.append(str(path))
            return check(baseline, paths, platform)[0]

    def test_sparse_all_neutral_warns_without_blocking(self):
        for platform in ("au", "hkjc"):
            violations = self.violations(60, platform=platform)
            self.assertTrue(any(v.check == "spread" for v in violations))
            self.assertTrue(all(v.severity == "warning" for v in violations))

    def test_normally_populated_field_still_blocks(self):
        violations = self.violations(60, neutral_rate=0.025)
        self.assertTrue(any(v.check == "dead-field" and v.severity == "error"
                            for v in violations))

    def test_boundary_is_still_normally_populated(self):
        self.assertTrue(any(v.check == "dead-field" and v.severity == "error"
                            for v in self.violations(60, neutral_rate=0.2)))

    def test_constant_non_neutral_still_blocks(self):
        self.assertTrue(any(v.check == "dead-field" and v.severity == "error"
                            for v in self.violations(63)))

    def test_missing_baseline_rate_does_not_disable_constant_gate(self):
        self.assertTrue(any(v.check == "dead-field" and v.severity == "error"
                            for v in self.violations(60, neutral_rate=None)))
