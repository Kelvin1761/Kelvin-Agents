from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
EXTRACTOR_SCRIPTS = (
    ROOT
    / ".agents"
    / "skills"
    / "au_racing"
    / "au_race_extractor"
    / "scripts"
)
ENGINE = (
    ROOT
    / ".agents"
    / "skills"
    / "au_racing"
    / "au_wong_choi_auto"
    / "scripts"
    / "racing_engine"
)
AUTO_SCRIPTS = ENGINE.parent
sys.path.insert(0, str(EXTRACTOR_SCRIPTS))
sys.path.insert(0, str(AUTO_SCRIPTS))
sys.path.insert(0, str(ENGINE))

from au_auto_orchestrator import _build_field_summary
from engine_core import RacingEngine, _parse_formguide_pf_metrics, _parse_pf_token
from extractor import _format_past_run_extra_tokens


class SectionalTransportTests(unittest.TestCase):
    def test_extractor_preserves_full_benchmark_split_profile(self) -> None:
        past_run = {
            "margin": 1.2,
            "handicapRating": 76,
            "rtRating": 91,
            "sectionalTime": {
                "l600": {"time": "34.44"},
                "finish": {"time": "70.12"},
            },
            "competitorFormBenchmark": {
                "runnerTimeDifference": "1.23",
                "runnerTempoLabel": "V. Slow",
                "leaderTempoLabel": "Moderate",
                "runnerTempoQuantileRank": "0.94",
                "runnerTimeDifferenceL800": "-0.65",
                "runnerTimeDifferenceL600": "-1.21",
                "runnerTimeDifferenceL400": "-1.41",
                "runnerTimeDifferenceL200": "-0.43",
            },
        }

        text = _format_past_run_extra_tokens(past_run)
        self.assertIn("Tempo QRank: 0.94", text)
        self.assertIn("L800 Delta: -0.65", text)
        self.assertIn("L600 Delta: -1.21", text)
        self.assertIn("L400 Delta: -1.41", text)
        self.assertIn("L200 Delta: -0.43", text)

        token = text.split("PF[", 1)[1].rsplit("]", 1)[0]
        parsed = _parse_pf_token(token)
        self.assertEqual(parsed["tempo_qrank"], 0.94)
        self.assertEqual(parsed["l800_delta"], -0.65)
        self.assertEqual(parsed["l600_delta"], -1.21)
        self.assertEqual(parsed["l400_delta"], -1.41)
        self.assertEqual(parsed["l200_delta"], -0.43)

    def test_missing_split_values_are_not_fabricated(self) -> None:
        text = _format_past_run_extra_tokens(
            {
                "competitorFormBenchmark": {
                    "runnerTimeDifferenceL600": "-0.30",
                    "runnerTimeDifferenceL400": None,
                }
            }
        )
        self.assertIn("L600 Delta: -0.30", text)
        self.assertNotIn("L800 Delta", text)
        self.assertNotIn("L400 Delta", text)
        self.assertNotIn("L200 Delta", text)
        self.assertNotIn("Tempo QRank", text)

    def test_canonical_parser_records_source_and_per_value_coverage(self) -> None:
        formguide = "\n".join(
            [
                "[1] Alpha (2)",
                "PF[Race Time: 0.2 Tempo QRank: 0.7 "
                "L800 Delta: -0.8 L600 Delta: -1.0 "
                "L400 Delta: -0.6 L200 Delta: -0.2]",
                "PF[Race Time: 0.4 L600 Delta: -0.4 L400 Delta: -0.1]",
            ]
        )
        parsed = _parse_formguide_pf_metrics(
            Path("Race_1_Facts.md"),
            formguide_text=formguide,
        )
        aggregates = parsed["1"]["pf_aggregates"]
        self.assertEqual(aggregates["source"], "racenet_formguide_cfb")
        self.assertEqual(aggregates["pf_run_count"], 2)
        self.assertEqual(aggregates["value_counts"]["l800_delta"], 1)
        self.assertEqual(aggregates["value_counts"]["l600_delta"], 2)
        self.assertEqual(aggregates["value_counts"]["l200_delta"], 1)
        self.assertEqual(aggregates["l600_delta_avg"], -0.7)

    def test_field_summary_exposes_split_coverage_without_changing_score(self) -> None:
        def horse(profile):
            return {
                "_data": {
                    "pf_metrics": {
                        "pf_aggregates": profile,
                    }
                }
            }

        summary = _build_field_summary(
            {
                "1": horse(
                    {
                        "l800_delta_avg": -0.8,
                        "l600_delta_avg": -1.0,
                        "l400_delta_avg": -0.6,
                        "l200_delta_avg": -0.2,
                    }
                ),
                "2": horse(
                    {
                        "l800_delta_avg": -0.2,
                        "l600_delta_avg": -0.4,
                        "l400_delta_avg": -0.1,
                    }
                ),
            }
        )
        self.assertEqual(summary["l600_delta_field_count"], 2)
        self.assertEqual(summary["l200_delta_field_count"], 1)
        self.assertEqual(summary["pf_complete_profile_field_count"], 1)

    def test_shadow_splits_do_not_change_production_scoring(self) -> None:
        def horse(number, l600, *, include_shadow):
            profile = {
                "l600_delta_avg": l600,
                "pf_run_count": 3,
            }
            if include_shadow:
                profile.update(
                    {
                        "l800_delta_avg": l600 + 0.2,
                        "l400_delta_avg": l600 - 0.1,
                        "l200_delta_avg": l600 + 0.1,
                        "tempo_qrank_avg": 0.75,
                    }
                )
            return {
                "horse_name": f"Horse {number}",
                "horse_number": str(number),
                "barrier": number,
                "weight": 56.0,
                "rating": 70,
                "_data": {
                    "pf_metrics": {
                        "pf_aggregates": profile,
                    }
                },
            }

        legacy_field = {
            str(number): horse(number, value, include_shadow=False)
            for number, value in enumerate((-1.0, -0.5, 0.2), start=1)
        }
        shadow_field = {
            str(number): horse(number, value, include_shadow=True)
            for number, value in enumerate((-1.0, -0.5, 0.2), start=1)
        }
        base_context = {
            "distance": "1400m",
            "meeting_intelligence": {
                "venue": "Randwick",
                "going": "Good 4",
            },
        }
        legacy_context = {
            **base_context,
            "field_summary": _build_field_summary(legacy_field),
        }
        shadow_context = {
            **base_context,
            "field_summary": _build_field_summary(shadow_field),
        }

        legacy = RacingEngine(legacy_field["1"], legacy_context).analyze_horse()
        shadow = RacingEngine(shadow_field["1"], shadow_context).analyze_horse()

        self.assertEqual(legacy["feature_scores"], shadow["feature_scores"])
        self.assertEqual(legacy["matrix_scores"], shadow["matrix_scores"])
        self.assertEqual(legacy["ability_score"], shadow["ability_score"])


if __name__ == "__main__":
    unittest.main()
