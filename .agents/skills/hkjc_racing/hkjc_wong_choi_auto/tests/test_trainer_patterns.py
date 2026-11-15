"""個別練馬師出擊 pattern（EXP-20261115-20）：live 判斷同表配對 —— 純顯示。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from hkjc_racing_engine import trainer_patterns as tp  # noqa: E402


def horse(trainer="告東尼", **data):
    return {"trainer": trainer, "_data": data}


class TrainerPatternsTest(unittest.TestCase):
    def test_lengths(self):
        self.assertAlmostEqual(tp._lengths("頸"), 0.3)
        self.assertAlmostEqual(tp._lengths("1-1/4"), 1.25)
        self.assertAlmostEqual(tp._lengths("3/4"), 0.75)
        self.assertIsNone(tp._lengths("N/A"))

    def test_patterns(self):
        p = tp.patterns(horse(last_finish="2", last_margin="頸", days_since_last="12"), "第四班", 1200, ["B-", "TT1"])
        self.assertTrue({"gear_removed", "gear_first", "last_close_2nd_3rd", "quick_backup14"} <= p)
        p = tp.patterns(horse(days_since_last="120", l400_last_run={"distance": 1400}), "第四班", 1650, [])
        self.assertTrue({"layoff90", "rest60", "dist_up200"} <= p)
        p = tp.patterns(horse(days_since_last="20", recent_6_detail="第1仗(01/10/2026 第三班): 5名 3 | 第2仗(10/09/2026 第三班): 6名 4 | 第3仗(01/05/2026 第三班): 4名 2",
                              jockey_change_note="今仗轉用騎師X"), "第四班", 1200, [])
        self.assertTrue({"classdrop_jchange", "third_up"} <= p)

    def test_matches_dedupe_rest(self):
        tp._TABLE = {("蔡約翰", "layoff90"): {"trainer": "蔡約翰", "pattern": "layoff90"},
                     ("蔡約翰", "rest60"): {"trainer": "蔡約翰", "pattern": "rest60"}}
        try:
            m = tp.matches(horse("蔡約翰", days_since_last="100"), "第四班", 1200, [])
            self.assertEqual([c["pattern"] for c in m], ["layoff90"])
        finally:
            tp._TABLE = None

    def test_real_table_loads(self):
        self.assertGreater(len(tp.table()), 10)


if __name__ == "__main__":
    unittest.main()
