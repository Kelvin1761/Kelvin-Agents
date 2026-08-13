from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from au_ml_rebuild import build_commands  # noqa: E402


class AuMlRebuildTests(unittest.TestCase):
    def test_build_commands_is_strict_and_keeps_market_out_of_training_args(self) -> None:
        commands, outputs = build_commands(
            python="python-test",
            archive_root=Path("/archive"),
            results_csv=Path("/results.csv"),
            work_dir=Path("/work"),
            report_dir=Path("/reports"),
        )
        self.assertEqual(len(commands), 3)
        self.assertIn("--require-complete", commands[0])
        self.assertIn("--results-csv", commands[0])
        self.assertNotIn("--results-csv", commands[2])
        self.assertEqual(outputs["experiment_report"], Path("/reports/au_ml_experiment_report.md"))


if __name__ == "__main__":
    unittest.main()
