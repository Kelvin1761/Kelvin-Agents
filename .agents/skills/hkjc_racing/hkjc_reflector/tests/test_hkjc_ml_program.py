from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_reflector" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from hkjc_ml_program import (  # noqa: E402
    _coherent_win_probabilities,
    assert_leakage_safe,
    clean_archive,
)


class HkjcMlProgramTests(unittest.TestCase):
    @staticmethod
    def _race(date: str, meeting: str, race_number: int, runners: int) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "meeting": [meeting] * runners,
                "meeting_name": [meeting] * runners,
                "date": [date] * runners,
                "race_number": [race_number] * runners,
                "venue": ["沙田AWT"] * runners,
                "track": ["Turf"] * runners,
                "course": ["1200米"] * runners,
                "distance": ["1200"] * runners,
                "distance_num": [1200] * runners,
                "race_class": ["第四班"] * runners,
                "race_class_label": ["Unknown"] * runners,
                "field_size": [14] * runners,
                "horse_number": list(range(1, runners + 1)),
                "horse_name": [f"馬{i}" for i in range(1, runners + 1)],
                "horse_id": [f"K{i:03d}" for i in range(1, runners + 1)],
                "finish_pos": list(range(1, runners + 1)),
            }
        )

    def test_clean_archive_repairs_alignment_and_place_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            primary = root / "primary.csv"
            external = root / "external.csv"
            self._race("2026-07-12", "2026-07-12_ShaTin", 1, 6).to_csv(primary, index=False)
            self._race("2026-07-15", "2026-07-15_HappyValley", 1, 7).to_csv(external, index=False)
            data, quality = clean_archive(primary, external)

        first = data[data["date"] == "2026-07-12"]
        second = data[data["date"] == "2026-07-15"]
        self.assertEqual(first["field_size"].unique().tolist(), [6])
        self.assertEqual(first["place_cutoff"].unique().tolist(), [2])
        self.assertEqual(int(first["is_place"].sum()), 2)
        self.assertEqual(second["place_cutoff"].unique().tolist(), [3])
        self.assertEqual(int(second["is_place"].sum()), 3)
        self.assertEqual(first["venue"].unique().tolist(), ["沙田"])
        self.assertEqual(second["venue"].unique().tolist(), ["跑馬地"])
        self.assertEqual(first["track"].unique().tolist(), ["AWT"])
        self.assertEqual(first["race_class_label"].unique().tolist(), ["Class 4"])
        self.assertEqual(quality["declared_actual_field_mismatch_races"], 2)

    def test_leakage_blacklist_rejects_static_priors_and_odds(self) -> None:
        with self.assertRaises(ValueError):
            assert_leakage_safe(["matrix_sectional", "prior_combo_win_rate"])
        with self.assertRaises(ValueError):
            assert_leakage_safe(["win_odds"])

    def test_non_contiguous_finish_order_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            primary = root / "primary.csv"
            external = root / "external.csv"
            broken = self._race("2026-07-12", "2026-07-12_ShaTin", 1, 6)
            broken["finish_pos"] = [1, 2, 3, 4, 7, 8]
            broken.to_csv(primary, index=False)
            self._race("2026-07-15", "2026-07-15_HappyValley", 1, 7).to_csv(external, index=False)
            data, quality = clean_archive(primary, external)
        self.assertEqual(quality["valid_races"], 1)
        self.assertEqual(len(quality["invalid_races"]), 1)
        self.assertEqual(data["date"].unique().tolist(), ["2026-07-15"])

    def test_win_probabilities_sum_to_one_within_race(self) -> None:
        frame = pd.DataFrame(
            {
                "race_key": ["A", "A", "B", "B", "B"],
                "field_size": [2, 2, 3, 3, 3],
            }
        )
        probabilities = _coherent_win_probabilities(
            frame, np.array([0.4, 0.2, 0.6, 0.3, 0.1])
        )
        totals = pd.Series(probabilities).groupby(frame["race_key"]).sum()
        np.testing.assert_allclose(totals.to_numpy(), np.ones(2))


if __name__ == "__main__":
    unittest.main()
