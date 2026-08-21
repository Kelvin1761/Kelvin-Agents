from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = (
    ROOT
    / ".agents"
    / "skills"
    / "au_racing"
    / "au_wong_choi_auto"
    / "scripts"
)
ENGINE = SCRIPTS / "au_racing_engine"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ENGINE.parent))

from au_archive_calibrator import load_historical_results


class HistoricalResultAlignmentTests(unittest.TestCase):
    def test_corrupt_track_race_is_quarantined_without_losing_valid_track(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "results.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "Date",
                        "Track",
                        "Race",
                        "Horse",
                        "Pos",
                        "Barrier",
                        "SP",
                        "Condition",
                    ],
                )
                writer.writeheader()
                for number in range(1, 6):
                    writer.writerow(
                        {
                            "Date": "2026-01-01",
                            "Track": "Broken Track",
                            "Race": 1,
                            "Horse": f"Broken {number}",
                            "Pos": 8,
                        }
                    )
                    writer.writerow(
                        {
                            "Date": "2026-01-01",
                            "Track": "Valid Track",
                            "Race": 1,
                            "Horse": f"Valid {number}",
                            "Pos": number,
                        }
                    )

            rows = load_historical_results(path)[("2026-01-01", 1)]
            self.assertEqual({row["track"] for row in rows}, {"Valid Track"})
            self.assertEqual([row["pos"] for row in rows], [1, 2, 3, 4, 5])

    def test_dead_heat_top_three_is_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "results.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "Date",
                        "Track",
                        "Race",
                        "Horse",
                        "Pos",
                        "Barrier",
                        "SP",
                        "Condition",
                    ],
                )
                writer.writeheader()
                for number, position in enumerate((1, 1, 3, 4), 1):
                    writer.writerow(
                        {
                            "Date": "2026-01-02",
                            "Track": "Valid Track",
                            "Race": 2,
                            "Horse": f"Horse {number}",
                            "Pos": position,
                        }
                    )
            rows = load_historical_results(path)[("2026-01-02", 2)]
            self.assertEqual(len(rows), 4)


if __name__ == "__main__":
    unittest.main()
