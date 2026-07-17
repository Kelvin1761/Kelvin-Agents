from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from au_archive_calibrator import load_scoring_rows
from au_model_improvement_shadow import _record_dates, _recency_eligible, _recency_score


class ModelImprovementShadowTests(unittest.TestCase):
    def test_scoring_loader_preserves_shadow_fields(self) -> None:
        fields = [
            "race_number",
            "horse_number",
            "horse_name",
            "ability_score",
            "pure_7d_score",
            "wet_form_feature",
            "rank_score",
            "pace_figure_score",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Meeting_Auto_Scoring.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerow(
                    {
                        "race_number": 2,
                        "horse_number": 9,
                        "horse_name": "Example",
                        "ability_score": 61.25,
                        "pure_7d_score": 60.0,
                        "wet_form_feature": 1.25,
                        "rank_score": 61.25,
                        "pace_figure_score": 42.0,
                    }
                )
            row = load_scoring_rows(path)[0]

        self.assertEqual(row["race_number"], 2)
        self.assertEqual(row["pure_7d_score"], 60.0)
        self.assertEqual(row["wet_form_feature"], 1.25)
        self.assertEqual(row["feature_scores"]["pace_figure_score"], 42.0)

    def test_record_dates_separate_trials_from_official_runs(self) -> None:
        facts = "\n".join(
            [
                "| # | 類型 | 日期 | 場地 | 路程 | 場地狀況 | 檔位 | 名次 | 班次 | 跑位軌跡 |",
                "|---|---|---|---|---|---|---|---|---|---|",
                "| 1 | 試閘 | 2026-07-03 | Randwick | 1045m | - | - | 1 | - | F1 |",
                "| 2 | Maiden | 2026-02-07 | Randwick | 1100m | Good 4 | 11 | 10 | - | F10 |",
                "| 3 | 試閘 | 2026-06-19 | Rosehill | 900m | - | - | 3 | - | F3 |",
            ]
        )
        self.assertEqual(_record_dates(facts), ("2026-02-07", "2026-07-03"))

    def test_recency_gate_is_capped_and_requires_dated_evidence(self) -> None:
        eligible = {
            "ability_score": 54.5,
            "official_age_days": 158,
            "trial_age_days": 12,
            "trial_score": 89.0,
            "pace_figure_score": 26.0,
        }
        self.assertTrue(_recency_eligible(eligible))
        self.assertGreater(_recency_score(eligible), eligible["ability_score"])
        self.assertLessEqual(_recency_score(eligible) - eligible["ability_score"], 3.0)

        missing_date = dict(eligible, official_age_days=None)
        self.assertFalse(_recency_eligible(missing_date))
        self.assertEqual(_recency_score(missing_date), missing_date["ability_score"])


if __name__ == "__main__":
    unittest.main()
