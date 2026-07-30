import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
ENGINE = SCRIPTS / "racing_engine"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ENGINE))

from au_pairwise_ranker_audit import (
    competitive_cutoff,
    date_partitions,
    gate,
    predict,
    train_pairwise,
)


def row(number, feature, position):
    return {
        "horse_number": number,
        "horse_name": f"Horse {number}",
        "actual_pos": position,
        "result_sp_label": None,
        "score": feature,
        "matrix_scores": {
            "stability": feature,
            "pace_perf": 60.0,
            "race_shape": 60.0,
            "jockey_trainer": 60.0,
            "class_weight": 60.0,
            "track": 60.0,
        },
        "feature_scores": {"form_score": feature},
    }


class PairwiseRankerAuditTests(unittest.TestCase):
    def test_competitive_cutoff_is_bounded(self):
        self.assertEqual(competitive_cutoff(6), 3)
        self.assertEqual(competitive_cutoff(12), 4)
        self.assertEqual(competitive_cutoff(18), 5)

    def test_pairwise_model_learns_positive_competitive_signal(self):
        race = {
            "metadata": {
                "date": "2026-01-01",
                "track": "Test",
                "race_number": 1,
            },
            "rows": [
                row(1, 80.0, 1),
                row(2, 75.0, 2),
                row(3, 70.0, 3),
                row(4, 50.0, 4),
                row(5, 45.0, 5),
                row(6, 40.0, 6),
            ],
        }
        model = train_pairwise(
            [race],
            ("form_score",),
            epochs=15,
            seed=1,
        )
        self.assertGreater(
            predict(model, race["rows"][0]),
            predict(model, race["rows"][-1]),
        )

    def test_date_partitions_never_train_on_validation_or_terminal_future(self):
        dataset = {
            "races": [
                {
                    "metadata": {
                        "date": f"2026-01-{day:02d}",
                        "track": "Test",
                        "race_number": 1,
                    },
                    "rows": [row(1, 70, 1), row(2, 50, 4)],
                }
                for day in range(1, 21)
            ]
        }
        folds, dev, terminal = date_partitions(dataset)
        self.assertTrue(folds)
        for train, valid in folds:
            self.assertLess(
                max(race["metadata"]["date"] for race in train),
                min(race["metadata"]["date"] for race in valid),
            )
        self.assertLess(
            max(race["metadata"]["date"] for race in dev),
            min(race["metadata"]["date"] for race in terminal),
        )

    def test_gate_rejects_good_or_top4_regression(self):
        good = {
            "good_positional": 0.01,
            "top3_all_within_top4": 0.01,
            "competitive_recall_at5": 0.01,
            "ndcg_at5": 0.01,
            "winner_top5": 0.01,
            "zero_hit": -0.01,
        }
        self.assertTrue(gate([good] * 5, good)["promote"])
        self.assertFalse(
            gate([good] * 5, {**good, "good_positional": -0.01})["promote"]
        )
        self.assertFalse(
            gate(
                [good] * 5,
                {**good, "top3_all_within_top4": -0.01},
            )["promote"]
        )


if __name__ == "__main__":
    unittest.main()
