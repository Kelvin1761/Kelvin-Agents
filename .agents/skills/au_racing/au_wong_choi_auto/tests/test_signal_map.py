from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
ENGINE_DIR = ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts" / "racing_engine"
sys.path.insert(0, str(ENGINE_DIR))

from engine_core import RacingEngine
from matrix_mapper import MATRIX_FORMULAS, map_features_to_matrix_scores
from scoring import MATRIX_WEIGHTS, clip_score


def _analyze(going: str = "Good 4") -> dict:
    horse = {
        "horse_name": "Signal Map Horse",
        "barrier": 5,
        "horse_number": "1",
        "weight": 56.0,
        "rating": 72,
    }
    race_context = {
        "distance": "1400m",
        "field_summary": {"count": 10},
        "meeting_intelligence": {"venue": "Randwick", "going": going},
    }
    return RacingEngine(horse, race_context).analyze_horse()


class SignalMapTests(unittest.TestCase):
    """Locks the ranking equation documented in resources/06_signal_map.md.

    If a future change sneaks a hidden adjustment into ability_score outside
    the (matrix weights x matrix scores) + wet_form_feature equation, or
    changes the live feature set feeding the matrix, these tests fail and the
    signal map must be updated in the same commit.
    """

    def test_ability_equation_is_matrix_plus_wet_only(self) -> None:
        auto = _analyze()
        expected = sum(
            MATRIX_WEIGHTS[dim] * auto["matrix_scores"][dim] for dim in MATRIX_WEIGHTS
        ) + auto["wet_form_feature"]
        self.assertAlmostEqual(auto["ability_score"], clip_score(expected), places=3)
        self.assertAlmostEqual(auto["pure_7d_score"], auto["ability_score"] - auto["wet_form_feature"], places=3)

    def test_matrix_scores_follow_declared_formulas(self) -> None:
        auto = _analyze()
        recomputed = map_features_to_matrix_scores(auto["feature_scores"])
        for dim, value in recomputed.items():
            self.assertAlmostEqual(auto["matrix_scores"][dim], value, places=1,
                                   msg=f"matrix dim {dim} no longer follows MATRIX_FORMULAS")

    def test_live_feature_set_is_exactly_the_documented_14(self) -> None:
        documented = {
            "form_score", "consistency_score",
            "pace_figure_score", "sectional_score", "trial_score",
            "jockey_score", "trainer_score", "jockey_horse_fit_score",
            "pace_map_score",
            "class_score", "rating_score", "weight_score",
            "track_score",
            "formline_score",  # form_line dim exists but its weight is 0.0
        }
        in_formulas = {name for comps in MATRIX_FORMULAS.values() for name, _w in comps}
        self.assertEqual(in_formulas, documented)

    def test_form_line_weight_is_still_zero(self) -> None:
        # If someone re-enables form_line, the signal map + gate evidence must
        # be revisited (see 06_signal_map.md section C).
        self.assertEqual(MATRIX_WEIGHTS.get("form_line", 0.0), 0.0)

    def test_display_features_do_not_enter_ability(self) -> None:
        for name in ("health_score", "confidence_score", "distance_score"):
            self.assertNotIn(name, {n for comps in MATRIX_FORMULAS.values() for n, _ in comps})

    def test_dry_going_has_zero_wet_overlay(self) -> None:
        auto = _analyze("Good 4")
        self.assertEqual(auto["wet_form_feature"], 0.0)


if __name__ == "__main__":
    unittest.main()
