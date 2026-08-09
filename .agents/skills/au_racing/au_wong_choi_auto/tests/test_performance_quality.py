from __future__ import annotations

import math
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[5]
ENGINE_DIR = ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts" / "racing_engine"
SCRIPTS_DIR = ENGINE_DIR.parent
sys.path.insert(0, str(ENGINE_DIR))
sys.path.insert(0, str(SCRIPTS_DIR))

from au_auto_orchestrator import _build_field_summary
from engine_core import RacingEngine, _summarize_formguide_section
from matrix_mapper import map_features_to_matrix_scores


def _run(date: str, prize: int, margin: float, starters: int = 10) -> str:
    return (
        f"Randwick R2 {date} 1400m cond:Good ${prize} Test Rider (2) 57.0kg "
        f"Flucs:$- $8.00 margin:{margin}L starters:{starters}\n"
        "1-Winner (57kg), 2-Runner (57kg) 1.00L, 3-Third (57kg) 2.00L\n"
        "Video:\nNote:\nStewards:\n"
    )


class PerformanceQualityTests(unittest.TestCase):
    def test_digest_combines_margin_and_race_strength(self) -> None:
        section = _run("2026-07-20", 150000, 2.0) + _run("2026-07-01", 50000, 1.0)
        digest = _summarize_formguide_section(
            section,
            "Runner",
            meeting_date="2026-08-01",
        )
        first = -2.0 + 4.0 * math.log10(3.0)
        second = -1.0
        expected = (first + 0.8 * second) / 1.8
        self.assertEqual(digest["performance_quality_run_count"], 2)
        self.assertAlmostEqual(digest["performance_quality_raw"], expected, places=5)
        self.assertEqual(
            digest["performance_quality_source"],
            "class_adjusted_margin_complete_formguide",
        )
        self.assertEqual(
            digest["performance_quality_runs"],
            [
                {
                    "date": "2026-07-20",
                    "finish_pos": 2,
                    "margin": 2.0,
                    "prize": 150000.0,
                    "starters": 10,
                    "distance": 1400,
                    "quality": round(first, 6),
                },
                {
                    "date": "2026-07-01",
                    "finish_pos": 2,
                    "margin": 1.0,
                    "prize": 50000.0,
                    "starters": 10,
                    "distance": 1400,
                    "quality": -1.0,
                },
            ],
        )

    def test_same_day_run_is_excluded_from_pre_race_digest(self) -> None:
        historical = _run("2026-07-20", 50000, 2.0) + _run("2026-07-01", 50000, 4.0)
        leaked = _run("2026-08-01", 5000000, 0.0) + historical
        base = _summarize_formguide_section(
            historical,
            "Runner",
            meeting_date="2026-08-01",
        )
        censored = _summarize_formguide_section(
            leaked,
            "Runner",
            meeting_date="2026-08-01",
        )
        self.assertEqual(censored["performance_quality_run_count"], 2)
        self.assertEqual(
            censored["performance_quality_raw"],
            base["performance_quality_raw"],
        )
        self.assertEqual(
            censored["performance_quality_runs"],
            base["performance_quality_runs"],
        )
        self.assertEqual(
            censored["latest_official_date"],
            base["latest_official_date"],
        )
        self.assertEqual(
            censored["recent_shape_summary_line"],
            base["recent_shape_summary_line"],
        )

    def test_partial_legacy_rows_do_not_enter_ranking(self) -> None:
        # Complete margin/prize rows without starter count belong to the partial
        # legacy schema and must not activate this ranking feature.
        section = _run("2026-07-20", 150000, 1.0, starters=0).replace(" starters:0", "")
        section += _run("2026-07-01", 150000, 1.0, starters=0).replace(" starters:0", "")
        digest = _summarize_formguide_section(
            section,
            "Runner",
            meeting_date="2026-08-01",
        )
        self.assertEqual(digest["performance_quality_run_count"], 0)
        self.assertIsNone(digest["performance_quality_raw"])

    def test_result_line_margin_is_not_treated_as_complete_schema(self) -> None:
        def result_only(date: str) -> str:
            return (
                f"Randwick R2 {date} 1400m cond:Good $150000 Test Rider (2) 57.0kg "
                "Flucs:$- $8.00 starters:10\n"
                "1-Winner (57kg), 2-Runner (57kg) 1.00L, 3-Third (57kg) 2.00L\n"
            )

        digest = _summarize_formguide_section(
            result_only("2026-07-20") + result_only("2026-07-01"),
            "Runner",
            meeting_date="2026-08-01",
        )
        self.assertEqual(digest["performance_quality_run_count"], 0)
        self.assertIsNone(digest["performance_quality_raw"])

    def test_field_relative_score_rewards_stronger_demonstrated_quality(self) -> None:
        horses = {
            "1": {"_data": {"performance_quality_raw": -4.0}},
            "2": {"_data": {"performance_quality_raw": 0.0}},
            "3": {"_data": {"performance_quality_raw": 4.0}},
        }
        summary = _build_field_summary(horses)
        low = RacingEngine(
            {"horse_name": "Low", "_data": {"performance_quality_raw": -4.0, "performance_quality_run_count": 2}},
            {"field_summary": summary},
        )._performance_quality_score()
        high = RacingEngine(
            {"horse_name": "High", "_data": {"performance_quality_raw": 4.0, "performance_quality_run_count": 2}},
            {"field_summary": summary},
        )._performance_quality_score()
        self.assertLess(low[0], 60.0)
        self.assertGreater(high[0], 60.0)
        self.assertEqual(high[2], "class_adjusted_margin_field_relative")

    def test_missing_quality_falls_back_to_existing_consistency_exactly(self) -> None:
        auto = RacingEngine(
            {"horse_name": "Legacy", "horse_number": "1", "barrier": 4},
            {"field_summary": {"count": 8}},
        ).analyze_horse()
        self.assertEqual(
            auto["feature_scores"]["performance_quality_score"],
            auto["feature_scores"]["consistency_score"],
        )
        expected = map_features_to_matrix_scores(auto["feature_scores"])["stability"]
        self.assertEqual(auto["matrix_scores"]["stability"], expected)
        self.assertEqual(
            auto["feature_evidence_state"]["performance_quality_score"],
            "fallback",
        )

    def test_disable_flag_is_rank_exact_fallback(self) -> None:
        horse = {
            "horse_name": "Switchable",
            "horse_number": "1",
            "barrier": 4,
            "_data": {
                "performance_quality_raw": 5.0,
                "performance_quality_run_count": 3,
            },
        }
        context = {
            "field_summary": {
                "count": 8,
                "performance_quality_field_count": 5,
                "performance_quality_field_mean": 0.0,
                "performance_quality_field_stdev": 2.0,
            }
        }
        with patch.dict(os.environ, {"WC_DISABLE_AU_PERFORMANCE_QUALITY": "1"}):
            auto = RacingEngine(horse, context).analyze_horse()
        self.assertEqual(
            auto["feature_scores"]["performance_quality_score"],
            auto["feature_scores"]["consistency_score"],
        )
        self.assertTrue(auto["stability_detail"]["performance_quality"]["disabled"])


if __name__ == "__main__":
    unittest.main()
