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
    add_race_confidence,
    _coherent_win_probabilities,
    assert_leakage_safe,
    calibration_curve_rows,
    clean_archive,
    feature_dictionary,
    metrics,
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

    def test_race_confidence_is_probability_gap_and_does_not_change_rank(self) -> None:
        frame = pd.DataFrame(
            {
                "race_key": ["A", "A", "A", "B", "B"],
                "probability": [0.40, 0.34, 0.26, 0.51, 0.49],
            }
        )
        enriched = add_race_confidence(frame)
        np.testing.assert_allclose(enriched.loc[:2, "race_confidence_score"], 0.06)
        np.testing.assert_allclose(enriched.loc[3:, "race_confidence_score"], 0.02)
        self.assertEqual(enriched.loc[0, "race_confidence_band"], "High ≥5pp")
        self.assertEqual(enriched.loc[3, "race_confidence_band"], "Medium 2–5pp")
        self.assertListEqual(
            enriched.sort_values(["race_key", "probability"], ascending=[True, False]).index.tolist(),
            frame.sort_values(["race_key", "probability"], ascending=[True, False]).index.tolist(),
        )

    def test_ranking_metrics_include_average_ranks_and_correlation(self) -> None:
        frame = pd.DataFrame(
            {
                "race_key": ["A"] * 4,
                "horse_number": [1, 2, 3, 4],
                "finish_pos": [1, 2, 3, 4],
                "is_win": [1, 0, 0, 0],
                "is_top3": [1, 1, 1, 0],
                "is_place": [1, 1, 1, 0],
                "place_cutoff": [3] * 4,
                "probability": [0.4, 0.3, 0.2, 0.1],
            }
        )
        result = metrics(frame, "probability", "Win")
        self.assertEqual(result["winner_average_rank"], 1.0)
        self.assertEqual(result["placegetter_average_rank"], 2.0)
        self.assertAlmostEqual(result["ranking_correlation"], 1.0)

    def test_feature_dictionary_has_readiness_coverage_fields(self) -> None:
        frame = pd.DataFrame(
            {
                "date": ["2026-07-12", "2026-07-15"],
                "matrix_stability": [60.0, 70.0],
                "venue": ["沙田", "跑馬地"],
            }
        )
        dictionary = feature_dictionary(
            frame,
            {"test": (["matrix_stability"], ["venue"])},
        )
        required = {
            "coverage_rate",
            "missing_rate",
            "neutral_default_rate",
            "unique_values",
            "suspicious_values",
            "historical_depth_days",
        }
        self.assertTrue(required.issubset(dictionary.columns))
        stability = dictionary[dictionary["feature"] == "matrix_stability"].iloc[0]
        self.assertEqual(stability["neutral_default_rate"], 0.5)

    def test_calibration_curve_uses_fixed_bins(self) -> None:
        frame = pd.DataFrame(
            {
                "race_key": ["A", "A", "B"],
                "probability": [0.05, 0.15, 0.85],
                "is_win": [0, 1, 1],
            }
        )
        rows = calibration_curve_rows(frame, "Test", "Win", "walk_forward")
        self.assertEqual(sum(row["runners"] for row in rows), 3)
        self.assertTrue(all(row["period"] == "walk_forward" for row in rows))


if __name__ == "__main__":
    unittest.main()
