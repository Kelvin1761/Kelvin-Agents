from __future__ import annotations

import sys
import unittest
from copy import deepcopy
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from au_sportsbet_performance_quality_candidate import (  # noqa: E402
    attach_candidate,
    candidate_scorer,
)


def _row(number, name, raw):
    return {
        "horse_number": number,
        "horse_name": name,
        "features": {
            "performance_quality_score": 60.0,
            "consistency_score": 60.0,
        },
        "wet": 0.0,
        "feature_evidence_state": {"performance_quality_score": "fallback"},
        "result_sp_label": 2.0,
        "_raw": raw,
    }


class SportsbetQualityCandidateTest(unittest.TestCase):
    def test_market_price_is_not_a_scorer_input(self):
        row = _row(1, "Test Horse", 1.0)
        row["_sb_performance_quality_score"] = 80.0
        scorer = candidate_scorer(0.5)
        before = scorer(row)
        changed = deepcopy(row)
        changed["result_sp_label"] = 1001.0
        self.assertEqual(before, scorer(changed))

    def test_field_relative_scores_require_three_complete_runners(self):
        race = {
            "date": "2026-08-09",
            "metadata": {
                "date": "2026-08-09", "track": "Randwick", "race_number": 1,
            },
            "rows": [
                _row(1, "Horse One", -1.0),
                _row(2, "Horse Two", 0.0),
                _row(3, "Horse Three", 1.0),
            ],
        }
        quality = {
            ("2026-08-09", "randwick", 1, "horseone"): {"raw": -1.0, "run_count": 2},
            ("2026-08-09", "randwick", 1, "horsetwo"): {"raw": 0.0, "run_count": 3},
            ("2026-08-09", "randwick", 1, "horsethree"): {"raw": 1.0, "run_count": 4},
        }
        counts = attach_candidate([race], quality)
        self.assertEqual(counts["race_field_gate_passed"], 1)
        self.assertEqual(counts["runner_fillable"], 3)
        scores = [row["_sb_performance_quality_score"] for row in race["rows"]]
        self.assertLess(scores[0], scores[1])
        self.assertLess(scores[1], scores[2])


if __name__ == "__main__":
    unittest.main()
