"""Wong Choi 唯一跑法標準（run_style.py；Kelvin 2026-11-16「唔好一樣嘢用兩套標準」）。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from hkjc_racing_engine import draw_style, run_style  # noqa: E402

# 機不可失（K417）2026-11-18 R3 之前嘅跑法表
K417 = [["2025-11-05", 0.5833], ["2025-11-26", 0.4167], ["2026-01-14", 0.6667],
        ["2026-02-19", 0.7857], ["2026-10-19", 0.5833]]
TABLE = {"horses": {"K417": K417}}


class RunStyleTest(unittest.TestCase):
    def test_thresholds(self):
        self.assertEqual(run_style.classify(0.30), "放頭")
        self.assertEqual(run_style.classify(0.31), "守中")
        self.assertEqual(run_style.classify(0.60), "守中")
        self.assertEqual(run_style.classify(0.61), "後上")
        self.assertIsNone(run_style.classify(None))
        self.assertEqual(run_style.fraction(3, 12), 0.25)
        self.assertIsNone(run_style.fraction(None, 12))
        self.assertIsNone(run_style.fraction(3, 0))

    def test_scoring_uses_the_same_standard(self):
        """入分（檔位×跑法）同顯示一定要同一個分類。"""
        for i in range(0, 101):
            frac = i / 100
            self.assertEqual(draw_style.style_class(frac), run_style.CODE[run_style.classify(frac)])
        self.assertEqual(draw_style.style_class(None), "U")
        self.assertEqual(draw_style.habitual_position("K417", "2026-11-18", TABLE),
                         run_style.habitual_fraction("K417", "2026-11-18", TABLE))

    def test_borderline_horse_reports_low_consistency(self):
        """機不可失：平均 60.7% → 後上，但 5 仗得 2 仗後上 → 多變（唔再一邊話守中、一邊話後上馬）。"""
        out = run_style.habitual("K417", "2026-11-18", TABLE)
        self.assertEqual((out["label"], out["code"], out["same"], out["consistency"]), ("後上", "B", 2, "多變"))
        self.assertAlmostEqual(out["habit"], 0.607, places=3)
        self.assertEqual(out["runs"][0]["date"], "2026-10-19")            # 新 → 舊
        self.assertEqual([r["style"] for r in out["runs"]], ["守中", "後上", "後上", "守中", "守中"])
        self.assertEqual(out["hit_rate"], 52.0)

    def test_strictly_before_and_minimum_runs(self):
        self.assertEqual(len(run_style.prior_runs("K417", "2026-10-19", TABLE)), 4)   # 唔包今仗
        self.assertIsNone(run_style.habitual("K417", "2025-11-26", TABLE))           # 得 1 仗
        self.assertIsNone(run_style.habitual("ZZZZ", "2026-11-18", TABLE))
        table = {"horses": {"A": [[f"2026-0{m}-01", 0.1] for m in range(1, 9)]}}
        out = run_style.habitual("A", "2026-09-01", table)
        self.assertEqual((len(out["runs"]), out["label"], out["consistency"]), (6, "放頭", "穩定"))


if __name__ == "__main__":
    unittest.main()
