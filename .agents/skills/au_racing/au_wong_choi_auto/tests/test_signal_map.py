from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
ENGINE_DIR = ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts" / "au_racing_engine"
SCRIPTS_DIR = ENGINE_DIR.parent
sys.path.insert(0, str(ENGINE_DIR.parent))
sys.path.insert(0, str(SCRIPTS_DIR))

from au_archive_calibrator import archive_snapshot
from au_racing_engine.engine_core import RacingEngine
from au_racing_engine.matrix_mapper import (
    MATRIX_FORMULAS,
    MATRIX_KEYS,
    canonicalize_matrix_scores,
    map_features_to_matrix_scores,
    matrix_score,
)
from au_racing_engine.scoring import (
    ABILITY_FEATURE_KEYS,
    FEATURE_KEYS,
    MATRIX_WEIGHTS,
    REPORT_ONLY_FEATURE_KEYS,
    clip_score,
)


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

    def test_direct_matrix_feature_set_matches_documentation(self) -> None:
        documented = {
            "form_score", "performance_quality_score",
            # sectional_score retired 2026-08-05: within-race AUC 0.525, and only
            # 0.532 even where the L400 PI data exists — weak because the leaf has
            # no discrimination, not because 21% of runners lack coverage.
            "pace_figure_score", "trial_score",
            "jockey_score", "trainer_score", "jockey_horse_fit_score",
            "pace_map_score",
            "rating_score",  # weight_score retired 2026-08-01 (AUC 0.480)
            "track_score",
            "formline_score",  # form_line dim exists but its weight is 0.0
        }
        in_formulas = {name for comps in MATRIX_FORMULAS.values() for name, _w in comps}
        self.assertEqual(in_formulas, documented)

    def test_class_score_is_context_only_not_a_direct_matrix_leaf(self) -> None:
        low = map_features_to_matrix_scores(
            {"class_score": 20, "rating_score": 70, "weight_score": 55}
        )
        high = map_features_to_matrix_scores(
            {"class_score": 95, "rating_score": 70, "weight_score": 55}
        )
        self.assertEqual(low["class_weight"], high["class_weight"])

    def test_weight_score_is_context_only_not_a_direct_matrix_leaf(self) -> None:
        # Retired from ranking 2026-08-01: 84.9% of runners scored exactly 60,
        # 41.5% of races had zero within-race spread, within-race AUC 0.480.
        # 負磅 stays in the report as context; it must not move the score.
        low = map_features_to_matrix_scores(
            {"weight_score": 20, "rating_score": 70, "class_score": 55}
        )
        high = map_features_to_matrix_scores(
            {"weight_score": 95, "rating_score": 70, "class_score": 55}
        )
        self.assertEqual(low["class_weight"], high["class_weight"])

    def test_form_line_weight_is_still_zero(self) -> None:
        # If someone re-enables form_line, the signal map + gate evidence must
        # be revisited (see 06_signal_map.md section C).
        self.assertNotIn("form_line", MATRIX_WEIGHTS)

    def test_matrix_schema_separates_ranking_and_report_only_dimensions(self) -> None:
        self.assertEqual(set(MATRIX_KEYS) - set(MATRIX_WEIGHTS), {"form_line"})
        self.assertEqual(tuple(key for key in MATRIX_KEYS if key in MATRIX_WEIGHTS),
                         tuple(MATRIX_WEIGHTS))

    def test_legacy_sectional_matrix_is_read_as_pace_perf(self) -> None:
        legacy = {"stability": 61.0, "sectional": 72.5}
        self.assertEqual(matrix_score(legacy, "pace_perf"), 72.5)
        self.assertEqual(
            canonicalize_matrix_scores(legacy)["pace_perf"],
            72.5,
        )

    def test_legacy_logic_snapshot_uses_canonical_archive_schema(self) -> None:
        horse = {
            "horse_name": "Legacy Star",
            "python_auto": {
                "ability_score": 61.0,
                "feature_scores": {},
                "matrix_scores": {
                    "stability": 63.0,
                    "sectional": 71.5,
                    "race_shape": 59.0,
                    "jockey_trainer": 62.0,
                    "class_weight": 60.0,
                    "track": 58.0,
                    "form_line": 64.0,
                },
            },
        }
        snapshot = archive_snapshot("1", horse, {}, {})
        self.assertEqual(snapshot["matrix_scores"]["pace_perf"], 71.5)
        self.assertNotIn("sectional", snapshot["matrix_scores"])

    def test_display_features_do_not_enter_ability(self) -> None:
        for name in ("health_score", "confidence_score", "distance_score"):
            self.assertNotIn(name, {n for comps in MATRIX_FORMULAS.values() for n, _ in comps})

    def test_feature_registry_separates_ability_from_report_only(self) -> None:
        self.assertEqual(
            set(FEATURE_KEYS),
            set(ABILITY_FEATURE_KEYS) | set(REPORT_ONLY_FEATURE_KEYS),
        )
        self.assertFalse(set(ABILITY_FEATURE_KEYS) & set(REPORT_ONLY_FEATURE_KEYS))
        self.assertEqual(
            set(REPORT_ONLY_FEATURE_KEYS),
            {
                "sectional_score",
                "class_score",
                "weight_score",
                "distance_score",
                "formline_score",
                "consistency_score",
                "health_score",
                "confidence_score",
            },
        )

    def test_dry_going_has_zero_wet_overlay(self) -> None:
        auto = _analyze("Good 4")
        self.assertEqual(auto["wet_form_feature"], 0.0)

    def test_coverage_uses_evidence_state_not_score_value(self) -> None:
        engine = RacingEngine(
            {
                "horse_name": "Coverage Horse",
                "horse_number": "1",
            },
            {},
        )
        engine.evidence_state = {
            key: "observed" for key in ABILITY_FEATURE_KEYS
        }
        coverage = engine._data_coverage()
        self.assertEqual(coverage["coverage_pct"], 100.0)
        self.assertEqual(coverage["missing_features"], [])

    def test_neutral_active_feature_is_still_reported_missing(self) -> None:
        """A neutral score must never be allowed to hide a data gap.

        A neutral ranking leaf must not hide a data gap. Retired/report-only
        leaves are deliberately outside this coverage denominator.
        """
        auto = _analyze()
        self.assertEqual(
            auto["feature_evidence_state"]["pace_figure_score"],
            "missing",
        )
        self.assertIn(
            "pace_figure_score",
            auto["data_coverage"]["missing_features"],
        )
        self.assertEqual(auto["feature_scores"]["pace_figure_score"], 60.0)


if __name__ == "__main__":
    unittest.main()
