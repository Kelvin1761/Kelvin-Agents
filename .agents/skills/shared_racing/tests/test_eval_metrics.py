from __future__ import annotations

import json
import subprocess
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
        # ⚠️ Gold is capture-at-4 since 2026-08-03: all three placegetters inside
        # the model's top FOUR picks. Races 2 and 3 place a runner at model rank 4,
        # so they are Gold now and were not before. The strict 3-of-3 reading is
        # still asserted below as `gold_strict`, which is what the old numbers used.
        races = [
            self._race({1: 1, 2: 2, 3: 3}),  # Gold + gold_strict
            self._race({1: 1, 2: 2, 4: 3}),  # Gold (3rd placegetter at rank 4)
            self._race({1: 1, 3: 2, 4: 3}),  # Gold, but only any-2 on the top three
            self._race({3: 1, 4: 2, 5: 3}),  # placegetter at rank 5 → not Gold
            self._race({4: 1, 5: 2}),        # miss for top-3 picks
        ]
        # HKJC and AU both have a top-level module named ``matrix_mapper``.
        # Exercise AU in a clean interpreter so parity never depends on which
        # racing stack pytest happened to import first.
        code = (
            "import json, sys\n"
            f"sys.path.insert(0, {str(AU_SCRIPTS)!r})\n"
            "from au_cached_walkforward_ml import metrics_for_races\n"
            "print(json.dumps(metrics_for_races(json.load(sys.stdin))))\n"
        )
        completed = subprocess.run(
            [sys.executable, "-c", code],
            input=json.dumps(races),
            text=True,
            capture_output=True,
            check=True,
        )
        metrics = json.loads(completed.stdout)
        self.assertEqual(metrics["races"], 5)
        self.assertEqual(metrics["gold"], 3)             # capture-at-4
        self.assertEqual(metrics["gold_strict"], 1)      # legacy 3-of-3
        self.assertEqual(metrics["good"], 3)  # any-2 (cumulative)
        self.assertEqual(metrics["good_positional"], 2)  # Gold + positional Good
        self.assertEqual(metrics["pass"], 4)
        self.assertEqual(
            metrics["exclusive_labels"],
            {"Gold": 3, "Good": 0, "Pass": 0, "1 Hit": 0, "Miss": 2},
        )

    def test_gold_is_capture_at_four_and_strict_gold_is_kept(self) -> None:
        """The two Gold readings must stay separable, and new ⊇ old.

        A race where the third placegetter is the model's 4th pick is the whole
        point of the change: nothing was missed, so it should not be graded the
        same as a race that dropped a placegetter outside the top four.
        """
        from eval_metrics import race_metrics

        at4 = race_metrics([1, 2, 3, 4], {1, 2, 4}, winner=1,
                           actual_pos={1: 1, 2: 2, 4: 3, 3: 5}, field_size=5)
        self.assertTrue(at4["gold"])
        self.assertFalse(at4["gold_strict"])
        self.assertEqual(at4["exclusive_label"], "Gold")

        at5 = race_metrics([1, 2, 3, 4, 5], {1, 2, 5}, winner=1,
                          actual_pos={1: 1, 2: 2, 5: 3, 3: 4, 4: 6}, field_size=6)
        self.assertFalse(at5["gold"])          # placegetter sits at rank 5
        self.assertTrue(at5["top3_all_within_top5"])
        self.assertEqual(at5["exclusive_label"], "Good")

        perfect = race_metrics([1, 2, 3], {1, 2, 3}, winner=1,
                               actual_pos={1: 1, 2: 2, 3: 3}, field_size=8)
        self.assertTrue(perfect["gold"] and perfect["gold_strict"])

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


class CompetitivenessTests(unittest.TestCase):
    """The top-3 KPIs are binary and score a top pick beaten a length into 4th
    identically to one that runs stone motherless last. These metrics record how
    wrong a miss was, normalised by field size so venues stay comparable."""

    def test_percentile_is_field_size_neutral(self) -> None:
        # 4th of 7 and 8th of 15 are the same relative run; raw position is not
        small = race_metrics([1], [9, 8, 7], winner=9,
                             actual_pos={1: 4, **{h: h for h in range(5, 8)}}, field_size=7)
        big = race_metrics([1], [9, 8, 7], winner=9,
                           actual_pos={1: 8}, field_size=15)
        self.assertAlmostEqual(small["top_pick_pct"], 0.5, places=6)
        self.assertAlmostEqual(big["top_pick_pct"], 0.5, places=6)

    def test_close_miss_and_blowout_are_distinguished(self) -> None:
        close = race_metrics([1, 2, 3], [4, 5, 6], winner=4,
                             actual_pos={1: 4, 2: 5, 3: 6}, field_size=13)
        blown = race_metrics([1, 2, 3], [4, 5, 6], winner=4,
                             actual_pos={1: 12, 2: 11, 3: 13}, field_size=13)
        # identical under every binary KPI ...
        for key in ("hits", "good_any2", "champion", "winner_in_top3", "exclusive_label"):
            self.assertEqual(close[key], blown[key])
        # ... and cleanly separated by competitiveness
        self.assertTrue(close["top_pick_competitive"])
        self.assertFalse(close["top_pick_blowout"])
        self.assertFalse(blown["top_pick_competitive"])
        self.assertTrue(blown["top_pick_blowout"])
        self.assertLess(close["mean_top3_pct"], blown["mean_top3_pct"])

    def test_winner_is_perfectly_competitive(self) -> None:
        row = race_metrics([1, 2, 3], [1, 2, 3], winner=1,
                           actual_pos={1: 1, 2: 2, 3: 3}, field_size=10)
        self.assertEqual(row["top_pick_pct"], 0.0)
        self.assertTrue(row["top2_both_competitive"])
        self.assertFalse(row["top2_any_blowout"])

    def test_absent_positions_leave_competitiveness_unscored(self) -> None:
        row = race_metrics([1, 2, 3], [1, 2, 3], winner=1)
        for key in ("top_pick_pct", "top_pick_competitive", "top2_both_competitive"):
            self.assertIsNone(row[key])
        # and such races must not be counted in the aggregate denominator
        summary = summarize_races([row])
        self.assertEqual(summary["competitiveness"]["top_pick_competitive"]["races"], 0)
        self.assertIsNone(summary["competitiveness"]["mean_top_pick_pct"])

    def test_summary_scores_only_races_with_positions(self) -> None:
        scored = race_metrics([1, 2, 3], [1, 2, 3], winner=1,
                              actual_pos={1: 1, 2: 2, 3: 3}, field_size=10)
        unscored = race_metrics([1, 2, 3], [1, 2, 3], winner=1)
        comp = summarize_races([scored, unscored])["competitiveness"]
        self.assertEqual(comp["top_pick_competitive"], {"races": 1, "count": 1, "rate": 1.0})
        self.assertEqual(comp["mean_top_pick_pct"], 0.0)

    def test_top3_capture_expands_from_four_to_five_picks(self) -> None:
        actual_pos = {1: 6, 2: 7, 3: 1, 4: 2, 5: 3, 6: 4, 7: 5}
        row = race_metrics(
            [1, 3, 2, 4, 5, 6, 7],
            [3, 4, 5],
            actual_pos=actual_pos,
            field_size=7,
        )
        self.assertEqual(row["top3_capture_at4_count"], 2)
        self.assertEqual(row["top3_capture_at5_count"], 3)
        self.assertAlmostEqual(row["top3_capture_at4"], 2 / 3)
        self.assertEqual(row["top3_capture_at5"], 1.0)
        self.assertFalse(row["top3_all_within_top4"])
        self.assertTrue(row["top3_all_within_top5"])
        self.assertEqual(row["actual_top3_model_ranks"], [2, 4, 5])
        self.assertAlmostEqual(row["top3_mean_model_rank"], 11 / 3)
        self.assertEqual(row["top3_worst_model_rank"], 5)

    def test_competitive_tier_recall_and_ndcg_reward_order(self) -> None:
        actual_pos = {horse: horse for horse in range(1, 13)}
        well_ordered = race_metrics(
            [1, 2, 3, 4, 9, 10, 11, 12, 5, 6, 7, 8],
            [1, 2, 3],
            actual_pos=actual_pos,
            field_size=12,
        )
        reversed_order = race_metrics(
            [4, 3, 2, 1, 9, 10, 11, 12, 5, 6, 7, 8],
            [1, 2, 3],
            actual_pos=actual_pos,
            field_size=12,
        )
        self.assertEqual(well_ordered["competitive_cutoff"], 4)
        self.assertEqual(well_ordered["competitive_recall_at5"], 1.0)
        self.assertEqual(well_ordered["competitive_precision_at5"], 0.8)
        self.assertEqual(well_ordered["ndcg_at5"], 1.0)
        self.assertLess(reversed_order["ndcg_at5"], well_ordered["ndcg_at5"])

    def test_summary_exposes_new_ranking_quality_metrics(self) -> None:
        actual_pos = {horse: horse for horse in range(1, 13)}
        row = race_metrics(
            list(range(1, 13)),
            [1, 2, 3],
            actual_pos=actual_pos,
            field_size=12,
        )
        summary = summarize_races([row])
        self.assertEqual(summary["counts"]["winner_in_top5"], 1)
        comp = summary["competitiveness"]
        self.assertEqual(comp["top3_all_within_top5"]["rate"], 1.0)
        self.assertEqual(comp["mean_top3_capture_at5"], 1.0)
        self.assertEqual(comp["mean_competitive_recall_at5"], 1.0)
        self.assertEqual(comp["mean_ndcg_at5"], 1.0)


if __name__ == "__main__":
    unittest.main()
