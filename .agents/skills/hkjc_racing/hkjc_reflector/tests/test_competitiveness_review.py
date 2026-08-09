from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_reflector" / "scripts"
SHARED = ROOT / ".agents" / "skills" / "shared_racing"
for path in (SCRIPTS, SHARED):
    sys.path.insert(0, str(path))

from build_hkjc_ranking_dataset import _is_foreign_runner
from hkjc_competitiveness_review import (
    classify_weak_race,
    evaluate_race,
    load_rank_overrides,
    metric_summary,
    normalise_races,
)
from hkjc_build_anomaly_annotations import (
    INJURY_PATTERNS,
    INTERFERENCE_PATTERNS,
    has_pattern,
    incident_segments,
)
from hkjc_debut_matrix_simplification_gate import gate_candidate


class ForeignRunnerDatasetTests(unittest.TestCase):
    def test_hk_starts_separates_visitor_from_local_import(self) -> None:
        base = {
            "last_6_finishes": "1-2-1",
            "_data": {
                "pdf_overseas_races": [
                    {"class_level": "G1", "rank": "1/12", "time": "1.35.2", "margin": "1"},
                ]
            },
        }
        self.assertEqual(_is_foreign_runner({**base, "hk_starts": 0}), 1)
        self.assertEqual(_is_foreign_runner({**base, "hk_starts": 3}), 0)

    def test_placeholder_overseas_rows_do_not_create_foreign_label(self) -> None:
        horse = {
            "hk_starts": 0,
            "_data": {
                "pdf_overseas_races": [
                    {"class_level": "-", "rank": "-", "time": "-", "margin": "-"},
                ]
            },
        }
        self.assertEqual(_is_foreign_runner(horse), 0)


class CompetitivenessReviewTests(unittest.TestCase):
    def _dataset(self, folder: str) -> Path:
        path = Path(folder) / "replay.csv"
        fields = [
            "dataset", "split", "meeting", "date", "race_number", "horse_number",
            "horse_name", "venue", "track", "distance_num", "is_debut", "is_import",
            "reference_original_rank", "reference_original_ability",
            "label_finish_position",
        ]
        rows = [
            ("archive", "archive_development", "2026-01-01_ShaTin", "2026-01-01", 1, 1, "甲", "沙田", "Turf", 1200, 0, 0, 1, 70, 7),
            ("archive", "archive_development", "2026-01-01_ShaTin", "2026-01-01", 1, 2, "乙", "沙田", "Turf", 1200, 0, 0, 2, 69, 2),
            ("archive", "archive_development", "2026-01-01_ShaTin", "2026-01-01", 1, 3, "丙", "沙田", "Turf", 1200, 0, 0, 3, 68, 1),
            ("archive", "archive_development", "2026-01-01_ShaTin", "2026-01-01", 1, 4, "丁", "沙田", "Turf", 1200, 0, 0, 4, 67, 3),
            ("archive", "archive_development", "2026-01-01_ShaTin", "2026-01-01", 1, 5, "戊", "沙田", "Turf", 1200, 0, 0, 5, 66, 4),
            ("archive", "archive_development", "2026-01-01_ShaTin", "2026-01-01", 1, 6, "己", "沙田", "Turf", 1200, 0, 0, 6, 65, 5),
            ("archive", "archive_development", "2026-01-01_ShaTin", "2026-01-01", 1, 7, "庚", "沙田", "Turf", 1200, 0, 0, 7, 64, 6),
        ]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(fields)
            writer.writerows(rows)
        return path

    def test_weak_race_keeps_top5_capture_separate_from_top2_hits(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            races = normalise_races(
                self._dataset(folder),
                dimension_path=None,
                rich_path=None,
                annotation_path=None,
            )
        evaluated = evaluate_race(races[0])
        case = classify_weak_race(evaluated)

        self.assertEqual(case["top2_hits"], 1)
        self.assertEqual(case["top3_capture_at5"], 1.0)
        self.assertTrue(case["top3_all_within_top5"])
        self.assertEqual(case["primary_cause"], "競爭層已捕捉但頭二排序不足")
        summary = metric_summary([evaluated])
        self.assertEqual(summary["top3_all_within_top5_rate"], 1.0)

    def test_live_matrix_rank_override_reorders_complete_field(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "matrix.csv"
            fields = [
                "meeting_name",
                "race_number",
                "horse_number",
                "matrix_sectional",
                "matrix_trainer_signal",
                "matrix_stability",
                "matrix_race_shape",
                "matrix_class_advantage",
                "matrix_horse_health",
                "matrix_form_line",
            ]
            rows = []
            for horse, trainer in ((1, 55), (2, 60), (3, 90)):
                rows.append(
                    [
                        "2026-01-01_ShaTin",
                        1,
                        horse,
                        60,
                        trainer,
                        60,
                        60,
                        60,
                        60,
                        60,
                    ]
                )
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(fields)
                writer.writerows(rows)
            overrides = load_rank_overrides([path])

        self.assertEqual(overrides[("2026-01-01_ShaTin", 1, 3)]["rank"], 1)
        self.assertEqual(overrides[("2026-01-01_ShaTin", 1, 1)]["rank"], 3)


class AnomalyAnnotationTests(unittest.TestCase):
    def test_incident_segments_are_assigned_to_correct_horse(self) -> None:
        results = [
            {"pos": "1", "horse_no": "3", "horse_name": "甲馬(K001)"},
            {"pos": "8", "horse_no": "7", "horse_name": "乙馬(K002)"},
        ]
        report = (
            "1 3 甲馬 (K001) 無特別報告。 "
            "8 7 乙馬 (K002) 三百米處至二百米處受困而未能望空。"
        )
        segments = incident_segments(report, results)

        self.assertIn("無特別報告", segments[3])
        self.assertTrue(has_pattern(segments[7], INTERFERENCE_PATTERNS))

    def test_negative_vet_finding_is_not_injury(self) -> None:
        text = "賽後立即接受獸醫檢查，並無發現任何明顯異常之處。"
        self.assertFalse(has_pattern(text, INJURY_PATTERNS))
        self.assertTrue(has_pattern("賽後發現此駒患有喘鳴症。", INJURY_PATTERNS))


class DebutGateTests(unittest.TestCase):
    def test_gate_requires_no_harm_in_every_slice(self) -> None:
        good_delta = {
            "zero_hit": 0,
            "top3_capture_at5": 0.01,
            "ndcg_at5": 0.01,
            "winner_in_top5": 0.01,
            "mrr": 0.01,
        }
        result = {
            name: {
                "delta": dict(good_delta),
                "candidate": {"races": 10},
            }
            for name in ("development", "temporal_holdout", "debut_all", "debut_temporal_holdout")
        }
        self.assertTrue(gate_candidate(result)["passes"])
        result["temporal_holdout"]["delta"]["mrr"] = -0.001
        self.assertFalse(gate_candidate(result)["passes"])


if __name__ == "__main__":
    unittest.main()
