from __future__ import annotations

import sys
import unittest
from copy import deepcopy
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from au_failure_cause_attribution import (  # noqa: E402
    _cohort_members,
    _control_summary,
    _primary_label,
    _rank_lookup,
    _transition_counts,
)


class FailureCauseAttributionTest(unittest.TestCase):
    def setUp(self):
        self.race = {"rows": [
            {"horse_number": 1, "_score": 90.0, "pos": 5, "result_sp_label": 31.0},
            {"horse_number": 2, "_score": 80.0, "pos": 1, "result_sp_label": 5.0},
            {"horse_number": 3, "_score": 70.0, "pos": 4, "result_sp_label": 8.0},
            {"horse_number": 4, "_score": 60.0, "pos": 3, "result_sp_label": 10.0},
            {"horse_number": 5, "_score": 50.0, "pos": 2, "result_sp_label": 2.0},
        ]}

    def test_rank_lookup_uses_frozen_scores_and_horse_number_tiebreak(self):
        race = {"rows": [{"horse_number": 2}, {"horse_number": 1}]}
        self.assertEqual(_rank_lookup(race, {1: 70.0, 2: 70.0}), {1: 1, 2: 2})

    def test_direct_leaf_counterfactual_takes_precedence(self):
        self.assertEqual(
            _primary_label(
                "cold_last", "stability", {"performance_quality_score"}, True
            ),
            "performance_quality_relative_distortion",
        )

    def test_missing_rating_explains_class_weight_suppression(self):
        self.assertEqual(
            _primary_label(
                "favourite_missed", "class_weight", {"rating_score"}, False
            ),
            "class_weight_evidence_gap",
        )

    def test_cohort_labels_are_applied_after_custom_score_ranking(self):
        cohorts = _cohort_members([self.race], lambda row: row["_score"])
        self.assertEqual(len(cohorts["cold_last"]), 1)
        self.assertEqual(len(cohorts["favourite_missed"]), 1)

    def test_market_price_change_does_not_change_score_order(self):
        changed = deepcopy(self.race)
        before = _rank_lookup(
            self.race,
            {row["horse_number"]: row["_score"] for row in self.race["rows"]},
        )
        for index, row in enumerate(changed["rows"]):
            row["result_sp_label"] = 1000.0 - index
        after = _rank_lookup(
            changed,
            {row["horse_number"]: row["_score"] for row in changed["rows"]},
        )
        self.assertEqual(before, after)

    def test_transition_counts_separate_fixed_and_new_failures(self):
        before = {
            "cold_last": {"a": {}},
            "favourite_missed": {"b": {}, "c": {}},
        }
        after = {
            "cold_last": {"d": {}},
            "favourite_missed": {"c": {}},
        }
        report = _transition_counts(before, after)
        self.assertEqual(report["cold_last"]["original_failures_fixed"], 1)
        self.assertEqual(report["cold_last"]["new_failures_created"], 1)
        self.assertEqual(report["favourite_missed"]["original_failures_fixed"], 1)

    def test_control_summary_exposes_sample_going_interaction(self):
        item = {
            "row": {
                "raw_pre_race": {"formal_count": 2},
                "features": {},
                "feature_evidence_state": {},
                "data_coverage": {"coverage_pct": 80},
            },
            "going": "soft",
            "matrix_deltas": {
                "stability": 1.0,
                "pace_perf": -1.0,
                "race_shape": 2.0,
                "jockey_trainer": 1.0,
                "class_weight": -1.0,
                "track": 1.0,
            },
        }
        summary = _control_summary([item])
        self.assertEqual(summary["formal_going_counts"], {"1-2|soft": 1})
        self.assertEqual(summary["ability_corroboration_counts"], {"3": 1})
        self.assertEqual(
            summary["matrix_field_delta_by_formal_band"]["1-2"]["race_shape"],
            2.0,
        )


if __name__ == "__main__":
    unittest.main()
