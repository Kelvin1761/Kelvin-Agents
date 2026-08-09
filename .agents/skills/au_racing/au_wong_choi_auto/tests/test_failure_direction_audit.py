from __future__ import annotations

import sys
import unittest
from copy import deepcopy
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from au_failure_direction_audit import _ranked, analyze_races  # noqa: E402


def _row(number, score, pos, sp, matrix):
    return {
        "horse_number": number,
        "horse_name": f"Horse {number}",
        "score": score,
        "actual_pos": pos,
        "result_sp_label": sp,
        "matrix_scores": {"stability": matrix, "pace_perf": 60.0},
        "feature_scores": {"form_score": matrix, "rating_score": 60.0},
        "feature_evidence_state": {"form_score": "observed"},
    }


class FailureDirectionAuditTest(unittest.TestCase):
    def setUp(self):
        self.race = {
            "metadata": {
                "date": "2026-01-01", "track": "Randwick", "race_number": 1,
                "going": "Good 4", "field_size": 5,
            },
            "rows": [
                _row(1, 90, 5, 31.0, 90),
                _row(2, 80, 1, 5.0, 75),
                _row(3, 70, 4, 8.0, 65),
                _row(4, 60, 3, 10.0, 55),
                _row(5, 50, 2, 2.0, 40),
            ],
        }

    def test_finds_exact_cold_last_and_missed_favourite(self):
        report = analyze_races([self.race])
        cold = report["cohorts"]["model_top_big_odds_finished_last"]
        missed = report["cohorts"]["market_favourite_top3_but_model_low"]
        self.assertEqual([(row["horse_number"], row["model_rank"]) for row in cold], [(1, 1)])
        self.assertEqual([(row["horse_number"], row["model_rank"]) for row in missed], [(5, 5)])
        self.assertEqual(report["design"]["sp_role"], "post-score retrospective cohort label only")

    def test_market_price_cannot_change_model_ranking(self):
        changed = deepcopy(self.race["rows"])
        before = [row["horse_number"] for row in _ranked(changed)]
        for index, row in enumerate(changed):
            row["result_sp_label"] = 1000 - index * 100
        after = [row["horse_number"] for row in _ranked(changed)]
        self.assertEqual(before, after)

    def test_tail_two_is_a_separate_sensitivity_cohort(self):
        race = deepcopy(self.race)
        race["rows"][0]["actual_pos"] = 4
        race["rows"][2]["actual_pos"] = 5
        report = analyze_races([race])
        self.assertEqual(report["cohorts"]["model_top_big_odds_finished_last"], [])
        self.assertEqual(
            len(report["cohorts"]["model_top_big_odds_finished_tail_two"]), 1
        )


if __name__ == "__main__":
    unittest.main()
