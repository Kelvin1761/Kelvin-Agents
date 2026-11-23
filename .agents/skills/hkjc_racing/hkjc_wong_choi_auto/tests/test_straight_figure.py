"""直路表現數字入分（EXP-20261123-18 SF，實驗性上線）：只限直路、場內置中、冇往績 = 0、退回開關、標籤入分。"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from hkjc_racing_engine import performance_figure as pf  # noqa: E402
from hkjc_racing_engine import straight_figure as sf  # noqa: E402

ALL = {"A": [(1.5, 123, 1.0, "d", "田草", True), (1.0, 123, 1.2, "d", "田草", False)],
       "B": [(1.0, 123, 1.0, "d", "田草", True), (1.0, 123, 1.2, "d", "田草", False)],
       "C": [(1.0, 123, 1.2, "d", "田草", False), (1.0, 123, 1.2, "d", "田草", False)]}
SEG = {"awt": {}, "straight": {"A": ALL["A"][:1], "B": ALL["B"][:1]}}
RC = {"venue": "沙田", "track": "草地", "distance": "1000m", "race_date": "2026-11-22"}


def horse(code, raw=70.0):
    return {"horse_code": code, "weight": 123, "python_auto": {"ability_score_raw": raw, "ability_score": 60.0, "grade": "B"}}


class StraightFigureTest(unittest.TestCase):
    def test_only_straight(self):
        self.assertTrue(sf.is_straight(RC))
        self.assertFalse(sf.is_straight(dict(RC, distance="1200m")))
        self.assertFalse(sf.is_straight(dict(RC, track="全天候")))
        self.assertFalse(sf.is_straight(dict(RC, venue="跑馬地")))

    def test_centred_gap_and_disable(self):
        hs = {"1": horse("A"), "2": horse("B"), "3": horse("C")}
        with patch.object(pf, "figures_as_of", return_value=ALL), patch.object(pf, "segment_figures", return_value=SEG):
            adj = sf.adjustments(hs, "2026-11-22")
            self.assertAlmostEqual(sum(a for a, _ in adj.values()), 0.0, places=6)
            self.assertGreater(adj["1"][0], adj["2"][0])          # A 直路快過自己平時
            self.assertIsNone(adj["3"][1]["gap"])                 # C 冇直路往績
            self.assertEqual(sf.apply(hs, RC), 3)
            self.assertIn("straight_figure_delta", hs["1"]["python_auto"])
            self.assertEqual(sf.apply({"1": horse("A"), "2": horse("B")}, dict(RC, distance="1200m")), 0)
            sf.ENABLED = False
            try:
                self.assertEqual(sf.apply({"1": horse("A"), "2": horse("B")}, RC), 0)
            finally:
                sf.ENABLED = True


if __name__ == "__main__":
    unittest.main()
