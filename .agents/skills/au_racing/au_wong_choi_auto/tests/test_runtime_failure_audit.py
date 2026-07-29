import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
ENGINE = SCRIPTS / "racing_engine"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ENGINE))

from au_runtime_failure_audit import PRIMARY_MATRIX_KEYS, analyze_race


def _row(number: int, score: float, actual_pos: int) -> dict:
    matrices = {key: 60.0 for key in PRIMARY_MATRIX_KEYS}
    if number == 6:
        matrices["stability"] = 50.0
    return {
        "horse_number": number,
        "horse_name": f"Horse {number}",
        "score": score,
        "actual_pos": actual_pos,
        "result_sp_label": 10.0,
        "matrix_scores": matrices,
        "feature_scores": {"form_score": 60.0},
        "feature_evidence_state": {"form_score": "observed"},
        "data_coverage": {"coverage_pct": 100},
        "reason_codes": [],
        "risk_flags": [],
    }


class RuntimeFailureAuditTests(unittest.TestCase):
    def test_failure_cohorts_and_score_compression(self):
        race = [
            _row(1, 66.0, 6),
            _row(2, 65.0, 7),
            _row(3, 64.0, 8),
            _row(4, 63.0, 3),
            _row(5, 62.0, 2),
            _row(6, 61.0, 1),
        ]
        result = analyze_race(
            {
                "date": "2026-01-01",
                "track": "Test",
                "race_number": 1,
                "distance": 1200,
                "going": "Good 4",
                "race_class": "BM70",
                "field_size": 6,
            },
            race,
        )
        self.assertEqual(result["hits_top3"], 0)
        self.assertEqual(result["hits_top5"], 2)
        self.assertEqual(result["winner_rank"], 6)
        self.assertEqual(len(result["underrated"]), 1)
        self.assertEqual(len(result["overrated"]), 3)
        self.assertTrue(result["separation"]["compressed_sd_lt_2"])
        self.assertEqual(
            result["underrated"][0]["low_matrices"][0]["signal"],
            "stability",
        )


if __name__ == "__main__":
    unittest.main()
