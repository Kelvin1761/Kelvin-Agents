from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import unified_reflector_core as core


class ResultQualityGateTests(unittest.TestCase):
    def test_parses_current_racenet_markdown_table_without_market_input(self) -> None:
        markdown = """# Results
## Race 1: Example Handicap
**Distance:** 1200m | **Class:** BM70
**Track:** Soft 5 | **Weather:** fine
**Winning Time:** 01:10.123

| Pos | # | Horse | Barrier | Jockey | Trainer | Weight | Margin | SP | Time |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 1 | 4 | Old Faithful | 11 | A Rider | A Trainer | 59kg | — | $7.50 | 01:10.123 |
| 2 | 1 | Kojak | 2 | B Rider | B Trainer | 60kg | 1.01L | $2.40 | 01:10.291 |
| 3DH | 5 | Clench | 6 | C Rider | C Trainer | 57kg | 1.19L | $11.00 | 01:10.321 |
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "results.md"
            path.write_text(markdown, encoding="utf-8")
            parsed = core.load_structured_results("au", path)

        rows = parsed[1]["results"]
        self.assertEqual([row["horse_no"] for row in rows], [4, 1, 5])
        self.assertEqual([row["placing"] for row in rows], [1, 2, 3])
        self.assertEqual(rows[0]["horse_name"], "Old Faithful")
        self.assertEqual(rows[1]["margin"], "1.01L")
        self.assertEqual(rows[0]["race_time"], "01:10.123")
        self.assertTrue(all(row["odds"] is None for row in rows))
        self.assertEqual(parsed[1]["meta"]["distance"], "1200m")
        self.assertEqual(parsed[1]["meta"]["track"], "Soft 5")

    def test_missing_results_fail_fast_instead_of_becoming_false_miss(self) -> None:
        meeting_stats = {"races": [{"race_num": 1}, {"race_num": 2}]}
        structured = {1: {"results": [{"placing": 1, "horse_no": 4}]}}

        with self.assertRaisesRegex(SystemExit, "Race 2"):
            core.validate_result_coverage(meeting_stats, structured)

    def test_target_race_filter_limits_quality_gate_scope(self) -> None:
        meeting_stats = {"races": [{"race_num": 1}, {"race_num": 2}]}
        structured = {1: {"results": [{"placing": 1, "horse_no": 4}]}}

        quality = core.validate_result_coverage(meeting_stats, structured, {1})

        self.assertEqual(quality["parsed_races"], 1)
        self.assertEqual(quality["missing_races"], [])

    def test_primary_top2_and_top4_metrics_are_reported_directly(self) -> None:
        race = SimpleNamespace(
            actual_top3=[
                {"horse_no": 4},
                {"horse_no": 1},
                {"horse_no": 5},
            ],
            model_top5=[
                {"horse_no": 4},
                {"horse_no": 1},
                {"horse_no": 7},
                {"horse_no": 5},
                {"horse_no": 9},
            ],
            top5_actual_top3_hits=3,
            winner_in_model_top5=True,
        )

        metrics = core.summarize_shortlist_metrics([race])

        self.assertEqual(metrics["top1_winner_rate"], 100.0)
        self.assertEqual(metrics["top2_place_strike_rate"], 100.0)
        self.assertEqual(metrics["top2_both_place_rate"], 100.0)
        self.assertEqual(metrics["top3_place_coverage_rate"], 66.7)
        self.assertEqual(metrics["top4_place_coverage_rate"], 100.0)
        self.assertEqual(metrics["top4_trifecta_rate"], 100.0)

    def test_missing_incident_data_is_not_called_clean_model_failure(self) -> None:
        race = SimpleNamespace(
            label="1 Hit",
            incident_analysis={"classification": "資料不足"},
        )

        verdict = core.race_failure_verdict(race)

        self.assertIn("不能判定", verdict)
        self.assertNotIn("偏向 clean", verdict)

    def test_single_race_feature_signal_is_not_claimed_as_historical_evidence(self) -> None:
        actual = {"horse_no": 4, "horse_name": "Example", "placing": 2}
        predictions = [
            {
                "horse_no": horse_no,
                "horse_name": f"Horse {horse_no}",
                "derived_rank": rank,
                "grade": "B",
                "composite_score": 70.0 - rank,
                "factor_scores": {"form_score": 60.0, "distance_score": 55.0},
            }
            for rank, horse_no in enumerate([1, 2, 3, 4], start=1)
        ]
        predictions[-1]["horse_name"] = "Example"

        review = core.analyse_missed_horse(actual, predictions, "")

        self.assertTrue(review["evidence_level"].startswith("未有"))
        self.assertIn("資料不足", review["verdict"])


if __name__ == "__main__":
    unittest.main()
