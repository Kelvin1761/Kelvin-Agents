import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
ENGINE = SCRIPTS / "au_racing_engine"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ENGINE.parent))

from au_shape_interaction_audit import (
    applies,
    raw_pace_adjustment,
    recompose_row,
)


class ShapeInteractionAuditTests(unittest.TestCase):
    def test_slow_pace_rewards_front_and_penalises_closer(self):
        speed_map = {
            "predicted_pace": "極慢",
            "leaders": [1],
            "pressers": [],
            "on_pace": [],
            "mid_pack": [],
            "closers": [2],
        }
        self.assertEqual(raw_pace_adjustment(speed_map, 1), 3.0)
        self.assertEqual(raw_pace_adjustment(speed_map, 2), -3.0)

    def test_condition_gates_are_interactions_not_standalone_bonuses(self):
        self.assertTrue(
            applies(
                "large_missing_pf",
                large=True,
                clear=False,
                missing_pf=True,
            )
        )
        self.assertFalse(
            applies(
                "large_missing_pf",
                large=False,
                clear=True,
                missing_pf=True,
            )
        )

    def test_recomposition_only_changes_pre_race_pace_map_feature(self):
        row = {
            "score": 60.0,
            "feature_scores": {
                "form_score": 60.0,
                "consistency_score": 60.0,
                "pace_figure_score": 60.0,
                "sectional_score": 60.0,
                "trial_score": 60.0,
                "pace_map_score": 60.0,
                "jockey_score": 60.0,
                "trainer_score": 60.0,
                "jockey_horse_fit_score": 60.0,
                "rating_score": 60.0,
                "weight_score": 60.0,
                "track_score": 60.0,
                "formline_score": 60.0,
            },
            "wet_form_feature": 0.0,
        }
        candidate = recompose_row(row, adjustment=3.0, scale=0.5)
        # `race_shape` left the ranking on 2026-08-22 (EXP-20260821-06), and it
        # was 100% `pace_map_score` — so nudging pace_map can no longer move a
        # composite score at all. This assertion is inverted deliberately: it
        # now pins the fact that this audit measures a REPORT-ONLY signal.
        # If race_shape is ever given weight back, this flips to assertGreater
        # and the audit becomes meaningful for ranking again.
        self.assertEqual(candidate["score"], row["score"])
        self.assertEqual(row["feature_scores"]["pace_map_score"], 60.0)


if __name__ == "__main__":
    unittest.main()
