from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from au_ml_dataset import (  # noqa: E402
    _facts_runs,
    build_rows,
    feature_contract,
    place_slots,
    validate_feature_contract,
)


def runtime_row(*, horse_number: int, actual_pos: int, facts: str = "") -> dict:
    features = {
        key: 60.0
        for key in (
            "form_score", "trial_score", "sectional_score", "pace_map_score",
            "jockey_score", "trainer_score", "jockey_horse_fit_score",
            "class_score", "rating_score", "weight_score", "distance_score",
            "track_score", "formline_score", "consistency_score",
            "performance_quality_score", "health_score", "confidence_score",
            "pace_figure_score",
        )
    }
    return {
        "horse_number": horse_number,
        "horse_name": f"Horse {horse_number}",
        "score": 60 + horse_number,
        "actual_pos": actual_pos,
        "result_sp_label": 5.0,
        "feature_scores": features,
        "feature_evidence_state": {key: "fallback" for key in features},
        "raw_pre_race": {
            "barrier": horse_number,
            "weight": 58,
            "rating": 70,
            "facts_section": facts,
        },
    }


class AuMlDatasetTests(unittest.TestCase):
    def test_australian_place_slots_follow_field_size(self) -> None:
        self.assertEqual(place_slots(4), 1)
        self.assertEqual(place_slots(5), 2)
        self.assertEqual(place_slots(7), 2)
        self.assertEqual(place_slots(8), 3)

    def test_feature_contract_has_no_market_or_outcome_features(self) -> None:
        contract = feature_contract()
        validate_feature_contract(contract)
        features = contract["numeric"] + contract["categorical"]
        self.assertNotIn("champion_score", features)
        self.assertFalse(any("market" in key or "actual_pos" in key for key in features))

    def test_facts_parser_reads_distance_with_unit(self) -> None:
        facts = (
            "| 1 | Maiden | 2026-05-01 | Randwick R5 | 1400m | Good 4 | "
            "3 | 2/10 | - | 4-3-2 |"
        )
        rows = _facts_runs(facts)
        self.assertEqual(rows[0]["distance"], 1400)
        self.assertEqual(rows[0]["finish"], 2)
        self.assertEqual(rows[0]["field"], 10)

    def test_target_date_run_is_reported_and_not_used_in_history(self) -> None:
        facts = "\n".join(
            [
                "| 1 | Maiden | 2026-06-01 | Randwick R5 | 1400m | Good 4 | 3 | 1/10 | - | 2-1-1 |",
                "| 2 | Maiden | 2026-05-01 | Randwick R4 | 1400m | Good 4 | 3 | 2/10 | - | 4-3-2 |",
            ]
        )
        runtime = {
            "races": [
                {
                    "metadata": {
                        "date": "2026-06-01", "track": "Randwick",
                        "race_number": 5, "distance": 1400,
                        "going": "Good 4", "race_class": "Maiden",
                        "field_size": 4,
                    },
                    "rows": [runtime_row(horse_number=i, actual_pos=i, facts=facts) for i in range(1, 5)],
                }
            ]
        }
        rows, audit = build_rows(runtime)
        self.assertEqual(len(audit["future_or_target_run_records"]), 4)
        self.assertEqual(rows[0]["formal_count"], 1)
        self.assertEqual(rows[0]["recent_finish_mean_3"], 2)

    def test_duplicate_runner_is_an_integrity_failure(self) -> None:
        row = runtime_row(horse_number=1, actual_pos=1)
        runtime = {
            "races": [
                {
                    "metadata": {
                        "date": "2026-06-01", "track": "Randwick",
                        "race_number": 5, "distance": 1400,
                        "going": "Good 4", "race_class": "Maiden",
                        "field_size": 4,
                    },
                    "rows": [row, row, runtime_row(horse_number=2, actual_pos=2), runtime_row(horse_number=3, actual_pos=3)],
                }
            ]
        }
        _rows, audit = build_rows(runtime)
        self.assertEqual(len(audit["duplicate_runners"]), 1)


if __name__ == "__main__":
    unittest.main()
