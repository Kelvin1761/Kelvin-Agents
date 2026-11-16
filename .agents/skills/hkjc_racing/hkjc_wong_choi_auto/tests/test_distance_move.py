"""大幅增程組件（EXP-20261117-03 D1）：≥400 米先算、場內置中、冇上仗中性、退回開關、shadow 同步。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from hkjc_racing_engine import distance_move as dm  # noqa: E402


def horse(prev, raw=60.0):
    return {"_data": {"prev_distance": prev} if prev else {},
            "python_auto": {"ability_score_raw": raw, "ability_score": 60.0, "grade": "B",
                            "shadow_profiles": {"x": {"ability_score_raw": raw}}}}


class DistanceMoveTest(unittest.TestCase):
    def test_only_big_increase_and_centred(self):
        hs = {"1": horse(1200), "2": horse(1400), "3": horse(None), "4": horse("2000")}
        adj = dm.adjustments(hs, "1650m")
        self.assertAlmostEqual(sum(adj.values()), 0.0, places=9)
        self.assertLess(adj["1"], adj["2"])                     # 1200→1650 增 450
        self.assertAlmostEqual(adj["2"], adj["3"], places=9)    # 增 250 唔算；冇上仗中性
        self.assertAlmostEqual(adj["4"], adj["3"], places=9)    # 減程唔郁
        self.assertAlmostEqual(adj["1"] - adj["2"], dm.BETA_UP, places=9)

    def test_apply_moves_raw_and_shadow_and_can_be_disabled(self):
        hs = {"1": horse(1200), "2": horse(1650)}
        self.assertEqual(dm.apply(hs, {"distance": "1650"}), 2)
        a = hs["1"]["python_auto"]
        self.assertTrue(a["distance_move"]["up"])
        self.assertAlmostEqual(a["ability_score_raw"] - 60.0, a["distance_move_delta"], places=4)
        self.assertAlmostEqual(a["shadow_profiles"]["x"]["ability_score_raw"], a["ability_score_raw"], places=4)
        dm.ENABLED = False
        try:
            hs = {"1": horse(1200), "2": horse(1650)}
            self.assertEqual(dm.apply(hs, {"distance": "1650"}), 0)
            self.assertEqual(hs["1"]["python_auto"]["ability_score_raw"], 60.0)
        finally:
            dm.ENABLED = True


if __name__ == "__main__":
    unittest.main()
