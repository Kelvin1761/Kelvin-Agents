"""晨操類型（Kelvin 2026-11-20）：退出排名嘅晨操格唔印假分數，改印類型；類型一處定義，報告、讀數、dashboard 共用。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from hkjc_racing_engine import scoring  # noqa: E402
from hkjc_racing_engine import summary  # noqa: E402
from hkjc_racing_engine.engine_core import RacingEngine  # noqa: E402


def engine(gallops, trials, swimming=3):
    digest = f"晨操資料已提取，分類為「狀態延續」。近21日快操{gallops}課、試閘{trials}課、踱步5課、游水{swimming}課，空白日2日"
    return RacingEngine({"_data": {"days_since_last": 21, "trackwork_digest": digest, "medical_flags": "✅ 無醫療事故記錄"}},
                        {"venue": "沙田", "distance": "1200m", "race_date": "2026-11-22"})


class TrackworkTypeTests(unittest.TestCase):
    def test_thresholds_match_the_old_workload_sentence(self):
        self.assertEqual(engine(5, 0)._trackwork_type()["text"], "操練密")
        self.assertEqual(engine(3, 1)._trackwork_type()["text"], "操練正常＋試閘1次")
        self.assertEqual(engine(1, 0, swimming=12)._trackwork_type()["text"], "放鬆為主")
        self.assertEqual(engine(0, 2)._trackwork_type()["text"], "操練少＋試閘2次")
        self.assertIsNone(RacingEngine({"_data": {}}, {})._trackwork_type())

    def test_read_line_and_type_agree(self):
        read = engine(5, 1)._trackwork_interpretation()
        self.assertIn("工作量充足", read["lines"][0])
        self.assertEqual(read["type"]["label"], "操練密")
        brief = summary._trackwork_brief({"trackwork_read": read})
        self.assertTrue(brief.startswith("操練密＋試閘1次；"))

    def test_retired_row_has_no_fake_score(self):
        self.assertNotEqual(scoring.TRACKWORK_SCORING, "on")
        auto = engine(2, 0).analyze_horse()
        rows = {r["key"]: r for r in auto["grade_transparency"]["rows"]}
        self.assertTrue(rows["trackwork"]["retired"])
        self.assertEqual(rows["trackwork"]["read"], "操練正常")
        self.assertNotIn("retired", rows["stability"])
        line = next(l for l in auto["grade_transparency"]["summary"].splitlines() if l.startswith("| 晨操"))
        self.assertEqual(line, "| 晨操狀態 | — | — | 退出排名 · 只作參考 | — | 操練正常 |")


if __name__ == "__main__":
    unittest.main()
