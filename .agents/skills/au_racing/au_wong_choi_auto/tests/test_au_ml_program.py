from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from au_ml_program import (  # noqa: E402
    _market_status_labels,
    _promotion_gate,
    _race_normalize,
    _race_confidence_labels,
    chronological_holdout,
    make_preprocessor,
    walkforward_splits,
)


class AuMlProgramTests(unittest.TestCase):
    def _frame(self) -> pd.DataFrame:
        rows = []
        for day in range(1, 11):
            for race in range(1, 3):
                for horse in range(1, 5):
                    rows.append(
                        {
                            "date": pd.Timestamp(f"2026-01-{day:02d}"),
                            "race_id": f"2026-01-{day:02d}|Track|R{race}",
                            "place_slots": 1,
                            "horse_number": horse,
                        }
                    )
        return pd.DataFrame(rows)

    def test_chronological_holdout_keeps_whole_dates_and_races(self) -> None:
        development, holdout, _meta = chronological_holdout(self._frame(), fraction=0.2)
        self.assertLess(development["date"].max(), holdout["date"].min())
        self.assertFalse(set(development["race_id"]) & set(holdout["race_id"]))

    def test_walkforward_validation_is_strictly_after_training(self) -> None:
        for train, valid, _meta in walkforward_splits(self._frame(), folds=3):
            self.assertLess(train["date"].max(), valid["date"].min())
            self.assertFalse(set(train["race_id"]) & set(valid["race_id"]))

    def test_race_probability_mass_is_normalized(self) -> None:
        frame = self._frame().iloc[:8].reset_index(drop=True)
        win = _race_normalize(frame, np.repeat(0.4, len(frame)), "win")
        place = _race_normalize(frame, np.repeat(0.6, len(frame)), "place")
        for race_id, indexes in frame.groupby("race_id").groups.items():
            _ = race_id
            self.assertAlmostEqual(float(win[list(indexes)].sum()), 1.0, places=6)
            self.assertAlmostEqual(float(place[list(indexes)].sum()), 1.0, places=6)

    def test_confidence_segment_keeps_each_race_whole(self) -> None:
        frame = self._frame().iloc[:8].reset_index(drop=True)
        frame["source_coverage_pct"] = [60, 80, 90, 100, 65, 75, 85, 95]
        labels = _race_confidence_labels(frame)
        for indexes in frame.groupby("race_id").groups.values():
            self.assertEqual(len(set(labels[list(indexes)])), 1)

    def test_preprocessor_keeps_feature_that_is_empty_in_early_window(self) -> None:
        preprocessor = make_preprocessor("xgboost", ["empty", "seen"], [])
        transformed = preprocessor.fit_transform(
            pd.DataFrame({"empty": [np.nan, np.nan], "seen": [1.0, 2.0]})
        )
        self.assertGreaterEqual(transformed.shape[1], 2)

    def test_market_status_is_post_prediction_race_relative(self) -> None:
        frame = self._frame().iloc[:8].reset_index(drop=True)
        frame["market_sp_label"] = [3.0, 5.0, 8.0, 3.0, 2.0, 4.0, np.nan, 9.0]
        labels = _market_status_labels(frame)
        self.assertEqual(labels.iloc[0], "Favourite/TiedFavourite")
        self.assertEqual(labels.iloc[3], "Favourite/TiedFavourite")
        self.assertEqual(labels.iloc[6], "MarketUnavailable")

    def test_promotion_gate_requires_all_analysis_and_betting_checks(self) -> None:
        champion = {
            "win_brier": 0.10, "place_brier": 0.20,
            "win_log_loss": 0.30, "place_log_loss": 0.50,
            "top1": 0.20, "top3": 0.50, "place_precision": 0.40,
        }
        candidate = {
            "win_brier": 0.09, "place_brier": 0.19,
            "win_log_loss": 0.29, "place_log_loss": 0.49,
            "top1": 0.21, "top3": 0.51, "place_precision": 0.41,
        }
        bootstrap = {
            "win_brier_improvement": {"ci95": [0.001, 0.01]},
            "place_brier_improvement": {"ci95": [-0.001, 0.01]},
        }
        periods = [
            {"metrics": {"champion": champion, "candidate": candidate}}
            for _ in range(5)
        ]
        gate = _promotion_gate(
            champion, candidate, bootstrap, periods, "candidate",
            {"roi": 0.01}, {"roi": -0.03},
        )
        self.assertTrue(gate["passed"])
        failed = _promotion_gate(
            champion, candidate, bootstrap, periods, "candidate",
            {"roi": 0.01}, {"roi": -0.05},
        )
        self.assertFalse(failed["betting_not_materially_worse"])
        self.assertFalse(failed["passed"])


if __name__ == "__main__":
    unittest.main()
