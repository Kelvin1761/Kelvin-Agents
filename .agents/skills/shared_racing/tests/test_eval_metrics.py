from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SHARED = ROOT / ".agents" / "skills" / "shared_racing"
AU_SCRIPTS = ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts"
HKJC_REFLECTOR_SCRIPTS = ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_reflector" / "scripts"

for path in (SHARED, AU_SCRIPTS, HKJC_REFLECTOR_SCRIPTS, SHARED / "race_reflector" / "scripts"):
    sys.path.insert(0, str(path))

from eval_metrics import exclusive_label, race_metrics, summarize_races, build_manifest


class ExclusiveLabelTests(unittest.TestCase):
    def test_label_ladder(self) -> None:
        self.assertEqual(exclusive_label(3, 2), "Gold")
        self.assertEqual(exclusive_label(2, 2), "Good")
        self.assertEqual(exclusive_label(2, 1), "Pass")
        self.assertEqual(exclusive_label(1, 1), "1 Hit")
        self.assertEqual(exclusive_label(0, 0), "Miss")

    def test_pick3_only_hit_is_miss(self) -> None:
        # Reflector semantics: a hit only on the model's 3rd pick counts as Miss.
        self.assertEqual(exclusive_label(1, 0), "Miss")


class RaceMetricsTests(unittest.TestCase):
    def test_positional_vs_any2_good_diverge(self) -> None:
        # Picks 1 and 3 hit: any-2 Good yes, positional Good no.
        row = race_metrics([7, 2, 5], [7, 5, 9], winner=9)
        self.assertTrue(row["good_any2"])
        self.assertFalse(row["good_positional"])
        self.assertEqual(row["exclusive_label"], "Pass")
        self.assertFalse(row["winner_in_top3"])

    def test_champion_and_winner_rank(self) -> None:
        actual_pos = {4: 1, 8: 2, 1: 3, 6: 4}
        row = race_metrics([4, 8, 1, 6], [4, 8, 1], actual_pos=actual_pos)
        self.assertTrue(row["gold"])
        self.assertTrue(row["champion"])
        self.assertEqual(row["winner_rank"], 1)
        self.assertEqual(row["exclusive_label"], "Gold")

    def test_dead_heat_winner_counts_for_champion(self) -> None:
        actual_pos = {4: 1, 8: 1, 1: 3, 6: 4}
        row = race_metrics([8, 6, 5], [4, 8, 1], actual_pos=actual_pos)
        self.assertTrue(row["champion"])
        self.assertTrue(row["winner_in_top3"])
        self.assertEqual(row["winner_rank"], 1)

    def test_summary_counts_and_labels(self) -> None:
        rows = [
            race_metrics([1, 2, 3], [1, 2, 3], winner=1),  # Gold
            race_metrics([1, 2, 3], [1, 2, 9], winner=9),  # Good (positional)
            race_metrics([1, 2, 3], [1, 3, 9], winner=9),  # Pass (any-2 only)
            race_metrics([1, 2, 3], [2, 8, 9], winner=9),  # 1 Hit
            race_metrics([1, 2, 3], [7, 8, 9], winner=9),  # Miss
        ]
        summary = summarize_races(rows)
        self.assertEqual(summary["races"], 5)
        self.assertEqual(summary["counts"]["gold"], 1)
        self.assertEqual(summary["counts"]["good_positional"], 2)  # Gold + Good
        self.assertEqual(summary["counts"]["good_any2"], 3)  # Gold + Good + Pass
        self.assertEqual(summary["counts"]["pass_any1"], 4)
        self.assertEqual(
            summary["exclusive_labels"],
            {"Gold": 1, "Good": 1, "Pass": 1, "1 Hit": 1, "Miss": 1},
        )

    def test_manifest_hash_is_order_independent(self) -> None:
        left = build_manifest([("m1", 1), ("m1", 2)], dates=["2026-07-01", "2026-06-30"], meetings=["m1"])
        right = build_manifest([("m1", 2), ("m1", 1)], dates=["2026-06-30", "2026-07-01"], meetings=["m1"])
        self.assertEqual(left["sample_hash"], right["sample_hash"])
        self.assertEqual(left["race_count"], 2)
        self.assertEqual(left["date_range"], ["2026-06-30", "2026-07-01"])


class HkjcParityTests(unittest.TestCase):
    """The HKJC walk-forward evaluator must agree with the canonical ruler."""

    def test_evaluate_model_matches_canonical(self) -> None:
        from walk_forward_auto_backtest import evaluate_model

        scored = [
            {"horse_num": 1, "prod": 71.0},
            {"horse_num": 2, "prod": 70.0},
            {"horse_num": 3, "prod": 66.0},
            {"horse_num": 4, "prod": 64.0},
            {"horse_num": 5, "prod": 60.0},
        ]
        cases = [
            {1: 1, 2: 2, 3: 3, 4: 4, 5: 5},  # Gold
            {1: 1, 2: 2, 3: 9, 4: 3, 5: 5},  # positional Good, any-2 Good
            {1: 1, 2: 9, 3: 2, 4: 4, 5: 5},  # any-2 Good only
            {1: 9, 2: 8, 3: 1, 4: 4, 5: 5},  # pick-3-only hit
            {1: 9, 2: 8, 3: 7, 4: 1, 5: 2},  # miss
        ]
        for actual_pos in cases:
            actual_top3 = [horse for horse, pos in actual_pos.items() if pos <= 3]
            legacy = evaluate_model(scored, actual_pos, actual_top3, "prod")
            canonical = race_metrics(legacy["picks"], actual_top3, actual_pos=actual_pos)
            self.assertEqual(legacy["gold"], canonical["gold"])
            self.assertEqual(legacy["good"], canonical["good_positional"])
            self.assertEqual(legacy["min_threshold"], canonical["good_any2"])
            self.assertEqual(legacy["single"], canonical["pass_any1"])
            self.assertEqual(legacy["champion"], canonical["champion"])
            self.assertEqual(legacy["top3_has_champion"], canonical["winner_in_top3"])
            self.assertEqual(legacy["exclusive_label"], canonical["exclusive_label"])


class AuParityTests(unittest.TestCase):
    """The AU cached walk-forward evaluator must agree with the canonical ruler."""

    def _race(self, positions: dict[int, int]) -> list[dict]:
        scores = {1: 71.0, 2: 70.0, 3: 66.0, 4: 64.0, 5: 60.0}
        return [
            {"horse_number": horse, "_score": scores[horse], "actual_pos": positions.get(horse, 9)}
            for horse in scores
        ]

    def test_metrics_for_races_matches_canonical(self) -> None:
        from au_cached_walkforward_ml import metrics_for_races

        races = [
            self._race({1: 1, 2: 2, 3: 3}),  # Gold
            self._race({1: 1, 2: 2, 4: 3}),  # positional Good
            self._race({1: 1, 3: 2, 4: 3}),  # any-2 Good only
            self._race({3: 1, 4: 2, 5: 3}),  # pick-3-only hit → exclusive Miss
            self._race({4: 1, 5: 2}),        # miss for top-3 picks
        ]
        metrics = metrics_for_races(races)
        self.assertEqual(metrics["races"], 5)
        self.assertEqual(metrics["gold"], 1)
        self.assertEqual(metrics["good"], 3)  # any-2 (cumulative)
        self.assertEqual(metrics["good_positional"], 2)  # Gold + positional Good
        self.assertEqual(metrics["pass"], 4)
        self.assertEqual(
            metrics["exclusive_labels"],
            {"Gold": 1, "Good": 1, "Pass": 1, "1 Hit": 0, "Miss": 2},
        )

    def test_reflector_label_parity(self) -> None:
        from unified_reflector_core import performance_label_from_rows

        model_top3 = [{"horse_no": 1}, {"horse_no": 2}, {"horse_no": 3}]
        cases = [
            ([1, 2, 3], "Gold"),
            ([1, 2, 9], "Good"),
            ([1, 3, 9], "Pass"),
            ([2, 8, 9], "1 Hit"),
            ([3, 8, 9], "Miss"),  # pick-3-only hit
            ([7, 8, 9], "Miss"),
        ]
        for actual, expected in cases:
            actual_rows = [{"horse_no": horse} for horse in actual]
            self.assertEqual(performance_label_from_rows(model_top3, actual_rows), expected)
            canonical = race_metrics([1, 2, 3], actual, winner=actual[0])
            self.assertEqual(canonical["exclusive_label"], expected)


if __name__ == "__main__":
    unittest.main()
