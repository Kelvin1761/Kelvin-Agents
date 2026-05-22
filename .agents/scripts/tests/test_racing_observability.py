from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = ROOT / ".agents" / "scripts"
HK_REFLECTOR_DIR = ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_reflector" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(HK_REFLECTOR_DIR))

from racing_observability import attach_results_and_evaluate, compute_file_hash, log_horse_score, start_run
from reflector_auto_stats import run_stats as hkjc_run_stats


class RacingObservabilityTests(unittest.TestCase):
    def test_logger_serializes_utf8_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            meeting_dir = Path(tmp)
            facts_path = meeting_dir / "05-13 Race 1 Facts.md"
            logic_path = meeting_dir / "Race_1_Logic.json"
            facts_path.write_text("測試 facts", encoding="utf-8")
            logic_path.write_text("{}", encoding="utf-8")

            run_id = start_run(meeting_dir, "HKJC", scoring_profile="baseline")
            log_horse_score(
                meeting_dir,
                "HKJC",
                run_id,
                race_no=1,
                horse_no=5,
                horse_name="快樂高球",
                python_auto={
                    "version": "TEST_V1",
                    "ability_score": 82.4,
                    "rank_score": 83.1,
                    "rank": 2,
                    "grade": "A",
                    "feature_scores": {"form_score": 81.0},
                    "matrix_scores": {"class_advantage": 79.0},
                    "matrix_reasoning": {"class_advantage": {"text": "降班有利"}},
                    "risk_flags": ["draw_pressure"],
                    "reason_codes": ["class_drop"],
                    "score_provenance": {"form_score": "facts_section"},
                },
                facts_path=facts_path,
                logic_path=logic_path,
            )

            records = [json.loads(line) for line in (meeting_dir / "racing_run_log.jsonl").read_text(encoding="utf-8").splitlines()]
            horse_record = next(record for record in records if record["event_type"] == "horse_scored")
            self.assertEqual(horse_record["horse_name"], "快樂高球")
            self.assertEqual(horse_record["facts_hash"], compute_file_hash(facts_path))
            self.assertEqual(horse_record["logic_hash"], compute_file_hash(logic_path))

    def test_hash_is_stable_until_file_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.txt"
            path.write_text("alpha", encoding="utf-8")

            first_hash = compute_file_hash(path)
            second_hash = compute_file_hash(path)
            self.assertEqual(first_hash, second_hash)

            path.write_text("beta", encoding="utf-8")
            self.assertNotEqual(first_hash, compute_file_hash(path))

    def test_validation_flags_cover_missing_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            meeting_dir = Path(tmp)
            facts_path = meeting_dir / "05-13 Race 1 Facts.md"
            logic_path = meeting_dir / "Race_1_Logic.json"
            logic_path.write_text("{}", encoding="utf-8")

            run_id = start_run(meeting_dir, "HKJC")
            record = log_horse_score(
                meeting_dir,
                "HKJC",
                run_id,
                race_no=1,
                horse_no=1,
                horse_name="測試馬",
                python_auto={
                    "version": "TEST_V1",
                    "ability_score": 70.0,
                    "feature_scores": {},
                    "matrix_scores": {},
                    "matrix_reasoning": {},
                    "score_provenance": {},
                },
                facts_path=facts_path,
                logic_path=logic_path,
            )

            self.assertIn("missing_facts_file", record["validation_flags"])
            self.assertIn("missing_matrix_reasoning", record["validation_flags"])
            self.assertIn("missing_score_provenance", record["validation_flags"])

    def test_hkjc_evaluation_summary_matches_reflector_stats(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            meeting_dir = Path(tmp)
            analysis_path = meeting_dir / "Race_1_Auto_Analysis.md"
            results_path = meeting_dir / "05-13 測試 全日賽果.json"
            analysis_path.write_text(
                "\n".join(
                    [
                        "## [第三部分] 🏆 Top 4 位置精選",
                        "",
                        "**第1選**",
                        "- **馬號及馬名:** [1] 測試甲",
                        "",
                        "**第2選**",
                        "- **馬號及馬名:** [2] 測試乙",
                        "",
                        "**第3選**",
                        "- **馬號及馬名:** [3] 測試丙",
                        "",
                        "### 【No.1】 測試甲",
                        "⭐ 最終評級: **A**",
                        "### 【No.2】 測試乙",
                        "⭐ 最終評級: **B+**",
                        "### 【No.3】 測試丙",
                        "⭐ 最終評級: **B**",
                    ]
                ),
                encoding="utf-8",
            )
            results_path.write_text(
                json.dumps(
                    {
                        "1": {
                            "results": [
                                {"pos": 1, "horse_no": 1, "horse_name": "測試甲"},
                                {"pos": 2, "horse_no": 2, "horse_name": "測試乙"},
                                {"pos": 3, "horse_no": 3, "horse_name": "測試丙"},
                            ]
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            run_id = start_run(meeting_dir, "HKJC", scoring_profile="baseline")

            evaluation = attach_results_and_evaluate(meeting_dir, "HKJC", run_id=run_id, scoring_profile="baseline")
            reflector = hkjc_run_stats(str(meeting_dir), str(results_path))

            self.assertIsNotNone(evaluation)
            self.assertEqual(evaluation["kpis"]["gold"]["rate"], reflector["summary"]["position_hit_rates"]["gold_standard"]["rate"])
            self.assertEqual(evaluation["kpis"]["good"]["rate"], reflector["summary"]["position_hit_rates"]["good_result"]["rate"])
            self.assertEqual(evaluation["kpis"]["pass"]["rate"], reflector["summary"]["position_hit_rates"]["min_threshold"]["rate"])
            self.assertTrue((meeting_dir / "evaluation_summary.json").exists())


if __name__ == "__main__":
    unittest.main()
